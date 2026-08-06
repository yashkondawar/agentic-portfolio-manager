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

    if result.strategy_id == "swing_backtest":
        _render_backtest(result.data)
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


def _fmt_inr(value: Any) -> str:
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return "-"


def _portfolio_metrics(data: dict) -> None:
    cols = st.columns(5)
    cols[0].metric("Open positions", data.get("num_open", 0))
    cols[1].metric("Invested", _fmt_inr(data.get("invested")))
    cols[2].metric("Cash", _fmt_inr(data.get("cash")))
    upnl = data.get("unrealized_pnl") or 0.0
    cols[3].metric("Unrealized P&L", _fmt_inr(upnl), delta=round(float(upnl), 0))
    rpnl = data.get("realized_pnl") or 0.0
    cols[4].metric("Realized P&L", _fmt_inr(rpnl), delta=round(float(rpnl), 0))


def _holdings_table(holdings: list) -> None:
    if not holdings:
        st.caption("No open positions.")
        return
    cols = [
        "symbol", "company", "quantity", "entry_price", "last_price",
        "invested", "market_value", "unrealized_pnl", "unrealized_pct",
        "stop_price", "target_price", "days_held", "conviction",
    ]
    frame = pd.DataFrame(holdings)
    frame = frame[[c for c in cols if c in frame.columns]]
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _tradebook_table(tradebook: list) -> None:
    if not tradebook:
        st.caption("No closed trades yet — the tradebook fills as positions exit.")
        return
    cols = [
        "symbol", "company", "entry_date", "exit_date", "days_held",
        "quantity", "entry_price", "exit_price", "invested",
        "realized_pnl", "realized_pct", "exit_reason",
    ]
    frame = pd.DataFrame(tradebook)
    frame = frame[[c for c in cols if c in frame.columns]]
    st.dataframe(frame, use_container_width=True, hide_index=True)
    wins = [t for t in tradebook if (t.get("realized_pnl") or 0) > 0]
    total = sum(t.get("realized_pnl") or 0 for t in tradebook)
    cols = st.columns(3)
    cols[0].metric("Closed trades", len(tradebook))
    cols[1].metric(
        "Win rate",
        f"{(len(wins) / len(tradebook) * 100):.0f}%" if tradebook else "-",
    )
    cols[2].metric("Total realized P&L", _fmt_inr(total))


def render_qtr_ledger_snapshot() -> None:
    """Always-on portfolio + tradebook view, read straight from the ledger on disk.

    Renders on page load without running the strategy (no network / no LLM), so the
    user can see their current holdings and trade history at any time.
    """
    from qtr_results import engine as qtr_engine

    try:
        snap = qtr_engine.ledger_snapshot()
    except Exception as exc:  # noqa: BLE001 - never let the snapshot break the page
        st.info(f"No ledger to show yet ({exc}).")
        return

    st.markdown("### 📁 Current portfolio")
    st.caption(
        "Live ledger state on disk — shown on every page load, marked at the last "
        "run's prices. Run the strategy below to refresh."
    )
    _portfolio_metrics(snap)
    st.markdown("#### Holdings")
    _holdings_table(snap.get("holdings") or [])
    with st.expander(
        f"📒 Tradebook — {snap.get('num_closed', 0)} closed trades", expanded=False
    ):
        _tradebook_table(snap.get("tradebook") or [])


_FUNNEL_STATUS_LABELS = {
    "BUY": "✅ BUY (new position)",
    "already_held": "Held (already open)",
    "deferred_cap": "Deferred — portfolio full",
    "no_cash": "Skipped — no cash",
    "no_price": "Skipped — no price",
    "no_plan": "Skipped — no plan",
    "llm_rejected": "❌ LLM rejected",
    "filtered_pre_llm": "Filtered — liquidity/uptrend",
    "weak_fundamentals": "Rejected — weak fundamentals",
    "data_error": "Errored — data gap",
    "strong_fundamentals": "Strong (pending gate)",
    "qualified": "Qualified",
}


def _render_quarterly_results(data: dict) -> None:
    # 1) Portfolio snapshot (post-run state of the ledger / holdings).
    st.markdown("### 📁 Portfolio after this run")
    _portfolio_metrics(data)
    _holdings_table(data.get("holdings") or [])

    # 2) Today's actions — the only thing the user needs to execute.
    actions = data.get("actions") or []
    st.markdown("### 🎯 Today's actions")
    if not actions:
        st.caption("No buy/sell actions today. Existing positions (if any) are held.")
    else:
        for label, kind in (("🟢 Buy", "BUY"), ("🔴 Sell", "SELL"), ("⚪ Hold", "HOLD")):
            rows = [a for a in actions if a.get("action") == kind]
            if not rows:
                continue
            st.markdown(f"**{label}** ({len(rows)})")
            frame = pd.DataFrame(rows)
            cols = [c for c in ["symbol", "company", "quantity", "price", "value",
                                "stop_price", "target_price", "detail"]
                    if c in frame.columns]
            st.dataframe(frame[cols], use_container_width=True, hide_index=True)

    # 3) Filtering funnel — how the day's declarers narrowed to the buys.
    funnel = data.get("funnel") or []
    st.markdown("### 🔻 Filtering funnel")
    if funnel:
        fcols = st.columns(len(funnel))
        for idx, stage in enumerate(funnel):
            dropped = stage.get("dropped") or 0
            fcols[idx].metric(
                stage["stage"],
                stage.get("count", 0),
                delta=(f"-{dropped} dropped" if dropped else None),
                delta_color="inverse",
            )
    analysed = data.get("analysed") or []
    if analysed:
        with st.expander(
            f"🔎 All {len(analysed)} analysed stocks — where each dropped",
            expanded=False,
        ):
            frame = pd.DataFrame(analysed)
            if "status" in frame.columns:
                frame["outcome"] = frame["status"].map(
                    lambda s: _FUNNEL_STATUS_LABELS.get(s, s)
                )
            cols = [c for c in ["symbol", "company", "result_date", "strength",
                                "stage", "outcome", "reason"] if c in frame.columns]
            st.dataframe(frame[cols], use_container_width=True, hide_index=True)

    # 4) Tradebook (closed trades) + upcoming heads-up.
    with st.expander(
        f"📒 Tradebook — {len(data.get('tradebook') or [])} closed trades",
        expanded=False,
    ):
        _tradebook_table(data.get("tradebook") or [])
    upcoming = data.get("upcoming") or []
    if upcoming:
        with st.expander(f"📅 Upcoming results ({len(upcoming)})", expanded=False):
            st.dataframe(
                pd.DataFrame(upcoming), use_container_width=True, hide_index=True
            )


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
