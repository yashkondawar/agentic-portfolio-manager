from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from core import storage
from core.run_history import save_run
from core.strategy import StrategyResult
from ui import overview_data as data
from ui.theme import money


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "overview.sqlite3"))
    from backtesting.breakout_ath import config

    monkeypatch.setattr(config, "STATE_PATH", tmp_path / "missing_ath.json")
    monkeypatch.setattr("core.scheduler.ensure_running", lambda: False)


def snapshot(symbol="ACME"):
    return {
        "exists": True,
        "as_of": "2026-10-02",
        "book": {
            "equity": 1100,
            "cash": 500,
            "starting_capital": 1000,
            "unrealized_pnl": 120,
            "realized_pnl": -5,
        },
        "holdings": [
            {
                "symbol": symbol,
                "quantity": 5,
                "last_price": 120,
                "value": 600,
                "unrealized_pnl": 120,
            }
        ],
        "orders": [
            {"symbol": "BUYME", "action": "BUY", "quantity": 2},
            {
                "symbol": "BLOCKED",
                "action": "BUY",
                "blocked": True,
                "blocked_reason": "sector_cap",
            },
        ],
        "equity_curve": [
            {"date": "2026-10-01", "equity": 1000},
            {"date": "2026-10-02", "equity": 1100},
        ],
    }


def test_empty_books_do_not_invent_capital(isolated_store):
    views = data.load_books()
    assert len(views) == 4
    assert not any(v.exists for v in views)
    assert all(v.value is None and v.pnl is None for v in views)
    assert all(v.action_count == 0 for v in views)


def test_all_s18_books_are_enumerated_not_latest_run(isolated_store):
    for book_id in ("alpha", "beta"):
        storage.set_document("s18", f"book:{book_id}:P15:both_priority", {})
    save_run(
        StrategyResult(
            "s18_daily", "completed", data={"portfolio_state": {"book_id": "preview"}}
        ),
        {"book_id": "preview"},
        duration_ms=1,
    )
    with (
        patch("backtesting.s18.portfolio.ledger_snapshot", return_value=snapshot()),
        patch("backtesting.s18.portfolio.latest_portfolio_run", return_value=None),
    ):
        books = data.load_books()
    s18 = [book for book in books if book.route == "s18"]
    assert [b.selection["book_id"] for b in s18] == ["alpha", "beta"]
    assert all(b.pnl == 100 and b.unrealized == 120 for b in s18)
    assert all(b.action_count == 1 for b in s18)


def test_failed_run_does_not_replace_committed_book(isolated_store):
    save_run(
        StrategyResult("gfs_live", "failed", error="Price coverage unavailable"),
        {},
        duration_ms=1,
    )
    with patch("gfs.engine.ledger_snapshot", return_value=snapshot()):
        view = data.load_books()[0]
    assert view.value == 1100
    assert view.pnl == 100
    assert view.last_run["status"] == "failed"
    assert view.action_count == 1
    assert len(view.orders) == 2


def test_corrupt_portfolio_is_not_an_empty_success(
    isolated_store, monkeypatch, tmp_path
):
    from backtesting.breakout_ath import config

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch.setattr(config, "STATE_PATH", broken)
    with patch("gfs.engine.ledger_snapshot", side_effect=ValueError("Missing marks")):
        books = data.load_books()
    assert books[0].error == "Missing marks"
    assert books[1].error
    assert not books[2].error


def test_incomplete_quarterly_state_never_reseeds_capital(isolated_store):
    storage.set_document("qtr_results", "ledger", [])
    view = data.load_books()[2]
    assert "incomplete" in view.error
    assert view.value is None


def test_quarterly_activity_is_historical_and_previews_are_excluded(isolated_store):
    storage.set_document(
        "qtr_results",
        "portfolio",
        {"cash": 1000, "starting_capital": 1000, "realized_pnl": 0},
    )
    storage.set_document("qtr_results", "ledger", [])
    save_run(
        StrategyResult(
            "qtr_results",
            "completed",
            data={
                "dry_run": False,
                "actions": [{"action": "BUY", "symbol": "COMMITTED"}],
            },
        ),
        {},
        duration_ms=1,
    )
    save_run(
        StrategyResult(
            "qtr_results",
            "completed",
            data={"dry_run": True, "actions": [{"action": "BUY", "symbol": "PREVIEW"}]},
        ),
        {},
        duration_ms=1,
    )
    view = data.load_books()[2]
    assert view.value == 1000
    assert view.action_count == 0
    assert [a["Symbol"] for a in view.activity] == ["COMMITTED"]
    assert view.timestamp_label == "Ledger saved"


def test_holding_normalization_keeps_tranches_and_missing_prices():
    rows = data.holding_rows(
        [
            {
                "symbol": "ACME",
                "tranche": "A",
                "qty": 2.5,
                "close": 100,
                "value": 250,
                "unrealised_pnl": -25,
            },
            {"symbol": "ACME", "tranche": "B", "qty": 3, "value": 0},
        ]
    )
    assert len(rows) == 2
    assert rows[0]["Quantity"] == 2.5
    assert rows[0]["P&L"] == -25
    assert rows[1]["Last mark"] is None
    assert rows[1]["Value"] == 0
    with pytest.raises(ValueError, match="non-finite"):
        data.number(float("nan"))


def test_history_uses_true_peak_before_cropping_and_is_sorted():
    curve = [
        {"date": "2026-10-02", "value": 90},
        {"date": "2026-06-01", "value": 120},
        {"date": "2026-10-01", "value": 100},
    ]
    result = data.filtered_curve(curve, "1M", drawdown=True)
    assert len(result) == 2
    assert result.iloc[-1]["value"] == -25


@pytest.mark.parametrize("missing_date", [None, ""])
@pytest.mark.parametrize("period", ["All", "1M"])
def test_history_rejects_missing_dates_before_plotting(missing_date, period):
    with pytest.raises(ValueError, match="missing dates"):
        data.filtered_curve([{"date": missing_date, "value": 1000}], period)


def test_money_preserves_zero_sign_and_indian_grouping():
    assert money(1234567.25) == "\u20b912,34,567.25"
    assert money(-0.5) == "-\u20b90.50"
    assert money(0) == "\u20b90.00"
    assert money(None) == "Not available"


def test_all_books_holdings_and_actions_visible_without_expanders(isolated_store):
    script = """
from unittest.mock import patch
from ui.state import initialize_state
from ui.overview_data import BookView
from ui.dashboards import invest_overview
initialize_state()
books = [
    BookView(str(i), name, "strategies", "Paper book", exists=True,
        value=1000+i, cash=100, pnl=100, as_of="2026-10-02",
        holdings=[{"Symbol": "HOLDING"+str(i), "Quantity": 1, "Value": 900}],
        orders=[{"Symbol": "ACTION"+str(i), "Action": "BUY", "blocked": False}])
    for i, name in enumerate(["GFS", "ATH", "Quarterly", "S18 alpha", "S18 beta"])
]
with patch("ui.dashboards.load_books", return_value=books):
    invest_overview()
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert not app.expander
    assert not app.selectbox
    text = "\n".join(item.value for item in app.markdown)
    for index in range(5):
        assert "HOLDING" + str(index) in text
        assert "ACTION" + str(index) in text
    assert next(m for m in app.metric if m.label == "Queued actions").value == "5"


def test_overview_tables_escape_saved_content(isolated_store):
    app = AppTest.from_string(
        "from ui.dashboards import _table\n"
        "_table([{'Symbol': '<script>alert(1)</script>'}], ['Symbol'], label='Holdings')"
    ).run()
    assert not app.exception
    assert "<script>" not in app.markdown[0].value
    assert "&lt;script&gt;" in app.markdown[0].value


@pytest.mark.parametrize(
    "page", ["research_overview", "invest_overview", "manage_overview", "history_page"]
)
def test_dashboard_empty_state_renders(page, isolated_store):
    app = AppTest.from_string(
        f"from ui.dashboards import {page}\n"
        "from ui.state import initialize_state\n"
        "initialize_state()\n"
        f"{page}()\n"
    ).run(timeout=30)
    assert not app.exception


def test_app_has_three_sections_and_switches_without_running_strategies(isolated_store):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
        timeout=30
    )
    assert not app.exception
    assert app.radio(key="_section_tab").options == ["Research", "Invest", "Manage"]
    assert app.sidebar.radio(key="_page_tab").options == [
        "Overview",
        "Stock research",
        "Market temperature",
        "Forecast lab",
        "Watchlist",
    ]
    app.radio(key="_section_tab").set_value("Invest").run()
    assert not app.exception
    assert any("Every strategy" in item.value for item in app.title)
    assert app.sidebar.radio(key="_page_tab").options == [
        "All portfolios",
        "Daily strategies",
        "Swing desk",
        "Rebalance",
        "Broker holdings",
    ]
    app.radio(key="_section_tab").set_value("Manage").run()
    assert not app.exception
    assert any("workspace that works" in item.value for item in app.title)
    assert app.sidebar.radio(key="_page_tab").options == [
        "Overview",
        "Backtests",
        "Schedules",
        "Run history",
        "Settings & integrations",
    ]
    assert not data.recent_runs()


def test_portfolio_card_opens_the_correct_strategy_desk(isolated_store):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
        timeout=30
    )
    app.radio(key="_section_tab").set_value("Invest").run()
    app.button(key="open_book_ath").click().run()
    assert not app.exception
    assert app.radio(key="daily_strategy").value == "ATH breakout"
    assert not app.get("form")
    app.toggle(key="configure_breakout_ath_daily").set_value(True).run()
    assert not app.exception
    assert app.get("form")
    assert not data.recent_runs()


def test_workspace_rail_opens_focused_pages_without_executing(isolated_store):
    with patch("core.registry.run_strategy") as execute:
        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py")
        ).run(timeout=30)
        for section, page in [
            ("Research", "stock"),
            ("Invest", "swing"),
            ("Manage", "schedules"),
        ]:
            app.radio(key="_section_tab").set_value(section).run(timeout=30)
            app.sidebar.radio(key="_page_tab").set_value(page).run(timeout=30)
            assert not app.exception
            assert app.sidebar.radio(key="_page_tab").value == page
            assert app.radio(key="_section_tab").value == section
        execute.assert_not_called()
    assert not data.recent_runs()


def test_s18_card_selects_book_combo_and_mode(isolated_store):
    storage.set_document(
        "strategy_defaults",
        "s18_daily",
        {
            "book_id": "selected-book",
            "combo": "P10",
            "metal_mode": "none",
            "capital": 5000,
        },
    )
    with (
        patch("backtesting.s18.portfolio.ledger_snapshot", return_value=snapshot()),
        patch("backtesting.s18.portfolio.latest_portfolio_run", return_value=None),
        patch("ui.pages.render_s18_ledger_snapshot") as render_snapshot,
        patch("core.registry.run_strategy") as execute,
    ):
        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py")
        ).run(timeout=30)
        app.radio(key="_section_tab").set_value("Invest").run()
        app.button(key="open_book_book:selected-book:P10:none").click().run()
        execute.assert_not_called()
        render_snapshot.assert_called_once_with(
            book_id="selected-book", combo="P10", metal_mode="none"
        )
    assert not app.exception
    assert app.sidebar.radio(key="_page_tab").value == "strategies"
    assert app.radio(key="daily_strategy").value == "S18 portfolios"
    assert app.text_input(key="discover_s18_book_id").value == "selected-book"
    assert app.selectbox(key="discover_s18_combo").value == "P10"
    assert app.selectbox(key="discover_s18_metal_mode").value == "none"
    assert app.number_input(key="discover_s18_capital").value == 1000


def test_routes_partition_workflows():
    from ui.navigation import routes

    by_key = {route.key: route for route in routes()}
    assert len({route.path for route in by_key.values()}) == len(by_key)
    assert by_key["watchlist"].section == "Research"
    assert by_key["forecast"].section == "Research"
    assert by_key["strategies"].section == "Invest"
    assert "s18" not in by_key
    assert by_key["rebalance"].section == "Invest"
    assert by_key["backtests"].section == "Manage"
    assert by_key["schedules"].section == "Manage"


def test_activity_counts_all_runs_not_only_latest_list(isolated_store):
    for index in range(28):
        save_run(
            StrategyResult("fixture", "completed" if index < 25 else "failed"),
            {},
            duration_ms=1,
        )
    assert len(data.recent_runs(limit=5)) == 5
    activity = data.run_activity()
    assert activity["count"].sum() == 28
    assert activity.loc[activity["status"] == "failed", "count"].sum() == 3


def test_s18_configuration_labels_are_unique_in_summary_and_history(isolated_store):
    for combo in ("P5", "P15"):
        storage.set_document("s18", f"book:default:{combo}:none", {})
    with (
        patch("backtesting.s18.portfolio.ledger_snapshot", return_value=snapshot()),
        patch("backtesting.s18.portfolio.latest_portfolio_run", return_value=None),
    ):
        books = [book for book in data.load_books() if book.route == "s18"]
    assert [b.name for b in books] == [
        "S18 / default / P15 / none",
        "S18 / default / P5 / none",
    ]
    with patch("ui.dashboards.load_books", return_value=books):
        app = AppTest.from_string(
            "from ui.state import initialize_state\n"
            "from ui.dashboards import invest_overview\n"
            "initialize_state()\n"
            "invest_overview()\n"
        ).run(timeout=30)
    assert not app.exception
    selector = next(s for s in app.selectbox if s.label == "Portfolio history")
    assert selector.options == [b.name for b in books]
    summary = next(m.value for m in app.markdown if "at a glance</caption>" in m.value)
    assert all(b.name in summary for b in books)


def test_history_link_outside_window_survives_rerun_but_not_workflow_change(
    isolated_store,
):
    target = save_run(
        StrategyResult("parallel_agents", "failed", error="Older research"),
        {},
        duration_ms=1,
    )
    for index in range(55):
        save_run(StrategyResult("fixture", "completed"), {}, duration_ms=index)
    backtest = save_run(
        StrategyResult("s18_replay", "failed", error="Backtest fixture"),
        {},
        duration_ms=1,
    )
    app = AppTest.from_string(
        "from ui.dashboards import history_page\nhistory_page()\n"
    )
    app.session_state["_history_run_id"] = target
    app.session_state["history_workflow"] = "Backtests"
    app.run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="history_workflow").value == "All"
    assert app.selectbox(key="history_selected_report").value == target
    assert "_history_run_id" not in app.session_state
    app.run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="history_selected_report").value == target
    app.selectbox(key="history_workflow").set_value("Backtests").run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="history_selected_report").value == backtest
    assert len(app.selectbox(key="history_selected_report").options) == 1
    assert "_history_linked_run" not in app.session_state
    assert all("Older research" not in error.value for error in app.error)


def test_completed_with_warnings_is_committed_quarterly_activity(isolated_store):
    storage.set_document(
        "qtr_results",
        "portfolio",
        {"cash": 1000, "starting_capital": 1000, "realized_pnl": 0},
    )
    storage.set_document("qtr_results", "ledger", [])
    save_run(
        StrategyResult(
            "qtr_results",
            "completed_with_warnings",
            data={
                "dry_run": False,
                "actions": [{"action": "SELL", "symbol": "EXITED"}],
            },
        ),
        {},
        duration_ms=1,
    )
    view = data.load_books()[2]
    assert [a["Symbol"] for a in view.activity] == ["EXITED"]
    assert view.action_count == 0
    app = AppTest.from_string(
        "from ui.dashboards import manage_overview\nmanage_overview()\n"
    ).run(timeout=30)
    assert not app.exception
    assert next(m.value for m in app.metric if m.label == "Completed") == "100.0%"


def test_s18_whole_share_units_costs_and_entitlements_are_not_lost(isolated_store):
    snap = snapshot()
    snap.update(
        execution_mode="whole_shares",
        pending_cash_in_lieu=[{"symbol": "PENDING", "value": 20, "basis": 10}],
        cash_in_lieu=[{"symbol": "SETTLED", "cash": 10}],
    )
    snap["orders"] = [
        {
            "side": "BUY",
            "symbol": "AFFORDABLE",
            "qty": 2,
            "quantity_units": "whole exchange shares",
            "reference_price": 120,
            "estimated_value": 240,
            "estimated_cost": 2,
            "estimated_amount": 242,
            "target_amount_estimate": 250,
            "sizing_status": "Estimated at last close",
        },
        {
            "side": "BUY",
            "symbol": "TOOEXPENSIVE",
            "qty": 0,
            "quantity_units": "whole exchange shares",
            "sizing_status": "Insufficient cash for one share",
        },
    ]
    view = data.BookView("s18", "S18 test", "s18", "Paper book")
    with (
        patch("backtesting.s18.portfolio.ledger_snapshot", return_value=snap),
        patch("backtesting.s18.portfolio.latest_portfolio_run", return_value=None),
    ):
        data._load_s18(view)
    assert view.starting_capital == 1000
    assert view.action_count == 1
    assert view.orders[0]["Cash required"] == 242
    assert view.orders[1]["blocked"]
    with patch("ui.dashboards.load_books", return_value=[view]):
        app = AppTest.from_string(
            "from ui.dashboards import invest_overview\ninvest_overview()\n"
        ).run(timeout=30)
    assert not app.exception
    tables = "\n".join(m.value for m in app.markdown)
    assert "Cash required" in tables and "whole exchange shares" in tables
    assert "Insufficient cash for one share" in tables
    assert {e.label for e in app.expander} == {
        "Pending fractional entitlements",
        "Modeled cash-in-lieu settlements",
    }


def test_app_retains_scheduler_recovery_once_per_resource(isolated_store):
    import streamlit as st

    st.cache_resource.clear()
    with patch("core.scheduler.ensure_running") as recover:
        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py")
        ).run(timeout=30)
        assert not app.exception
        app.radio(key="_section_tab").set_value("Invest").run(timeout=30)
        assert not app.exception
        recover.assert_called_once()
    st.cache_resource.clear()
