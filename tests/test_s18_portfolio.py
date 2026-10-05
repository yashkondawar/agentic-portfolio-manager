from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core import storage
from core.run_history import save_run
from core.strategy import StrategyResult
from backtesting.s18 import portfolio, service
from test_s18_service import daily_setup  # noqa: F401


def _saved_run(book_id, output, **params):
    return save_run(
        StrategyResult("s18_daily", "completed", data=output),
        {"book_id": book_id, "combo": "P5", "metal_mode": "none", **params},
        duration_ms=1,
    )


def test_snapshot_uses_saved_portfolio_not_preview_or_network(daily_setup):
    m = daily_setup
    first = service.run_daily(as_of=str(m.dates[0]), combo="P5", metal_mode="none")
    service.run_daily(as_of=str(m.dates[1]), combo="P5", metal_mode="none")
    m.close[2] *= 1.2
    preview = service.run_daily(
        as_of=str(m.dates[2]),
        combo="P5",
        metal_mode="none",
        persist=False,
    )
    _saved_run("default", preview)
    with (
        patch(
            "backtesting.s18.data.load_market",
            side_effect=AssertionError("Price reload"),
        ),
        patch(
            "backtesting.s18.live_data.collect_market",
            side_effect=AssertionError("Network"),
        ),
    ):
        snap = portfolio.ledger_snapshot(combo="P5", metal_mode="none")
    assert snap["as_of"] == str(m.dates[1])
    assert snap["book"]["equity"] == pytest.approx(99980)
    assert snap["book"]["open_positions"] == 10
    assert snap["book"]["total_pnl"] == pytest.approx(-20)
    assert snap["book"]["unrealized_pnl"] == pytest.approx(-20)
    assert snap["book"]["realized_pnl"] == 0
    assert snap["book"]["tax_paid"] == 0
    assert snap["opened_on"] == first["as_of"]
    assert preview["metrics"]["final_value"] > snap["book"]["equity"]
    assert all(h["average_cost"] > 100 for h in snap["holdings"])


def test_latest_run_is_scoped_to_selected_portfolio(daily_setup):
    first = service.run_daily(
        as_of="2025-01-01",
        book_id="first",
        combo="P5",
        metal_mode="none",
    )
    second = service.run_daily(
        as_of="2025-01-01",
        book_id="second",
        combo="P5",
        metal_mode="none",
        capital=200000,
    )
    first_id = _saved_run("first", first)
    _saved_run("second", second)
    assert (
        portfolio.latest_portfolio_run(book_id="first", combo="P5", metal_mode="none")[
            "id"
        ]
        == first_id
    )
    failure_id = save_run(
        StrategyResult("s18_daily", "failed", error="Input unavailable"),
        {"book_id": "first", "combo": "P5", "metal_mode": "none"},
        duration_ms=1,
    )
    assert (
        portfolio.latest_portfolio_run(book_id="first", combo="P5", metal_mode="none")[
            "id"
        ]
        == failure_id
    )
    assert (
        portfolio.ledger_snapshot(book_id="first", combo="P5", metal_mode="none")[
            "book"
        ]["equity"]
        == 100000
    )
    assert portfolio.latest_portfolio_run(book_id="unused") is None


def test_missing_committed_artifact_is_explicit(daily_setup):
    output = service.run_daily(as_of="2025-01-01", combo="P5", metal_mode="none")
    with storage.connection_scope() as connection:
        connection.execute(
            "DELETE FROM artifacts WHERE group_id=? AND name='holdings.csv'",
            (output["artifact_group_id"],),
        )
    with pytest.raises(ValueError, match="missing holdings"):
        portfolio.ledger_snapshot(combo="P5", metal_mode="none")


def test_page_updates_saved_snapshot_above_latest_run_on_same_submission(daily_setup):
    m = daily_setup
    defaults = {
        "book_id": "layout",
        "combo": "P5",
        "metal_mode": "none",
        "capital": 100000.0,
        "persist": True,
        "as_of": str(m.dates[0]),
    }
    storage.set_document("strategy_defaults", "s18_daily", defaults)
    service.run_daily(**defaults)
    app = AppTest.from_string(
        "from ui.state import initialize_state\n"
        "from ui.pages import _s18_portfolio_desk\n"
        "initialize_state()\n"
        "_s18_portfolio_desk()\n"
    ).run(timeout=120)
    assert not app.exception
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "100,000"
    )
    assert [v.value for v in app.subheader] == ["Run S18 Daily", "Latest run"]
    assert any(v.value == "### S18 portfolio" for v in app.markdown)
    assert any(
        v.value == "### S18 portfolio" for v in app.main.children[0].get("markdown")
    )
    app.date_input(key="discover_s18_as_of").set_value(pd.Timestamp(m.dates[1]).date())
    next(b for b in app.button if b.label == "Run S18 Daily").click().run(timeout=120)
    assert not app.exception
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "99,980"
    )
    assert next(v for v in app.metric if v.label == "Positions (A + B)").value == "10"
    assert any("Portfolio updated" in s.value for s in app.success)
    assert any(
        "2025-01-02" in c.value and "Saved through" in c.value for c in app.caption
    )
    assert not any(v.value == "#### Daily data ingestion" for v in app.markdown)
    assert not any(v.value == "#### Golden validation evidence" for v in app.markdown)

    m.close[2] *= 1.2
    app.date_input(key="discover_s18_as_of").set_value(date(2025, 1, 3))
    app.checkbox(key="discover_s18_persist").uncheck()
    next(b for b in app.button if b.label == "Run S18 Daily").click().run(timeout=120)
    assert not app.exception
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "99,980"
    )
    assert any("Preview only" in s.value for s in app.info)
    assert (
        portfolio.ledger_snapshot(book_id="layout", combo="P5", metal_mode="none")[
            "as_of"
        ]
        == "2025-01-02"
    )
    app.date_input(key="discover_s18_as_of").set_value(date(2025, 1, 1))
    app.checkbox(key="discover_s18_persist").check()
    next(b for b in app.button if b.label == "Run S18 Daily").click().run(timeout=120)
    assert not app.exception
    assert any("backwards" in e.value for e in app.error)
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "99,980"
    )


def test_empty_portfolio_does_not_replay_old_run_into_saved_state(daily_setup):
    preview = service.run_daily(
        as_of="2025-01-01",
        combo="P5",
        metal_mode="none",
        persist=False,
    )
    _saved_run("default", preview)
    assert not portfolio.ledger_snapshot(combo="P5", metal_mode="none")["exists"]
    assert portfolio.latest_portfolio_run(combo="P5", metal_mode="none") is not None
