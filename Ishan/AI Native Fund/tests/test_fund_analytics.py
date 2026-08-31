"""Offline tests for afund.derive.fund_analytics (Phase 10 — ETF/MF fund
analytics: rolling returns/SD/risk-adjusted, capture ratios, ETF premium/
discount, and the derived_series cache refresh).

All synthetic data seeded into a temp SQLite DB built from schema.sql. No
network, no LLM calls. Goldens are hand-computed so the exact formula
(documented in fund_analytics.py's docstrings) is pinned, not just "some
number came back".
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from afund.derive import fund_analytics as fa

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"


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


def _insert_instrument(conn, instrument_id, symbol, instrument_type="ETF", amfi_scheme_code=None):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, amfi_scheme_code, active) VALUES (?, ?, ?, ?, 1)",
        (instrument_id, symbol, instrument_type, amfi_scheme_code),
    )


def _insert_nav(conn, scheme_code, date, nav):
    conn.execute(
        "INSERT INTO mf_navs (scheme_code, date, nav) VALUES (?, ?, ?)",
        (scheme_code, date, nav),
    )


def _insert_price(conn, instrument_id, date, close):
    conn.execute(
        "INSERT INTO daily_prices (instrument_id, date, close) VALUES (?, ?, ?)",
        (instrument_id, date, close),
    )


def _insert_index_close(conn, index_name, date, close):
    conn.execute(
        "INSERT INTO index_data (index_name, date, close) VALUES (?, ?, ?)",
        (index_name, date, close),
    )


# ---------------------------------------------------------------------------
# mf_rolling_returns
# ---------------------------------------------------------------------------

def test_mf_rolling_returns_hand_computed_cagr(conn):
    # NAV exactly doubles over ~5 years -> 5y CAGR = 2**(1/actual_years) - 1,
    # where actual_years uses the same round(5*365.25)-day window the
    # production code computes (not exactly 5.0 due to calendar rounding —
    # see mf_rolling_returns' start_target derivation).
    _insert_nav(conn, "SC1", "2021-07-06", 100.0)
    _insert_nav(conn, "SC1", "2026-07-06", 200.0)
    conn.commit()

    start_date = dt.date(2026, 7, 6) - dt.timedelta(days=round(5 * 365.25))
    actual_years = (dt.date(2026, 7, 6) - start_date).days / 365.25
    expected = 2 ** (1 / actual_years) - 1

    result = fa.mf_rolling_returns(conn, "SC1", years=[5], as_of="2026-07-06")
    assert result["5y"] == pytest.approx(expected, rel=1e-9)


def test_mf_rolling_returns_none_when_window_not_reached(conn):
    # Only 1 year of history -> the 5y window has no valid start point.
    _insert_nav(conn, "SC1", "2025-07-06", 100.0)
    _insert_nav(conn, "SC1", "2026-07-06", 110.0)
    conn.commit()

    result = fa.mf_rolling_returns(conn, "SC1", years=[5], as_of="2026-07-06")
    assert result["5y"] is None


def test_mf_rolling_returns_empty_series_degrades_to_none(conn):
    result = fa.mf_rolling_returns(conn, "NONEXISTENT", years=[3, 5])
    assert result == {"3y": None, "5y": None}


# ---------------------------------------------------------------------------
# mf_rolling_sd
# ---------------------------------------------------------------------------

def test_mf_rolling_sd_below_min_observations_is_none(conn):
    # Fewer than 30 observations in the window -> None (documented floor).
    start = dt.date(2026, 1, 1)
    for i in range(10):
        _insert_nav(conn, "SC1", (start + dt.timedelta(days=i)).isoformat(), 100.0 + i)
    conn.commit()

    result = fa.mf_rolling_sd(conn, "SC1", years=[3, 5], as_of=(start + dt.timedelta(days=9)).isoformat())
    assert result["3y"] is None
    assert result["5y"] is None


def test_mf_rolling_sd_constant_returns_is_zero(conn):
    # Constant daily return -> zero variance -> SD == 0.0 (not None).
    start = dt.date(2024, 1, 1)
    nav = 100.0
    for i in range(40):
        _insert_nav(conn, "SC1", (start + dt.timedelta(days=i)).isoformat(), nav)
        nav *= 1.001  # constant 0.1% daily return
    conn.commit()

    result = fa.mf_rolling_sd(conn, "SC1", years=[3], as_of=(start + dt.timedelta(days=39)).isoformat())
    assert result["3y"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# mf_risk_adjusted
# ---------------------------------------------------------------------------

def test_mf_risk_adjusted_none_when_sd_is_none(conn):
    _insert_nav(conn, "SC1", "2025-07-06", 100.0)
    _insert_nav(conn, "SC1", "2026-07-06", 110.0)
    conn.commit()
    result = fa.mf_risk_adjusted(conn, "SC1", years=[5], as_of="2026-07-06")
    assert result["5y"] is None


def test_mf_risk_adjusted_hand_computed(conn, monkeypatch):
    # Force a known risk-free rate, known CAGR (doubling over 5y), and patch
    # mf_rolling_sd to return a fixed SD so the ratio itself is pinned.
    monkeypatch.setattr(
        fa, "load_settings", lambda: {"portfolio": {"risk_free_rate_annual": 0.05}}
    )
    monkeypatch.setattr(fa, "mf_rolling_sd", lambda *a, **k: {"5y": 0.2})

    _insert_nav(conn, "SC1", "2021-07-06", 100.0)
    _insert_nav(conn, "SC1", "2026-07-06", 200.0)
    conn.commit()

    start_date = dt.date(2026, 7, 6) - dt.timedelta(days=round(5 * 365.25))
    actual_years = (dt.date(2026, 7, 6) - start_date).days / 365.25
    cagr = 2 ** (1 / actual_years) - 1

    result = fa.mf_risk_adjusted(conn, "SC1", years=[5], as_of="2026-07-06")
    expected = (cagr - 0.05) / 0.2
    assert result["5y"] == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# mf_capture_ratios
# ---------------------------------------------------------------------------

def test_mf_capture_ratios_hand_computed(conn):
    # 12 up-days and 12 down-days (>= 10 each side, the documented floor).
    # Scheme return = exactly 2x the benchmark return every day, both up and
    # down -> upside_capture == downside_capture == 2.0 exactly.
    start = dt.date(2026, 1, 1)
    bench = 100.0
    nav = 100.0
    dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(25)]
    _insert_index_close(conn, "NIFTY 50", dates[0], bench)
    _insert_nav(conn, "SC1", dates[0], nav)
    for i in range(1, 25):
        bench_ret = 0.01 if i % 2 == 1 else -0.01
        bench *= 1 + bench_ret
        nav *= 1 + 2 * bench_ret
        _insert_index_close(conn, "NIFTY 50", dates[i], bench)
        _insert_nav(conn, "SC1", dates[i], nav)
    conn.commit()

    result = fa.mf_capture_ratios(conn, "SC1", benchmark="NIFTY 50", as_of=dates[-1])
    assert result["upside_capture"] == pytest.approx(2.0, rel=1e-6)
    assert result["downside_capture"] == pytest.approx(2.0, rel=1e-6)
    assert result["observations"] == 24


def test_mf_capture_ratios_none_below_min_observations(conn):
    # Only 4 up-days, 4 down-days -> both below the 10-observation floor.
    start = dt.date(2026, 1, 1)
    bench = 100.0
    nav = 100.0
    dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(9)]
    _insert_index_close(conn, "NIFTY 50", dates[0], bench)
    _insert_nav(conn, "SC1", dates[0], nav)
    for i in range(1, 9):
        bench_ret = 0.01 if i % 2 == 1 else -0.01
        bench *= 1 + bench_ret
        nav *= 1 + 2 * bench_ret
        _insert_index_close(conn, "NIFTY 50", dates[i], bench)
        _insert_nav(conn, "SC1", dates[i], nav)
    conn.commit()

    result = fa.mf_capture_ratios(conn, "SC1", benchmark="NIFTY 50", as_of=dates[-1])
    assert result["upside_capture"] is None
    assert result["downside_capture"] is None


def test_mf_capture_ratios_no_overlap_degrades_cleanly(conn):
    result = fa.mf_capture_ratios(conn, "NONEXISTENT", benchmark="NIFTY 50")
    assert result == {"upside_capture": None, "downside_capture": None, "observations": 0}


# ---------------------------------------------------------------------------
# etf_premium_discount
# ---------------------------------------------------------------------------

def test_etf_premium_discount_hand_computed(conn):
    _insert_instrument(conn, 1, "NIFTYBEES", amfi_scheme_code="140084")
    _insert_nav(conn, "140084", "2026-07-02", 100.0)
    _insert_price(conn, 1, "2026-07-02", 99.5)  # -0.5% discount
    conn.commit()

    result = fa.etf_premium_discount(conn, "NIFTYBEES")
    assert result["as_of"] == "2026-07-02"
    assert result["latest_pct"] == pytest.approx(-0.005, rel=1e-9)
    assert result["series"] == [("2026-07-02", pytest.approx(-0.005, rel=1e-9))]
    assert result["note"] is None


def test_etf_premium_discount_no_scheme_code_mapped(conn):
    _insert_instrument(conn, 1, "UNMAPPED", amfi_scheme_code=None)
    conn.commit()

    result = fa.etf_premium_discount(conn, "UNMAPPED")
    assert result["latest_pct"] is None
    assert result["note"] == "no amfi_scheme_code mapped"


def test_etf_premium_discount_no_overlapping_dates(conn):
    _insert_instrument(conn, 1, "NIFTYBEES", amfi_scheme_code="140084")
    _insert_nav(conn, "140084", "2026-01-01", 100.0)
    _insert_price(conn, 1, "2026-07-02", 99.5)  # no shared date
    conn.commit()

    result = fa.etf_premium_discount(conn, "NIFTYBEES")
    assert result["latest_pct"] is None
    assert result["note"] == "no overlapping price/NAV dates"


def test_etf_premium_discount_unknown_symbol(conn):
    result = fa.etf_premium_discount(conn, "GHOST")
    assert result["latest_pct"] is None
    assert result["note"] == "no amfi_scheme_code mapped"


# ---------------------------------------------------------------------------
# refresh_fund_analytics — cache write-through
# ---------------------------------------------------------------------------

def test_refresh_fund_analytics_caches_premium_discount(conn, monkeypatch):
    monkeypatch.setattr(
        fa, "load_settings",
        lambda: {"portfolio": {"benchmark": "NIFTY 50"}, "universe": {"mf_watchlist": []}},
    )
    _insert_instrument(conn, 1, "NIFTYBEES", amfi_scheme_code="140084")
    _insert_nav(conn, "140084", "2026-07-02", 100.0)
    _insert_price(conn, 1, "2026-07-02", 99.5)
    conn.commit()

    summary = fa.refresh_fund_analytics(conn, as_of="2026-07-02")
    assert summary["etfs_processed"] == 1
    assert summary["mf_watchlist_processed"] == 0

    row = conn.execute(
        "SELECT value FROM derived_series WHERE instrument_id = 1 AND metric_name = 'premium_discount_pct'"
    ).fetchone()
    assert row is not None
    assert row["value"] == pytest.approx(-0.005, rel=1e-9)


def test_refresh_fund_analytics_is_idempotent_upsert(conn, monkeypatch):
    monkeypatch.setattr(
        fa, "load_settings",
        lambda: {"portfolio": {"benchmark": "NIFTY 50"}, "universe": {"mf_watchlist": []}},
    )
    _insert_instrument(conn, 1, "NIFTYBEES", amfi_scheme_code="140084")
    _insert_nav(conn, "140084", "2026-07-02", 100.0)
    _insert_price(conn, 1, "2026-07-02", 99.5)
    conn.commit()

    fa.refresh_fund_analytics(conn, as_of="2026-07-02")
    fa.refresh_fund_analytics(conn, as_of="2026-07-02")  # run twice

    count = conn.execute(
        "SELECT COUNT(*) c FROM derived_series WHERE instrument_id = 1 AND metric_name = 'premium_discount_pct'"
    ).fetchone()["c"]
    assert count == 1  # upsert, not a duplicate row


def test_refresh_fund_analytics_processes_mf_watchlist(conn, monkeypatch):
    monkeypatch.setattr(
        fa, "load_settings",
        lambda: {"portfolio": {"benchmark": "NIFTY 50"}, "universe": {"mf_watchlist": ["999001"]}},
    )
    _insert_nav(conn, "999001", "2021-07-06", 100.0)
    _insert_nav(conn, "999001", "2026-07-06", 200.0)
    conn.commit()

    summary = fa.refresh_fund_analytics(conn, as_of="2026-07-06")
    assert summary["mf_watchlist_processed"] == 1

    row = conn.execute(
        "SELECT value FROM derived_series WHERE scheme_code = '999001' AND metric_name = 'rolling_return_5y'"
    ).fetchone()
    assert row is not None
    start_date = dt.date(2026, 7, 6) - dt.timedelta(days=round(5 * 365.25))
    actual_years = (dt.date(2026, 7, 6) - start_date).days / 365.25
    assert row["value"] == pytest.approx(2 ** (1 / actual_years) - 1, rel=1e-9)
