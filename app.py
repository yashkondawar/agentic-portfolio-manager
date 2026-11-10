"""Unified Streamlit entry point for the trader workbench."""

import streamlit as st
from dotenv import load_dotenv
from streamlit.runtime.scriptrunner import get_script_run_ctx

from ui.pages import (
    backtest_page,
    broker_page,
    dashboard_page,
    discover_page,
    kronos_page,
    market_temperature_page,
    portfolio_page,
    research_page,
    schedules_page,
    settings_page,
    swing_page,
)
from ui.state import initialize_state

load_dotenv(override=True)

st.set_page_config(
    page_title="NSE Trader Workbench",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1500px;}
    [data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, .2);
        border-radius: .75rem;
        padding: .85rem 1rem;
    }
    [data-testid="stSidebar"] {border-right: 1px solid rgba(128, 128, 128, .18);}
    </style>
    """,
    unsafe_allow_html=True,
)

initialize_state()


@st.cache_resource
def _start_installed_scheduler() -> None:
    from core.scheduler import ensure_running

    ensure_running()


try:
    if get_script_run_ctx(suppress_warning=True) is not None:
        _start_installed_scheduler()
except (OSError, RuntimeError) as error:
    st.warning(f"Could not recover the installed strategy scheduler: {error}")

navigation = st.navigation(
    {
        "Overview": [
            st.Page(
                dashboard_page,
                title="Dashboard",
                icon=":material/dashboard:",
                default=True,
            )
        ],
        "Ideas & research": [
            st.Page(
                discover_page, title="Discover Ideas", icon=":material/travel_explore:"
            ),
            st.Page(
                research_page, title="Stock Research", icon=":material/query_stats:"
            ),
            st.Page(
                market_temperature_page,
                title="Market Temperature",
                icon=":material/thermostat:",
            ),
            st.Page(
                kronos_page, title="Kronos Forecast Lab", icon=":material/insights:"
            ),
        ],
        "Portfolio": [
            st.Page(
                swing_page, title="Swing Desk", icon=":material/candlestick_chart:"
            ),
            st.Page(
                portfolio_page, title="Portfolio Review", icon=":material/pie_chart:"
            ),
        ],
        "Validation": [
            st.Page(backtest_page, title="Backtest Lab", icon=":material/history:")
        ],
        "Account": [
            st.Page(
                broker_page,
                title="Broker & Holdings",
                icon=":material/account_balance:",
            ),
            st.Page(
                schedules_page,
                title="Automation & Schedules",
                icon=":material/schedule:",
            ),
            st.Page(
                settings_page, title="Settings & Catalog", icon=":material/settings:"
            ),
        ],
    }
)
navigation.run()
