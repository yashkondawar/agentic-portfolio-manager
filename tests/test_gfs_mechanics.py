"""
Trade-mechanics tests for the GFS backtest.

Leakage tests establish that the *information* is honest. These establish that
the *accounting* is honest: that a fill can never happen at a price that was not
available, that an unresolvable intrabar ambiguity is always resolved against
us, and that costs are actually charged.

The recurring theme is pessimism. Wherever daily OHLC cannot say what really
happened, the harness must assume the worse outcome - because a backtest that
guesses favourably is just an expensive way to lie to yourself.
"""

import random
from datetime import date, timedelta

import pandas as pd
import pytest

from backtesting.gfs import strategy as st
from backtesting.gfs.config import (
    EXIT_RESISTANCE,
    EXIT_RSI,
    EXIT_SCALE_OUT,
    EXIT_TRAIL,
    GFSConfig,
    SIZING_EQUAL,
    SIZING_RISK,
    STOP_ATR,
    STOP_PCT,
    STOP_SWING,
)
from backtesting.gfs.portfolio import Portfolio, Position


def make_cfg(**kw) -> GFSConfig:
    base = dict(
        start_date=date(2020, 1, 1),
        end_date=date(2021, 1, 1),
        commission_pct=0.0,
        slippage_bps=0.0,
    )
    base.update(kw)
    return GFSConfig(**base)


def make_row(**kw) -> pd.Series:
    row = {
        "Open": 100.0,
        "High": 102.0,
        "Low": 98.0,
        "Close": 101.0,
        "atr": 3.0,
        "rsi_d": 45.0,
        "rsi_w": 65.0,
        "rsi_m": 70.0,
        "swing_low": 95.0,
        "resistance": 110.0,
        "tradable": True,
        "gf_ok": True,
        "s_dip": True,
        "s_recross": False,
    }
    row.update(kw)
    return pd.Series(row)


def make_pos(**kw) -> Position:
    args = dict(
        symbol="TEST",
        sector="IT",
        quantity=100,
        entry_price=100.0,
        entry_date=date(2020, 1, 1),
        stop_loss=95.0,
        initial_stop=95.0,
        target_price=110.0,
        atr_at_entry=3.0,
    )
    args.update(kw)
    pos = Position(**args)
    pos.original_quantity = pos.quantity
    pos.highest_close = pos.entry_price
    pos.highest_high = pos.entry_price
    pos.lowest_low = pos.entry_price
    return pos


# ── Stops ────────────────────────────────────────────────────────────────────


def test_stop_modes():
    row = make_row()
    assert st.stop_for(100.0, row, make_cfg(stop_mode=STOP_PCT, fixed_stop_pct=4.0)) == 96.0
    assert st.stop_for(100.0, row, make_cfg(stop_mode=STOP_ATR, atr_stop_mult=2.0)) == 94.0
    got = st.stop_for(
        100.0, row, make_cfg(stop_mode=STOP_SWING, swing_low_buffer_pct=1.0)
    )
    assert got == pytest.approx(95.0 * 0.99)


def test_stop_falls_back_when_its_input_is_missing():
    """A data gap must never produce a position with no stop."""
    cfg = make_cfg(stop_mode=STOP_ATR, fixed_stop_pct=5.0)
    assert st.stop_for(100.0, make_row(atr=float("nan")), cfg) == 95.0
    assert st.stop_for(100.0, make_row(atr=0.0), cfg) == 95.0


def test_swing_stop_above_entry_is_rejected():
    """A swing low above the entry would invert the trade's risk."""
    cfg = make_cfg(stop_mode=STOP_SWING, fixed_stop_pct=4.0)
    assert st.stop_for(90.0, make_row(swing_low=95.0), cfg) == pytest.approx(86.4)


# ── Exit resolution ──────────────────────────────────────────────────────────


def test_stop_wins_when_stop_and_target_are_both_touched():
    """Daily OHLC cannot order intrabar events, so the stop must be assumed
    first. Anything else invents a favourable outcome out of nothing."""
    cfg = make_cfg(exit_mode=EXIT_RESISTANCE)
    pos = make_pos(stop_loss=95.0)
    row = make_row(Open=100.0, High=115.0, Low=94.0, Close=112.0, resistance=110.0)
    ops = st.evaluate_exits(pos, row, date(2020, 2, 1), cfg)
    assert len(ops) == 1
    assert ops[0].reason == "stop"
    assert ops[0].price == 95.0


def test_gap_through_the_stop_fills_at_the_open_not_the_stop():
    """Overnight gaps are where real money is lost; filling at the stop level
    would silently cap every loss at exactly 1R."""
    pos = make_pos(stop_loss=95.0)
    row = make_row(Open=88.0, High=90.0, Low=86.0, Close=87.0)
    ops = st.evaluate_exits(pos, row, date(2020, 2, 1), make_cfg())
    assert ops[0].price == 88.0
    assert ops[0].price < pos.stop_loss


def test_stop_exactly_touched_still_triggers():
    pos = make_pos(stop_loss=95.0)
    row = make_row(Open=99.0, High=100.0, Low=95.0, Close=97.0)
    ops = st.evaluate_exits(pos, row, date(2020, 2, 1), make_cfg())
    assert ops and ops[0].reason == "stop"


def test_rsi_exit_is_deferred_to_the_next_open():
    """'RSI closed at 66' is only knowable after the close that produced it."""
    cfg = make_cfg(exit_mode=EXIT_RSI, exit_rsi=65.0)
    ops = st.evaluate_exits(make_pos(), make_row(rsi_d=66.0), date(2020, 2, 1), cfg)
    assert len(ops) == 1
    assert ops[0].reason == "rsi_target"
    assert ops[0].fill == st.FILL_NEXT_OPEN


def test_rsi_exit_can_be_made_optimistic_on_purpose():
    """The flag exists so the cost of the honest assumption can be measured."""
    cfg = make_cfg(exit_mode=EXIT_RSI, exit_rsi=65.0, indicator_exit_delay=False)
    ops = st.evaluate_exits(make_pos(), make_row(rsi_d=66.0), date(2020, 2, 1), cfg)
    assert ops[0].fill == st.FILL_NOW


def test_no_exit_when_nothing_triggers():
    cfg = make_cfg(exit_mode=EXIT_RSI, exit_rsi=65.0, max_holding_days=0)
    assert st.evaluate_exits(make_pos(), make_row(rsi_d=50.0), date(2020, 2, 1), cfg) == []


def test_time_stop_fires_on_the_calendar_boundary():
    cfg = make_cfg(exit_mode=EXIT_RSI, exit_rsi=95.0, max_holding_days=30)
    pos = make_pos(entry_date=date(2020, 1, 1))
    assert st.evaluate_exits(pos, make_row(), date(2020, 1, 30), cfg) == []
    ops = st.evaluate_exits(pos, make_row(), date(2020, 1, 31), cfg)
    assert ops and ops[0].reason == "time_stop"
    assert ops[0].fill == st.FILL_NEXT_OPEN


def test_resistance_exit_uses_the_level_not_the_high():
    """Filling at the day's high would assume a perfect sale at the top tick."""
    cfg = make_cfg(exit_mode=EXIT_RESISTANCE)
    row = make_row(Open=105.0, High=118.0, Low=104.0, Close=117.0, resistance=110.0)
    ops = st.evaluate_exits(make_pos(), row, date(2020, 2, 1), cfg)
    assert ops[0].reason == "resistance"
    assert ops[0].price == 110.0


def test_resistance_exit_fills_at_the_open_when_the_gap_is_above_the_level():
    cfg = make_cfg(exit_mode=EXIT_RESISTANCE)
    row = make_row(Open=114.0, High=118.0, Low=113.0, Close=117.0, resistance=110.0)
    ops = st.evaluate_exits(make_pos(), row, date(2020, 2, 1), cfg)
    assert ops[0].price == 114.0


def test_scale_out_books_a_fraction_once_only():
    cfg = make_cfg(exit_mode=EXIT_SCALE_OUT, exit_rsi=65.0, scale_out_frac=0.5)
    pos = make_pos()
    ops = st.evaluate_exits(pos, make_row(rsi_d=70.0), date(2020, 2, 1), cfg)
    assert ops[0].fraction == 0.5 and ops[0].reason == "rsi_partial"
    pos.partial_booked = True
    assert st.evaluate_exits(pos, make_row(rsi_d=70.0), date(2020, 2, 2), cfg) == []


# ── Stop ratcheting ──────────────────────────────────────────────────────────


def test_trailing_stop_only_ever_moves_up():
    cfg = make_cfg(exit_mode=EXIT_TRAIL, trail_atr_mult=3.0)
    pos = make_pos(stop_loss=95.0)
    pos.mark(120.0, 99.0, 118.0)
    st.update_stop(pos, make_row(atr=3.0), cfg)
    assert pos.stop_loss == pytest.approx(109.0)

    pos.mark(112.0, 105.0, 106.0)  # a pullback
    st.update_stop(pos, make_row(atr=3.0), cfg)
    assert pos.stop_loss == pytest.approx(109.0), "stop must never loosen"


def test_breakeven_stop_activates_at_the_configured_r():
    cfg = make_cfg(exit_mode=EXIT_RSI, move_stop_to_breakeven_at_r=1.0)
    pos = make_pos(entry_price=100.0, stop_loss=95.0, initial_stop=95.0)
    pos.mark(103.0, 99.0, 103.0)
    st.update_stop(pos, make_row(), cfg)
    assert pos.stop_loss == 95.0
    pos.mark(106.0, 102.0, 106.0)  # +1R
    st.update_stop(pos, make_row(), cfg)
    assert pos.stop_loss == 100.0


def test_rsi_mode_does_not_trail():
    """Pure GFS keeps its original stop - the ablation is what compares them."""
    cfg = make_cfg(exit_mode=EXIT_RSI)
    pos = make_pos(stop_loss=95.0)
    pos.mark(150.0, 99.0, 148.0)
    st.update_stop(pos, make_row(atr=3.0), cfg)
    assert pos.stop_loss == 95.0


# ── Sizing ───────────────────────────────────────────────────────────────────


def test_equal_sizing_splits_capital_across_slots():
    cfg = make_cfg(sizing_mode=SIZING_EQUAL, max_positions=8, max_position_pct=100.0)
    assert st.size_position(100.0, 95.0, 800_000.0, cfg) == 1000


def test_risk_sizing_buys_fewer_shares_when_the_stop_is_wider():
    cfg = make_cfg(sizing_mode=SIZING_RISK, risk_per_trade_pct=2.0, max_position_pct=100.0)
    tight = st.size_position(100.0, 98.0, 1_000_000.0, cfg)
    wide = st.size_position(100.0, 90.0, 1_000_000.0, cfg)
    assert tight == 10_000 and wide == 2_000
    assert tight > wide


def test_concentration_cap_binds_in_both_modes():
    for mode in (SIZING_EQUAL, SIZING_RISK):
        cfg = make_cfg(
            sizing_mode=mode, max_positions=2, max_position_pct=10.0, risk_per_trade_pct=5.0
        )
        qty = st.size_position(100.0, 99.0, 1_000_000.0, cfg)
        assert qty * 100.0 <= 1_000_000.0 * 0.10 + 1e-6, mode


def test_zero_or_inverted_risk_is_refused():
    cfg = make_cfg(sizing_mode=SIZING_RISK)
    assert st.size_position(100.0, 100.0, 1_000_000.0, cfg) == 0
    assert st.size_position(100.0, 105.0, 1_000_000.0, cfg) == 0


def test_sector_cap():
    cfg = make_cfg(max_per_sector=2)
    assert st.can_open_sector("IT", {}, cfg)
    assert st.can_open_sector("IT", {"IT": 1}, cfg)
    assert not st.can_open_sector("IT", {"IT": 2}, cfg)


# ── Ranking ──────────────────────────────────────────────────────────────────


def test_random_ranking_is_seed_reproducible():
    cfg = make_cfg(rank_by="random")
    a = [st.score_candidate(make_row(), 1, 10, cfg, random.Random(7)) for _ in range(3)]
    b = [st.score_candidate(make_row(), 1, 10, cfg, random.Random(7)) for _ in range(3)]
    assert a == b


def test_composite_score_prefers_deeper_dips_in_stronger_sectors():
    cfg = make_cfg(rank_by="composite", s_rsi_entry=40.0)
    rng = random.Random(1)
    strong = st.score_candidate(make_row(rsi_d=30.0, rsi_w=80.0, rsi_m=80.0), 1, 10, cfg, rng)
    weak = st.score_candidate(make_row(rsi_d=39.0, rsi_w=61.0, rsi_m=61.0), 9, 10, cfg, rng)
    assert strong > weak


# ── Portfolio accounting ─────────────────────────────────────────────────────


def test_costs_are_actually_charged():
    pf = Portfolio(cash=100_000.0, commission_pct=0.1, slippage_bps=20.0)
    assert pf.buy_fill_price(100.0) == pytest.approx(100.20)
    assert pf.sell_fill_price(100.0) == pytest.approx(99.80)

    pf.open_position(make_pos(quantity=100, entry_price=100.0))
    assert pf.cash == pytest.approx(100_000.0 - 10_000.0 - 10.0)
    trade = pf.close_position("TEST", 100.0, date(2020, 2, 1), "flat")
    # A round trip at an unchanged price must lose exactly the commissions.
    assert trade.pnl == pytest.approx(-10.0)
    assert pf.cash == pytest.approx(100_000.0 - 20.0)


def test_cannot_spend_cash_it_does_not_have():
    pf = Portfolio(cash=10_000.0, commission_pct=0.05)
    assert pf.affordable_quantity(100.0, 1000) < 100
    assert not pf.open_position(make_pos(quantity=1000, entry_price=100.0))
    assert pf.cash == 10_000.0


def test_partial_close_leaves_a_position_open_and_flags_it():
    pf = Portfolio(cash=100_000.0, commission_pct=0.0, slippage_bps=0.0)
    pf.open_position(make_pos(quantity=100, entry_price=100.0))
    trade = pf.close_position("TEST", 110.0, date(2020, 2, 1), "rsi_partial", fraction=0.5)
    assert trade.partial and trade.quantity == 50
    assert pf.positions["TEST"].quantity == 50
    assert pf.positions["TEST"].partial_booked

    pf.close_position("TEST", 120.0, date(2020, 3, 1), "trailing_stop")
    assert "TEST" not in pf.positions
    assert len(pf.closed) == 2


def test_partial_that_rounds_to_nothing_is_refused():
    pf = Portfolio(cash=100_000.0)
    pf.open_position(make_pos(quantity=1, entry_price=100.0))
    assert pf.close_position("TEST", 110.0, date(2020, 2, 1), "rsi_partial", 0.5) is None
    assert pf.positions["TEST"].quantity == 1


def test_r_multiple_and_excursions():
    pf = Portfolio(cash=100_000.0, commission_pct=0.0, slippage_bps=0.0)
    pos = make_pos(quantity=100, entry_price=100.0, stop_loss=95.0, initial_stop=95.0)
    pf.open_position(pos)
    pos.mark(112.0, 92.0, 110.0)
    trade = pf.close_position("TEST", 110.0, date(2020, 2, 1), "rsi_target")
    assert trade.r_multiple == pytest.approx(2.0)  # +10 on 5 of risk
    assert trade.mae_pct == pytest.approx(-8.0)
    assert trade.mfe_pct == pytest.approx(12.0)
    assert trade.mae_r == pytest.approx(-1.6)


def test_holding_days_and_pnl_pct():
    pf = Portfolio(cash=100_000.0, commission_pct=0.0, slippage_bps=0.0)
    pf.open_position(make_pos(quantity=10, entry_price=200.0, entry_date=date(2020, 1, 1)))
    trade = pf.close_position("TEST", 220.0, date(2020, 1, 31), "rsi_target")
    assert trade.holding_days == 30
    assert trade.pnl_pct == pytest.approx(10.0)
    assert trade.pnl == pytest.approx(200.0)
