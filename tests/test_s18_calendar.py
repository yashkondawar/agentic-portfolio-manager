import numpy as np
import pandas as pd
import pytest

from backtesting.s18.calendar import review_flags


@pytest.mark.parametrize("tranche", ["A", "B"])
def test_next_month_preview_does_not_add_reviews_to_completed_month(tranche):
    preview = pd.bdate_range("2026-09-01", "2026-11-06").to_numpy(dtype="datetime64[D]")
    complete = pd.bdate_range("2026-09-01", "2026-11-30").to_numpy(
        dtype="datetime64[D]"
    )
    preview_flags = review_flags(preview, tranche, complete_through="2026-11-07")
    full_flags = review_flags(complete, tranche, complete_through="2026-11-30")
    october = np.array([str(day).startswith("2026-10") for day in preview])
    np.testing.assert_array_equal(
        preview_flags[october], full_flags[: len(preview)][october]
    )
    assert int(preview_flags[october].sum()) == 1
    if tranche == "B":
        assert [str(day) for day in preview[october & preview_flags]] == ["2026-10-16"]
        assert not preview_flags[
            int(np.flatnonzero(preview == np.datetime64("2026-10-23"))[0])
        ]


@pytest.mark.parametrize("tranche,expected", [("A", "2026-10-30"), ("B", "2026-10-16")])
def test_complete_month_ending_on_nontrading_day_is_included(tranche, expected):
    days = pd.bdate_range("2026-10-01", "2026-10-30").to_numpy(dtype="datetime64[D]")
    flags = review_flags(days, tranche, complete_through="2026-10-31")
    assert [str(day) for day in days[flags]] == [expected]
    assert not review_flags(days, tranche).any()


def test_incomplete_month_does_not_arm_stop_early():
    from backtesting.s18.book import Book, Position
    from backtesting.s18.config import S18Config
    from test_s18_book import market

    days = pd.bdate_range("2026-09-01", "2026-11-06").to_numpy(dtype="datetime64[D]")
    m = market(rows=len(days), stocks=40, start="2026-09-01")
    row = int(np.flatnonzero(days == np.datetime64("2026-10-23"))[0])
    m.sell_rank[row, 0] = 32767
    book = Book(S18Config("P15", "none"), "B")
    book.positions = [Position(0, 1, 100, 100, 0, 0, "S1", "S1")]
    flags = review_flags(days, "B", complete_through="2026-11-07")
    book.decide(m, row, bool(flags[row]), m.buy_order[row])
    assert not book.positions[0].armed


def test_completeness_cannot_precede_last_supplied_session():
    days = pd.bdate_range("2026-10-01", "2026-11-06").to_numpy(dtype="datetime64[D]")
    with pytest.raises(ValueError, match="completeness"):
        review_flags(days, "B", complete_through="2026-10-31")


def test_reference_terminal_convention_is_unchanged():
    days = pd.bdate_range("2026-09-01", "2026-11-06").to_numpy(dtype="datetime64[D]")
    flags = review_flags(days, "B", reference=True)
    assert flags[0] and flags[-1]
    assert not flags[-11]
