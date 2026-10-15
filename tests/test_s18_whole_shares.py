from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from backtesting.s18 import live_data, portfolio, service
from backtesting.s18.book import Book, Position
from backtesting.s18.config import COST, S18Config
from backtesting.s18.sizing import quote_factor, size_buy
from core import storage
from test_s18_book import market, step
from test_s18_service import daily_setup  # noqa: F401


def live_market(*, factor=1.0, **kwargs):
    m = market(**kwargs)
    m.provenance["raw_to_book"] = {identity: factor for identity in m.identities}
    return m


@pytest.mark.parametrize("price", [0.05, 41.740585, 100.0, 50000.0])
@pytest.mark.parametrize("budget", [0.0, 10.0, 16666.666666666668, 1000000.0])
def test_size_is_largest_whole_count_including_costs(price, budget):
    qty, amount = size_buy(budget, price)
    assert isinstance(qty, int)
    assert qty >= 0 and amount <= budget
    assert amount == pytest.approx(qty * price / (1 - COST))
    assert (qty + 1) * price / (1 - COST) > budget


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf")])
def test_invalid_exchange_price_is_an_explicit_error(price):
    with pytest.raises(ValueError, match="exchange price"):
        size_buy(1000, price)


def test_exact_cost_boundary():
    price = 41.740585
    budget = 8534 * (price / (1 - COST))
    assert size_buy(budget, price)[0] == 8534
    assert size_buy(np.nextafter(budget, 0), price)[0] == 8533


def test_buy_uses_integer_exchange_shares_not_integer_model_units():
    m = live_market(factor=2, rows=3)
    book = Book.from_cash(S18Config("P5", "none"), "A", 5000, whole_shares=True)
    step(book, m, 0, initial=True)
    before = deepcopy(book.to_dict())
    orders = service._orders([book], m, str(m.dates[1]))
    assert book.to_dict() == before
    assert all(o["qty"] == 19 and o["reference_price"] == 50 for o in orders)
    assert all(o["estimated_value"] == 950 for o in orders)
    assert sum(o["estimated_amount"] for o in orders) <= 5000
    step(book, m, 1, decisions=False)
    assert all(p.qty == 9.5 for p in book.positions)
    assert all(f["share_qty"] == 19 for f in book.fills)
    assert book.cash == pytest.approx(5000 - 5 * 950 / (1 - COST))
    assert all(
        p.basis == pytest.approx(f["amount"])
        and f["amount"] == pytest.approx(f["share_qty"] * f["share_price"] + f["model_cost"])
        for p, f in zip(book.positions, book.fills)
    )
    assert all(h["qty"] == 19 for h in service._display_holdings([book], m))
    assert all(f["qty"] == 19 and f["price"] == 50 for f in service._display_fills([book]))


def test_open_gap_resizes_estimate_and_unaffordable_buy_is_recorded():
    m = live_market(rows=3)
    book = Book.from_cash(S18Config("P5", "none"), "A", 5000, whole_shares=True)
    step(book, m, 0, initial=True)
    estimates = service._orders([book], m, str(m.dates[1]))
    assert all(o["qty"] == 9 for o in estimates)
    m.open[1, 0] = 1100
    m.open[1, 1:5] = 120
    step(book, m, 1, decisions=False)
    assert 0 not in {p.gid for p in book.positions}
    assert all(f["share_qty"] == 8 for f in book.fills)
    assert book.skipped_buys[0]["symbol"] == "S0"
    assert "one whole share" in book.skipped_buys[0]["reason"]
    assert book.cash >= 0


def test_reference_mode_remains_fractional_by_default():
    m = market(rows=3)
    book = Book.from_cash(S18Config("P5", "none"), "A", 1)
    step(book, m, 0, initial=True)
    assert all(o["qty"] is None for o in service._orders([book], m, str(m.dates[1])))
    step(book, m, 1, decisions=False)
    assert book.positions[0].qty == pytest.approx(0.2 * (1 - COST) / 100)
    assert not book.whole_shares


def test_zero_affordable_quantity_has_no_position_or_cash_debit():
    m = live_market(rows=3)
    book = Book.from_cash(S18Config("P5", "none"), "A", 100, whole_shares=True)
    step(book, m, 0, initial=True)
    orders = service._orders([book], m, str(m.dates[1]))
    assert all(o["qty"] == 0 and o["estimated_amount"] == 0 for o in orders)
    assert all("one whole share" in o["sizing_status"] for o in orders)
    step(book, m, 1, decisions=False)
    assert not book.positions and not book.fills
    assert book.cash == 100 and len(book.skipped_buys) == 5


def test_integer_tax_sales_release_basis_and_remove_fully_sold_positions():
    m = live_market(rows=2, start="2025-03-31")
    book = Book(S18Config("P5", "none"), "A", cash=0, realised_st=100, whole_shares=True)
    book.last_row, book.last_date = 0, str(m.dates[0])
    book.positions = [
        Position(0, 1, 80, 100, 0, 0, "S1", "S1"),
        Position(1, 2, 160, 100, 0, 0, "S1", "S1"),
    ]
    step(book, m, 1, decisions=False)
    assert [f["share_qty"] for f in book.fills] == [1, 1]
    assert len(book.positions) == 1 and book.positions[0].qty == 1
    assert book.positions[0].basis == 80
    assert book.cash == pytest.approx(200 * (1 - COST) - 20)


def test_whole_sell_uses_raw_qty_and_preserves_gain_accounting():
    m = live_market(factor=2, rows=3)
    book = Book(S18Config("P5", "none"), "A", cash=0, whole_shares=True)
    book.last_row, book.last_date = 0, str(m.dates[0])
    book.positions = [
        Position(0, 1.5, 120, 100, 0, 0, "S1", "S1", queued_sell_reason="floor")
    ]
    book.equity = [{"nav": 150}]
    assert service._orders([book], m, str(m.dates[1]))[0]["qty"] == 3
    step(book, m, 1, decisions=False)
    assert not book.positions
    assert book.fills[0]["share_qty"] == 3
    assert book.cash == pytest.approx(150 * (1 - COST))
    assert book.trades[0]["gain"] == pytest.approx(book.cash - 120)


def test_dated_conversion_preserves_fill_units_across_split_catchup():
    m = live_market(rows=4)
    for prices in (m.open, m.close, m.high, m.low):
        prices[:] = 50
    m.provenance["raw_to_book_events"] = [
        {"date": str(m.dates[2]), "identity": i, "factor": 0.5, "kind": "split"}
        for i in m.identities
    ]
    assert quote_factor(m, m.identities[0], 1) == 0.5
    assert quote_factor(m, m.identities[0], 2) == 1
    book = Book.from_cash(S18Config("P5", "none"), "A", 5000, whole_shares=True)
    step(book, m, 0, initial=True)
    step(book, m, 1, decisions=False)
    assert all(f["share_qty"] == 9 and f["share_price"] == 100 for f in book.fills)
    step(book, m, 2, decisions=False)
    assert all(h["qty"] == 18 for h in service._display_holdings([book], m))
    assert all(f["qty"] == 9 and f["price"] == 100 for f in service._display_fills([book]))

    prior = live_market(rows=4)
    incremental = Book.from_cash(S18Config("P5", "none"), "A", 5000, whole_shares=True)
    step(incremental, prior, 0, initial=True)
    step(incremental, prior, 1, decisions=False)
    service._rescale_books(
        [incremental], {}, {i: 0.5 for i in m.identities}, list(m.identities), m
    )
    step(incremental, m, 2, decisions=False)
    assert incremental.to_dict() == book.to_dict()


@pytest.mark.parametrize("kind,factor,message", [
    ("unverified", 2.0, "unverified requires holdings reconciliation"),
    ("demerger", 1.0, "demerger requires holdings reconciliation"),
])
def test_corporate_action_is_not_silently_rounded(kind, factor, message):
    m = live_market(rows=4)
    m.provenance["raw_to_book_events"] = [
        {"date": str(m.dates[2]), "identity": i, "factor": factor, "kind": kind}
        for i in m.identities
    ]
    book = Book.from_cash(S18Config("P5", "none"), "A", 2500, whole_shares=True)
    step(book, m, 0, initial=True)
    step(book, m, 1, decisions=False)
    with pytest.raises(ValueError, match=message):
        step(book, m, 2, decisions=False)


def test_whole_share_execution_refuses_unverified_quote_units():
    m = market(rows=3)
    book = Book.from_cash(S18Config("P5", "none"), "A", 5000, whole_shares=True)
    step(book, m, 0, initial=True)
    with pytest.raises(ValueError, match="Missing current quote conversion"):
        step(book, m, 1, decisions=False)


def test_cash_shortfall_keeps_weighting_and_sleeve_priority():
    m = live_market(rows=3, stocks=40, metals=2)
    m.open[:, 0] = m.close[:, 0] = 30
    m.open[:, 40] = m.close[:, 40] = 40
    book = Book(S18Config("P20", "both"), "A", cash=300, whole_shares=True)
    book.last_row, book.last_date = 0, str(m.dates[0])
    book.positions = [Position(10, 100, 10000, 100, 0, 0, "S2", "S2")]
    book.queued_buys = [
        {"gid": 0, "sleeve": "S1", "weight": 1},
        {"gid": 40, "sleeve": "S1", "weight": 2},
        {"gid": 15, "sleeve": "S2", "weight": 1},
    ]
    book.equity = [{"nav": 10300}]
    before = deepcopy(book.to_dict())
    estimates = service._orders([book], m, str(m.dates[1]))
    assert book.to_dict() == before
    assert [o["qty"] for o in estimates] == [3, 5, 0]
    assert sum(o["estimated_amount"] for o in estimates) <= 300
    step(book, m, 1, decisions=False)
    assert [f["share_qty"] for f in book.fills] == [3, 5]
    assert book.cash == pytest.approx(300 - 290 / (1 - COST))
    assert all(f["sleeve"] == "S1" for f in book.fills)


def test_estimates_include_exit_proceeds_without_changing_book():
    m = live_market(rows=3)
    book = Book(S18Config("P5", "none"), "A", cash=0, whole_shares=True)
    book.last_row, book.last_date = 0, str(m.dates[0])
    book.positions = [
        Position(0, 10, 900, 100, 0, 0, "S1", "S1", queued_sell_reason="floor")
    ]
    book.queued_buys = [{"gid": 1, "sleeve": "S1", "weight": 1}]
    book.equity = [{"nav": 1000}]
    before = deepcopy(book.to_dict())
    estimates = service._orders([book], m, str(m.dates[1]))
    assert book.to_dict() == before
    assert [(o["side"], o["qty"]) for o in estimates] == [("SELL", 10), ("BUY", 1)]
    step(book, m, 1, decisions=False)
    assert [(f["side"], f["share_qty"]) for f in book.fills] == [("SELL", 10), ("BUY", 1)]


def test_tax_estimate_and_actual_execution_agree_at_unchanged_prices():
    m = live_market(rows=2, start="2025-03-31")
    book = Book(S18Config("P5", "none"), "A", cash=500, realised_st=1000, whole_shares=True)
    book.last_row, book.last_date = 0, str(m.dates[0])
    book.equity = [{"nav": 500}]
    book.queued_buys = [{"gid": 0, "sleeve": "S1", "weight": 1}]
    estimates = service._orders([book], m, str(m.dates[1]))
    assert estimates[0]["qty"] == 0
    step(book, m, 1, decisions=False)
    assert not book.positions and book.cash == 300 and book.tax_paid == 200


@pytest.fixture
def native_setup(request, monkeypatch):
    request.getfixturevalue("daily_setup")
    m = live_market(rows=45, start="2026-09-01")
    m.provenance.update(
        session_calendar=[str(d) for d in m.dates],
        calendar_complete_through="2026-11-02",
        as_of="2026-09-03", price_scales={}, history_fingerprints={},
    )
    monkeypatch.setattr(
        live_data, "collect_market",
        lambda **kw: SimpleNamespace(market=m, readiness={"status": "ready"}),
    )
    return m


def legacy_cash_book():
    result = service.run_daily(
        as_of="2026-09-03", book_id="live", combo="P5", metal_mode="none"
    )
    saved = deepcopy(result["portfolio_state"])
    saved["book_fingerprint"] = service.LEGACY_FRACTIONAL_BOOK
    saved["source_hash"] = "legacy"
    saved.pop("execution_mode")
    for book in saved["books"]:
        book.pop("whole_shares")
        book.pop("skipped_buys")
    storage.set_document("s18", "book:live:P5:none", saved)
    return saved


def test_cash_only_migration_is_explicit_atomic_and_preserves_pending_state(native_setup):
    before = legacy_cash_book()
    params = dict(as_of="2026-09-03", book_id="live", combo="P5", metal_mode="none")
    with pytest.raises(ValueError, match="engine changed"):
        service.run_daily(**params)
    preview = service.run_daily(**params, migrate_cash_only=True, persist=False)
    assert storage.get_document("s18", "book:live:P5:none") == before
    after = service.run_daily(**params, migrate_cash_only=True)
    for original, migrated in zip(before["books"], after["portfolio_state"]["books"]):
        for key, value in original.items():
            assert migrated[key] == value
        assert migrated["whole_shares"]
    assert after["equity_curve"] == preview["equity_curve"]
    assert after["orders"] == preview["orders"]
    assert all(isinstance(o["qty"], int) for o in after["orders"])
    assert not after["fills"]
    assert after["portfolio_state"]["sizing_migration"]["previous_artifact_group_id"] == (
        before["artifact_group_id"]
    )
    snap = portfolio.ledger_snapshot(book_id="live", combo="P5", metal_mode="none")
    assert snap["execution_mode"] == "whole_shares"
    assert snap["book"]["cash"] == before["capital"]
    assert len(snap["orders"]) == sum(len(b["queued_buys"]) for b in before["books"])
    assert not snap["fills"]

    native_setup.provenance["as_of"] = "2026-09-04"
    filled = service.run_daily(**{**params, "as_of": "2026-09-04"})
    repeated = service.run_daily(**{**params, "as_of": "2026-09-04"})
    assert filled["fills"] == repeated["fills"]
    assert all(isinstance(f["qty"], int) for f in filled["fills"])
    assert all(f["amount"] == pytest.approx(f["qty"] * f["price"] + f["model_cost"])
               for f in filled["fills"])


@pytest.mark.parametrize("alteration", ["positions", "fills", "cash", "fingerprint", "date"])
def test_migration_rejects_any_trading_or_unknown_engine(native_setup, alteration):
    before = legacy_cash_book()
    saved = deepcopy(before)
    if alteration in {"positions", "fills"}:
        saved["books"][0][alteration] = [{}]
    elif alteration == "cash":
        saved["books"][0]["cash"] -= 1
    elif alteration == "fingerprint":
        saved["book_fingerprint"] = "unrecognized"
    else:
        saved["as_of"] = "2026-09-02"
    with pytest.raises(ValueError):
        service._migrate_cash_only(saved, "2026-09-03")
    assert storage.get_document("s18", "book:live:P5:none") == before


def test_whole_share_orders_table_shows_quantity_and_calculated_value(native_setup):
    result = service.run_daily(
        as_of="2026-09-03", book_id="live", combo="P5", metal_mode="none", persist=False
    )
    app = AppTest.from_string(
        "from ui.components import _s18_orders_table\n"
        f"_s18_orders_table({result['orders']!r})\n"
    ).run(timeout=30)
    assert not app.exception
    frame = app.dataframe[0].value
    assert pd.api.types.is_integer_dtype(frame["Quantity (buy estimate)"])
    assert all(
        frame["Estimated share value"] == frame["Quantity (buy estimate)"] * frame["Reference close"]
    )
    assert any("next open" in c.value and "unused money" in c.value for c in app.caption)
