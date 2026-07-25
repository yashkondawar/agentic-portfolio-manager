"""Shared workbench components and result renderers."""

from __future__ import annotations

import json
import time
from typing import Any, Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import registry
from core.run_history import save_run
from core.strategy import StrategyResult


def page_header(title: str, description: str) -> None:
    st.title(title)
    st.caption(description)


def run_strategy(strategy_id: str, params: dict) -> StrategyResult:
    started = time.perf_counter()
    with st.status(
        f"Running {strategy_id.replace('_', ' ')}...", expanded=True
    ) as status:
        st.write("Preparing inputs and dependencies")
        result = registry.run_strategy(strategy_id, params)
        duration_ms = int((time.perf_counter() - started) * 1000)
        run_id = save_run(result, params, duration_ms=duration_ms)
        st.session_state["latest_results"][strategy_id] = result.to_dict()
        st.session_state["latest_run_id"] = run_id
        if result.ok:
            status.update(label="Run completed", state="complete", expanded=False)
        else:
            status.update(label="Run failed", state="error", expanded=True)
    return result


def latest_result(strategy_id: str) -> StrategyResult | None:
    raw = st.session_state.get("latest_results", {}).get(strategy_id)
    return StrategyResult(**raw) if raw else None


def render_result(result: StrategyResult, *, heading: bool = True) -> None:
    if heading:
        st.subheader("Results")
    if not result.ok:
        st.error(result.error or result.report or "Strategy failed")
        return

    if result.strategy_id in {"swing_backtest", "breakout_52w_backtest"}:
        _render_backtest(result.data)
    elif result.strategy_id == "breakout_52w_daily":
        _render_breakout_daily(result.data)
    elif result.strategy_id == "parallel_agents":
        _render_decisions(result.data.get("decisions", {}))
    elif result.strategy_id == "watchlist_curation":
        _render_watchlist(result.data)
    elif result.strategy_id == "qtr_results":
        _render_quarterly_results(result.data)
    else:
        _render_summary_data(result.data)

    with st.expander(
        "Full report",
        expanded=result.strategy_id
        not in {
            "swing_backtest",
            "breakout_52w_backtest",
            "parallel_agents",
            "watchlist_curation",
            "qtr_results",
        },
    ):
        st.markdown(result.report or "_No report returned._")
    _render_downloads(result)


def result_symbols(result: StrategyResult) -> list[str]:
    data = result.data
    if result.strategy_id == "watchlist_curation":
        return [
            str(item.get("symbol", ""))
            for item in data.get("picks", [])
            if item.get("symbol")
        ]
    if result.strategy_id == "qtr_results":
        return [
            str(item.get("symbol", ""))
            for item in data.get("new_picks", [])
            if item.get("symbol")
        ]
    if result.strategy_id == "parallel_agents":
        return list(data.get("decisions", {}))
    if result.strategy_id == "breakout_52w_daily":
        return [
            str(item["symbol"])
            for item in data.get("new_entries", [])
            if item.get("symbol")
        ]
    return list(data.get("symbols", []))


def clean_editor_rows(rows: Any, required: Iterable[str]) -> list[dict]:
    if isinstance(rows, pd.DataFrame):
        records = rows.to_dict("records")
    else:
        records = list(rows or [])
    required_fields = tuple(required)
    cleaned = []
    for record in records:
        symbol = str(record.get("symbol", "") or "").strip().upper().replace(".NS", "")
        if not symbol:
            continue
        item = {
            key: (None if pd.isna(value) else value) for key, value in record.items()
        }
        item["symbol"] = symbol
        if all(item.get(field) not in (None, "") for field in required_fields):
            cleaned.append(item)
    return cleaned


def _render_decisions(decisions: dict) -> None:
    rows = [{"symbol": symbol, **values} for symbol, values in decisions.items()]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_watchlist(data: dict) -> None:
    st.metric("Screening stage", data.get("stage", "-"))
    rows = data.get("picks") or data.get("shortlist") or []
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_quarterly_results(data: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Declarers", data.get("num_declarers", 0))
    cols[1].metric("Strong results", data.get("num_strong", 0))
    cols[2].metric("New picks", data.get("num_new_picks", 0))
    cols[3].metric("Open picks", data.get("num_open", 0))
    for title, key in (
        ("New picks", "new_picks"),
        ("Closed this run", "closed"),
        ("Upcoming results", "upcoming"),
    ):
        rows = data.get(key) or []
        if rows:
            st.markdown(f"#### {title}")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_breakout_daily(data: dict) -> None:
    first = st.columns(4)
    first[0].metric("As of", data.get("as_of", "-"))
    first[1].metric(
        "Market regime",
        "Longs enabled" if data.get("regime_allows_entries") else "No new longs",
    )
    first[2].metric("Portfolio equity", f"₹{data.get('portfolio_equity', 0):,.0f}")
    first[3].metric("Open risk", _pct(data.get("open_risk_pct")))
    second = st.columns(3)
    second[0].metric("Open positions", data.get("open_positions", 0))
    second[1].metric("Pending entries", data.get("pending_entries_count", 0))
    second[2].metric("Universe scanned", data.get("universe_size", 0))

    for title, key in (
        ("Position actions", "position_actions"),
        ("New entries for next open", "new_entries"),
        ("Pending for next open", "pending_entries"),
        ("Filled from prior signals", "filled_entries"),
        ("Lapsed or rejected entries", "rejected_entries"),
    ):
        rows = data.get(key) or []
        if rows:
            st.markdown(f"#### {title}")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_backtest(data: dict) -> None:
    metrics = data.get("metrics", {})
    first = st.columns(4)
    first[0].metric("Total return", _pct(metrics.get("total_return_pct")))
    first[1].metric("CAGR", _pct(metrics.get("cagr_pct")))
    first[2].metric("Max drawdown", _pct(metrics.get("max_drawdown_pct")))
    first[3].metric("Sharpe", metrics.get("sharpe", "-"))
    second = st.columns(4)
    second[0].metric("Trades", metrics.get("num_trades", 0))
    second[1].metric("Win rate", _pct(metrics.get("win_rate_pct")))
    second[2].metric("Profit factor", metrics.get("profit_factor") or "-")
    second[3].metric(
        "Goal",
        "Reached" if metrics.get("goal_reached") else "Not reached",
    )

    curve = pd.DataFrame(data.get("equity_curve") or [])
    if not curve.empty:
        curve["date"] = pd.to_datetime(curve["date"])
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=curve["date"],
                y=curve["equity"],
                name="Equity",
                line={"color": "#4f7cff", "width": 2},
            )
        )
        figure.add_hline(
            y=metrics.get("goal_capital", 0),
            line_dash="dash",
            line_color="#22a06b",
            annotation_text="Goal",
        )
        figure.update_layout(
            height=420,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
            yaxis_title="Portfolio value (₹)",
        )
        st.plotly_chart(figure, use_container_width=True)

    trades = data.get("trades") or []
    if trades:
        st.markdown("#### Closed trades")
        st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)
    positions = data.get("open_positions") or []
    if positions:
        st.markdown("#### Open at end date")
        st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)


def _render_summary_data(data: dict) -> None:
    scalar = {
        key: value
        for key, value in data.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    if scalar:
        cols = st.columns(min(4, len(scalar)))
        for index, (key, value) in enumerate(scalar.items()):
            cols[index % len(cols)].metric(key.replace("_", " ").title(), value)


def _render_downloads(result: StrategyResult) -> None:
    col1, col2 = st.columns(2)
    col1.download_button(
        "Download report",
        data=result.report,
        file_name=f"{result.strategy_id}_report.md",
        mime="text/markdown",
        use_container_width=True,
    )
    col2.download_button(
        "Download structured data",
        data=json.dumps(result.to_dict(), indent=2, default=str),
        file_name=f"{result.strategy_id}_result.json",
        mime="application/json",
        use_container_width=True,
    )


def _pct(value: Any) -> str:
    return "-" if value is None else f"{float(value):.2f}%"
