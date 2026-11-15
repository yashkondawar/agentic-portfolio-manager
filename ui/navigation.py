"""One route map for primary tabs, contextual navigation and dashboard actions."""

from dataclasses import dataclass
from typing import Callable

import streamlit as st

from ui.theme import badge, brand_markup


@dataclass(frozen=True)
class Route:
    key: str
    section: str
    label: str
    icon: str
    function: Callable
    path: str


def routes() -> list[Route]:
    from ui import dashboards, pages

    return [
        Route(
            "research",
            "Research",
            "Overview",
            "travel_explore",
            dashboards.research_overview,
            "research",
        ),
        Route(
            "stock",
            "Research",
            "Stock research",
            "query_stats",
            pages.research_page,
            "research_page",
        ),
        Route(
            "temperature",
            "Research",
            "Market temperature",
            "thermostat",
            pages.market_temperature_page,
            "market_temperature_page",
        ),
        Route(
            "forecast",
            "Research",
            "Forecast lab",
            "insights",
            pages.kronos_page,
            "kronos_page",
        ),
        Route(
            "watchlist",
            "Research",
            "Watchlist",
            "bookmark",
            pages.watchlist_page,
            "watchlist",
        ),
        Route(
            "invest",
            "Invest",
            "All portfolios",
            "account_balance_wallet",
            dashboards.invest_overview,
            "invest",
        ),
        Route(
            "strategies",
            "Invest",
            "Daily strategies",
            "candlestick_chart",
            pages.strategies_page,
            "discover_page",
        ),
        Route(
            "swing",
            "Invest",
            "Swing desk",
            "monitoring",
            pages.swing_page,
            "swing_page",
        ),
        Route(
            "rebalance",
            "Invest",
            "Rebalance",
            "pie_chart",
            pages.portfolio_page,
            "portfolio_page",
        ),
        Route(
            "holdings",
            "Invest",
            "Broker holdings",
            "account_balance",
            pages.broker_page,
            "broker_page",
        ),
        Route(
            "manage", "Manage", "Overview", "tune", dashboards.manage_overview, "manage"
        ),
        Route(
            "backtests",
            "Manage",
            "Backtests",
            "history",
            pages.backtest_page,
            "backtest_page",
        ),
        Route(
            "schedules",
            "Manage",
            "Schedules",
            "schedule",
            pages.schedules_page,
            "schedules_page",
        ),
        Route(
            "history",
            "Manage",
            "Run history",
            "receipt_long",
            dashboards.history_page,
            "history",
        ),
        Route(
            "settings",
            "Manage",
            "Settings & integrations",
            "settings",
            pages.settings_page,
            "settings_page",
        ),
    ]


def open_page(
    key: str, *, selection: dict | None = None, run_id: str | None = None
) -> None:
    if key == "s18":
        key = "strategies"
        selection = {"daily_strategy": "S18 portfolios", **(selection or {})}
    pages = st.session_state.get("_workbench_pages", {})
    if key not in pages:
        st.error(
            "Navigation is unavailable outside the workbench. Open app.py to continue."
        )
        return
    if selection:
        if key == "strategies":
            st.session_state["daily_strategy"] = selection["daily_strategy"]
        # Widget keys are intentionally unchanged from the existing S18 desk.
        for name, value in selection.items():
            if name != "daily_strategy":
                st.session_state[f"discover_s18_{name}"] = value
    if run_id:
        st.session_state["_history_run_id"] = run_id
    # Streamlit treats a rerun (including switch_page) inside a widget callback
    # as a no-op. Consume the navigation request in the next normal script run.
    st.session_state["_requested_page"] = key


def page_button(
    label: str,
    target: str,
    *,
    key: str,
    selection: dict | None = None,
    primary: bool = False,
) -> None:
    st.button(
        label,
        key=key,
        type="primary" if primary else "secondary",
        on_click=open_page,
        args=(target,),
        kwargs={"selection": selection},
        use_container_width=True,
    )


def render_navigation(route: Route, route_list: list[Route]) -> None:
    with st.sidebar:
        st.markdown(brand_markup(), unsafe_allow_html=True)
        st.markdown(
            '<div class="rail-workspace"><span class="rail-avatar">PW</span>'
            "<div><strong>Personal workspace</strong><small>Research. Invest. Refine.</small></div></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"{route.section.upper()} WORKSPACE")
        sections = {
            item.key: item for item in route_list if item.section == route.section
        }
        st.session_state["_page_tab"] = route.key

        def switch_context():
            open_page(st.session_state["_page_tab"])

        st.radio(
            f"Pages in {route.section}",
            list(sections),
            format_func=lambda key: sections[key].label,
            key="_page_tab",
            label_visibility="collapsed",
            on_change=switch_context,
        )
        st.markdown(
            '<div class="rail-note"><span class="eyebrow">Designed for perspective</span>'
            "<p>Research with evidence.<br>Keep risk in view.</p>"
            "<small>Decision support only.<br>No broker orders are placed.</small></div>",
            unsafe_allow_html=True,
        )
    with st.container(key="workspace_navigation"):
        st.markdown(
            '<div class="workspace-switch-heading"><span class="eyebrow">Choose your workspace</span>'
            "<span>Switch sections to change the tools in the side menu.</span></div>",
            unsafe_allow_html=True,
        )
        st.session_state["_section_tab"] = route.section

        def switch_section():
            open_page(st.session_state["_section_tab"].lower())

        st.radio(
            "Workspace",
            ["Research", "Invest", "Manage"],
            key="_section_tab",
            horizontal=True,
            label_visibility="collapsed",
            on_change=switch_section,
        )
        st.markdown(
            '<div class="workspace-context">'
            f'<div class="meridian-breadcrumb">{route.section}<span>/</span>{route.label}</div>'
            + badge("Saved data / not live")
            + "</div>",
            unsafe_allow_html=True,
        )
        st.divider()
