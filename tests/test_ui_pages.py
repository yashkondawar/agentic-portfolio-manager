import ast
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize(
    "page_name",
    [
        "dashboard_page",
        "discover_page",
        "watchlist_page",
        "strategies_page",
        "research_page",
        "swing_page",
        "portfolio_page",
        "backtest_page",
        "broker_page",
        "settings_page",
        "kronos_page",
        "market_temperature_page",
        "schedules_page",
    ],
)
def test_page_renders_without_exception(page_name):
    script = (
        "from ui.state import initialize_state\n"
        f"from ui.pages import {page_name}\n"
        "initialize_state()\n"
        f"{page_name}()\n"
    )
    if page_name == "market_temperature_page":
        from research.market_temperature import MarketDataUnavailable

        context = patch(
            "ui.market_temperature._load",
            side_effect=MarketDataUnavailable("No test prices"),
        )
    else:
        context = nullcontext()
    with context:
        app = AppTest.from_string(script).run(timeout=120)
    assert not app.exception


def test_full_width_layout_remains_compatible_with_streamlit_137():
    for path in (Path(__file__).resolve().parents[1] / "ui").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                assert not (
                    keyword.arg == "width"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value == "stretch"
                ), f"{path.name}:{node.lineno}: use use_container_width=True"


def test_watchlist_form_can_submit_and_render_downloads():
    script = (
        "from unittest.mock import patch\n"
        "from core.strategy import StrategyResult\n"
        "from ui.state import initialize_state\n"
        "from ui.pages import watchlist_page\n"
        "initialize_state()\n"
        "result = StrategyResult('watchlist_curation', 'completed', "
        "'Layout submission fixture', data={'picks': [{'symbol': 'ACME'}]})\n"
        "with patch('ui.pages.run_strategy', return_value=result):\n"
        "    watchlist_page()\n"
    )
    app = AppTest.from_string(script).run(timeout=120)
    assert not app.exception
    from core import registry

    label = f"Run {registry.get_strategy('watchlist_curation').name}"
    next(button for button in app.button if button.label == label).click().run(
        timeout=120
    )
    assert not app.exception
    assert app.get("download_button")
    assert any("Layout submission fixture" in item.value for item in app.markdown)


def _research_app():
    return AppTest.from_string(
        "from ui.state import initialize_state\n"
        "from ui.pages import research_page\n"
        "initialize_state()\n"
        "research_page()\n"
    )


@pytest.mark.parametrize("symbols", ["", "   ", ", ,"])
def test_empty_research_submission_does_not_start_or_save_a_run(symbols):
    previous = {
        "strategy_id": "parallel_agents",
        "status": "completed",
        "report": "Existing research",
        "data": {},
    }
    with (
        patch("ui.components.registry.run_strategy") as execute,
        patch("ui.components.save_run") as save,
        patch("ui.components.latest_run_record", return_value=None),
    ):
        app = _research_app().run(timeout=120)
        app.session_state["latest_results"] = {"parallel_agents": previous}
        app.session_state["latest_run_id"] = "previous-run"
        app.text_input(key="research_parallel_agents_symbols").set_value(symbols)
        next(b for b in app.button if b.label == "Run stock research").click().run(
            timeout=120
        )

        assert not app.exception
        assert any("symbols" in error.value.lower() for error in app.error)
        assert not app.status
        execute.assert_not_called()
        save.assert_not_called()
        assert app.session_state["latest_results"]["parallel_agents"] == previous
        assert app.session_state["latest_run_id"] == "previous-run"


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_research_can_be_corrected_and_submit_the_entered_symbols(status):
    from core.strategy import StrategyResult

    error = "Research provider unavailable" if status == "failed" else None
    result = StrategyResult("parallel_agents", status, "Research report", error=error)
    with (
        patch("ui.components.registry.run_strategy", return_value=result) as execute,
        patch("ui.components.save_run", return_value="new-run") as save,
        patch("ui.components.latest_run_record", return_value=None),
    ):
        app = _research_app().run(timeout=120)
        next(b for b in app.button if b.label == "Run stock research").click().run(
            timeout=120
        )
        execute.assert_not_called()

        app.text_input(key="research_parallel_agents_symbols").set_value("tcs, infy")
        next(b for b in app.button if b.label == "Run stock research").click().run(
            timeout=120
        )

        assert not app.exception
        assert [item.value for item in app.error] == ([error] if error else [])
        execute.assert_called_once()
        strategy_id, params = execute.call_args.args
        assert strategy_id == "parallel_agents"
        assert params["symbols"] == ["TCS", "INFY"]
        save.assert_called_once()
        assert save.call_args.args[0] == result
        assert save.call_args.args[1] == params
        assert app.session_state["latest_run_id"] == "new-run"


def test_research_prefills_the_shared_shortlist_without_replacing_manual_input():
    app = _research_app()
    app.session_state["symbol_basket"] = ["TCS", "INFY"]
    with patch("ui.components.latest_run_record", return_value=None):
        app.run(timeout=120)
        assert (
            app.text_input(key="research_parallel_agents_symbols").value == "TCS, INFY"
        )
        app.text_input(key="research_parallel_agents_symbols").set_value("RELIANCE")
        app.run(timeout=120)
        assert not app.exception
        assert (
            app.text_input(key="research_parallel_agents_symbols").value == "RELIANCE"
        )


def test_discover_page_renders_a_populated_gfs_book(tmp_path, monkeypatch):
    """The empty-book path is trivially safe; the populated one is where the
    holdings and tradebook tables actually get exercised."""
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "gfs-ui.sqlite3"))
    script = (
        "from datetime import date\n"
        "from backtesting.gfs.portfolio import Position\n"
        "from gfs import state as live_state\n"
        "from ui.state import initialize_state\n"
        "from ui.pages import discover_page\n"
        "book = live_state.Book()\n"
        "book.open_with(500000.0, date(2024, 1, 2))\n"
        "book.last_session = date(2024, 3, 15)\n"
        "book.equity_curve = [{'date': '2024-03-15', 'equity': 512000.0,"
        " 'cash': 400000.0, 'deployed': 112000.0}]\n"
        "book.positions = {'ACME': Position(symbol='ACME', sector='IT', quantity=100,"
        " entry_price=100.0, entry_date=date(2024, 2, 1), stop_loss=90.0,"
        " initial_stop=90.0, target_price=130.0, atr_at_entry=3.0,"
        " entry_rsi_d=38.0, entry_rsi_w=64.0, entry_rsi_m=67.0)}\n"
        "book.marks = {'ACME': {'price': 120.0, 'rsi_d': 65.0, 'rsi_w': 66.0,"
        " 'rsi_m': 68.0}}\n"
        "live_state.save_book(book)\n"
        "initialize_state()\n"
        "discover_page()\n"
    )
    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception


@pytest.mark.parametrize("status", ["completed", "completed_with_warnings", "failed"])
def test_saved_run_notice_distinguishes_warnings_from_failed_runs(status):
    record = {
        "strategy_id": "qtr_results",
        "status": status,
        "report": "",
        "data": {},
        "error": None,
        "created_at": "2026-11-10T02:00:00+00:00",
    }
    app = AppTest.from_string(
        "from unittest.mock import patch\n"
        "from ui.pages import _render_saved_run_notice\n"
        f"with patch('ui.pages.latest_run_record', return_value={record!r}):\n"
        "    _render_saved_run_notice('qtr_results')\n"
    ).run(timeout=30)
    assert not app.exception
    if status == "failed":
        assert "did not complete" in app.warning[0].value
    else:
        assert not app.warning
        assert "Showing the saved run" in app.caption[0].value


STRATEGY_VIEWS = [
    ("parallel_agents", "research_page", "research_parallel_agents", "Research system"),
    (
        "sequential_agents",
        "research_page",
        "research_sequential_agents",
        "Research system",
    ),
    ("watchlist_curation", "watchlist_page", "discover_watchlist", None),
    ("gfs_live", "strategies_page", "discover_gfs", "GFS multi-timeframe"),
    ("breakout_ath_daily", "strategies_page", "discover_ath", "ATH breakout"),
    ("qtr_results", "strategies_page", "discover_results", "Quarterly results"),
    ("s18_daily", "strategies_page", "discover_s18", "S18 portfolios"),
    ("swing_trading", "swing_page", "swing", None),
    ("portfolio_analysis", "portfolio_page", "portfolio", None),
    ("swing_backtest", "backtest_page", "backtest_swing_backtest", "Strategy"),
    (
        "breakout_ath_backtest",
        "backtest_page",
        "backtest_breakout_ath_backtest",
        "Strategy",
    ),
    ("s18_backtest", "backtest_page", "backtest_s18_backtest", "Strategy"),
    ("s18_replay", "backtest_page", "backtest_s18_replay", "Strategy"),
]


def test_every_registered_strategy_has_a_ui_view():
    from core import registry
    from ui.navigation import routes

    assert {s["id"] for s in registry.list_specs()} == {
        row[0] for row in STRATEGY_VIEWS
    }
    routed = {route.function.__name__ for route in routes()}
    assert all(row[1] in routed for row in STRATEGY_VIEWS)


@pytest.mark.parametrize("strategy_id,page,prefix,choice", STRATEGY_VIEWS)
def test_strategy_views_preserve_every_parameter_and_submit_without_running_engines(
    strategy_id, page, prefix, choice, tmp_path, monkeypatch
):
    from core import registry
    from core.strategy import ParamType, StrategyResult

    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "strategy-ui.sqlite3"))
    strategy = registry.get_strategy(strategy_id)
    app = AppTest.from_string(
        "from ui.state import initialize_state\n"
        f"from ui.pages import {page}\n"
        "initialize_state()\n"
        f"{page}()\n"
    ).run(timeout=30)
    assert not app.exception
    if choice == "Research system":
        next(r for r in app.radio if r.label == choice).set_value(strategy_id).run(
            timeout=30
        )
    elif choice == "Strategy":
        next(s for s in app.selectbox if s.label == choice).set_value(strategy_id).run(
            timeout=30
        )
    elif choice:
        app.radio(key="daily_strategy").set_value(choice).run(timeout=30)
    if page == "strategies_page" and strategy_id != "s18_daily":
        app.toggle(key=f"configure_{strategy_id}").set_value(True).run(timeout=30)
    assert not app.exception
    for spec in strategy.param_specs():
        if spec.type == ParamType.SYMBOLS and spec.required:
            app.text_input(key=f"{prefix}_{spec.name}").set_value("TCS, INFY")
    # Failure envelopes avoid inventing successful strategy-specific payloads.
    result = StrategyResult(strategy_id, "failed", error="Isolated submission fixture")
    with (
        patch("ui.components.registry.run_strategy", return_value=result) as execute,
        patch("ui.components.save_run", return_value="fixture-run"),
    ):
        next(b for b in app.button if b.label.startswith("Run ")).click().run(
            timeout=30
        )
    assert not app.exception
    execute.assert_called_once()
    submitted_id, params = execute.call_args.args
    assert submitted_id == strategy_id
    assert set(params) == {spec.name for spec in strategy.param_specs()}
