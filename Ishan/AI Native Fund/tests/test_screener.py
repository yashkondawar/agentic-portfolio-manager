"""Offline tests for afund.derive.screener.run_screen and its wiring into
afund.orchestrator.context.build_packet(role="idea_gen").

All synthetic data seeded into a temp SQLite DB built from schema.sql. No
network, no LLM calls. Four instruments engineered to each trigger exactly
one primary contrarian flag (plus deep_drawdown, which piggybacks on any deep
price fall) so scoring/ordering/exclusion behavior can be asserted precisely.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from afund.derive import screener
from afund.orchestrator import context

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

AS_OF = dt.date(2026, 7, 3)


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


@pytest.fixture(autouse=True)
def _redirect_packets_dir(tmp_path, monkeypatch):
    packets_dir = tmp_path / "packets"
    monkeypatch.setattr(context, "PACKETS_DIR", packets_dir)
    yield packets_dir


def _insert_instrument(conn, instrument_id: int, symbol: str, instrument_type: str = "STOCK", sector: str | None = None):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector, active) VALUES (?, ?, ?, ?, 1)",
        (instrument_id, symbol, instrument_type, sector),
    )


def _insert_daily_series(conn, instrument_id: int, dates_closes: list[tuple[dt.date, float]]):
    conn.executemany(
        "INSERT INTO daily_prices (instrument_id, date, close) VALUES (?, ?, ?)",
        [(instrument_id, d.isoformat(), c) for d, c in dates_closes],
    )


def _panic_series() -> list[tuple[dt.date, float]]:
    """~3 years of history: flat-ish for the first 2y, then a sharp decline
    in the trailing year so ret_1y <= -45% and the price is also well off its
    52w high (deep_drawdown) — but NOT enough history for a 10y read, so
    long_term_neglect must not trigger and ret_10y must be None."""
    out = []
    start = AS_OF - dt.timedelta(days=3 * 365)
    price = 100.0
    d = start
    while d < AS_OF - dt.timedelta(days=365):
        out.append((d, price))
        d += dt.timedelta(days=1)
    # Trailing 1y: 100 -> 55 (a -45% return), monotonic decline so 52w high
    # is ~100 (near the start of this window) and current price is well below it.
    days_left = (AS_OF - d).days
    start_price = 100.0
    end_price = 55.0
    for i in range(days_left + 1):
        frac = i / days_left
        out.append((d, start_price + (end_price - start_price) * frac))
        d += dt.timedelta(days=1)
    return out


def _neglect_series() -> list[tuple[dt.date, float]]:
    """~11 years of history, essentially flat (small oscillation) throughout,
    including the trailing 1y — so long_term_neglect triggers (|ret_10y| <
    10%) while panic_buy/euphoria_avoid/deep_drawdown do not."""
    out = []
    start = AS_OF - dt.timedelta(days=round(11 * 365.25))
    d = start
    i = 0
    while d <= AS_OF:
        # Oscillate narrowly around 100 so neither a 52w high/low drawdown
        # nor a 1y/5y panic move is ever large.
        price = 100.0 + (i % 20) * 0.1
        out.append((d, price))
        d += dt.timedelta(days=1)
        i += 1
    return out


def _euphoria_series() -> list[tuple[dt.date, float]]:
    """~2 years of history; trailing 1y return >= +120% (euphoria_avoid)."""
    out = []
    start = AS_OF - dt.timedelta(days=2 * 365)
    price = 100.0
    d = start
    while d < AS_OF - dt.timedelta(days=365):
        out.append((d, price))
        d += dt.timedelta(days=1)
    days_left = (AS_OF - d).days
    start_price = 100.0
    end_price = 220.0  # +120% over the trailing year
    for i in range(days_left + 1):
        frac = i / days_left
        out.append((d, start_price + (end_price - start_price) * frac))
        d += dt.timedelta(days=1)
    return out


def _normal_series() -> list[tuple[dt.date, float]]:
    """~3 years of history, steady modest compounding growth — no flag
    should trigger."""
    out = []
    start = AS_OF - dt.timedelta(days=3 * 365)
    price = 100.0
    d = start
    daily_growth = 0.0003  # modest steady growth, ~12%/yr
    while d <= AS_OF:
        out.append((d, price))
        price *= 1 + daily_growth
        d += dt.timedelta(days=1)
    return out


@pytest.fixture()
def seeded_conn(conn):
    _insert_instrument(conn, 1, "PANICCO", sector="Information Technology")
    _insert_instrument(conn, 2, "NEGLECTCO", sector="Financial Services")
    _insert_instrument(conn, 3, "EUPHORCO", sector="Information Technology")
    _insert_instrument(conn, 4, "NORMALCO", sector="Financial Services")

    _insert_daily_series(conn, 1, _panic_series())
    _insert_daily_series(conn, 2, _neglect_series())
    _insert_daily_series(conn, 3, _euphoria_series())
    _insert_daily_series(conn, 4, _normal_series())
    conn.commit()
    return conn


# --- run_screen ---------------------------------------------------------------


def test_panic_instrument_flagged(seeded_conn):
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    by_symbol = {c["symbol"]: c for c in result["candidates"]}
    assert "PANICCO" in by_symbol
    panic = by_symbol["PANICCO"]
    assert "panic_buy" in panic["flags"]
    assert panic["ret_1y"] <= -0.40
    assert panic["ret_10y"] is None  # not enough history for a 10y read


def test_neglect_instrument_flagged(seeded_conn):
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    by_symbol = {c["symbol"]: c for c in result["candidates"]}
    assert "NEGLECTCO" in by_symbol
    neglect = by_symbol["NEGLECTCO"]
    assert "long_term_neglect" in neglect["flags"]
    assert neglect["ret_10y"] is not None
    assert abs(neglect["ret_10y"]) < 0.10
    assert "panic_buy" not in neglect["flags"]
    assert "euphoria_avoid" not in neglect["flags"]


def test_euphoria_instrument_excluded_from_candidates_but_in_euphoria_list(seeded_conn):
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    candidate_symbols = {c["symbol"] for c in result["candidates"]}
    assert "EUPHORCO" not in candidate_symbols

    euphoria_symbols = {e["symbol"] for e in result["euphoria_list"]}
    assert "EUPHORCO" in euphoria_symbols
    euphor = next(e for e in result["euphoria_list"] if e["symbol"] == "EUPHORCO")
    assert euphor["ret_1y"] >= 1.00


def test_normal_instrument_has_no_flags_and_is_excluded(seeded_conn):
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    all_symbols = {c["symbol"] for c in result["candidates"]} | {e["symbol"] for e in result["euphoria_list"]}
    assert "NORMALCO" not in all_symbols


def test_universe_scanned_counts_all_active_instruments(seeded_conn):
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    assert result["universe_scanned"] == 4


def test_euphoria_list_capped_at_five(seeded_conn):
    # Add 6 more euphoria-triggering instruments (ids 100-105).
    for i in range(6):
        instrument_id = 100 + i
        _insert_instrument(seeded_conn, instrument_id, f"EUPH{i}", sector="Information Technology")
        _insert_daily_series(seeded_conn, instrument_id, _euphoria_series())
    seeded_conn.commit()

    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    assert len(result["euphoria_list"]) <= 5


def test_scoring_order_deep_drawdown_and_panic_outrank_single_flag(seeded_conn):
    # PANICCO has panic_buy + deep_drawdown (score 2). Add a pure
    # long_term_neglect-only instrument (score 1, since long_term_neglect
    # alone doesn't imply a 52w drawdown given its flat history) and confirm
    # the higher-scoring candidate sorts first.
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    by_symbol = {c["symbol"]: c for c in result["candidates"]}
    assert by_symbol["PANICCO"]["score"] >= by_symbol["NEGLECTCO"]["score"]

    scores = [c["score"] for c in result["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_top_n_respected(seeded_conn):
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat(), top_n=1)
    assert len(result["candidates"]) == 1


def test_deep_drawdown_flag_present_for_panic_instrument(seeded_conn):
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    by_symbol = {c["symbol"]: c for c in result["candidates"]}
    assert "deep_drawdown" in by_symbol["PANICCO"]["flags"]
    assert by_symbol["PANICCO"]["pct_from_52w_high"] <= -0.30


def test_derived_ratios_tolerant_attachment(seeded_conn):
    # Sparse derived_ratios row using a live-DB-style metric name ('stock_p_e')
    # rather than a canonical 'pe' — the lookup must still find it.
    seeded_conn.execute(
        """
        INSERT INTO derived_ratios (instrument_id, as_of_date, cadence, metric_name, metric_value)
        VALUES (1, ?, 'quarterly', 'stock_p_e', 18.5)
        """,
        (AS_OF.isoformat(),),
    )
    seeded_conn.execute(
        """
        INSERT INTO derived_ratios (instrument_id, as_of_date, cadence, metric_name, metric_value)
        VALUES (1, ?, 'quarterly', 'roce', 12.3)
        """,
        (AS_OF.isoformat(),),
    )
    seeded_conn.commit()

    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    by_symbol = {c["symbol"]: c for c in result["candidates"]}
    assert by_symbol["PANICCO"]["pe"] == pytest.approx(18.5)
    assert by_symbol["PANICCO"]["roce"] == pytest.approx(12.3)
    # No derived_ratios rows for NEGLECTCO -> tolerant None, not a KeyError/crash.
    assert by_symbol["NEGLECTCO"]["pe"] is None


def test_run_screen_empty_universe_degrades_gracefully(conn):
    result = screener.run_screen(conn, as_of=AS_OF.isoformat())
    assert result == {"as_of": AS_OF.isoformat(), "candidates": [], "euphoria_list": [], "universe_scanned": 0}


def test_inactive_instrument_excluded(seeded_conn):
    seeded_conn.execute("UPDATE instruments SET active = 0 WHERE symbol = 'PANICCO'")
    seeded_conn.commit()
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    assert result["universe_scanned"] == 3
    assert "PANICCO" not in {c["symbol"] for c in result["candidates"]}


def test_mutual_fund_instrument_excluded(seeded_conn):
    _insert_instrument(seeded_conn, 5, "SOMEMF", instrument_type="MUTUAL_FUND")
    _insert_daily_series(seeded_conn, 5, _panic_series())
    seeded_conn.commit()
    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    assert result["universe_scanned"] == 4  # MF not counted
    assert "SOMEMF" not in {c["symbol"] for c in result["candidates"]}


def test_json_serializable_output(seeded_conn):
    import json

    result = screener.run_screen(seeded_conn, as_of=AS_OF.isoformat())
    json.dumps(result)  # must not raise


# --- context.py wiring ---------------------------------------------------------


def test_idea_gen_packet_contains_screen(seeded_conn):
    result = context.build_packet(
        seeded_conn, role="idea_gen", trigger="weekly_idea_cycle", batch_id="test_batch"
    )
    packet = result["packet"]
    # Phase 10: idea_gen now receives the 4-gate funnel's compact output
    # (py:afund.cycles.funnel.run_funnel via _compact_funnel), not the raw
    # screener dump — see orchestrator/context.py's role == "idea_gen" branch.
    assert "funnel" in packet
    assert "candidates" in packet["funnel"]
    assert len(packet["funnel"]["candidates"]) > 0
    assert any(c["symbol"] == "PANICCO" for c in packet["funnel"]["candidates"])


def test_idea_gen_packet_respects_budget(seeded_conn):
    result = context.build_packet(
        seeded_conn, role="idea_gen", trigger="weekly_idea_cycle", batch_id="test_batch"
    )
    budget = context._packet_budget_chars("idea_gen")
    assert budget == 16000
    assert result["approx_tokens"] <= budget // 4 + 1


def test_idea_gen_packet_budget_truncates_screen_candidates_under_tiny_budget(seeded_conn, monkeypatch):
    # Force a tiny (but satisfiable — the fixed packet skeleton alone, before
    # any candidates, already costs a couple thousand chars) idea_gen budget
    # so the funnel.candidates truncation path (drop from the bottom) is
    # actually exercised.
    original_load_settings = context.load_settings

    def _tiny_budget_settings():
        settings = original_load_settings()
        settings = dict(settings)
        settings["packet_budgets"] = dict(settings.get("packet_budgets", {}))
        settings["packet_budgets"]["idea_gen"] = 3000
        return settings

    monkeypatch.setattr(context, "load_settings", _tiny_budget_settings)

    result = context.build_packet(
        seeded_conn, role="idea_gen", trigger="weekly_idea_cycle", batch_id="test_batch"
    )
    packet = result["packet"]
    assert result["approx_tokens"] <= 3000 // 4 + 1
    assert any("funnel.candidates" in note for note in packet["truncation_notes"])
    # Truncation drops from the bottom but always leaves at least 1 candidate.
    assert 0 < len(packet["funnel"]["candidates"])


def test_non_idea_gen_role_has_no_screen_key(seeded_conn):
    result = context.build_packet(
        seeded_conn, role="critique", trigger="weekly_idea_cycle", instrument_id=1, batch_id="test_batch"
    )
    assert "funnel" not in result["packet"]
