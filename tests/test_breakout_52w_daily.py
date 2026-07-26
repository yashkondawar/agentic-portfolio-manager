from datetime import date

import pandas as pd
import pytest

from backtesting.breakout_52w.config import BreakoutConfig
from backtesting.breakout_52w.daily import (
    _fill_pending,
    _future_business_sessions,
    empty_state,
    normalize_state,
    run_daily,
)
from backtesting.breakout_52w.strategy import EntrySignal
from backtesting.swing_trading.portfolio import Portfolio


class FakeData:
    def __init__(self, bars):
        self.bars = bars

    def bar_on(self, symbol, day):
        return self.bars.get((symbol, day))


def _signal() -> EntrySignal:
    return EntrySignal(
        symbol="TEST",
        signal_date=date(2026, 7, 24),
        signal_close=101.0,
        signal_low=99.0,
        breakout_level=100.0,
        atr=2.0,
        volume_ratio=2.0,
        average_volume_50=1_000_000.0,
        average_turnover_cr=10.0,
        score=2.5,
    )


def test_empty_and_normalized_state_support_strategy_owned_portfolio():
    state = empty_state(500_000)
    assert state["cash"] == 500_000
    assert state["positions"] == []
    assert state["pending_entries"] == []

    state["last_run_date"] = "2026-07-24"
    normalized = normalize_state(state, 1)
    assert normalized == state


def test_state_upgrade_discards_pending_signals_from_superseded_rules():
    state = empty_state(500_000)
    state["version"] = 2
    state["pending_entries"] = [{"symbol": "OLD-RULE-SIGNAL"}]

    normalized = normalize_state(state, 1)

    assert normalized["version"] == 3
    assert normalized["pending_entries"] == []


def test_state_rejects_positions_without_strategy_risk_metadata():
    with pytest.raises(ValueError, match="missing required fields"):
        normalize_state(
            {
                "cash": 10_000,
                "positions": [
                    {
                        "symbol": "TCS",
                        "quantity": 1,
                        "entry_price": 3_000,
                        "entry_date": "2026-07-24",
                    }
                ],
            },
            10_000,
        )


def test_pending_signal_fills_next_session_and_creates_managed_position():
    day = date(2026, 7, 27)
    data = FakeData(
        {
            (
                "TEST",
                day,
            ): pd.Series(
                {
                    "Open": 101.0,
                    "High": 103.0,
                    "Low": 100.0,
                    "Close": 102.0,
                    "Volume": 1_000_000,
                }
            )
        }
    )
    portfolio = Portfolio(cash=100_000, commission_pct=0)
    pending = [_signal()]
    filled = []
    rejected = []
    exits = []

    opened = _fill_pending(
        day,
        pending,
        portfolio,
        data,
        BreakoutConfig(),
        filled,
        rejected,
        exits,
    )

    assert opened == {"TEST"}
    assert pending == []
    assert filled[0]["action"] == "ENTERED"
    assert portfolio.positions["TEST"].stop_loss == 99.0
    assert portfolio.positions["TEST"].target_price == 106.0
    assert rejected == []
    assert exits == []


def test_entry_day_hard_stop_is_recorded_immediately():
    day = date(2026, 7, 27)
    data = FakeData(
        {
            (
                "TEST",
                day,
            ): pd.Series(
                {
                    "Open": 101.0,
                    "High": 102.0,
                    "Low": 97.0,
                    "Close": 99.0,
                    "Volume": 1_000_000,
                }
            )
        }
    )
    portfolio = Portfolio(cash=100_000, commission_pct=0)
    pending = [_signal()]
    exits = []

    opened = _fill_pending(
        day,
        pending,
        portfolio,
        data,
        BreakoutConfig(),
        [],
        [],
        exits,
    )

    assert opened == set()
    assert "TEST" not in portfolio.positions
    assert exits[0]["reason"] == "ENTRY-DAY-STOP"
    assert exits[0]["pnl_pct"] == -1.98


def test_entry_day_target_is_recorded_when_stop_is_not_touched():
    day = date(2026, 7, 27)
    data = FakeData(
        {
            (
                "TEST",
                day,
            ): pd.Series(
                {
                    "Open": 101.0,
                    "High": 110.0,
                    "Low": 100.0,
                    "Close": 109.0,
                    "Volume": 1_000_000,
                }
            )
        }
    )
    portfolio = Portfolio(cash=100_000, commission_pct=0)
    pending = [_signal()]
    exits = []

    opened = _fill_pending(
        day,
        pending,
        portfolio,
        data,
        BreakoutConfig(enable_partial_profit=False),
        [],
        [],
        exits,
    )

    assert opened == set()
    assert "TEST" not in portfolio.positions
    assert exits[0]["reason"] == "ENTRY-DAY-TARGET"
    assert exits[0]["exit_price"] == 109.0
    assert exits[0]["pnl_pct"] == 7.92


def test_entry_day_partial_books_half_and_keeps_trailing_remainder():
    day = date(2026, 7, 27)
    data = FakeData(
        {
            (
                "TEST",
                day,
            ): pd.Series(
                {
                    "Open": 101.0,
                    "High": 110.0,
                    "Low": 100.0,
                    "Close": 109.0,
                    "Volume": 1_000_000,
                }
            )
        }
    )
    portfolio = Portfolio(cash=100_000, commission_pct=0)
    pending = [_signal()]
    exits = []

    opened = _fill_pending(
        day,
        pending,
        portfolio,
        data,
        BreakoutConfig(enable_partial_profit=True),
        [],
        [],
        exits,
    )

    assert opened == {"TEST"}
    assert "TEST" in portfolio.positions
    position = portfolio.positions["TEST"]
    assert position.partial_booked is True
    assert position.stop_loss >= position.entry_price
    assert exits[0]["reason"] == "ENTRY-DAY-PARTIAL"


def test_earnings_window_counts_weekdays_from_next_session():
    assert _future_business_sessions(date(2026, 7, 24), 5) == [
        date(2026, 7, 27),
        date(2026, 7, 28),
        date(2026, 7, 29),
        date(2026, 7, 30),
        date(2026, 7, 31),
    ]


def test_daily_run_scans_custom_universe_and_persists_pending_state(monkeypatch):
    session_day = date(2026, 7, 24)
    index = pd.bdate_range(end=session_day, periods=253)
    rows = []
    for offset in range(252):
        close = 100.0 + offset * 0.2
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
            "High": 151.8,
            "Low": 150.2,
            "Close": 151.6,
            "Volume": 2_000_000,
        }
    )
    stock = pd.DataFrame(rows, index=index)
    price_columns = ["Open", "High", "Low", "Close"]
    benchmark = stock.copy()
    benchmark[price_columns] = 80.0
    benchmark.loc[index[-64], price_columns] = 140.0
    benchmark.loc[index[-63:-1], price_columns] = 100.0
    benchmark.loc[index[-1], price_columns] = 121.0

    class FakePointInTimeData:
        def __init__(self, _cache_dir):
            self.benchmark = benchmark
            self.frames = {"TEST": stock}

        def load_or_download(self, **_kwargs):
            return None

        def benchmark_as_of(self, day):
            return self.benchmark.loc[: pd.Timestamp(day)]

        def bar_on(self, symbol, day):
            timestamp = pd.Timestamp(day)
            frame = self.frames.get(symbol)
            return (
                frame.loc[timestamp]
                if frame is not None and timestamp in frame.index
                else None
            )

        def as_of(self, symbol, day, lookback_rows=None):
            frame = self.frames[symbol].loc[: pd.Timestamp(day)]
            return frame.tail(lookback_rows) if lookback_rows else frame

        def trading_days(self, start, end):
            return [
                timestamp.date()
                for timestamp in self.benchmark.index
                if start <= timestamp.date() <= end
            ]

    monkeypatch.setattr(
        "backtesting.breakout_52w.daily.PointInTimeData",
        FakePointInTimeData,
    )
    cfg = BreakoutConfig(
        starting_capital=100_000,
        enforce_earnings_blackout=False,
    )

    result = run_daily(
        cfg,
        symbols=["TEST"],
        as_of=session_day,
        persist_state=False,
    )

    assert result["universe"] == "custom"
    assert result["new_entries"][0]["symbol"] == "TEST"
    assert result["portfolio_state"]["pending_entries"][0]["symbol"] == "TEST"
    assert result["portfolio_state"]["last_run_date"] == session_day.isoformat()


def test_daily_run_refuses_to_move_portfolio_state_backward(monkeypatch):
    session_day = date(2026, 7, 24)
    index = pd.bdate_range(end=session_day, periods=253)
    benchmark = pd.DataFrame(
        {
            "Open": range(253),
            "High": range(253),
            "Low": range(253),
            "Close": range(1, 254),
            "Volume": [1_000_000] * 253,
        },
        index=index,
    )

    class FakePointInTimeData:
        def __init__(self, _cache_dir):
            self.benchmark = benchmark
            self.frames = {}

        def load_or_download(self, **_kwargs):
            return None

    monkeypatch.setattr(
        "backtesting.breakout_52w.daily.PointInTimeData",
        FakePointInTimeData,
    )
    state = empty_state(100_000)
    state["last_run_date"] = "2026-07-27"

    with pytest.raises(ValueError, match="cannot run it backward"):
        run_daily(
            BreakoutConfig(enforce_earnings_blackout=False),
            portfolio_state=state,
            symbols=["TEST"],
            as_of=session_day,
            persist_state=False,
        )
