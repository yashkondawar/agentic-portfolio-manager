from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtesting.s18.book import Book, Position, tax_on
from backtesting.s18.calendar import review_flags
from backtesting.s18.config import COST, S18Config
from backtesting.s18.replay import compare_trades


def market(rows=150, stocks=40, metals=0, start="2025-01-01"):
    count = stocks + metals
    dates = pd.bdate_range(start, periods=rows).to_numpy(dtype="datetime64[D]")
    price = np.full((rows, count), 100.0)
    ranks = np.tile(np.arange(1, count + 1), (rows, 1))
    order = np.tile(np.arange(count), (rows, 1))
    data = SimpleNamespace(
        dates=dates,
        open=price.copy(),
        high=price.copy(),
        low=price.copy(),
        close=price.copy(),
        tradable=np.ones(price.shape, bool),
        last_rows=np.full(count, rows - 1),
        benchmark=np.full(rows, 100.0),
        risk_off=np.zeros(rows, bool),
        sell_rank=ranks.copy(),
        s2_sell_rank=ranks.copy(),
        s2_buy_order=order[:, :stocks],
        buy_order=order,
        x63=np.ones(price.shape, bool),
        sc15=np.ones(price.shape, bool),
        at_high=np.ones(price.shape, bool),
        n_stocks=stocks,
        symbols=tuple(f"S{i}" for i in range(count)),
        identities=tuple(f"ISIN{i}" for i in range(count)),
        provenance={},
    )
    data.s1_order = lambda tiered, priority: order
    return data


def step(book, data, row, review=False, initial=False, decisions=True):
    book.step(
        data,
        row,
        review=review,
        initial=initial,
        order=data.buy_order[row],
        decisions=decisions,
    )


def test_next_open_floor_and_refill_timing():
    data = market()
    book = Book(S18Config("P5", "none"), "A")
    step(book, data, 0, initial=True)
    assert not book.positions
    assert len(book.queued_buys) == 5
    for row in range(1, 65):
        step(book, data, row)
    assert all(p.queued_sell_reason == "floor" for p in book.positions)
    assert not book.queued_buys
    step(book, data, 65)
    assert len(book.trades) == 5
    assert not book.positions
    assert len(book.queued_buys) == 5
    assert all(r["reason"] == "floor" for r in book.trades)
    step(book, data, 66)
    assert len(book.positions) == 5


def test_stop_arms_at_close_and_fills_gap_at_next_open():
    data = market(rows=4)
    data.sell_rank[1:, :5] = 32767
    data.low[1, :5] = 60
    data.open[2, :5] = 60
    data.low[2, :5] = 50
    data.high[1] = 1000  # Peak is based on close, not intraday high.
    book = Book(S18Config("P5", "none"), "A")
    step(book, data, 0, initial=True)
    step(book, data, 1, review=True)
    assert len(book.positions) == 5
    assert all(p.armed and p.peak == 100 for p in book.positions)
    step(book, data, 2)
    assert len(book.trades) == 5
    assert all(
        r["exit_px"] == 60 and r["reason"] == "trailing stop" for r in book.trades
    )


def test_momentum_recovery_disarms_without_sale():
    data = market(rows=4)
    book = Book(S18Config("P5", "none"), "A")
    step(book, data, 0, initial=True)
    step(book, data, 1)
    for p in book.positions:
        p.armed = True
    step(book, data, 2, review=True)
    assert not book.trades
    assert not any(p.armed for p in book.positions)


def test_nontrading_buy_drops_sell_waits():
    data = market(rows=5)
    data.tradable[1, 0] = False
    book = Book(S18Config("P5", "none"), "A")
    step(book, data, 0, initial=True)
    step(book, data, 1, decisions=False)
    assert 0 not in {p.gid for p in book.positions}
    assert not book.queued_buys
    p = book.positions[0]
    p.queued_sell_reason = "floor"
    data.tradable[2, p.gid] = False
    step(book, data, 2, decisions=False)
    assert p in book.positions and not book.trades
    step(book, data, 3, decisions=False)
    assert len(book.trades) == 1


def test_delisting_is_distinct_from_temporary_suspension():
    data = market(rows=5)
    data.last_rows[0] = 1
    data.tradable[2:, 0] = False
    book = Book(S18Config("P5", "none"), "A")
    step(book, data, 0, initial=True)
    step(book, data, 1)
    step(book, data, 2, decisions=False)
    assert book.trades[0]["reason"] == "delisted"
    assert book.trades[0]["exit_px"] == 100


def test_promotion_cancels_exit_keeps_basis_peak_and_restarts_floor():
    data = market()
    config = S18Config("P15", "none")
    p = Position(0, 1.0, 80.0, 150.0, 0, 0, "S2", "S2", queued_sell_reason="momentum")
    book = Book(config, "A", positions=[p])
    book.decide(data, 100, False, data.buy_order[100])
    assert p.sleeve == "S1" and p.bought_as == "S2"
    assert p.basis == 80 and p.peak == 150
    assert p.s1_since == p.promoted_row == 100
    assert not p.queued_sell_reason and not p.armed and not book.trades


def test_overlay_blocks_only_s1_s2_still_walks_after_top15():
    data = market()
    data.risk_off[:] = True
    book = Book(S18Config("P5", "none"), "A")
    book.allowed_history = [5] * 5
    book.decide(data, 10, True, data.buy_order[10])
    assert [o["gid"] for o in book.queued_buys] == list(range(15, 20))
    assert all(o["sleeve"] == "S2" for o in book.queued_buys)


def test_s2_lag_minimum_and_monthly_reason_precedence():
    data = market()
    data.risk_off[:] = True
    book = Book(S18Config("P5", "none"), "A")
    book.allowed_history = [0, 5, 5, 5, 5]
    book.decide(data, 10, True, data.buy_order[10])
    assert not book.queued_buys
    book.decide(data, 11, True, data.buy_order[11])
    assert len(book.queued_buys) == 5

    book = Book(S18Config("P5", "none"), "A")
    book.positions = [
        Position(20, 1, 100, 100, 0, 0, "S2", "S2"),
        Position(21, 1, 100, 100, 0, 0, "S2", "S2"),
    ]
    data.risk_off[10] = False
    data.sell_rank[10, :5] = 1
    data.s2_sell_rank[10, 20] = 100
    book.decide(data, 10, True, data.buy_order[10])
    assert book.positions[0].queued_sell_reason == "momentum"
    assert book.positions[1].queued_sell_reason == "clear S2"


def test_s1_weighted_cash_shortfall_and_s2_lower_priority():
    data = market(rows=3, stocks=40, metals=2)
    book = Book(S18Config("P20", "both"), "A", cash=30)
    book.positions = [Position(10, 10, 1000, 100, 0, 0, "S2", "S2")]
    book.queued_buys = [
        {"gid": 0, "sleeve": "S1", "weight": 1},
        {"gid": 40, "sleeve": "S1", "weight": 2},
        {"gid": 15, "sleeve": "S2", "weight": 1},
    ]
    book.last_row = 0
    book.last_date = str(data.dates[0])
    step(book, data, 1, decisions=False)
    by_gid = {p.gid: p for p in book.positions}
    assert by_gid[0].basis == pytest.approx(10)
    assert by_gid[40].basis == pytest.approx(20)
    assert 15 not in by_gid
    assert by_gid[0].qty == pytest.approx(10 * (1 - COST) / 100)


def test_tax_setoff_and_financial_year_boundary():
    assert tax_on(-50, 100, 10, 20) == pytest.approx((2.5, 0, 0))
    assert tax_on(100, -50, 20, 0) == pytest.approx((16, 0, 50))
    data = market(rows=2, start="2025-03-31")
    book = Book(S18Config("P5", "none"), "A", cash=0)
    book.last_row = 0
    book.last_date = str(data.dates[0])
    book.realised_st = 100
    p = Position(0, 2, 100, 100, 0, 0, "S1", "S1", queued_sell_reason="floor")
    book.positions = [p]
    step(book, data, 1, decisions=False)
    assert book.tax_paid == pytest.approx(20)
    assert book.realised_st == pytest.approx(200 * (1 - COST) - 100)
    assert book.tax_ledger[0]["realised_st"] == 100


def test_tax_shortfall_pro_rata_keeps_cost_basis_ratio():
    data = market(rows=2, start="2025-03-31")
    book = Book(S18Config("P5", "none"), "A", cash=0, realised_st=100)
    book.last_row = 0
    book.last_date = str(data.dates[0])
    book.positions = [
        Position(0, 1, 80, 100, 0, 0, "S1", "S1"),
        Position(1, 2, 160, 100, 0, 0, "S1", "S1"),
    ]
    step(book, data, 1, decisions=False)
    assert all(t["reason"] == "tax sale" for t in book.trades)
    assert all(p.basis / p.qty == pytest.approx(80) for p in book.positions)
    assert book.cash == pytest.approx(0)


def test_json_roundtrip_and_contiguous_sessions():
    data = market(rows=4)
    book = Book(S18Config("P5", "none"), "A")
    step(book, data, 0, initial=True)
    restored = Book.from_dict(book.to_dict())
    step(book, data, 1)
    step(restored, data, 1)
    assert restored.to_dict() == book.to_dict()
    with pytest.raises(ValueError, match="once, in order"):
        step(restored, data, 1)


def test_reference_terminal_calendar_differs_from_complete_live_calendar():
    dates = pd.bdate_range("2025-01-01", "2025-02-28").to_numpy(dtype="datetime64[D]")
    ref = review_flags(dates, "B", reference=True)
    live = review_flags(dates, "B")
    assert not ref[-11]
    assert live[-11]
    assert ref[0] and ref[-1]


def test_open_snapshot_not_a_real_sale_and_rounding_comparison():
    data = market(rows=3)
    book = Book(S18Config("P5", "none"), "A")
    step(book, data, 0, initial=True)
    step(book, data, 1, decisions=False)
    frame = pd.DataFrame(book.open_trades(data))
    assert not book.trades
    expected = pd.read_csv(
        __import__("io").StringIO(frame.to_csv(index=False, float_format="%.6g")),
        keep_default_na=False,
    )
    compare_trades(frame, expected, "test")
    expected.loc[0, "symbol"] = "WRONG"
    with pytest.raises(ValueError, match="symbol"):
        compare_trades(frame, expected, "test")
