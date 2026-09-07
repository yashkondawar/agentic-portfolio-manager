"""Tests for earnings-season staggering and weakest-holding replacement.

A quarter's declarers arrive in a ~6-week burst. With a flat slot/cash cap the
book fills on whoever reports FIRST, and later — often stronger — declarers are
dropped for want of a slot. These tests pin the two mechanisms that fix that:

  * ``_stagger_factor`` / ``_slot_cap`` ration slots and capital across the
    declaration window using only the quarter-end date and the configured
    reporting lags, so the schedule is knowable on the day.
  * ``_apply_upgrades`` displaces the weakest holding when a materially
    stronger name declares into a full book.
"""

from __future__ import annotations

from datetime import date

import pytest

from backtesting.qtr_results.config import BacktestConfig
from backtesting.qtr_results.engine import BacktestEngine
from backtesting.qtr_results.portfolio import Portfolio, Position


class _Ev:
    """Minimal stand-in for analysis.ResultEvent."""

    def __init__(self, symbol, quarter_end):
        self.symbol = symbol
        self.quarter_end = quarter_end


class _Prices:
    """Fake tape: {symbol: {day: (open, close)}}."""

    def __init__(self, bars):
        self.bars = bars

    def bar_on(self, symbol, day):
        row = self.bars.get(symbol, {}).get(day)
        if row is None:
            return None
        op, close = row
        return {"Open": op, "High": close, "Low": op, "Close": close}


def _engine(cfg, pf=None, prices=None, pending=None, scores=None):
    eng = object.__new__(BacktestEngine)
    eng.cfg = cfg
    eng.pf = pf
    eng.prices = prices
    eng.pending = pending or []
    eng.pending_scores = scores or {}
    eng.filter_stats = {}
    return eng


def _pos(symbol, strength, entry_price=100.0):
    return Position(
        symbol=symbol,
        quantity=10,
        entry_price=entry_price,
        entry_date=date(2025, 7, 20),
        target_price=entry_price * 1.2,
        target_pct=20.0,
        trailing_stop_pct=20.0,
        stop_distance=20.0,
        stop_price=entry_price * 0.8,
        highest_price=entry_price,
        strength_score=strength,
    )


# ── season schedule ──────────────────────────────────────────────────────────

def test_stagger_off_never_throttles():
    cfg = BacktestConfig(season_stagger=False, max_positions=10)
    eng = _engine(cfg)
    ev = _Ev("A", date(2025, 6, 30))
    # Even on day one of the window the legacy path gets the whole book.
    assert eng._stagger_factor([ev], date(2025, 7, 15)) == 1.0
    assert eng._slot_cap(1.0) == 10


def test_factor_ramps_from_floor_to_one_across_the_window():
    cfg = BacktestConfig(
        season_stagger=True, season_deploy_floor=0.5,
        reporting_lag_min=15, reporting_lag_max=45,
    )
    eng = _engine(cfg)
    ev = _Ev("A", date(2025, 6, 30))
    start, end = date(2025, 7, 15), date(2025, 8, 14)
    assert eng._stagger_factor([ev], start) == pytest.approx(0.5)
    assert eng._stagger_factor([ev], date(2025, 7, 30)) == pytest.approx(0.75)
    assert eng._stagger_factor([ev], end) == pytest.approx(1.0)


def test_factor_is_clamped_outside_the_window():
    cfg = BacktestConfig(season_stagger=True, season_deploy_floor=0.4)
    eng = _engine(cfg)
    ev = _Ev("A", date(2025, 6, 30))
    # An early filer cannot unlock more than the floor...
    assert eng._stagger_factor([ev], date(2025, 7, 2)) == pytest.approx(0.4)
    # ...and a late one is never penalised beyond full allowance.
    assert eng._stagger_factor([ev], date(2025, 9, 30)) == pytest.approx(1.0)


def test_most_advanced_event_sets_the_allowance():
    """A straggler from an older quarter must not be throttled by a fresh one."""
    cfg = BacktestConfig(season_stagger=True, season_deploy_floor=0.5)
    eng = _engine(cfg)
    fresh = _Ev("FRESH", date(2025, 6, 30))     # window opens 2025-07-15
    stale = _Ev("STALE", date(2025, 3, 31))     # window closed 2025-05-15
    assert eng._stagger_factor([fresh], date(2025, 7, 15)) == pytest.approx(0.5)
    assert eng._stagger_factor(
        [fresh, stale], date(2025, 7, 15)
    ) == pytest.approx(1.0)


def test_slot_cap_rounds_up_and_keeps_at_least_one_slot():
    cfg = BacktestConfig(season_stagger=True, max_positions=10)
    eng = _engine(cfg)
    assert eng._slot_cap(0.5) == 5
    assert eng._slot_cap(0.51) == 6      # rounds UP, never strands capital
    assert eng._slot_cap(0.0) == 1       # always at least one slot
    assert eng._slot_cap(1.0) == 10


# ── upgrade / replacement ────────────────────────────────────────────────────

DAY = date(2025, 8, 12)


def _upgrade_fixture(cfg, holdings, cand_score=90.0):
    pf = Portfolio(cash=0.0, commission_pct=0.0)
    for sym, strength, entry, today_open in holdings:
        pf.positions[sym] = _pos(sym, strength, entry)
    bars = {sym: {DAY: (today_open, today_open)}
            for sym, _, _, today_open in holdings}
    bars["NEW"] = {DAY: (50.0, 50.0)}
    ev = _Ev("NEW", date(2025, 6, 30))
    return _engine(cfg, pf=pf, prices=_Prices(bars), pending=[ev],
                   scores={"NEW": cand_score})


def test_upgrade_disabled_by_default():
    cfg = BacktestConfig()
    assert cfg.upgrade_margin == 0.0
    eng = _upgrade_fixture(cfg, [("WEAK", 10.0, 100.0, 90.0)])
    eng._apply_upgrades(DAY, slot_cap=1)
    assert "WEAK" in eng.pf.positions
    assert eng.filter_stats == {}


def test_strong_declarer_displaces_the_weakest_loser():
    cfg = BacktestConfig(upgrade_margin=20.0, max_upgrades_per_day=1)
    eng = _upgrade_fixture(cfg, [
        ("WEAK", 10.0, 100.0, 90.0),    # losing, weakest -> displaced
        ("MID", 40.0, 100.0, 90.0),     # losing but stronger
    ])
    eng._apply_upgrades(DAY, slot_cap=2)
    assert "WEAK" not in eng.pf.positions
    assert "MID" in eng.pf.positions
    assert eng.filter_stats["upgrade_swap"] == 1
    assert eng.pf.closed[0].exit_reason == "upgrade_swap"


def test_margin_is_hysteresis_not_a_tiebreak():
    cfg = BacktestConfig(upgrade_margin=20.0)
    # Candidate 90 vs incumbent 75 -> excess 15 < 20, so no churn.
    eng = _upgrade_fixture(cfg, [("HELD", 75.0, 100.0, 90.0)])
    eng._apply_upgrades(DAY, slot_cap=1)
    assert "HELD" in eng.pf.positions
    assert "upgrade_swap" not in eng.filter_stats


def test_winners_are_not_displaced_by_default():
    cfg = BacktestConfig(upgrade_margin=20.0)
    # Only holding is up on the day -> protected, nothing to swap.
    eng = _upgrade_fixture(cfg, [("WINNER", 10.0, 100.0, 130.0)])
    eng._apply_upgrades(DAY, slot_cap=1)
    assert "WINNER" in eng.pf.positions

    cfg_any = BacktestConfig(upgrade_margin=20.0, upgrade_only_losers=False)
    eng2 = _upgrade_fixture(cfg_any, [("WINNER", 10.0, 100.0, 130.0)])
    eng2._apply_upgrades(DAY, slot_cap=1)
    assert "WINNER" not in eng2.pf.positions


def test_no_swap_when_a_slot_is_already_free():
    cfg = BacktestConfig(upgrade_margin=20.0)
    eng = _upgrade_fixture(cfg, [("WEAK", 10.0, 100.0, 90.0)])
    eng._apply_upgrades(DAY, slot_cap=5)   # room for 5, holding 1
    assert "WEAK" in eng.pf.positions


def test_never_sells_when_the_candidate_cannot_be_filled_today():
    """Selling an incumbent to buy nothing would be a pure cost."""
    cfg = BacktestConfig(upgrade_margin=20.0)
    eng = _upgrade_fixture(cfg, [("WEAK", 10.0, 100.0, 90.0)])
    eng.prices.bars["NEW"] = {}            # candidate has no session today
    eng._apply_upgrades(DAY, slot_cap=1)
    assert "WEAK" in eng.pf.positions


def test_swaps_are_capped_per_day():
    cfg = BacktestConfig(upgrade_margin=5.0, max_upgrades_per_day=1)
    eng = _upgrade_fixture(cfg, [
        ("W1", 10.0, 100.0, 90.0),
        ("W2", 11.0, 100.0, 90.0),
    ])
    eng.pending.append(_Ev("NEW2", date(2025, 6, 30)))
    eng.pending_scores["NEW2"] = 88.0
    eng.prices.bars["NEW2"] = {DAY: (50.0, 50.0)}
    eng._apply_upgrades(DAY, slot_cap=2)
    assert eng.filter_stats["upgrade_swap"] == 1
    assert len(eng.pf.positions) == 1


def test_exit_uses_todays_open_not_todays_close():
    """The swap transacts at the open; marking to the close is look-ahead."""
    cfg = BacktestConfig(upgrade_margin=20.0)
    pf = Portfolio(cash=0.0, commission_pct=0.0)
    pf.positions["WEAK"] = _pos("WEAK", 10.0, 100.0)
    bars = {
        "WEAK": {DAY: (90.0, 120.0)},   # open 90 (a loss), close 120 (a gain)
        "NEW": {DAY: (50.0, 50.0)},
    }
    eng = _engine(cfg, pf=pf, prices=_Prices(bars),
                  pending=[_Ev("NEW", date(2025, 6, 30))],
                  scores={"NEW": 90.0})
    eng._apply_upgrades(DAY, slot_cap=1)
    # Judged AND sold on the open: a loser at 90, exited at 90.
    assert "WEAK" not in pf.positions
    assert pf.closed[0].exit_price == pytest.approx(90.0)
