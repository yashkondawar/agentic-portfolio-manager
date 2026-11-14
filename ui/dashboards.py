"""Task-focused landing pages. Opening a dashboard never runs a strategy."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import schedules
from core.run_history import get_run
from ui.components import (
    format_run_timestamp,
    page_header,
    render_result,
    result_from_record,
)
from ui.navigation import open_page, page_button
from ui.overview_data import (
    BACKTEST_IDS,
    INVEST_IDS,
    READ_ERRORS,
    RESEARCH_IDS,
    BookView,
    filtered_curve,
    load_books,
    recent_runs,
    run_activity,
    saved_prices,
)
from ui.state import add_symbols
from ui.theme import ACCENT, badge, card, empty_state, money, style_chart

logger = logging.getLogger(__name__)


def _error(context: str, exc: Exception) -> None:
    logger.exception(context)
    st.error(f"{context}: {exc}")


def _section_heading(title: str, description: str, *, label: str = "") -> None:
    st.markdown(
        '<div class="section-heading"><div>'
        f'<span class="eyebrow">{escape(label)}</span>'
        f"<h2>{escape(title)}</h2><p>{escape(description)}</p></div></div>",
        unsafe_allow_html=True,
    )


def _workflow_card(
    number: str, title: str, description: str, action: str, target: str, key: str
) -> None:
    with card(key=key):
        st.markdown(
            f'<span class="feature-number" aria-hidden="true">{escape(number)}</span>'
            f'<div class="feature-copy"><h3>{escape(title)}</h3><p>{escape(description)}</p></div>',
            unsafe_allow_html=True,
        )
        page_button(action, target, key=f"{key}_action")


def _table(rows: list[dict], columns: list[str], *, label: str) -> None:
    """A compact, scrollable overview; the full desks retain sortable data grids."""
    if not rows:
        return
    columns = [
        name for name in columns if any(row.get(name) is not None for row in rows)
    ]
    numeric_columns = {
        name
        for name in columns
        if any(
            isinstance(row.get(name), (int, float))
            and not isinstance(row.get(name), bool)
            for row in rows
        )
    }
    cells = []
    for row in rows:
        values = []
        for name in columns:
            value = row.get(name)
            classes = ["numeric"] if name in numeric_columns else []
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if name in {"P&L", "Net P&L"}:
                    classes.append("positive" if value >= 0 else "negative")
                if name in {"Quantity", "Actions"}:
                    text = f"{value:,.4f}".rstrip("0").rstrip(".")
                elif name in {
                    "Last mark",
                    "Value",
                    "P&L",
                    "Net P&L",
                    "Cash",
                    "Stop",
                    "Reference",
                    "Allocation",
                    "Share value",
                    "Model cost",
                    "Cash required",
                }:
                    text = money(value)
                else:
                    text = str(value)
            else:
                text = str(value) if value is not None else "-"
            attributes = f' class="{" ".join(classes)}"' if classes else ""
            values.append(f"<td{attributes}>{escape(text)}</td>")
        cells.append("<tr>" + "".join(values) + "</tr>")
    st.markdown(
        '<div class="meridian-table-wrap" role="region" tabindex="0" '
        f'aria-label="{escape(label, quote=True)}"><table class="meridian-table">'
        f'<caption class="eyebrow">{escape(label)}</caption><thead><tr>'
        + "".join(
            f'<th scope="col" class="{"numeric" if name in numeric_columns else ""}">{escape(name)}</th>'
            for name in columns
        )
        + "</tr></thead><tbody>"
        + "".join(cells)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _book_card(view: BookView) -> None:
    with card(key=f"portfolio_card_{view.key}"):
        identifier = "S18" if view.route == "s18" else view.key[:3].upper()
        st.markdown(
            '<div class="book-header"><div class="book-title">'
            f'<span class="book-identifier" aria-hidden="true">{escape(identifier)}</span>'
            f"<div><h3>{escape(view.name)}</h3><p>{escape(view.mode)}</p></div></div>"
            + badge(view.state_label, warning=bool(view.error))
            + "</div>",
            unsafe_allow_html=True,
        )
        if view.error:
            st.error(f"Cannot read this portfolio: {view.error}")
        elif not view.exists:
            message = (
                "No saved ATH state file in this checkout. If this sleeve runs in another "
                "checkout, its saved state must be made available here. Do not start a new "
                "book just to restore visibility."
                if view.key == "ath"
                else "No committed portfolio yet. Start a daily run to establish the book. "
                "No sample capital or returns are shown."
            )
            empty_state("Your portfolio starts here", message)
        else:
            tone = (
                "" if view.pnl is None else "positive" if view.pnl >= 0 else "negative"
            )
            ret = (
                f"{view.return_pct:+.2f}% since inception"
                if view.return_pct is not None
                else "Return unavailable"
            )
            st.markdown(
                '<div class="book-amounts">'
                f"<div><span>Portfolio value</span><strong>{money(view.value)}</strong><small>Saved marks, not live</small></div>"
                f'<div><span>Net P&amp;L</span><strong class="{tone}">{money(view.pnl)}</strong><small>{ret}</small></div>'
                f"<div><span>Cash</span><strong>{money(view.cash)}</strong><small>Within this book only</small></div>"
                f"<div><span>Order actions</span><strong>{view.action_count}</strong><small>{len(view.holdings)} current holdings</small></div>"
                "</div>",
                unsafe_allow_html=True,
            )
            timestamp = (
                format_run_timestamp(view.as_of)
                if view.as_of and "T" in view.as_of
                else view.as_of or "not recorded"
            )
            st.markdown(
                '<div class="book-meta"><span aria-hidden="true"></span>'
                f"{escape(view.timestamp_label)}: {escape(timestamp)}</div>",
                unsafe_allow_html=True,
            )
            if view.curve:
                try:
                    frame = filtered_curve(view.curve, "All")
                    figure = go.Figure(
                        go.Scatter(
                            x=frame["date"],
                            y=frame["value"],
                            mode="lines",
                            name="Saved value",
                            line={"color": ACCENT, "width": 2.5},
                            fill="tozeroy",
                            fillcolor="rgba(8,127,91,.06)",
                            hovertemplate="%{x|%d %b %Y}<br>Saved NAV: \u20b9%{y:,.2f}<extra></extra>",
                        )
                    )
                    figure.update_yaxes(rangemode="normal", tickprefix="\u20b9")
                    low, high = frame["value"].min(), frame["value"].max()
                    padding = max(high - low, abs(high) * 0.01, 1) * 0.15
                    figure.update_yaxes(range=[low - padding, high + padding])
                    st.plotly_chart(
                        style_chart(figure, height=180),
                        use_container_width=True,
                        theme=None,
                        key=f"book_curve_{view.key}",
                        config={"displayModeBar": False},
                    )
                    st.caption("Saved NAV history. No inferred or backfilled sessions.")
                except READ_ERRORS as exc:
                    _error("Could not display this book's history", exc)
            st.caption(
                f"Unrealised {money(view.unrealized)}  /  Realised {money(view.realized)}"
            )
            for note in view.notes:
                if "behind" in note:
                    st.warning(note)
            st.markdown(
                f'<div class="book-section">{escape(view.action_label)}<small>{view.action_count} actionable</small></div>',
                unsafe_allow_html=True,
            )
            if view.orders:
                _table(
                    view.orders,
                    [
                        "Action",
                        "Symbol",
                        "Tranche",
                        "Quantity",
                        "Units",
                        "Reference",
                        "Allocation",
                        "Share value",
                        "Model cost",
                        "Cash required",
                        "Sizing",
                        "Session",
                        "Status",
                    ],
                    label=f"{view.name} order actions",
                )
                blocked = sum(bool(row.get("blocked")) for row in view.orders)
                if blocked:
                    st.warning(
                        f"{blocked} blocked or zero-quantity signal(s) excluded from the action count. Do not treat them as placeable orders."
                    )
            elif not view.activity:
                st.caption(
                    "No pending-order queue is tracked for this ledger."
                    if view.key == "quarterly"
                    else "No saved instructions waiting for the next session."
                )
            if view.activity:
                _table(
                    view.activity,
                    ["Action", "Symbol", "Quantity", "Reference", "Status"],
                    label="Historical actions already applied, not pending orders",
                )
            st.markdown(
                f'<div class="book-section">Current holdings<small>{len(view.holdings)} positions</small></div>',
                unsafe_allow_html=True,
            )
            if view.holdings:
                _table(
                    view.holdings,
                    [
                        "Symbol",
                        "Tranche",
                        "Quantity",
                        "Units",
                        "Last mark",
                        "Value",
                        "P&L",
                        "Stop",
                    ],
                    label=f"{view.name} current holdings",
                )
            else:
                st.caption("No open holdings in the saved book.")
            if view.pending_cash_in_lieu or view.cash_in_lieu:
                from ui.components import _s18_entitlements

                _s18_entitlements(
                    {
                        "pending_cash_in_lieu": view.pending_cash_in_lieu,
                        "cash_in_lieu": view.cash_in_lieu,
                    }
                )
            st.caption(" ".join(note for note in view.notes if "behind" not in note))
        if view.last_run and view.last_run["status"] == "completed_with_warnings":
            st.warning(
                f"Latest run completed with warnings ({format_run_timestamp(view.last_run['created_at'])}). "
                "Some work may be deferred. Inspect the saved report; the values above are committed state."
            )
        elif view.last_run and view.last_run["status"] != "completed":
            st.warning(
                f"Latest run: {view.last_run['status']} ({format_run_timestamp(view.last_run['created_at'])}). "
                f"{view.last_run.get('error') or 'Inspect the saved report.'} "
                "The committed portfolio above has not been replaced by this run."
            )
        page_button(
            "Open portfolio desk",
            view.route,
            key=f"open_book_{view.key}",
            selection=(
                {**view.selection, "capital": view.starting_capital}
                if view.route == "s18" and view.starting_capital is not None
                else view.selection or None
            ),
        )


def invest_overview() -> None:
    page_header(
        "Every strategy. One clear view.",
        "Your portfolio command center. Know what you own, how it is doing, and what needs your attention.",
    )
    st.caption(
        "Independent strategy books, not a combined brokerage balance. "
        "Reading this page never runs a strategy or places an order."
    )
    books = load_books()
    columns = st.columns(4)
    columns[0].metric(
        "Started portfolios", sum(b.exists and not b.error for b in books)
    )
    columns[1].metric(
        "Queued actions",
        sum(b.action_count for b in books if not b.error),
        help="Excludes blocked signals and historical actions already applied.",
    )
    columns[2].metric(
        "Holdings across books",
        sum(len(b.holdings) for b in books if not b.error),
        help="Counts positions, not unique symbols. S18 A/B tranches are separate.",
    )
    columns[3].metric(
        "Unavailable portfolios",
        sum(bool(b.error) for b in books),
        help="A read failure is never shown as a zero balance.",
    )
    _portfolio_history(books)
    _section_heading(
        "Your strategy portfolios",
        "Every book, every balance. Holdings and saved instructions are visible below.",
        label="Portfolio overview",
    )
    _table(
        [
            {
                "Portfolio": b.name,
                "Value": None if b.error else b.value,
                "Net P&L": None if b.error else b.pnl,
                "Cash": None if b.error else b.cash,
                "Actions": None if b.error else b.action_count,
                "State": b.state_label,
                "Timestamp": (
                    f"{b.timestamp_label}: "
                    + (format_run_timestamp(b.as_of) if "T" in b.as_of else b.as_of)
                    if b.as_of
                    else "-"
                ),
            }
            for b in books
        ],
        ["Portfolio", "Value", "Net P&L", "Cash", "Actions", "State", "Timestamp"],
        label="All strategy portfolios at a glance",
    )
    st.caption(
        "Net P&L is saved portfolio value minus initial capital. Realised/unrealised figures retain each engine's cost treatment; they need not sum to net P&L."
    )
    for offset in range(0, len(books), 2):
        pair = st.columns(2)
        for column, book in zip(pair, books[offset : offset + 2]):
            with column:
                _book_card(book)
    with card():
        st.subheader("Your account and discretionary reviews")
        st.caption(
            "Swing and portfolio reviews use the holdings you supply; they do not own separate strategy capital."
        )
        left, middle, right = st.columns(3)
        with left:
            page_button("Broker holdings (read-only)", "holdings", key="invest_broker")
        with middle:
            page_button("Review swing positions", "swing", key="invest_swing")
        with right:
            page_button("Review rebalancing", "rebalance", key="invest_rebalance")


def _portfolio_history(books: list[BookView]) -> None:
    available = {book.key: book for book in books if book.curve and not book.error}
    if not available:
        return
    with card(key="portfolio_performance"):
        st.subheader("Performance & risk")
        st.caption(
            "Explore each book's saved NAV and drawdown. Independent portfolios are never summed or compared as if they shared the same inception."
        )
        selection, range_control, display = st.columns([2, 1, 1.25])
        key = selection.selectbox(
            "Portfolio history",
            list(available),
            format_func=lambda key: available[key].name,
        )
        period = range_control.selectbox(
            "History window", ["1M", "3M", "1Y", "All"], index=3
        )
        mode = display.radio("Measure", ["Value", "Drawdown"], horizontal=True)
        try:
            frame = filtered_curve(
                available[key].curve, period, drawdown=mode == "Drawdown"
            )
            latest = frame["value"].iloc[-1]
            st.metric(
                (
                    "Latest saved value"
                    if mode == "Value"
                    else "Drawdown at last saved close"
                ),
                money(latest) if mode == "Value" else f"{latest:.2f}%",
            )
            figure = go.Figure(
                go.Scatter(
                    x=frame["date"],
                    y=frame["value"],
                    name=mode,
                    mode="lines",
                    fill="tozeroy",
                    fillcolor=(
                        "rgba(8,127,91,.06)"
                        if mode == "Value"
                        else "rgba(185,68,70,.06)"
                    ),
                    line={
                        "color": ACCENT if mode == "Value" else "#b94446",
                        "width": 2,
                    },
                )
            )
            figure.update_yaxes(
                title=(
                    "Portfolio value (INR)"
                    if mode == "Value"
                    else "Below historical peak (%)"
                )
            )
            if mode == "Value":
                low, high = frame["value"].min(), frame["value"].max()
                padding = max(high - low, abs(high) * 0.01, 1) * 0.15
                figure.update_yaxes(range=[low - padding, high + padding])
            st.plotly_chart(
                style_chart(figure, height=300),
                use_container_width=True,
                theme=None,
                key="portfolio_history_explorer",
                config={"displayModeBar": False},
            )
            st.caption(
                f"Showing {len(frame)} saved observations through {frame['date'].max():%d %b %Y}. "
                "Drawdown uses the peak over all available saved history before cropping the window. "
                "Some engines retain limited history; missing sessions are not fabricated."
            )
        except READ_ERRORS as exc:
            _error("Could not display portfolio history", exc)


def _run_list(rows: list[dict], *, key: str) -> None:
    if not rows:
        empty_state(
            "Your report library starts here",
            "Saved reports will appear here after your first run. Reopen them anytime without running a strategy again.",
        )
        return
    for row in rows:
        text, action = st.columns([3, 1])
        with text:
            status = row["status"]
            st.markdown(
                '<div class="attention-item"><div>'
                f"<strong>{escape(row['strategy_id'].replace('_', ' ').title())}</strong><p>"
                f"{escape(format_run_timestamp(row['created_at']))} / {row['duration_ms'] / 1000:.1f}s"
                "</p></div>"
                + badge(status.replace("_", " "), warning=status != "completed")
                + "</div>",
                unsafe_allow_html=True,
            )
        with action:
            st.button(
                "Open report",
                key=f"{key}_{row['id']}",
                on_click=open_page,
                args=("history",),
                kwargs={"run_id": row["id"]},
            )


def _market_context() -> None:
    with card(key="market_context"):
        _section_heading(
            "The market, in perspective",
            "Stored index history. A backdrop for research, not a trading signal.",
            label="Market context",
        )
        index = st.selectbox(
            "Index history", ["NIFTY 50", "SENSEX"], key="overview_index"
        )
        ticker = "^NSEI" if index == "NIFTY 50" else "^BSESN"
        try:
            frame = saved_prices([ticker]).get(ticker)
            if frame is None or frame.empty:
                empty_state(
                    "Your market view is ready",
                    "No stored prices for this index yet. Open Market temperature to load data through its existing workflow. This overview never downloads or simulates quotes.",
                )
            else:
                close = frame["Close"]
                change = (
                    float((close.iloc[-1] / close.iloc[-2] - 1) * 100)
                    if len(close) > 1 and close.iloc[-2]
                    else None
                )
                st.metric(
                    "Last stored close",
                    f"{close.iloc[-1]:,.2f}",
                    delta=(
                        f"{change:+.2f}% vs prior stored close"
                        if change is not None
                        else None
                    ),
                )
                figure = go.Figure(
                    go.Scatter(
                        x=frame.index,
                        y=close,
                        name=index,
                        mode="lines",
                        line={"color": ACCENT, "width": 2},
                        fill="tozeroy",
                        fillcolor="rgba(8,127,91,.06)",
                    )
                )
                low, high = close.min(), close.max()
                padding = max(high - low, abs(high) * 0.01, 1) * 0.15
                figure.update_yaxes(range=[low - padding, high + padding])
                st.plotly_chart(
                    style_chart(figure, height=330),
                    use_container_width=True,
                    theme=None,
                    config={"displayModeBar": False},
                )
                st.caption(
                    f"Stored daily prices through {frame.index[-1]:%d %b %Y}. Not live. This price chart is not the market-temperature reading."
                )
        except READ_ERRORS as exc:
            _error("Cannot read stored index prices", exc)
        page_button(
            "Explore market temperature", "temperature", key="research_temperature"
        )


def _idea_basket() -> None:
    with card(key="research_shortlist"):
        basket = st.session_state.get("symbol_basket", [])
        _section_heading(
            "Your research shortlist",
            "Turn interesting companies into your next research session.",
            label=f"{len(basket)} companies / this session",
        )
        st.caption(
            "A shared idea basket for stock research, watchlist screening and swing reviews."
        )
        with st.form("overview_add_symbols", clear_on_submit=True):
            raw = st.text_input("Add NSE symbols", placeholder="HDFCBANK, TCS, INFY")
            if st.form_submit_button("Add to shortlist"):
                values = raw.replace("\n", ",").replace(" ", ",").split(",")
                if not any(value.strip() for value in values):
                    st.warning("Enter at least one symbol.")
                else:
                    add_symbols(values)
                    st.rerun()
        basket = st.session_state.get("symbol_basket", [])
        if basket:
            st.markdown(
                '<div class="symbol-chips">'
                + "".join(
                    f'<span class="symbol-chip">{escape(symbol)}</span>'
                    for symbol in basket
                )
                + "</div>",
                unsafe_allow_html=True,
            )
            query = st.text_input(
                "Find a saved idea",
                key="overview_idea_filter",
                placeholder="Filter by symbol",
            )
            wanted = [s for s in basket if query.strip().upper() in s]
            if not wanted:
                st.info("No matching symbols.")
            else:
                try:
                    prices = saved_prices(wanted, days=45)
                    rows = []
                    for symbol in wanted:
                        frame = prices.get(symbol)
                        rows.append(
                            {
                                "Symbol": symbol,
                                "Last mark": (
                                    float(frame["Close"].iloc[-1])
                                    if frame is not None and not frame.empty
                                    else None
                                ),
                                "As of": (
                                    frame.index[-1].strftime("%d %b %Y")
                                    if frame is not None and not frame.empty
                                    else "No saved prices"
                                ),
                            }
                        )
                    _table(
                        rows,
                        ["Symbol", "Last mark", "As of"],
                        label="Saved ideas and stored prices",
                    )
                except READ_ERRORS as exc:
                    _error("Cannot read shortlist prices", exc)
            with st.expander("Edit shortlist"):
                keep = st.multiselect(
                    "Keep these symbols",
                    basket,
                    default=basket,
                    key="overview_keep_symbols",
                )
                if st.button("Update shortlist"):
                    st.session_state["symbol_basket"] = keep
                    st.rerun()
        else:
            empty_state(
                "Keep your next idea close",
                "Add companies above or discover candidates with the watchlist screener. The shortlist is shared across research and swing reviews for this browser session.",
            )
        page_button(
            "Research these companies", "stock", key="research_basket", primary=True
        )


def research_overview() -> None:
    page_header(
        "Make sense of the market.",
        "A quieter place to find your next idea. Put evidence before conviction.",
    )
    workflows = [
        (
            "01",
            "Research a company",
            "Let specialist agents examine fundamentals, technicals and risk before you form a view.",
            "Start stock research",
            "stock",
            "research_start",
        ),
        (
            "02",
            "Discover opportunities",
            "Screen a broad universe and build a shortlist worth investigating further.",
            "Build a watchlist",
            "watchlist",
            "research_watchlist",
        ),
        (
            "03",
            "Explore possible paths",
            "Visualise Kronos forecasts alongside their assumptions. Scenarios, never promises.",
            "Open forecast lab",
            "forecast",
            "research_forecast",
        ),
    ]
    for column, workflow in zip(st.columns(3), workflows):
        with column:
            _workflow_card(*workflow)
    left, right = st.columns([1.7, 1])
    with left:
        _market_context()
    with right:
        _idea_basket()
    with card(key="research_library"):
        _section_heading(
            "Pick up where you left off",
            "Your latest research, saved with its evidence and assumptions.",
            label="Research library",
        )
        try:
            _run_list(recent_runs(RESEARCH_IDS, limit=4), key="research_recent")
        except READ_ERRORS as exc:
            _error("Cannot load saved research", exc)
        page_button("Browse all saved reports", "history", key="research_history")


def manage_overview() -> None:
    from core import scheduler
    from ui.pages import _health_verdict

    page_header(
        "A workspace that works for you.",
        "Your runs, schedules, validation and integrations. Organized and under control.",
    )
    try:
        activity = run_activity()
        configured = schedules.list_schedules()
        beat = scheduler.read_heartbeat()
        status, detail, running = _health_verdict(
            scheduler.heartbeat_age_seconds(),
            int(beat.get("poll_seconds") or scheduler.DEFAULT_POLL_SECONDS),
        )
    except READ_ERRORS as exc:
        _error("Cannot load workspace status", exc)
        return
    total = int(activity["count"].sum())
    completed = int(
        activity.loc[
            activity["status"].isin(["completed", "completed_with_warnings"]), "count"
        ].sum()
    )
    metrics = st.columns(4)
    metrics[0].metric("Runs / last 30 days", total)
    metrics[1].metric(
        "Completed",
        f"{completed / total:.1%}" if total else "No runs",
        help="Includes completed-with-warnings runs, whose deferred work remains visible in reports. Previews may also be completed runs.",
    )
    metrics[2].metric("Enabled schedules", sum(s.enabled for s in configured))
    metrics[3].metric("Scheduler", status)
    left, right = st.columns([1.65, 1])
    with left:
        with card(key="workspace_activity"):
            _section_heading(
                "Your workspace, over time",
                "Completed, deferred and failed runs stay distinguishable.",
                label="Activity / last 30 days",
            )
            if activity.empty:
                empty_state(
                    "A clearer picture with every run",
                    "Your first saved run will start this activity chart. No simulated activity is shown.",
                )
            else:
                figure = go.Figure()
                for label, rows in activity.groupby("status"):
                    figure.add_bar(
                        x=rows["day"],
                        y=rows["count"],
                        name=label.replace("_", " "),
                        marker_color=(
                            ACCENT
                            if label == "completed"
                            else (
                                "#bd8c49"
                                if label == "completed_with_warnings"
                                else "#be676b"
                            )
                        ),
                    )
                figure.update_layout(barmode="stack", bargap=0.4)
                days = activity["day"].drop_duplicates().tolist()
                figure.update_xaxes(
                    type="category",
                    tickmode="array",
                    tickvals=days,
                    ticktext=[pd.Timestamp(day).strftime("%d %b") for day in days],
                )
                figure.update_yaxes(dtick=1, title="Recorded runs")
                st.plotly_chart(
                    style_chart(figure, height=340),
                    use_container_width=True,
                    theme=None,
                    config={"displayModeBar": False},
                )
                st.caption(
                    "Last 30 days, UTC. A completed run is not a guarantee of investment performance."
                )
        with card(key="workspace_recent"):
            _section_heading(
                "Recent activity",
                "Reopen the report, not the strategy.",
                label="Saved evidence",
            )
            try:
                _run_list(recent_runs(limit=5), key="manage_recent")
            except READ_ERRORS as exc:
                _error("Cannot load recent runs", exc)
            page_button("Browse all saved reports", "history", key="manage_history")
    with right:
        with card(key="workspace_schedule"):
            _section_heading(
                "Your daily rhythm",
                "Automation with visibility and control.",
                label="Schedules",
            )
            (st.success if running else st.warning)(detail)
            if not configured:
                empty_state(
                    "Make a routine of it",
                    "No schedules configured. Set a time, choose a strategy, and inspect every recorded outcome.",
                )
            for schedule in configured:
                next_run = (
                    schedule.next_occurrence(datetime.now(timezone.utc))
                    if schedule.enabled
                    else None
                )
                st.markdown(f"**{schedule.name}**")
                st.caption(
                    f"{schedule.describe()} | "
                    + (
                        f"Next: {next_run:%d %b, %H:%M}"
                        if next_run
                        else "Paused / no upcoming occurrence"
                    )
                )
                if schedule.last_error:
                    st.error(f"Last run: {schedule.last_error}")
            page_button("Manage schedules", "schedules", key="manage_schedules")
        with card(key="workspace_validation"):
            st.subheader("Confidence before capital")
            st.caption(
                "Inspect historical returns, drawdowns, costs and trade logs. Keep backtests separate from forward books."
            )
            page_button("Open backtest lab", "backtests", key="manage_backtests")
            page_button("Settings & integrations", "settings", key="manage_settings")


def history_page() -> None:
    page_header(
        "Nothing important gets lost.",
        "Reopen saved results, inspect failures and download evidence without triggering a new run.",
    )
    requested = st.session_state.pop("_history_run_id", None)
    if requested:
        st.session_state["history_workflow"] = "All"
        st.session_state["_history_linked_run"] = requested
        st.session_state["history_selected_report"] = requested
    group, count = st.columns([2, 1])
    scope = group.selectbox(
        "Workflow",
        ["All", "Research", "Invest", "Backtests"],
        key="history_workflow",
        on_change=st.session_state.pop,
        args=("_history_linked_run", None),
    )
    limit = count.selectbox("Recent runs to show", [25, 50, 100, 250], index=1)
    ids = {
        "All": (),
        "Research": RESEARCH_IDS,
        "Invest": INVEST_IDS,
        "Backtests": BACKTEST_IDS,
    }[scope]
    try:
        rows = recent_runs(ids, limit=limit)
    except READ_ERRORS as exc:
        _error("Cannot load run history", exc)
        return
    target = st.session_state.get("_history_linked_run")
    if target:
        try:
            record = get_run(target)
        except READ_ERRORS as exc:
            _error("Cannot open the requested run", exc)
            return
        if record:
            # Deep links remain usable when the run is outside the recent window.
            rows = [record, *[r for r in rows if r["id"] != target]]
        else:
            st.warning("The requested saved report is no longer available.")
    if not rows:
        st.info("No saved runs for this workflow yet.")
        return
    frame = pd.DataFrame(rows)
    st.dataframe(
        frame[["strategy_id", "status", "created_at", "duration_ms"]].rename(
            columns={
                "strategy_id": "Strategy",
                "status": "Status",
                "created_at": "Recorded (UTC)",
                "duration_ms": "Duration (ms)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    by_id = {row["id"]: row for row in rows}
    selected = st.selectbox(
        "Open saved report",
        list(by_id),
        format_func=lambda key: f"{by_id[key]['strategy_id']} / {format_run_timestamp(by_id[key]['created_at'])} / {by_id[key]['status']} / {key[:6]}",
        key="history_selected_report",
    )
    try:
        record = get_run(selected)
        if record:
            st.caption(
                f"Saved {format_run_timestamp(record['created_at'])}. This is a historical result, not the current portfolio."
            )
            render_result(result_from_record(record))
            with st.expander("Run metadata"):
                st.json(
                    {
                        "id": record["id"],
                        "duration_ms": record["duration_ms"],
                        "parameters": record["params"],
                    }
                )
        else:
            st.error("This run is no longer available.")
    except READ_ERRORS as exc:
        _error("Cannot open this saved run", exc)
