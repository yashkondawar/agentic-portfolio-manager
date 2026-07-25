from datetime import date, timedelta

import pandas as pd
import pytest

from backtesting.breakout_52w.calendar import EarningsCalendar
from backtesting.breakout_52w.config import BreakoutConfig
from backtesting.breakout_52w.engine import BreakoutEngine
from backtesting.breakout_52w.strategy import (
    EntrySignal,
    compute_entry_signal,
    evaluate_exit,
    market_regime_allows_entries,
    size_position,
)
from backtesting.swing_trading.portfolio import Portfolio, Position
from backtesting.swing_trading.watchlist import UniverseStock


def _breakout_history() -> pd.DataFrame:
    rows = []
    start = date(2025, 1, 1)
    for index in range(252):
        close = 100.0 + index * 0.2
        rows.append(
            {
                "Open": close - 0.2,
                "High": close + 0.5,
                "Low": close - 0.5,
                "Close": close,
                "Volume": 1_000_000,
            }
        )
    rows.append(
        {
            "Open": 150.5,
            "High": 151.2,
            "Low": 150.2,
            "Close": 151.0,
            "Volume": 2_000_000,
        }
    )
    return pd.DataFrame(
        rows,
        index=pd.to_datetime(
            [start + timedelta(days=index) for index in range(len(rows))]
        ),
    )


def _signal() -> EntrySignal:
    return EntrySignal(
        symbol="TEST",
        signal_date=date(2026, 1, 2),
        signal_close=101.0,
        signal_low=99.0,
        breakout_level=100.0,
        atr=2.0,
        volume_ratio=2.0,
        average_volume_50=1_000_000,
        average_turnover_cr=10.0,
        score=2.5,
    )


def _position(**overrides) -> Position:
    values = {
        "symbol": "TEST",
        "quantity": 100,
        "entry_price": 100.0,
        "entry_date": date(2026, 1, 2),
        "stop_loss": 90.0,
        "target_price": float("inf"),
        "initial_stop": 90.0,
        "atr_at_entry": 2.0,
        "setup": "52W Breakout",
        "breakout_level": 99.0,
        "breakout_signal_date": date(2026, 1, 1),
        "highest_high": 100.0,
    }
    values.update(overrides)
    return Position(**values)


def _bar(open_price: float, high: float, low: float, close: float) -> pd.Series:
    return pd.Series(
        {
            "Open": open_price,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": 1_000_000,
        }
    )


def test_entry_requires_strict_breakout_confirmation_and_liquidity():
    history = _breakout_history()
    cfg = BreakoutConfig()

    signal = compute_entry_signal(history, "TEST", date(2026, 1, 2), cfg)

    assert signal is not None
    assert signal.breakout_level == 150.7
    assert signal.volume_ratio == 2.0

    low_volume = history.copy()
    low_volume.loc[low_volume.index[-1], "Volume"] = 1_400_000
    assert compute_entry_signal(low_volume, "TEST", date(2026, 1, 2), cfg) is None

    marginal = history.copy()
    marginal.loc[marginal.index[-1], ["High", "Close"]] = [150.8, 150.75]
    assert compute_entry_signal(marginal, "TEST", date(2026, 1, 2), cfg) is None

    extended = history.copy()
    extended.loc[extended.index[-1], ["High", "Close"]] = [155.5, 155.0]
    assert compute_entry_signal(extended, "TEST", date(2026, 1, 2), cfg) is None


def test_optimized_defaults_use_confirmed_volume_and_bounded_reward():
    cfg = BreakoutConfig()

    assert cfg.min_volume_ratio == 2.0
    assert cfg.min_breakout_pct == 0.1
    assert cfg.atr_stop_mult == 1.0
    assert cfg.profit_target_atr == 3.0

    with pytest.raises(ValueError, match="profit_target_atr"):
        BreakoutConfig(profit_target_atr=0)


def test_engine_indexes_only_primary_breakout_days(tmp_path):
    history = _breakout_history()

    class FakeData:
        frames = {"TEST": history}

    engine = BreakoutEngine(
        BreakoutConfig(),
        FakeData(),
        [UniverseStock(symbol="TEST")],
        EarningsCalendar(tmp_path),
    )

    assert engine.breakout_candidates[history.index[-1].date()][0].symbol == "TEST"


def test_market_regime_requires_price_above_both_moving_averages():
    history = _breakout_history()
    cfg = BreakoutConfig()
    assert market_regime_allows_entries(history, cfg) is True

    bearish = history.copy()
    bearish.loc[bearish.index[-1], "Close"] = 80.0
    assert market_regime_allows_entries(bearish, cfg) is False


def test_position_size_respects_per_trade_risk_and_remaining_heat():
    cfg = BreakoutConfig(
        risk_per_trade_pct=1.0,
        max_open_risk_pct=5.0,
        atr_stop_mult=1.5,
    )

    shares, stop = size_position(101.0, _signal(), 100_000.0, 100_000.0, 4_500.0, cfg)

    assert stop == 98.0
    assert shares == 166
    assert shares * (101.0 - stop) <= 500.0


def test_false_breakout_exits_after_two_consecutive_closes():
    cfg = BreakoutConfig(false_breakout_closes=2)
    pos = _position()
    history = _breakout_history()

    first = evaluate_exit(pos, _bar(100, 101, 98, 98.5), history, cfg)
    second = evaluate_exit(pos, _bar(98.5, 100, 97, 98.0), history, cfg)

    assert first == []
    assert second[0].reason == "FALSE-BREAKOUT"


def test_chandelier_activates_after_two_atr_and_only_moves_stop_up():
    cfg = BreakoutConfig(
        trail_method="chandelier",
        trail_activation_atr=2.0,
        chandelier_atr_mult=2.0,
    )
    pos = _position()
    history = _breakout_history()

    operations = evaluate_exit(pos, _bar(101, 105, 100, 104), history, cfg)

    assert operations == []
    assert pos.trailing_active is True
    assert pos.stop_loss > 90.0


def test_profit_target_executes_after_stop_guardrail():
    cfg = BreakoutConfig(profit_target_atr=3.0)
    history = _breakout_history()
    pos = _position(target_price=106.0)

    target = evaluate_exit(pos, _bar(104, 107, 101, 106), history, cfg)

    assert target[0].reason == "TARGET"
    assert target[0].price == 106.0

    stopped = _position(stop_loss=99.0, target_price=106.0)
    stop = evaluate_exit(stopped, _bar(100, 107, 98, 106), history, cfg)
    assert stop[0].reason == "STOP"


def test_time_exit_counts_sessions_and_requires_five_percent_progress():
    cfg = BreakoutConfig(time_exit_sessions=10, time_exit_progress_pct=5.0)
    pos = _position(bars_held=9, highest_high=104.0)
    history = _breakout_history()

    operations = evaluate_exit(pos, _bar(102, 104.5, 101, 102), history, cfg)

    assert operations[0].reason == "TIME-EXIT"


def test_earnings_blackout_uses_trading_sessions(tmp_path):
    calendar = EarningsCalendar(tmp_path)
    calendar.events = {"TEST": {date(2026, 1, 9)}}
    sessions = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
    ]

    assert calendar.has_event_within("TEST", date(2026, 1, 5), sessions, 4) is True
    assert calendar.has_event_within("TEST", date(2026, 1, 5), sessions, 3) is False


def test_closed_trade_pnl_includes_both_commission_legs():
    portfolio = Portfolio(cash=10_000.0, commission_pct=0.1)
    position = _position(quantity=10, entry_price=100.0)
    assert portfolio.open_position(position) is True

    trade = portfolio.close_position("TEST", 110.0, date(2026, 1, 12), "TEST-EXIT")

    assert trade is not None
    assert trade.pnl == 97.9
