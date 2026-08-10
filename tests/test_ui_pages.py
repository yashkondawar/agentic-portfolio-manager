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
    ],
)
def test_page_renders_without_exception(page_name):
    script = (
        "from ui.state import initialize_state\n"
        f"from ui.pages import {page_name}\n"
        "initialize_state()\n"
        f"{page_name}()\n"
    )
    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception
