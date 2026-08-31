"""Offline tests for afund.data.macro_fred — FRED CSV parsing, the derived
CPI_YOY computation, and upsert idempotency/revision-refresh against a temp
SQLite DB built from schema.sql. No network."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from afund.data.macro_fred import MacroFredPipeline, compute_cpi_yoy, parse_fred_csv

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

# Mirrors the live gateway shape exactly: "observation_date,{SERIES_ID}"
# header, one row per observation, missing values as a literal ".".
SAMPLE_CSV = """observation_date,INDIRLTLT01STM
2025-12-01,6.83
2026-01-01,6.98
2026-02-01,.
2026-03-01,7.15
2026-04-01,
2026-05-01,7.02
not-a-date-but-value-bad,abc
"""


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


def test_parse_fred_csv_skips_missing_markers_and_malformed():
    rows = parse_fred_csv(SAMPLE_CSV, "INDIRLTLT01STM")
    # "." and empty values skipped, unparseable value skipped — never
    # coerced to 0 or fabricated.
    assert rows == [
        ("2025-12-01", 6.83),
        ("2026-01-01", 6.98),
        ("2026-03-01", 7.15),
        ("2026-05-01", 7.02),
    ]


def test_parse_fred_csv_empty_and_headerless():
    assert parse_fred_csv("", "X") == []
    assert parse_fred_csv("just_one_column\n2026-01-01\n", "X") == []


def test_compute_cpi_yoy_matches_hand_computation():
    # 24 monthly index points, +1 per month starting at 100.
    dates = [f"{2024 + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}-01" for m in range(1, 25)]
    index_rows = [(d, 100.0 + i) for i, d in enumerate(dates)]

    yoy = compute_cpi_yoy(index_rows)
    assert len(yoy) == 12  # first 12 months have no 12m-earlier base
    # First YoY point: (112 - 100) / 100 * 100 = 12.0% at month 13.
    assert yoy[0][0] == dates[12]
    assert yoy[0][1] == pytest.approx(12.0)
    # Last: (123 - 111) / 111 * 100.
    assert yoy[-1][0] == dates[23]
    assert yoy[-1][1] == pytest.approx((123.0 - 111.0) / 111.0 * 100.0)


def test_compute_cpi_yoy_skips_zero_base():
    rows = [(f"2024-{m:02d}-01", 0.0) for m in range(1, 13)] + [("2025-01-01", 5.0)]
    assert compute_cpi_yoy(rows) == []


def test_upsert_is_idempotent_and_refreshes_revisions(conn):
    pipeline = MacroFredPipeline(conn=conn)
    parsed = {"GSEC_10Y": [("2026-04-01", 7.10), ("2026-05-01", 7.02)]}

    assert pipeline.upsert(parsed) == 2
    # Re-run with one REVISED value: the row must be refreshed (this is why
    # macro_fred uses ON CONFLICT DO UPDATE, not INSERT OR IGNORE).
    parsed_revised = {"GSEC_10Y": [("2026-04-01", 7.12), ("2026-05-01", 7.02)]}
    pipeline.upsert(parsed_revised)

    stored = conn.execute(
        "SELECT date, value, unit, freq, source FROM macro_series "
        "WHERE series_code = 'GSEC_10Y' ORDER BY date"
    ).fetchall()
    assert len(stored) == 2  # no duplicates
    assert stored[0]["value"] == pytest.approx(7.12)  # revision applied
    assert stored[0]["unit"] == "%"
    assert stored[0]["freq"] == "M"
    assert stored[0]["source"] == "FRED"
