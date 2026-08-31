"""Offline tests for the niftyindices.com Daily_Snapshot backfill path:
parse_daily_snapshot_csv() (parser) and backfill_index_valuation() (upsert
semantics — idempotent, never overwrites an existing non-NULL pe). No
network — exercises fixtures saved from the live archive/holiday response.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from afund.data.index_valuation import (
    ALL_INDICES,
    BACKFILL_SOURCE_TAG,
    SECTOR_INDICES,
    TARGET_INDICES,
    backfill_index_valuation,
    parse_daily_snapshot_csv,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE_CSV = (FIXTURES / "niftyindices_daily_snapshot_sample.csv").read_text(encoding="utf-8")
HOLIDAY_SHELL = (FIXTURES / "niftyindices_daily_snapshot_holiday_shell.html").read_text(encoding="utf-8")

SAMPLE_DATE = dt.date(2026, 7, 3)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE index_data (
            id          INTEGER PRIMARY KEY,
            index_name  TEXT NOT NULL,
            date        TEXT NOT NULL,
            close       REAL,
            pe          REAL,
            pb          REAL,
            div_yield   REAL,
            source      TEXT,
            UNIQUE(index_name, date)
        )
        """
    )
    yield c
    c.close()


class _FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Serves SAMPLE_CSV for SAMPLE_DATE and the holiday shell for every
    other date, mimicking niftyindices.com's real behavior (200 + generic
    HTML for dates with no snapshot) without any network access."""

    def __init__(self):
        self.calls = 0

    def get(self, url, timeout=20.0, **kwargs):
        self.calls += 1
        if SAMPLE_DATE.strftime("%d%m%Y") in url:
            return _FakeResponse(SAMPLE_CSV)
        return _FakeResponse(HOLIDAY_SHELL)


# ---------------------------------------------------------------------------
# parse_daily_snapshot_csv
# ---------------------------------------------------------------------------


def test_parses_all_target_indices_from_sample():
    rows = parse_daily_snapshot_csv(SAMPLE_CSV, SAMPLE_DATE)
    names = {r["index_name"] for r in rows}
    assert set(TARGET_INDICES).issubset(names)


def test_nifty_50_row_values_match_live_snapshot():
    rows = parse_daily_snapshot_csv(SAMPLE_CSV, SAMPLE_DATE)
    nifty50 = next(r for r in rows if r["index_name"] == "NIFTY 50")
    assert nifty50 == {
        "index_name": "NIFTY 50",
        "date": "2026-07-03",
        "close": 24270.85,
        "pe": 20.92,
        "pb": 3.17,
        "div_yield": 1.25,
    }


def test_holiday_shell_yields_no_rows():
    """niftyindices.com returns HTTP 200 with its generic site shell (not a
    404) for dates with no snapshot; the parser must detect this by content
    shape, not status code."""
    assert parse_daily_snapshot_csv(HOLIDAY_SHELL, dt.date(2026, 1, 26)) == []


def test_empty_text_yields_no_rows():
    assert parse_daily_snapshot_csv("", SAMPLE_DATE) == []


def test_ignores_index_rows_outside_known_set():
    # The fixture includes "Nifty Next 50" and "Nifty Midcap 50" rows which
    # are not in _SNAPSHOT_NAME_MAP (TARGET_INDICES + SECTOR_INDICES) and
    # must not leak into the parsed output.
    rows = parse_daily_snapshot_csv(SAMPLE_CSV, SAMPLE_DATE)
    assert all(r["index_name"] in ALL_INDICES for r in rows)


# ---------------------------------------------------------------------------
# Sector indices (SECTOR_INDICES / ALL_INDICES) — Phase 6 extension
# ---------------------------------------------------------------------------


def test_sector_indices_parse_when_requested():
    """parse_daily_snapshot_csv itself only ever filters to _SNAPSHOT_NAME_MAP
    keys; callers select the subset they want via backfill_index_valuation's
    index_names. Here we verify all 8 sector names are recognized/mapped."""
    rows = parse_daily_snapshot_csv(SAMPLE_CSV, SAMPLE_DATE)
    names = {r["index_name"] for r in rows}
    assert set(SECTOR_INDICES).issubset(names)


def test_nifty_it_row_values_match_fixture():
    rows = parse_daily_snapshot_csv(SAMPLE_CSV, SAMPLE_DATE)
    nifty_it = next(r for r in rows if r["index_name"] == "NIFTY IT")
    assert nifty_it == {
        "index_name": "NIFTY IT",
        "date": "2026-07-03",
        "close": 38050.5,
        "pe": 26.34,
        "pb": 7.45,
        "div_yield": 2.6,
    }


def test_all_indices_covers_target_and_sector_with_no_duplicates():
    assert set(TARGET_INDICES).issubset(set(ALL_INDICES))
    assert set(SECTOR_INDICES).issubset(set(ALL_INDICES))
    assert len(ALL_INDICES) == len(set(ALL_INDICES))
    # NIFTY BANK is intentionally in both lists but must appear once in ALL_INDICES.
    assert ALL_INDICES.count("NIFTY BANK") == 1


def test_backfill_sector_indices_inserts_fresh_rows(conn):
    session = _FakeSession()
    result = backfill_index_valuation(
        conn,
        index_names=SECTOR_INDICES,
        from_date=SAMPLE_DATE,
        to_date=SAMPLE_DATE,
        session=session,
        sleep_between_requests=0,
    )
    for name in SECTOR_INDICES:
        assert result[name] == 1

    row = conn.execute(
        "SELECT * FROM index_data WHERE index_name = 'NIFTY PHARMA' AND date = ?",
        (SAMPLE_DATE.isoformat(),),
    ).fetchone()
    assert row["pe"] == 29.87
    assert row["source"] == BACKFILL_SOURCE_TAG


def test_dash_placeholder_parses_as_none():
    # Craft a row with '-' placeholders (as niftyindices.com uses for
    # metrics that don't apply to a given index, e.g. dividend-point series).
    text = (
        "Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,"
        "Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield\n"
        "Nifty 50,03-07-2026,-,-,-,24270.85,-,-,-,-,-,-,-\n"
    )
    rows = parse_daily_snapshot_csv(text, SAMPLE_DATE)
    assert rows[0]["pe"] is None
    assert rows[0]["pb"] is None
    assert rows[0]["div_yield"] is None
    assert rows[0]["close"] == 24270.85


# ---------------------------------------------------------------------------
# backfill_index_valuation: upsert / no-overwrite semantics
# ---------------------------------------------------------------------------


def test_backfill_inserts_fresh_rows(conn):
    session = _FakeSession()
    result = backfill_index_valuation(
        conn,
        index_names=TARGET_INDICES,
        from_date=SAMPLE_DATE,
        to_date=SAMPLE_DATE,
        session=session,
        sleep_between_requests=0,
    )
    for name in TARGET_INDICES:
        assert result[name] == 1

    row = conn.execute(
        "SELECT * FROM index_data WHERE index_name = 'NIFTY 50' AND date = ?",
        (SAMPLE_DATE.isoformat(),),
    ).fetchone()
    assert row["pe"] == 20.92
    assert row["source"] == BACKFILL_SOURCE_TAG


def test_backfill_never_overwrites_existing_live_pe(conn):
    """A row already populated by the daily nse_all_indices snapshot (real
    pe, source left NULL/'nse_all_indices') must survive a backfill run
    untouched — this is the mandatory no-overwrite quality gate."""
    conn.execute(
        """
        INSERT INTO index_data (index_name, date, close, pe, pb, div_yield, source)
        VALUES ('NIFTY 50', ?, 99999.0, 1.23, 4.56, 7.89, 'nse_all_indices')
        """,
        (SAMPLE_DATE.isoformat(),),
    )
    conn.commit()

    session = _FakeSession()
    result = backfill_index_valuation(
        conn,
        index_names=["NIFTY 50"],
        from_date=SAMPLE_DATE,
        to_date=SAMPLE_DATE,
        session=session,
        sleep_between_requests=0,
    )

    row = conn.execute(
        "SELECT * FROM index_data WHERE index_name = 'NIFTY 50' AND date = ?",
        (SAMPLE_DATE.isoformat(),),
    ).fetchone()
    # Untouched: still the live-snapshot values, not the archive's.
    assert row["close"] == 99999.0
    assert row["pe"] == 1.23
    assert row["pb"] == 4.56
    assert row["div_yield"] == 7.89
    assert row["source"] == "nse_all_indices"
    # Not counted as a fresh fill since pe was already non-NULL.
    assert result["NIFTY 50"] == 0


def test_backfill_fills_null_pe_on_ohlc_only_row(conn):
    """A pre-existing OHLC-only row (e.g. from fetch_index_history, pe/pb/
    div_yield all NULL) should have those NULLs filled by the backfill —
    this is the normal, expected "backfill" case, not an overwrite."""
    conn.execute(
        """
        INSERT INTO index_data (index_name, date, close, pe, pb, div_yield, source)
        VALUES ('NIFTY 50', ?, 24270.85, NULL, NULL, NULL, NULL)
        """,
        (SAMPLE_DATE.isoformat(),),
    )
    conn.commit()

    session = _FakeSession()
    result = backfill_index_valuation(
        conn,
        index_names=["NIFTY 50"],
        from_date=SAMPLE_DATE,
        to_date=SAMPLE_DATE,
        session=session,
        sleep_between_requests=0,
    )

    row = conn.execute(
        "SELECT * FROM index_data WHERE index_name = 'NIFTY 50' AND date = ?",
        (SAMPLE_DATE.isoformat(),),
    ).fetchone()
    assert row["pe"] == 20.92
    assert row["pb"] == 3.17
    assert row["div_yield"] == 1.25
    assert row["source"] == BACKFILL_SOURCE_TAG
    assert result["NIFTY 50"] == 1


def test_backfill_is_idempotent_on_rerun(conn):
    session = _FakeSession()
    backfill_index_valuation(
        conn, index_names=["NIFTY 50"], from_date=SAMPLE_DATE, to_date=SAMPLE_DATE,
        session=session, sleep_between_requests=0,
    )
    count_after_first = conn.execute("SELECT COUNT(*) FROM index_data").fetchone()[0]

    result_second = backfill_index_valuation(
        conn, index_names=["NIFTY 50"], from_date=SAMPLE_DATE, to_date=SAMPLE_DATE,
        session=session, sleep_between_requests=0,
    )
    count_after_second = conn.execute("SELECT COUNT(*) FROM index_data").fetchone()[0]

    assert count_after_first == count_after_second == 1
    # Second run shouldn't count as a fresh fill (pe already present).
    assert result_second["NIFTY 50"] == 0


def test_backfill_skips_holiday_dates_gracefully(conn):
    """Dates with no real snapshot (holiday shell) must contribute zero
    rows and not raise, matching niftyindices.com's HTTP-200-shell quirk."""
    session = _FakeSession()
    holiday_date = dt.date(2026, 1, 26)  # Republic Day
    result = backfill_index_valuation(
        conn, index_names=["NIFTY 50"], from_date=holiday_date, to_date=holiday_date,
        session=session, sleep_between_requests=0,
    )
    assert result["NIFTY 50"] == 0
    assert result["_days_with_data"] == 0
    assert conn.execute("SELECT COUNT(*) FROM index_data").fetchone()[0] == 0


def test_backfill_only_writes_requested_indices(conn):
    session = _FakeSession()
    backfill_index_valuation(
        conn, index_names=["NIFTY 50"], from_date=SAMPLE_DATE, to_date=SAMPLE_DATE,
        session=session, sleep_between_requests=0,
    )
    names_written = {
        r["index_name"] for r in conn.execute("SELECT DISTINCT index_name FROM index_data").fetchall()
    }
    assert names_written == {"NIFTY 50"}
