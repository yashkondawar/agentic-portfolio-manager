"""Offline tests for afund.derive.company_fit (Phase 12 universe screening —
company-fit classification). All synthetic data; no network, no LLM calls.

Two layers tested:
  1. classify_fit() — the pure golden-rule function, one test per bucket
     (including the priority ordering between euphoria_avoid and
     contrarian_candidate/quality_watch) plus the fit_score formula.
  2. build_company_fit()/refresh_company_fit() — integration over a seeded
     temp DB, verifying the sector/cycle/screener joins land correctly and
     that refresh_company_fit() upserts idempotently.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from afund.derive import company_fit as cf

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


def _insert_instrument(conn, instrument_id, symbol, sector=None, instrument_type="STOCK"):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector, active) VALUES (?, ?, ?, ?, 1)",
        (instrument_id, symbol, instrument_type, sector),
    )


def _insert_derived_ratio(conn, instrument_id, as_of_date, metric_name, metric_value):
    conn.execute(
        "INSERT INTO derived_ratios (instrument_id, as_of_date, metric_name, metric_value) VALUES (?, ?, ?, ?)",
        (instrument_id, as_of_date, metric_name, metric_value),
    )


def _insert_cycle_assessment(conn, *, scope, as_of_date, phase_id, directional_lean, data_pending=0):
    conn.execute(
        """
        INSERT INTO cycle_assessments
            (cycle_id, scope, as_of_date, framework_version, phase_id, directional_lean,
             data_pending, created_at)
        VALUES ('valuation_cycle', ?, ?, 'test-fw-v1', ?, ?, ?, ?)
        """,
        (scope, as_of_date, phase_id, directional_lean, data_pending, dt.datetime.now().isoformat()),
    )


def _seed_price_history(conn, instrument_id, as_of, *, years=15, flat=True):
    """Long, roughly flat price history so derive.screener.run_screen picks
    the instrument up as a long_term_neglect candidate (mirrors
    tests/test_funnel_wiring.py's own fixture approach)."""
    start = as_of - dt.timedelta(days=years * 365)
    d = start
    price = 100.0
    rows = []
    while d <= as_of:
        rows.append((instrument_id, d.isoformat(), price))
        d += dt.timedelta(days=1)
    conn.executemany(
        "INSERT INTO daily_prices (instrument_id, date, close) VALUES (?, ?, ?)", rows
    )


# ---------------------------------------------------------------------------
# classify_fit — golden rules, one per bucket
# ---------------------------------------------------------------------------

def test_classify_data_gap_when_no_fundamentals_at_all():
    bucket, score = cf.classify_fit(
        pe=None, roce=None, roe=None, flags=[], gate1_result="UNKNOWN", pct_52w=None,
    )
    assert bucket == "data_gap"
    assert score is None


def test_classify_euphoria_avoid_on_explicit_flag():
    bucket, score = cf.classify_fit(
        pe=20.0, roce=18.0, roe=15.0, flags=["euphoria_avoid"], gate1_result="PASS", pct_52w=50.0,
    )
    assert bucket == "euphoria_avoid"
    assert score is not None


def test_classify_euphoria_avoid_on_high_52w_position_even_without_flag():
    bucket, score = cf.classify_fit(
        pe=20.0, roce=18.0, roe=15.0, flags=[], gate1_result="PASS", pct_52w=95.0,
    )
    assert bucket == "euphoria_avoid"


def test_classify_euphoria_avoid_takes_priority_over_contrarian_flags():
    # Both euphoria_avoid AND a neglect flag present -- euphoria dominates.
    bucket, _ = cf.classify_fit(
        pe=20.0, roce=None, roe=None, flags=["euphoria_avoid", "panic_buy"],
        gate1_result="PASS", pct_52w=None,
    )
    assert bucket == "euphoria_avoid"


def test_classify_contrarian_candidate_on_gate1_pass_plus_panic_flag():
    bucket, score = cf.classify_fit(
        pe=15.0, roce=None, roe=None, flags=["panic_buy"], gate1_result="PASS", pct_52w=20.0,
    )
    assert bucket == "contrarian_candidate"
    assert score is not None


def test_classify_contrarian_candidate_requires_gate1_pass():
    # Neglect flag present but gate1 FAILs -- not a contrarian_candidate.
    bucket, _ = cf.classify_fit(
        pe=15.0, roce=None, roe=None, flags=["long_term_neglect"], gate1_result="FAIL", pct_52w=20.0,
    )
    assert bucket != "contrarian_candidate"


def test_classify_weak_avoid_on_low_roce():
    bucket, score = cf.classify_fit(
        pe=15.0, roce=5.0, roe=20.0, flags=[], gate1_result="FAIL", pct_52w=40.0,
    )
    assert bucket == "weak_avoid"
    assert score is not None


def test_classify_weak_avoid_on_low_roe():
    bucket, _ = cf.classify_fit(
        pe=15.0, roce=20.0, roe=3.0, flags=[], gate1_result="FAIL", pct_52w=40.0,
    )
    assert bucket == "weak_avoid"


def test_classify_quality_watch_on_strong_roce_and_roe_no_entry_signal():
    bucket, score = cf.classify_fit(
        pe=25.0, roce=20.0, roe=18.0, flags=[], gate1_result="FAIL", pct_52w=50.0,
    )
    assert bucket == "quality_watch"
    assert score is not None


def test_classify_neutral_when_no_signal_either_way():
    bucket, score = cf.classify_fit(
        pe=18.0, roce=10.0, roe=10.0, flags=[], gate1_result="FAIL", pct_52w=50.0,
    )
    assert bucket == "neutral"
    assert score is not None


# ---------------------------------------------------------------------------
# fit_score formula — pinned values
# ---------------------------------------------------------------------------

def test_fit_score_baseline_is_50_with_no_adjustments():
    # roce/roe present but between weak/strong thresholds -> no quality
    # adjustment; no flags; gate1 not PASS; pct_52w mid-range.
    _, score = cf.classify_fit(
        pe=18.0, roce=10.0, roe=10.0, flags=[], gate1_result="FAIL", pct_52w=50.0,
    )
    assert score == pytest.approx(50.0)


def test_fit_score_gate1_pass_and_contrarian_flag_additive():
    _, score = cf.classify_fit(
        pe=15.0, roce=10.0, roe=10.0, flags=["panic_buy"], gate1_result="PASS", pct_52w=20.0,
    )
    # 50 (baseline) + 20 (gate1 PASS) + 15 (contrarian flag) = 85
    assert score == pytest.approx(85.0)


def test_fit_score_euphoria_and_near_52w_high_both_apply():
    _, score = cf.classify_fit(
        pe=25.0, roce=10.0, roe=10.0, flags=["euphoria_avoid"], gate1_result="FAIL", pct_52w=95.0,
    )
    # 50 - 25 (euphoria flag) - 15 (near 52w high) = 10
    assert score == pytest.approx(10.0)


def test_fit_score_clamped_to_zero_floor():
    _, score = cf.classify_fit(
        pe=25.0, roce=2.0, roe=2.0, flags=["euphoria_avoid"], gate1_result="FAIL", pct_52w=99.0,
    )
    # 50 - 25 - 15 - 15 - 15 = -20 -> clamped to 0
    assert score == pytest.approx(0.0)


def test_fit_score_clamped_to_hundred_ceiling():
    _, score = cf.classify_fit(
        pe=15.0, roce=20.0, roe=20.0, flags=["panic_buy"], gate1_result="PASS", pct_52w=10.0,
    )
    # 50 + 20 + 15 + 10 + 10 = 105 -> clamped to 100
    assert score == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# build_company_fit / refresh_company_fit — integration
# ---------------------------------------------------------------------------

def test_build_company_fit_data_gap_for_instrument_with_no_ratios(conn):
    as_of = dt.date(2026, 7, 3)
    _insert_instrument(conn, 1, "NODATA", sector="Information Technology")
    conn.commit()

    rows = cf.build_company_fit(conn, as_of=as_of.isoformat())
    assert len(rows) == 1
    assert rows[0]["fit_bucket"] == "data_gap"
    assert rows[0]["fit_score"] is None
    assert rows[0]["kpi_sector"] == "it_technology"


def test_build_company_fit_picks_up_sector_phase(conn):
    as_of = dt.date(2026, 7, 3)
    _insert_instrument(conn, 1, "HASPHASE", sector="Information Technology")
    _insert_derived_ratio(conn, 1, as_of.isoformat(), "roce", 20.0)
    _insert_cycle_assessment(
        conn, scope="it_technology", as_of_date="2026-07-01",
        phase_id="deep_value", directional_lean=1,
    )
    conn.commit()

    rows = cf.build_company_fit(conn, as_of=as_of.isoformat())
    row = next(r for r in rows if r["symbol"] == "HASPHASE")
    assert row["sector_phase"] == "deep_value"


def test_build_company_fit_joins_screener_flags_and_gates(conn):
    as_of = dt.date(2026, 7, 3)
    _insert_instrument(conn, 1, "CONTRA", sector="Information Technology")
    _seed_price_history(conn, 1, as_of)
    # A PE on file so this instrument isn't classified data_gap -- the point
    # of this test is the screener-flag/gate join, not the data_gap path
    # (covered separately above).
    _insert_derived_ratio(conn, 1, as_of.isoformat(), "stock_p_e", 12.0)
    _insert_cycle_assessment(
        conn, scope="it_technology", as_of_date="2026-07-01",
        phase_id="deep_value", directional_lean=1,
    )
    conn.commit()

    rows = cf.build_company_fit(conn, as_of=as_of.isoformat())
    row = next(r for r in rows if r["symbol"] == "CONTRA")
    # Flat 15y history -> long_term_neglect flag from the screener; gate1
    # PASSes (deep_value phase) -> contrarian_candidate.
    assert "long_term_neglect" in row["flags"]
    assert row["gates_passed"] >= 1
    assert row["fit_bucket"] == "contrarian_candidate"


def test_refresh_company_fit_upserts_idempotently(conn):
    as_of = dt.date(2026, 7, 3)
    _insert_instrument(conn, 1, "IDEMPOTENT", sector="Information Technology")
    _insert_derived_ratio(conn, 1, as_of.isoformat(), "roce", 20.0)
    _insert_derived_ratio(conn, 1, as_of.isoformat(), "roe", 18.0)
    conn.commit()

    summary1 = cf.refresh_company_fit(conn, as_of=as_of.isoformat())
    assert summary1["rows_written"] == 1

    summary2 = cf.refresh_company_fit(conn, as_of=as_of.isoformat())
    assert summary2["rows_written"] == 1

    count = conn.execute("SELECT COUNT(*) AS n FROM company_fit").fetchone()["n"]
    assert count == 1  # UNIQUE(instrument_id, as_of_date) enforced upsert, not a duplicate insert

    stored = conn.execute("SELECT flags, fit_bucket FROM company_fit WHERE instrument_id = 1").fetchone()
    assert json.loads(stored["flags"]) == []
    assert stored["fit_bucket"] == "quality_watch"


def test_refresh_company_fit_bucket_counts_in_summary(conn):
    as_of = dt.date(2026, 7, 3)
    _insert_instrument(conn, 1, "GAPCO", sector="Information Technology")
    _insert_instrument(conn, 2, "QUALCO", sector="Financial Services")
    _insert_derived_ratio(conn, 2, as_of.isoformat(), "roce", 20.0)
    _insert_derived_ratio(conn, 2, as_of.isoformat(), "roe", 18.0)
    conn.commit()

    summary = cf.refresh_company_fit(conn, as_of=as_of.isoformat())
    assert summary["bucket_counts"]["data_gap"] == 1
    assert summary["bucket_counts"]["quality_watch"] == 1


def test_export_csv_writes_sorted_by_mcap_desc(conn, tmp_path):
    as_of = dt.date(2026, 7, 3)
    _insert_instrument(conn, 1, "SMALL", sector="Information Technology")
    _insert_instrument(conn, 2, "BIG", sector="Information Technology")
    _insert_derived_ratio(conn, 1, as_of.isoformat(), "market_cap", 1000.0)
    _insert_derived_ratio(conn, 1, as_of.isoformat(), "roce", 20.0)
    _insert_derived_ratio(conn, 2, as_of.isoformat(), "market_cap", 50000.0)
    _insert_derived_ratio(conn, 2, as_of.isoformat(), "roce", 20.0)
    conn.commit()

    cf.refresh_company_fit(conn, as_of=as_of.isoformat())
    out_path = tmp_path / "export.csv"
    result_path = cf.export_csv(conn, as_of=as_of.isoformat(), path=out_path)

    assert result_path == out_path
    content = out_path.read_text(encoding="utf-8")
    big_idx = content.index("BIG")
    small_idx = content.index("SMALL")
    assert big_idx < small_idx  # higher mcap (BIG) sorted first
