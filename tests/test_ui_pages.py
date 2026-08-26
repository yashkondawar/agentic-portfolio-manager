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
