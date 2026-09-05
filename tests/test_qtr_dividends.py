"""Cash dividends on an unadjusted price series.

The tape stores what the exchange printed, so on an ex-date the quote really
does fall by roughly the payout. Vendor "adjusted" series hide that gap, which
flatters stop-based exits by removing a move a real holder would have seen.
Keeping the drop means the cash has to be paid separately, and the entitlement
rule -- held at the previous close -- is easy to get subtly wrong.
"""
from __future__ import annotations

from datetime import date

import pytest

from backtesting.qtr_results.config import BacktestConfig
from backtesting.qtr_results.engine import BacktestEngine
from backtesting.qtr_results.portfolio import Position


class StubPrices:
    def has(self, symbol):
        return True


class StubFunds:
    def symbols(self):
        return []

    def get(self, symbol):
        return {}


EX_DATE = date(2019, 7, 15)


def make_engine(dividends):
    cfg = BacktestConfig()
    return BacktestEngine(
        cfg, StubPrices(), StubFunds(), dividends=dividends
    )


def hold(engine, symbol="TCS", quantity=100.0, entry=date(2019, 7, 1)):
    engine.pf.positions[symbol] = Position(
        symbol=symbol, quantity=quantity, entry_price=1000.0,
        entry_date=entry, target_price=1200.0, target_pct=0.2,
        trailing_stop_pct=0.1, stop_distance=100.0, stop_price=900.0,
        highest_price=1000.0,
    )


def test_a_held_position_is_paid_on_the_ex_date():
    engine = make_engine({"TCS": {EX_DATE: 12.5}})
    hold(engine)
    before = engine.pf.cash
    engine._credit_dividends(EX_DATE)
    assert engine.pf.cash == pytest.approx(before + 1250.0)
    assert engine.dividend_cash == pytest.approx(1250.0)


def test_nothing_is_paid_on_any_other_day():
    engine = make_engine({"TCS": {EX_DATE: 12.5}})
    hold(engine)
    before = engine.pf.cash
    engine._credit_dividends(date(2019, 7, 14))
    engine._credit_dividends(date(2019, 7, 16))
    assert engine.pf.cash == before
    assert engine.dividend_cash == 0.0


def test_a_name_that_is_not_held_pays_nothing():
    engine = make_engine({"INFY": {EX_DATE: 12.5}})
    hold(engine, symbol="TCS")
    before = engine.pf.cash
    engine._credit_dividends(EX_DATE)
    assert engine.pf.cash == before


def test_two_payouts_sharing_one_ex_date_are_both_paid():
    """An interim and a special can land on the same day; summing matters."""
    engine = make_engine({"TCS": {EX_DATE: 12.5 + 4.0}})
    hold(engine)
    before = engine.pf.cash
    engine._credit_dividends(EX_DATE)
    assert engine.pf.cash == pytest.approx(before + 1650.0)


def test_no_dividend_data_is_a_no_op():
    """The yfinance path must stay untouched -- there the payout is already
    inside the adjusted close, so crediting it again would double-count."""
    engine = make_engine(None)
    hold(engine)
    before = engine.pf.cash
    engine._credit_dividends(EX_DATE)
    assert engine.pf.cash == before
    assert engine.dividend_cash == 0.0
