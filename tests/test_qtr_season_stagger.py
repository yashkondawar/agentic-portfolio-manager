"""Tests for earnings-season capital staggering.

A quarter's declarers arrive in a ~6-week burst. With a flat slot/cash cap the
book fills on whoever reports FIRST, and later -- often stronger -- declarers
are dropped for want of a slot. The schedule in ``qtr_results.season`` rations
slots and capital across the whole declaration window instead.

The maths lives in the LIVE package and is imported by the backtest, so these
tests cover both engines at once. The parity tests at the bottom pin that
shared wiring: if someone re-implements the schedule inside the backtest, live
and backtest can silently diverge and the dossier stops describing live.
"""

from __future__ import annotations

from datetime import date

import pytest

from backtesting.qtr_results.config import BacktestConfig, live_mirror_config
from backtesting.qtr_results.engine import BacktestEngine
from qtr_results import config as live_config
from qtr_results import season


class _Ev:
    """Minimal stand-in for analysis.ResultEvent."""

    def __init__(self, symbol, quarter_end):
        self.symbol = symbol
        self.quarter_end = quarter_end


def _engine(cfg, pending=None):
    eng = object.__new__(BacktestEngine)
    eng.cfg = cfg
    eng.pending = pending or []
    eng.filter_stats = {}
    return eng


# -- quarter-label parsing ---------------------------------------------------

def test_quarter_end_from_label_returns_the_month_end():
    assert season.quarter_end_from_label("Jun 2025") == date(2025, 6, 30)
    assert season.quarter_end_from_label("Mar 2025") == date(2025, 3, 31)
    assert season.quarter_end_from_label("Sep 2025") == date(2025, 9, 30)


def test_quarter_end_from_label_handles_december_year_rollover():
    """December must not roll into month 13."""
    assert season.quarter_end_from_label("Dec 2025") == date(2025, 12, 31)


def test_quarter_end_from_label_returns_none_when_unparseable():
    for bad in ("", "   ", "Jun", "Smarch 2025", "Jun twenty", "Jun 2025 Q1"):
        assert season.quarter_end_from_label(bad) is None


# -- the season ramp ---------------------------------------------------------

def test_floor_of_one_disables_staggering_entirely():
    """1.0 is the documented off switch and must never throttle."""
    q = date(2025, 6, 30)
    assert season.deploy_factor([q], date(2025, 7, 15), 1.0, 15, 45) == 1.0
    assert season.slot_cap(10, 1.0) == 10


def test_factor_ramps_linearly_across_the_declaration_window():
    q = date(2025, 6, 30)
    start, mid, end = date(2025, 7, 15), date(2025, 7, 30), date(2025, 8, 14)
    assert season.deploy_factor([q], start, 0.5, 15, 45) == pytest.approx(0.5)
    assert season.deploy_factor([q], mid, 0.5, 15, 45) == pytest.approx(0.75)
    assert season.deploy_factor([q], end, 0.5, 15, 45) == pytest.approx(1.0)


def test_factor_clamps_outside_the_window():
    """Before the window opens we sit at the floor; long after it, wide open."""
    q = date(2025, 6, 30)
    early = season.deploy_factor([q], date(2025, 7, 2), 0.4, 15, 45)
    late = season.deploy_factor([q], date(2025, 9, 30), 0.4, 15, 45)
    assert early == pytest.approx(0.4)
    assert late == pytest.approx(1.0)


def test_most_advanced_quarter_wins():
    """A straggler filing for an OLD quarter must not be throttled by a new one."""
    fresh, stale = date(2025, 6, 30), date(2025, 3, 31)
    day = date(2025, 7, 15)
    assert season.deploy_factor([fresh], day, 0.5, 15, 45) == pytest.approx(0.5)
    # The March quarter's window closed on 15 May, so it is fully mature.
    both = season.deploy_factor([fresh, stale], day, 0.5, 15, 45)
    assert both == pytest.approx(1.0)


def test_no_quarters_in_play_means_no_throttle():
    assert season.deploy_factor([], date(2025, 7, 15), 0.5, 15, 45) == 1.0
    assert season.deploy_factor([None], date(2025, 7, 15), 0.5, 15, 45) == 1.0


def test_degenerate_lag_window_does_not_divide_by_zero():
    q = date(2025, 6, 30)
    assert season.deploy_factor([q], date(2025, 7, 15), 0.5, 45, 45) == 1.0
    assert season.deploy_factor([q], date(2025, 7, 15), 0.5, 45, 15) == 1.0


def test_floor_is_clamped_into_range():
    q, day = date(2025, 6, 30), date(2025, 7, 15)
    assert season.deploy_factor([q], day, -1.0, 15, 45) == pytest.approx(0.0)
    assert season.deploy_factor([q], day, 5.0, 15, 45) == 1.0


# -- slot rationing ----------------------------------------------------------

def test_slot_cap_rounds_up_and_keeps_at_least_one_slot():
    assert season.slot_cap(10, 0.5) == 5
    assert season.slot_cap(10, 0.51) == 6      # rounds UP, never strands capital
    assert season.slot_cap(10, 0.0) == 1       # always at least one slot
    assert season.slot_cap(10, 1.0) == 10


# -- backtest engine wiring --------------------------------------------------

def test_engine_delegates_to_the_shared_schedule():
    cfg = BacktestConfig(
        season_deploy_floor=0.5, max_positions=10,
        reporting_lag_min=15, reporting_lag_max=45,
    )
    eng = _engine(cfg)
    ev = _Ev("A", date(2025, 6, 30))
    assert eng._stagger_factor([ev], date(2025, 7, 15)) == pytest.approx(0.5)
    assert eng._stagger_factor([ev], date(2025, 8, 14)) == pytest.approx(1.0)
    assert eng._slot_cap(0.5) == 5


def test_engine_honours_the_off_switch():
    cfg = BacktestConfig(season_deploy_floor=1.0, max_positions=10)
    eng = _engine(cfg)
    ev = _Ev("A", date(2025, 6, 30))
    assert eng._stagger_factor([ev], date(2025, 7, 15)) == 1.0
    assert eng._slot_cap(1.0) == 10


# -- live/backtest parity ----------------------------------------------------

def test_live_and_backtest_share_one_schedule():
    """Guards against the dossier silently ceasing to describe live.

    The live mirror must inherit live's floor, and the backtest's lags must
    match live's, or the two engines ration capital on different clocks.
    """
    mirror = live_mirror_config()
    assert mirror.season_deploy_floor == live_config.SEASON_DEPLOY_FLOOR
    assert mirror.reporting_lag_min == live_config.REPORTING_LAG_MIN_DAYS
    assert mirror.reporting_lag_max == live_config.REPORTING_LAG_MAX_DAYS


def test_backtest_defaults_match_the_live_portfolio_caps():
    cfg = BacktestConfig()
    assert cfg.max_positions == live_config.MAX_POSITIONS
    assert cfg.max_position_pct == live_config.MAX_POSITION_PCT
    assert cfg.season_deploy_floor == live_config.SEASON_DEPLOY_FLOOR
