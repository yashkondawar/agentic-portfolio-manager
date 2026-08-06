"""Tests for the live↔backtest sync: ATR stops, risk sizing, cash book, exits.

These pin the capital layer that was ported from the winning backtest experiment
onto the live ``qtr_results`` package -- risk-based position sizing against a
persisted cash balance, an ATR-based (volatility) trailing stop, and the
ride-the-wave exit (no fixed profit cap). Everything must also degrade safely on
missing data (the GESHIP lesson), so the data-gap-safe paths are pinned too.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from qtr_results import config, ledger, portfolio, targets, technicals


# ── portfolio.size_position (mirror of the backtest rule) ───────────────────
def test_size_position_uses_risk_budget_over_stop_distance():
    # equity 5,00,000 @ 4% risk = 20,000 budget; stop 50 -> 400 shares,
    # not capped by 20% concentration (400*100 = 40k < 1,00,000) or cash.
    shares = portfolio.size_position(
        entry_price=100.0, stop_distance=50.0, equity=500000.0, cash=500000.0,
        risk_per_trade_pct=4.0, max_position_pct=20.0,
    )
    assert shares == 400


def test_size_position_capped_by_concentration():
    # Tight stop would want a huge line; 20% of 5L / 100 = 1000 shares ceiling.
    shares = portfolio.size_position(
        entry_price=100.0, stop_distance=1.0, equity=500000.0, cash=500000.0,
        risk_per_trade_pct=4.0, max_position_pct=20.0,
    )
    assert shares == 1000


def test_size_position_capped_by_available_cash():
    # Only 5,000 cash left -> at 100/share you can afford ~49 (0.999 buffer).
    shares = portfolio.size_position(
        entry_price=100.0, stop_distance=1.0, equity=500000.0, cash=5000.0,
        risk_per_trade_pct=4.0, max_position_pct=20.0,
    )
    assert shares == 49


def test_size_position_zero_on_bad_inputs():
    assert portfolio.size_position(0.0, 10.0, 5e5, 5e5,
                                   risk_per_trade_pct=4.0, max_position_pct=20.0) == 0
    assert portfolio.size_position(100.0, 0.0, 5e5, 5e5,
                                   risk_per_trade_pct=4.0, max_position_pct=20.0) == 0


# ── portfolio cash accounting ───────────────────────────────────────────────
def test_buy_then_close_round_trips_cash_and_pnl():
    pf = portfolio.Portfolio(starting_capital=100000.0, cash=100000.0)
    invested = portfolio.apply_buy(pf, entry_price=100.0, quantity=100)
    assert invested == 10000.0
    # cash debited notional + one-side commission (0.20% of 10k = 20).
    assert pf.cash == pytest.approx(100000.0 - 10000.0 - 20.0)

    portfolio.apply_close(pf, exit_price=120.0, quantity=100)
    portfolio.record_realized(pf, entry_price=100.0, exit_price=120.0, quantity=100)
    # proceeds 12,000 net of 0.20% (24) credited back.
    assert pf.cash == pytest.approx(100000.0 - 10000.0 - 20.0 + 12000.0 - 24.0)
    # realised = gross 2,000 minus both-side commission (20 + 24).
    assert pf.realized_pnl == pytest.approx(2000.0 - 20.0 - 24.0)


def test_marked_equity_counts_open_book_at_last_price():
    pf = portfolio.Portfolio(starting_capital=100000.0, cash=40000.0)
    opens = [{"quantity": 100, "last_price": 150.0, "entry_price": 100.0}]
    assert portfolio.marked_equity(pf, opens) == 40000.0 + 15000.0


# ── ATR stop resolution + target plan ───────────────────────────────────────
def test_resolve_stop_prefers_atr_distance():
    dist, pct, basis = targets._resolve_stop(entry_price=200.0, atr=5.0)
    assert basis == "atr"
    assert dist == pytest.approx(config.ATR_STOP_MULTIPLIER * 5.0)


def test_resolve_stop_falls_back_to_pct_without_atr():
    dist, pct, basis = targets._resolve_stop(entry_price=200.0, atr=None)
    assert basis == "fallback_pct"
    assert dist == pytest.approx(200.0 * config.FALLBACK_STOP_PCT / 100.0)


def test_build_target_plan_carries_atr_stop_distance():
    analysis = SimpleNamespace(
        current_pe=None, ttm_eps=None, strength_score=80.0,
    )
    plan = targets.build_target_plan(analysis, entry_price=100.0, atr=2.0)
    assert plan is not None
    assert plan.stop_basis == "atr"
    assert plan.stop_distance_abs == pytest.approx(config.ATR_STOP_MULTIPLIER * 2.0)


# ── ledger stores sizing + abs stop ─────────────────────────────────────────
def _dummy_analysis(symbol="GESHIP"):
    return SimpleNamespace(
        symbol=symbol, company_name="Great Eastern", latest_quarter="Q1FY26",
        current_pe=None, ttm_eps=None, strength_score=80.0,
        rationale="strong", conviction=None,
    )


def test_add_pick_stores_quantity_and_abs_stop():
    analysis = _dummy_analysis()
    plan = targets.build_target_plan(analysis, entry_price=100.0, atr=2.0)
    picks: list = []
    pick = ledger.add_pick(
        picks, analysis, plan, result_date="2026-08-03", quantity=50, invested=5000.0,
    )
    assert pick is not None
    assert pick["quantity"] == 50
    assert pick["invested"] == 5000.0
    assert pick["stop_distance_abs"] == pytest.approx(config.ATR_STOP_MULTIPLIER * 2.0)
    # stop_price = entry - abs distance (12), not a legacy percent of entry.
    assert pick["stop_price"] == pytest.approx(100.0 - config.ATR_STOP_MULTIPLIER * 2.0)


# ── ride-the-wave + ATR ratchet exits ───────────────────────────────────────
def test_ride_the_wave_skips_target_but_time_stops(monkeypatch):
    monkeypatch.setattr(config, "DISABLE_PROFIT_TARGET", True)
    # A pick far above its "target" price should NOT close on the target.
    pick = {
        "symbol": "X", "entry_price": 100.0, "entry_date": "2026-01-01",
        "target_price": 110.0, "trailing_stop_pct": 8.0,
        "stop_distance_abs": 12.0, "highest_price": 100.0, "stop_price": 88.0,
        "max_holding_days": 90, "status": "open",
    }
    picks = [pick]
    closed = ledger.update_open_positions(picks, lambda s: 130.0,
                                          as_of=__import__("datetime").date(2026, 1, 15))
    assert closed == []  # target ignored under ride-the-wave
    # Stop ratcheted off the new high (130) by the absolute distance (12).
    assert pick["stop_price"] == pytest.approx(118.0)


def test_atr_ratchet_stops_out_on_pullback(monkeypatch):
    monkeypatch.setattr(config, "DISABLE_PROFIT_TARGET", True)
    pick = {
        "symbol": "X", "entry_price": 100.0, "entry_date": "2026-01-01",
        "target_price": 110.0, "trailing_stop_pct": 8.0,
        "stop_distance_abs": 12.0, "highest_price": 130.0, "stop_price": 118.0,
        "max_holding_days": 90, "status": "open",
    }
    picks = [pick]
    closed = ledger.update_open_positions(picks, lambda s: 117.0,
                                          as_of=__import__("datetime").date(2026, 1, 10))
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "trailing_stop"


# ── data-gap-safe technicals ────────────────────────────────────────────────
def test_empty_technicals_have_no_opinion():
    t = technicals.Technicals()
    assert t.in_uptrend is None       # missing data => never rejects
    assert t.atr is None
    assert t.median_turnover_20d is None
