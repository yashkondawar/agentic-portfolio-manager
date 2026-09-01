"""Shared workbench components and result renderers."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import registry
from core.run_history import get_run, list_runs, save_run
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


def latest_result(strategy_id: str, *, from_history: bool = True) -> StrategyResult | None:
    """Latest result for a strategy: this session's, else the newest saved run.

    The history fallback is what makes an overnight scheduled run visible when
    you open the app in the morning — the browser session that produced it does
    not exist any more.
    """
    raw = st.session_state.get("latest_results", {}).get(strategy_id)
    if raw:
        return StrategyResult(**raw)
    if not from_history:
        return None
    record = latest_run_record(strategy_id)
    return result_from_record(record) if record else None


def latest_run_record(strategy_id: str) -> dict | None:
    """Newest persisted run for a strategy, or ``None`` when it never ran."""
    try:
        rows = list_runs(limit=1, strategy_id=strategy_id)
        return get_run(rows[0]["id"]) if rows else None
    except Exception:
        return None


def result_from_record(record: dict) -> StrategyResult:
    return StrategyResult(
        strategy_id=record["strategy_id"],
        status=record["status"],
        report=record["report"],
        data=record["data"],
        error=record["error"],
    )


def format_run_timestamp(value: str | None) -> str:
    """Render a stored UTC timestamp in the viewer's local time."""
    if not value:
        return "unknown time"
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime("%d %b %Y, %H:%M")


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
    elif result.strategy_id == "gfs_live":
        _render_gfs_live(result.data)
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
            "gfs_live",
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
    if result.strategy_id == "gfs_live":
        # The actionable set is the queued buys, not the whole watchlist.
        return [
            str(order.get("symbol", ""))
            for order in data.get("orders", [])
            if order.get("action") == "BUY" and order.get("symbol")
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


# ── GFS (Grandfather / Father / Son) ─────────────────────────────────────────

_GFS_STATUS_LABELS = {
    "queued": "✅ Queued to buy",
    "already_held": "Held (already open)",
    "regime_closed": "Blocked — market regime closed",
    "sector_weak": "Blocked — sector outside the top N",
    "sector_cap": "Blocked — sector already at its cap",
    "portfolio_full": "Deferred — portfolio full",
    "ranked_out": "Ranked below today's winners",
}


def _gfs_unrealized(book: dict, holdings: list) -> float:
    """Book-level unrealised P&L, derived from the holdings when the payload
    predates the field — a run recorded before it existed must not read ₹0."""
    value = book.get("unrealized_pnl")
    if value is not None:
        return float(value)
    total = 0.0
    for row in holdings or []:
        pnl = row.get("unrealized_pnl")
        if pnl is None:
            entry, last = row.get("entry_price"), row.get("last_price")
            if entry is None or last is None:
                continue
            pnl = (float(last) - float(entry)) * float(row.get("quantity") or 0)
        total += float(pnl)
    return round(total, 2)


def _gfs_book_metrics(book: dict, holdings: list | None = None) -> None:
    cols = st.columns(6)
    cols[0].metric("Equity", _fmt_inr(book.get("equity")))
    cols[1].metric(
        "Deployed",
        _fmt_inr(book.get("deployed")),
        delta=f"{book.get('exposure_pct', 0)}% of book",
        delta_color="off",
    )
    cols[2].metric("Cash", _fmt_inr(book.get("cash")))
    cols[3].metric("Open positions", book.get("open_positions", 0))
    upnl = _gfs_unrealized(book, holdings or [])
    cols[4].metric("Unrealized P&L", _fmt_inr(upnl), delta=round(upnl, 0))
    rpnl = book.get("realized_pnl") or 0.0
    cols[5].metric("Realized P&L", _fmt_inr(rpnl), delta=round(float(rpnl), 0))
    total = book.get("total_return_pct")
    if total is not None:
        st.caption(
            f"Since inception ({book.get('opened_on') or '-'}): **{total:+.2f}%** on a "
            f"{_fmt_inr(book.get('starting_capital'))} starting book · "
            f"{book.get('closed_trades', 0)} closed trades."
        )


def _gfs_holdings_table(holdings: list, shadow: dict | None = None) -> None:
    if not holdings:
        st.caption("No open positions. The regime or the sector gate may be shut.")
        return
    cols = [
        "symbol", "sector", "quantity", "entry_date", "entry_price", "last_price",
        "unrealized_pnl", "unrealized_pct", "value", "stop_price", "target_price",
        "days_held", "rsi_d", "rsi_w", "rsi_m", "shadow_exit",
    ]
    frame = pd.DataFrame(holdings)
    frame = frame[[c for c in cols if c in frame.columns]]
    st.dataframe(frame, use_container_width=True, hide_index=True)
    if shadow and shadow.get("exit_rsi"):
        would = shadow.get("would_exit") or []
        threshold = shadow["exit_rsi"]
        if would:
            st.caption(
                f"🔍 **Shadow rule** — exiting at daily RSI {threshold:.0f} instead would "
                f"already be selling {', '.join(would)}. Reported only; the book did not act."
            )
        else:
            st.caption(
                f"🔍 **Shadow rule** — exiting at daily RSI {threshold:.0f} instead would "
                "not be selling anything right now."
            )


def _gfs_tradebook_table(tradebook: list) -> None:
    if not tradebook:
        st.caption("No closed trades yet — the tradebook fills as positions exit.")
        return
    cols = [
        "symbol", "sector", "entry_date", "exit_date", "holding_days", "quantity",
        "entry_price", "exit_price", "pnl", "pnl_pct", "r_multiple",
        "entry_rsi", "exit_rsi", "exit_reason",
    ]
    frame = pd.DataFrame(tradebook)
    frame = frame[[c for c in cols if c in frame.columns]]
    st.dataframe(frame, use_container_width=True, hide_index=True)
    wins = [t for t in tradebook if (t.get("pnl") or 0) > 0]
    stats = st.columns(3)
    stats[0].metric("Closed trades", len(tradebook))
    stats[1].metric("Win rate", f"{len(wins) / len(tradebook) * 100:.0f}%")
    stats[2].metric(
        "Total realized P&L", _fmt_inr(sum(t.get("pnl") or 0 for t in tradebook))
    )


def render_gfs_ledger_snapshot() -> None:
    """Always-on book view, read straight from the DB — no network, no rerun."""
    from gfs import engine as gfs_engine

    try:
        snap = gfs_engine.ledger_snapshot()
    except Exception as exc:  # noqa: BLE001 - never let the snapshot break the page
        st.info(f"No GFS book to show yet ({exc}).")
        return

    if not snap.get("as_of"):
        st.info(
            "The GFS book has not been created yet. Run the strategy below — it "
            "starts flat from today, or backfills from a date you choose."
        )
        return

    st.markdown("### 📁 GFS book")
    st.caption(
        f"Saved state as of the **{snap['as_of']}** close. Positions are marked at "
        "the close the last run saw — not a live quote. Run the strategy to bring "
        "the book up to date."
    )
    stale = snap.get("freshness") or {}
    if stale.get("stale"):
        st.warning(
            f"This book is **{stale.get('weekdays_behind')} weekdays** behind "
            f"({stale.get('last_session')} vs {stale.get('today')}). Marks, "
            "stops and the shadow exit are all computed off that old close, so "
            "treat them as history until you run the strategy."
        )
    _gfs_book_metrics(snap.get("book") or {}, snap.get("holdings") or [])
    pending_orders = snap.get("orders") or []
    if pending_orders:
        st.markdown("#### 🎯 Orders waiting for the next open")
        st.warning(
            f"**{len(pending_orders)} order(s) queued.** Place these at the next "
            "session's open, then run the strategy after that close so the book "
            "records the fill. GFS never fills on the bar that produced the "
            "signal, so waiting for these to appear in Holdings before buying "
            "would put you a session late."
        )
        _gfs_orders_tables(pending_orders)
    elif snap.get("pending"):
        st.warning(
            f"{snap['pending']} order(s) are queued for the next open. Run the "
            "strategy after the close to fill them."
        )
    st.markdown("#### Holdings")
    _gfs_holdings_table(snap.get("holdings") or [], snap.get("shadow"))
    with st.expander(
        f"📒 Tradebook — {snap.get('num_closed', 0)} closed trades", expanded=False
    ):
        _gfs_tradebook_table(snap.get("tradebook") or [])


def _gfs_orders_tables(orders: list) -> None:
    """The only actionable section, rendered identically whether it comes from a
    fresh run or from the queue persisted in the saved book. A count alone is
    useless: you cannot place an order you cannot see."""
    for label, kind, columns in (
        (
            "🟢 Buy",
            "BUY",
            ["symbol", "sector", "quantity", "reference_price", "stop_price",
             "rsi_m", "rsi_w", "rsi_d", "resistance"],
        ),
        (
            "🔴 Sell",
            "SELL",
            ["symbol", "sector", "quantity", "reference_price", "reason"],
        ),
    ):
        rows = [o for o in orders if o.get("action") == kind]
        if not rows:
            continue
        st.markdown(f"**{label}** ({len(rows)})")
        frame = pd.DataFrame(rows)
        st.dataframe(
            frame[[c for c in columns if c in frame.columns]],
            use_container_width=True,
            hide_index=True,
        )
    if any(o.get("action") == "BUY" for o in orders):
        st.caption(
            "Quantities are indicative. The engine re-derives the stop and the "
            "size from the actual opening print, so an overnight gap changes the "
            "size rather than silently changing the risk."
        )


def _render_gfs_live(data: dict) -> None:
    # 0) Stale data outranks everything else on the page: if the newest close is
    #    days old, every order below is priced off the wrong bar.
    fresh = data.get("freshness") or {}
    if fresh.get("stale"):
        st.error(
            f"**Stale price data — do not place these orders.** The newest "
            f"session available is **{fresh.get('last_session')}**, "
            f"{fresh.get('weekdays_behind')} weekdays behind "
            f"{fresh.get('today')}. Every order below is priced off that stale "
            "close, so filling it at the next open is not the trade the "
            "strategy tested. Refresh the bar store and re-run."
        )

    # 1) Where the book stands after this run.
    st.markdown("### 📁 Book after this run")
    if data.get("dry_run"):
        st.warning("Dry run — nothing was saved to the database.")
    as_of = data.get("as_of")
    replayed = len(data.get("sessions_replayed") or [])
    if data.get("up_to_date"):
        st.info(
            "Already up to date — no new trading session since the last run. "
            "Showing the saved book."
        )
    elif as_of:
        st.caption(
            f"Marked to the **{as_of}** close · {replayed} session(s) replayed since "
            "the last run."
        )
    _gfs_book_metrics(data.get("book") or {}, data.get("holdings") or [])

    # 2) The regime banner — the single gate that decides whether GFS trades.
    diag = data.get("diagnostics") or {}
    if diag.get("regime_ok") is not None:
        breadth = diag.get("breadth_pct")
        floor = diag.get("min_breadth_pct")
        if diag["regime_ok"]:
            st.success(
                f"🟢 **Market regime open** — breadth {breadth}% of the universe is "
                f"above its 200-DMA (needs ≥ {floor}%). New entries are allowed."
            )
        else:
            st.error(
                f"🔴 **Market regime closed** — breadth {breadth}% is below the "
                f"{floor}% floor. No new entries; open positions are still managed."
            )

    # 3) The only thing to execute: orders for the next open.
    orders = data.get("orders") or []
    st.markdown("### 🎯 Orders for the next open")
    st.caption(
        "GFS never fills on the bar that produced the signal. These are placed at "
        "the **next** session's open — the same timing the backtest was measured on."
    )
    if not orders:
        st.caption("Nothing to place. Hold what you have.")
    else:
        _gfs_orders_tables(orders)

    # 4) What the replay already executed since the previous run.
    fills = data.get("fills") or []
    if fills:
        with st.expander(f"✅ Filled since the last run ({len(fills)})", expanded=True):
            frame = pd.DataFrame(fills)
            cols = ["date", "action", "symbol", "quantity", "price", "detail"]
            st.dataframe(
                frame[[c for c in cols if c in frame.columns]],
                use_container_width=True,
                hide_index=True,
            )

    # 5) Holdings + the shadow-exit reading.
    st.markdown("### 📊 Holdings")
    _gfs_holdings_table(data.get("holdings") or [], data.get("shadow"))

    # 6) The top-down funnel, universe -> order.
    funnel = data.get("funnel") or []
    if funnel:
        st.markdown("### 🔻 Top-down funnel")
        fcols = st.columns(len(funnel))
        for idx, stage in enumerate(funnel):
            dropped = stage.get("dropped") or 0
            fcols[idx].metric(
                stage["stage"],
                stage.get("count", 0),
                delta=(f"-{dropped}" if dropped else None),
                delta_color="inverse",
            )

    watchlist = data.get("watchlist") or []
    if watchlist:
        with st.expander(
            f"🔎 {len(watchlist)} name(s) met the GFS condition today — and why each "
            "did or did not become an order",
            expanded=False,
        ):
            frame = pd.DataFrame(watchlist)
            if "status" in frame.columns:
                frame["outcome"] = frame["status"].map(
                    lambda s: _GFS_STATUS_LABELS.get(s, s)
                )
            cols = [
                "symbol", "sector", "sector_rank", "close", "rsi_m", "rsi_w", "rsi_d",
                "headroom_pct", "resistance", "outcome",
            ]
            st.dataframe(
                frame[[c for c in cols if c in frame.columns]],
                use_container_width=True,
                hide_index=True,
            )

    # 7) Track record.
    metrics = data.get("metrics") or {}
    if metrics.get("num_trades"):
        st.markdown("### 📈 Track record")
        cols = st.columns(5)
        cols[0].metric("Win rate", _pct(metrics.get("win_rate_pct")))
        cols[1].metric("Payoff ratio", metrics.get("payoff_ratio", "-"))
        cols[2].metric("Expectancy", f"{metrics.get('expectancy_r', 0)}R")
        cols[3].metric("Avg hold", f"{metrics.get('avg_holding_days', 0)}d")
        cols[4].metric("Max drawdown", _pct(metrics.get("max_drawdown_pct")))
        if metrics.get("cagr_pct") is not None:
            st.caption(
                f"CAGR {metrics['cagr_pct']}% · Sharpe {metrics.get('sharpe')} · "
                f"avg exposure {metrics.get('avg_exposure_pct')}% over "
                f"{metrics.get('years')} years."
            )
        else:
            st.caption(
                "The book is too young for an annualised figure — CAGR is withheld "
                "until it has at least 90 days of history."
            )

    curve = data.get("equity_curve") or []
    if len(curve) > 2:
        frame = pd.DataFrame(curve)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=pd.to_datetime(frame["date"]),
                y=frame["equity"],
                name="Equity",
                mode="lines",
            )
        )
        fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=30, b=10),
            title="Book equity",
        )
        st.plotly_chart(fig, use_container_width=True)

    with st.expander(f"📒 Tradebook — {len(data.get('tradebook') or [])} closed trades"):
        _gfs_tradebook_table(data.get("tradebook") or [])

    # 8) Diagnostics and the exact configuration that produced all of the above.
    rejections = diag.get("rejections") or {}
    config = data.get("config") or {}
    if rejections or config:
        with st.expander("⚙️ Diagnostics and configuration", expanded=False):
            if rejections:
                st.markdown("**Why candidates were turned away this run**")
                st.dataframe(
                    pd.DataFrame(
                        [{"reason": k, "count": v} for k, v in rejections.items()]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            if config:
                st.markdown("**Configuration**")
                st.dataframe(
                    pd.DataFrame(
                        [{"setting": k, "value": str(v)} for k, v in config.items()]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            note = diag.get("universe_note")
            if note:
                st.caption(note)


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
