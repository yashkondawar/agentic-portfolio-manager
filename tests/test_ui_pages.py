import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize(
    "page_name",
    [
        "dashboard_page",
        "discover_page",
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


def test_discover_form_can_submit_and_render_downloads():
    script = (
        "from unittest.mock import patch\n"
        "from core.strategy import StrategyResult\n"
        "from ui.state import initialize_state\n"
        "from ui.pages import discover_page\n"
        "initialize_state()\n"
        "result = StrategyResult('watchlist_curation', 'completed', "
        "'Layout submission fixture', data={'picks': [{'symbol': 'ACME'}]})\n"
        "with patch('ui.pages.run_strategy', return_value=result):\n"
        "    discover_page()\n"
    )
    app = AppTest.from_string(script).run(timeout=120)
    assert not app.exception
    from core import registry

    label = f"Run {registry.get_strategy('watchlist_curation').name}"
    next(button for button in app.button if button.label == label).click().run(timeout=120)
    assert not app.exception
    assert app.get("download_button")
    assert any("Layout submission fixture" in item.value for item in app.markdown)


def test_discover_page_renders_a_populated_gfs_book():
    """The empty-book path is trivially safe; the populated one is where the
    holdings and tradebook tables actually get exercised."""
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
