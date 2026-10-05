"""Opt-in real-panel parity across uninterrupted, daily and catch-up execution."""

import os
from pathlib import Path

import numpy as np
import pytest

from core import storage
from backtesting.s18 import service
from backtesting.s18.book import Book
from backtesting.s18.calendar import review_flags
from backtesting.s18.config import S18Config
from backtesting.s18.data import load_market
from backtesting.s18.dataset import get_dataset


def test_saved_daily_runs_match_uninterrupted_and_catchup(tmp_path, monkeypatch):
    location = os.environ.get("S18_DATASET_DB")
    if not location:
        pytest.skip("Set S18_DATASET_DB for real historical daily execution parity")
    dataset = get_dataset(db_path=Path(location))
    market = load_market(source=dataset, metals=True)
    first = int(np.searchsorted(market.dates, np.datetime64("2019-12-02")))
    last = int(np.searchsorted(market.dates, np.datetime64("2020-07-31")))
    config = S18Config("P15", "both_priority")
    order = market.s1_order(True, True)
    calendar = np.array(market.provenance["session_calendar"], dtype="datetime64[D]")
    expected = []
    for tranche in ("A", "B"):
        book = Book.from_cash(config, tranche, 250000)
        book.allowed_history = [0] * 5
        flags = review_flags(
            calendar,
            tranche,
            complete_through=market.provenance["calendar_complete_through"],
        )
        for row in range(first, last + 1):
            ci = int(np.searchsorted(calendar, market.dates[row]))
            book.step(
                market,
                row,
                review=bool(flags[ci]),
                order=order[row],
                initial=row == first,
            )
        expected.append(book.to_dict())
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "restart.sqlite3"))
    monkeypatch.setattr(service, "REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr(service, "get_dataset", lambda: dataset)
    monkeypatch.setattr("backtesting.s18.data.load_market", lambda **kwargs: market)
    # Certificate validity and native signal/reference parity have their own tests.
    monkeypatch.setattr(
        service,
        "_certificate",
        lambda *args, **kwargs: {
            "status": "passed",
            "source_hash": "parity-test",
            "data_hash": dataset.fingerprint(),
        },
    )
    for row in range(first, last + 1):
        result = service.run_daily(
            as_of=str(market.dates[row]),
            book_id="daily",
            capital=500000,
        )
    assert result["portfolio_state"]["books"] == expected
    service.run_daily(as_of=str(market.dates[first]), book_id="catchup", capital=500000)
    catchup = service.run_daily(
        as_of=str(market.dates[last]),
        book_id="catchup",
        capital=500000,
    )
    repeated = service.run_daily(
        as_of=str(market.dates[last]),
        book_id="daily",
        capital=500000,
    )
    assert catchup["portfolio_state"]["books"] == expected
    assert repeated["portfolio_state"]["books"] == expected
    before = storage.get_document("s18", "book:daily:P15:both_priority")
    service.run_daily(
        as_of=str(market.dates[last + 1]),
        book_id="daily",
        capital=500000,
        persist=False,
    )
    assert storage.get_document("s18", "book:daily:P15:both_priority") == before
    assert sum(len(b["fills"]) for b in expected) == 190
    assert sum(len(b["tax_ledger"]) for b in expected) == 2
