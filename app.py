"""Meridian workbench: Research, Invest and Manage."""

from dotenv import load_dotenv
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from ui.navigation import render_navigation, routes
from ui.state import initialize_state
from ui.theme import apply_theme

load_dotenv(override=True)

st.set_page_config(
    page_title="Portfolio | Research, Invest, Manage",
    page_icon=":material/finance:",
    layout="wide",
    initial_sidebar_state="auto",
)
apply_theme()
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

route_list = routes()
pages = {
    route.key: st.Page(
        route.function,
        title=f"{route.section} / {route.label}",
        icon=f":material/{route.icon}:",
        url_path=route.path,
        default=route.key == "research",
    )
    for route in route_list
}
st.session_state["_workbench_pages"] = pages
navigation = st.navigation(list(pages.values()), position="hidden")
requested = st.session_state.pop("_requested_page", None)
if requested is not None:
    st.switch_page(pages[requested])
current = next(
    route for route in route_list if pages[route.key].url_path == navigation.url_path
)
render_navigation(current, route_list)
navigation.run()

st.markdown(
    '<div class="meridian-footer">Private workspace &nbsp; / &nbsp; '
    "Saved data is timestamped, not live. Research and modelled portfolios are "
    "decision support only. This application never places broker orders.</div>",
    unsafe_allow_html=True,
)
