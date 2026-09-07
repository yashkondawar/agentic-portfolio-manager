"""Tests for the days-to-profitability metric.

"How long does a trade take to turn profitable?" is easy to compute wrongly.
The trap is treating a single green close as the answer: under that reading
almost every trade "turns profitable" on day one and the metric says nothing.
Requiring a RUN of consecutive profitable closes is what makes it a statement
about the position holding up rather than about one tick.

These tests pin the run semantics, the two break-even thresholds, and -- most
importantly -- the honest handling of trades that never get there, which must
be reported rather than quietly dropped from the average.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from backtesting.qtr_results.dossier import (
    _dtp_stats,
    _dtp_summary_sheet,
    days_to_profitability,
)


class _Trade:
    def __init__(self, symbol, entry_date, exit_date, entry_price,
                 pnl_pct=0.0, exit_reason="target", holding_days=0):
        self.symbol = symbol
        self.entry_date = entry_date
        self.exit_date = exit_date
        self.entry_price = entry_price
        self.pnl_pct = pnl_pct
        self.exit_reason = exit_reason
        self.holding_days = holding_days


def _frame(start: date, closes):
    """Daily close series starting at ``start``, one row per calendar day."""
    idx = pd.to_datetime([start + timedelta(days=i) for i in range(len(closes))])
    return pd.DataFrame({"Close": closes}, index=idx)


ENTRY = date(2025, 1, 1)


def _run(closes, *, entry_price=100.0, streak=5, cost=0.0, hold=None):
    exit_date = ENTRY + timedelta(days=len(closes) - 1)
    trade = _Trade("AAA", ENTRY, exit_date, entry_price,
                   holding_days=hold if hold is not None else len(closes))
    return days_to_profitability(
        [trade], {"AAA": _frame(ENTRY, closes)},
        streak=streak, round_trip_cost_pct=cost,
    )[0]


# -- the run requirement -----------------------------------------------------

def test_a_single_green_close_is_not_enough():
    """One profitable close then a relapse must NOT count."""
    row = _run([101, 99, 99, 99, 99, 99])
    assert row["sessions_to_profit_gross"] is None
    assert row["outcome"] == "never_sustained"


def test_first_session_of_the_qualifying_run_is_reported():
    """Not the last session of the run, and not the first green close."""
    #        s1  s2   s3   s4   s5   s6   s7   s8
    row = _run([99, 101, 99, 101, 102, 103, 104, 105])
    # The run starts at session 4 (index 3) and lasts five sessions.
    assert row["sessions_to_profit_gross"] == 4
    assert row["days_to_profit_gross"] == 3   # calendar days from entry


def test_profit_on_the_entry_day_counts_as_session_one():
    row = _run([101, 102, 103, 104, 105])
    assert row["sessions_to_profit_gross"] == 1
    assert row["days_to_profit_gross"] == 0


def test_close_must_beat_entry_strictly():
    """Flat at the entry price is not profit."""
    row = _run([100, 100, 100, 100, 100])
    assert row["sessions_to_profit_gross"] is None


def test_streak_length_is_honoured():
    closes = [101, 102, 99, 99, 99]
    assert _run(closes, streak=2)["sessions_to_profit_gross"] == 1
    assert _run(closes, streak=3)["sessions_to_profit_gross"] is None


# -- censoring, reported rather than hidden ----------------------------------

def test_a_trade_shorter_than_the_streak_is_flagged_not_dropped():
    """Exiting on day 3 cannot produce a 5-session run; say so explicitly."""
    row = _run([101, 102, 103])
    assert row["sessions_to_profit_gross"] is None
    assert row["outcome"] == "too_short"
    assert row["sessions_held"] == 3


def test_the_clock_never_runs_past_the_exit():
    """Prices after the exit must not be used to rescue a losing trade."""
    closes = [99, 99, 99, 101, 102, 103, 104, 105]
    trade = _Trade("AAA", ENTRY, ENTRY + timedelta(days=2), 100.0)
    row = days_to_profitability([trade], {"AAA": _frame(ENTRY, closes)})[0]
    assert row["sessions_held"] == 3          # only the held window
    assert row["sessions_to_profit_gross"] is None


def test_missing_price_history_is_reported_distinctly():
    trade = _Trade("ZZZ", ENTRY, ENTRY + timedelta(days=10), 100.0)
    row = days_to_profitability([trade], {})[0]
    assert row["outcome"] == "no_price_data"
    assert row["sessions_held"] is None


def test_empty_frame_is_treated_as_missing_data():
    trade = _Trade("AAA", ENTRY, ENTRY + timedelta(days=10), 100.0)
    row = days_to_profitability([trade], {"AAA": pd.DataFrame()})[0]
    assert row["outcome"] == "no_price_data"


# -- gross vs net of costs ---------------------------------------------------

def test_costs_push_the_break_even_higher_and_delay_profitability():
    """A trade up 0.3% is green gross but under water after a 0.4% round trip."""
    closes = [100.3] * 5
    row = _run(closes, cost=0.4)
    assert row["sessions_to_profit_gross"] == 1
    assert row["sessions_to_profit_net"] is None


def test_net_matches_gross_when_costs_are_zero():
    row = _run([101, 102, 103, 104, 105], cost=0.0)
    assert row["sessions_to_profit_net"] == row["sessions_to_profit_gross"] == 1


# -- aggregation -------------------------------------------------------------

def test_stats_report_the_achiever_rate_alongside_the_average():
    """The average alone is a survivorship claim; the rate must travel with it."""
    rows = [
        {"sessions_to_profit_gross": 2},
        {"sessions_to_profit_gross": 4},
        {"sessions_to_profit_gross": None},
        {"sessions_to_profit_gross": None},
    ]
    stats = _dtp_stats(rows, "sessions_to_profit_gross")
    assert stats["n"] == 4
    assert stats["reached"] == 2
    assert stats["reached_pct"] == pytest.approx(50.0)
    assert stats["mean"] == pytest.approx(3.0)     # over achievers only
    assert stats["median"] == pytest.approx(3.0)


def test_stats_on_an_empty_cohort_do_not_explode():
    stats = _dtp_stats([], "sessions_to_profit_gross")
    assert stats == {"n": 0, "reached": 0, "reached_pct": None}


def test_stats_when_nobody_reached_it():
    stats = _dtp_stats([{"sessions_to_profit_gross": None}], "sessions_to_profit_gross")
    assert stats["reached_pct"] == pytest.approx(0.0)
    assert "mean" not in stats


def test_summary_sheet_splits_winners_from_losers_and_carries_notes():
    rows = [
        {"symbol": "W", "pnl_pct": 12.0, "exit_reason": "target",
         "sessions_to_profit_gross": 3, "days_to_profit_gross": 4,
         "sessions_to_profit_net": 3, "outcome": "reached"},
        {"symbol": "L", "pnl_pct": -8.0, "exit_reason": "stop",
         "sessions_to_profit_gross": None, "days_to_profit_gross": None,
         "sessions_to_profit_net": None, "outcome": "never_sustained"},
    ]
    sheet = _dtp_summary_sheet(rows, 5, 0.4)
    cohorts = sheet["cohort"].tolist()
    assert "All trades" in cohorts
    assert "Winners (net P&L > 0)" in cohorts
    assert "Losers (net P&L <= 0)" in cohorts
    assert "Exit: target" in cohorts and "Exit: stop" in cohorts

    by_cohort = sheet.set_index("cohort")
    assert by_cohort.loc["Winners (net P&L > 0)", "reached (%)"] == pytest.approx(100.0)
    assert by_cohort.loc["Losers (net P&L <= 0)", "reached (%)"] == pytest.approx(0.0)
    # The censoring note must survive into the sheet.
    assert any("never sustained" in str(c) for c in cohorts)
