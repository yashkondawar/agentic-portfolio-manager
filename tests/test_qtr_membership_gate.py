"""The engine's point-in-time membership gate.

The gate is the single line that decides whether the backtest is honest about
which companies were investable on a given day. Without it every signal is
screened against the index as it stands today, which by construction contains
only the companies that survived and stayed large -- so the strategy is
credited with a shortlist nobody could have had at the time.
"""
from __future__ import annotations

from datetime import date

import pytest

from backtesting.qtr_results import analysis as an
from backtesting.qtr_results import engine as engine_mod
from backtesting.qtr_results.config import BacktestConfig
from backtesting.qtr_results.engine import BacktestEngine


class StubPrices:
    """Just enough of PointInTimeData for `_prepare_events`."""

    def __init__(self, symbols):
        self._symbols = set(symbols)

    def has(self, symbol):
        return symbol in self._symbols


class StubFunds:
    def __init__(self, symbols):
        self._symbols = list(symbols)

    def symbols(self):
        return self._symbols

    def get(self, symbol):
        return {"symbol": symbol}


class StubUniverse:
    """Membership that a name can drop out of on a known date."""

    def __init__(self, exits):
        self.exits = exits
        self.calls = []

    def contains(self, symbol, day):
        self.calls.append((symbol, day))
        gone = self.exits.get(symbol)
        return not (gone is not None and day >= gone)


@pytest.fixture()
def calendar():
    days, day = [], date(2019, 1, 1)
    while day <= date(2019, 12, 31):
        if day.weekday() < 5:
            days.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return days


@pytest.fixture()
def patched(monkeypatch):
    """Bypass fundamentals parsing; this test is about the gate only."""
    monkeypatch.setattr(
        an, "parse_quarters", lambda raw: (list(range(6)), {})
    )
    monkeypatch.setattr(
        engine_mod.an, "parse_quarters", lambda raw: (list(range(6)), {})
    )

    def fake_events(sym, raw, quarters, **kwargs):
        return [an.ResultEvent(
            symbol=sym, company=sym, q_idx=0, quarter_label="Jun 2019",
            quarter_end=date(2019, 6, 30), decl_date=date(2019, 7, 15),
            decl_date_real=True,
        )]

    monkeypatch.setattr(an, "enumerate_events", fake_events)
    monkeypatch.setattr(engine_mod.an, "enumerate_events", fake_events)
    monkeypatch.setattr(
        engine_mod.an, "quality_metrics", lambda raw, q: None
    )


def build(universe, symbols=("SURVIVOR", "JETAIRWAYS")):
    cfg = BacktestConfig()
    cfg.use_real_decl_dates = False
    return BacktestEngine(
        cfg, StubPrices(symbols), StubFunds(symbols), universe=universe
    )


def traded(engine):
    return {
        event.symbol
        for events in engine.events_by_day.values()
        for event in events
    }


def test_without_a_gate_every_name_is_tradable(patched, calendar):
    """The old behaviour, kept as the baseline the fix is measured against."""
    engine = build(None)
    engine._prepare_events(calendar)
    assert traded(engine) == {"SURVIVOR", "JETAIRWAYS"}


def test_a_name_that_left_the_index_is_not_traded_after_it_left(
    patched, calendar
):
    universe = StubUniverse({"JETAIRWAYS": date(2019, 1, 1)})
    engine = build(universe)
    engine._prepare_events(calendar)
    assert traded(engine) == {"SURVIVOR"}


def test_a_name_still_in_the_index_on_the_day_is_traded(patched, calendar):
    """A company that fails LATER must still be traded while it was a member.

    This is the half of the fix that is easy to get wrong: over-filtering would
    drop the losers and leave the survivorship bias exactly where it was.
    """
    universe = StubUniverse({"JETAIRWAYS": date(2019, 9, 24)})
    engine = build(universe)
    engine._prepare_events(calendar)
    assert traded(engine) == {"SURVIVOR", "JETAIRWAYS"}


def test_the_gate_is_asked_about_the_declaration_date(patched, calendar):
    universe = StubUniverse({})
    engine = build(universe)
    engine._prepare_events(calendar)
    assert set(universe.calls) == {
        ("SURVIVOR", date(2019, 7, 15)),
        ("JETAIRWAYS", date(2019, 7, 15)),
    }
