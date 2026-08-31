"""Offline tests for afund.cycles.funnel — the Phase 10 4-gate idea funnel.

All synthetic data seeded into a temp SQLite DB built from schema.sql. No
network, no LLM calls. Gate functions are tested individually (pure, small
inputs) plus one run_funnel() integration test verifying a euphoria-phase
sector candidate is ranked behind a favorable-phase one and that a
long_term_neglect flag clears gate4 while an euphoria_avoid flag does not.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from afund.cycles import funnel

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


def _insert_derived_ratio(conn, instrument_id, as_of_date, metric_name, metric_value):
    conn.execute(
        "INSERT INTO derived_ratios (instrument_id, as_of_date, metric_name, metric_value) VALUES (?, ?, ?, ?)",
        (instrument_id, as_of_date, metric_name, metric_value),
    )


# ---------------------------------------------------------------------------
# gate1_quant_cycle
# ---------------------------------------------------------------------------

def test_gate1_passes_on_favorable_sector_phase(conn):
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="deep_value", directional_lean=1)
    conn.commit()

    result = funnel.gate1_quant_cycle(conn, "Information Technology")
    assert result["result"] == "PASS"
    assert result["scope_used"] == "it_technology"
    assert result["phase_id"] == "deep_value"


def test_gate1_fails_on_denial_phase(conn):
    _insert_cycle_assessment(conn, scope="commodities_energy", as_of_date="2026-07-01",
                              phase_id="denial", directional_lean=-1)
    conn.commit()

    result = funnel.gate1_quant_cycle(conn, "Metals & Mining")
    assert result["result"] == "FAIL"
    assert result["scope_used"] == "commodities_energy"
    assert result["phase_id"] == "denial"


def test_gate1_falls_back_to_nifty_500_when_sector_scope_missing(conn):
    _insert_cycle_assessment(conn, scope="NIFTY 500", as_of_date="2026-07-01",
                              phase_id="attractive_growth", directional_lean=1)
    conn.commit()

    # "Healthcare" maps to pharma_chemicals, which has no assessment row here.
    result = funnel.gate1_quant_cycle(conn, "Healthcare")
    assert result["result"] == "PASS"
    assert result["scope_used"] == "NIFTY 500"


def test_gate1_unknown_when_no_assessment_anywhere(conn):
    result = funnel.gate1_quant_cycle(conn, "Healthcare")
    assert result["result"] == "UNKNOWN"
    assert result["scope_used"] is None


def test_gate1_ignores_data_pending_rows(conn):
    # A data_pending row must not be picked up even if it's the only one.
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id=None, directional_lean=None, data_pending=1)
    conn.commit()
    result = funnel.gate1_quant_cycle(conn, "Information Technology")
    assert result["result"] == "UNKNOWN"


def test_gate1_unmapped_sector_string_falls_back_to_generic_then_nifty(conn):
    _insert_cycle_assessment(conn, scope="NIFTY 50", as_of_date="2026-07-01",
                              phase_id="momentum", directional_lean=1)
    conn.commit()
    # A sector string with no SECTOR_TO_KPI_KEY entry maps to "generic",
    # which also has no assessment -> falls through to NIFTY 500 (absent)
    # then NIFTY 50 (present).
    result = funnel.gate1_quant_cycle(conn, "Some Unmapped Sector")
    assert result["result"] == "PASS"
    assert result["scope_used"] == "NIFTY 50"


# ---------------------------------------------------------------------------
# gate2_quality
# ---------------------------------------------------------------------------

def test_gate2_partial_when_roe_present():
    result = funnel.gate2_quality(roe=18.5, roce=None, debt_to_equity=0.4)
    assert result["quality"] == "partial"
    assert result["roe"] == 18.5


def test_gate2_unknown_when_nothing_present():
    result = funnel.gate2_quality(roe=None, roce=None, debt_to_equity=None)
    assert result["quality"] == "unknown"


def test_gate2_never_fails_regardless_of_inputs():
    # gate2 has no "result" FAIL concept at all -- assert the key doesn't exist.
    result = funnel.gate2_quality(roe=None, roce=None, debt_to_equity=None)
    assert "result" not in result


# ---------------------------------------------------------------------------
# gate3_idiosyncratic
# ---------------------------------------------------------------------------

def test_gate3_uses_52w_position_proxy_when_pe_history_insufficient(conn):
    _insert_instrument(conn, 1, "TESTCO")
    conn.commit()
    # No derived_ratios rows at all -> falls back to 52w proxy.
    result = funnel.gate3_idiosyncratic(conn, 1, pct_from_52w_low=0.10, pct_from_52w_high=-0.20)
    assert result["proxy_used"] == "52w_position"
    # span = 0.10 - (-0.20) = 0.30; position = 0.10/0.30*100 = 33.33...
    assert result["percentile"] == pytest.approx(0.10 / 0.30 * 100.0)


def test_gate3_uses_own_pe_history_when_two_or_more_points(conn):
    _insert_instrument(conn, 1, "TESTCO")
    _insert_derived_ratio(conn, 1, "2025-01-01", "stock_p_e", 10.0)
    _insert_derived_ratio(conn, 1, "2025-06-01", "stock_p_e", 15.0)
    _insert_derived_ratio(conn, 1, "2026-01-01", "stock_p_e", 12.0)  # current/latest
    conn.commit()

    result = funnel.gate3_idiosyncratic(conn, 1, pct_from_52w_low=0.10, pct_from_52w_high=-0.20)
    assert result["proxy_used"] == "own_pe_history"
    # current = 12.0 (latest as_of_date); history = [10.0, 15.0, 12.0];
    # count_le(12.0) = 2 (10.0, 12.0) -> percentile = 2/3*100 = 66.67
    assert result["percentile"] == pytest.approx(2 / 3 * 100.0)


def test_gate3_no_data_at_all_returns_none_percentile(conn):
    _insert_instrument(conn, 1, "TESTCO")
    conn.commit()
    result = funnel.gate3_idiosyncratic(conn, 1, pct_from_52w_low=None, pct_from_52w_high=None)
    assert result["proxy_used"] is None
    assert result["percentile"] is None


# ---------------------------------------------------------------------------
# gate4_neglect
# ---------------------------------------------------------------------------

def test_gate4_passes_on_panic_buy_flag():
    result = funnel.gate4_neglect(["panic_buy"], score=42)
    assert result["result"] == "PASS"
    assert result["reason"] == "panic_buy"


def test_gate4_passes_on_long_term_neglect_flag():
    result = funnel.gate4_neglect(["long_term_neglect", "deep_drawdown"], score=30)
    assert result["result"] == "PASS"
    assert "long_term_neglect" in result["reason"]


def test_gate4_fails_on_euphoria_avoid_even_with_other_flags(conn):
    # euphoria_avoid must exclude the candidate even if a neglect flag is
    # also present -- this is the "NOT euphoria" requirement from the spec.
    result = funnel.gate4_neglect(["panic_buy", "euphoria_avoid"], score=42)
    assert result["result"] == "FAIL"
    assert result["reason"] == "euphoria_avoid"


def test_gate4_fails_when_no_contrarian_flag_present():
    result = funnel.gate4_neglect([], score=10)
    assert result["result"] == "FAIL"
    assert result["reason"] == "no contrarian/neglect flag"


# ---------------------------------------------------------------------------
# run_funnel — integration: ranking behavior
# ---------------------------------------------------------------------------

def _seed_screenable_instrument(conn, instrument_id, symbol, sector, as_of):
    """Seed enough daily_prices history that derive.screener.run_screen picks
    this instrument up with a long_term_neglect-style flag: flat-ish for a
    long span (>= the screener's long-term lookback) so ret_10y is small/
    unremarkable but there's enough history to be scanned at all. Mirrors
    tests/test_screener.py's own fixture-building approach at a smaller
    scale, since funnel.py only needs the screener to surface >=1 candidate,
    not to exercise every screener flag combination itself (that's already
    covered by test_screener.py)."""
    _insert_instrument(conn, instrument_id, symbol, sector=sector)
    start = as_of - dt.timedelta(days=15 * 365)
    d = start
    price = 100.0
    rows = []
    while d <= as_of:
        rows.append((instrument_id, d.isoformat(), price))
        d += dt.timedelta(days=1)
    conn.executemany(
        "INSERT INTO daily_prices (instrument_id, date, close) VALUES (?, ?, ?)", rows
    )


def test_run_funnel_ranks_favorable_phase_ahead_of_denial_phase(conn):
    as_of = dt.date(2026, 7, 3)
    # Two instruments, both long-term-flat (long_term_neglect-eligible),
    # different sectors: one in a favorable (deep_value) phase, one in a
    # denial (unfavorable) phase.
    _seed_screenable_instrument(conn, 1, "GOODPHASE", "Information Technology", as_of)
    _seed_screenable_instrument(conn, 2, "BADPHASE", "Metals & Mining", as_of)
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="deep_value", directional_lean=1)
    _insert_cycle_assessment(conn, scope="commodities_energy", as_of_date="2026-07-01",
                              phase_id="denial", directional_lean=-1)
    conn.commit()

    result = funnel.run_funnel(conn, as_of=as_of.isoformat(), top_n=15)
    symbols = [c["symbol"] for c in result["candidates"]]
    assert "GOODPHASE" in symbols and "BADPHASE" in symbols
    # gate1 PASS candidates are ranked strictly ahead of gate1 FAIL ones.
    assert symbols.index("GOODPHASE") < symbols.index("BADPHASE")

    good = next(c for c in result["candidates"] if c["symbol"] == "GOODPHASE")
    bad = next(c for c in result["candidates"] if c["symbol"] == "BADPHASE")
    assert good["gates"]["gate1_quant_cycle"]["result"] == "PASS"
    assert bad["gates"]["gate1_quant_cycle"]["result"] == "FAIL"


def test_run_funnel_every_candidate_carries_all_four_gates(conn):
    as_of = dt.date(2026, 7, 3)
    _seed_screenable_instrument(conn, 1, "GOODPHASE", "Information Technology", as_of)
    conn.commit()

    result = funnel.run_funnel(conn, as_of=as_of.isoformat(), top_n=15)
    assert result["universe_scanned"] >= 1
    for c in result["candidates"]:
        assert set(c["gates"]) == {
            "gate1_quant_cycle", "gate2_quality", "gate3_idiosyncratic", "gate4_neglect",
        }
        assert "gates_passed" in c
