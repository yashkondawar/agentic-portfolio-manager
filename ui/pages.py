"""Task-oriented pages for the trader workbench."""

from __future__ import annotations

import io
import json
import os
import shutil
from datetime import datetime
from importlib.util import find_spec

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import registry
from core.run_history import get_run, list_runs
from core.strategy import StrategyResult
from ui.components import (
    clean_editor_rows,
    latest_result,
    page_header,
    render_gfs_ledger_snapshot,
    render_qtr_ledger_snapshot,
    render_result,
    result_symbols,
    run_strategy,
)
from ui.forms import render_strategy_params
from ui.market_temperature import market_temperature_page
from ui.state import add_symbols, clear_symbols

__all__ = [
    "backtest_page",
    "broker_page",
    "dashboard_page",
    "discover_page",
    "kronos_page",
    "market_temperature_page",
    "portfolio_page",
    "research_page",
    "settings_page",
    "swing_page",
]


def dashboard_page() -> None:
    page_header(
        "Trader Workbench",
        "Discover, research, manage, and validate Indian-equity ideas from one place.",
    )
    st.info(
        "Decision-support mode is active. This application never places broker orders."
    )

    broker_holdings = st.session_state.get("broker_holdings", [])
    recent = list_runs(limit=10)
    basket = st.session_state.get("symbol_basket", [])
    cards = st.columns(4)
    cards[0].metric("Strategies", len(registry.list_specs()))
    cards[1].metric("Idea basket", len(basket))
    cards[2].metric("Broker holdings", len(broker_holdings))
    cards[3].metric("Recent runs", len(recent))

    st.subheader("Daily workflow")
    workflow = st.columns(4)
    workflow[0].markdown("**1. Discover**\n\nBuild a watchlist or scan fresh results.")
    workflow[1].markdown("**2. Research**\n\nRun multi-agent conviction checks.")
    workflow[2].markdown("**3. Review risk**\n\nManage swing and portfolio exposure.")
    workflow[3].markdown("**4. Validate**\n\nBacktest the deterministic playbook.")

    st.subheader("Shared idea basket")
    if basket:
        st.write(" · ".join(basket))
        if st.button("Clear basket"):
            clear_symbols()
            st.rerun()
    else:
        st.caption("Ideas selected on Discover or Research pages appear here.")

    st.subheader("Recent runs")
    if not recent:
        st.caption("No workbench runs have been recorded yet.")
        return
    table = pd.DataFrame(recent)
    table["created_at"] = pd.to_datetime(table["created_at"]).dt.strftime(
        "%Y-%m-%d %H:%M"
    )
    st.dataframe(
        table[["strategy_id", "status", "created_at", "duration_ms"]],
        use_container_width=True,
        hide_index=True,
    )
    labels = {
        f"{row['strategy_id']} · {row['created_at'][:19]} · {row['status']}": row["id"]
        for row in recent
    }
    selected = st.selectbox("Reopen a run", [""] + list(labels), index=0)
    if selected:
        record = get_run(labels[selected])
        if record:
            render_result(
                StrategyResult(
                    strategy_id=record["strategy_id"],
                    status=record["status"],
                    report=record["report"],
                    data=record["data"],
                    error=record["error"],
                )
            )


def discover_page() -> None:
    page_header(
        "Discover Ideas",
        "Screen broad universes, monitor fresh quarterly-result catalysts, and "
        "track the GFS multi-timeframe book.",
    )
    watchlist_tab, results_tab, gfs_tab = st.tabs(
        ["Watchlist builder", "Quarterly results", "GFS multi-timeframe"]
    )
    with watchlist_tab:
        _registry_runner("watchlist_curation", "discover_watchlist")
        _basket_action(latest_result("watchlist_curation"), "watchlist")
    with results_tab:
        render_qtr_ledger_snapshot()
        st.divider()
        _registry_runner("qtr_results", "discover_results")
        _basket_action(latest_result("qtr_results"), "quarterly")
    with gfs_tab:
        st.caption(
            "Grandfather (monthly RSI) and Father (weekly RSI) confirm the trend "
            "while the Son (daily RSI) pulls back. Run it **after the market "
            "closes**: it replays every session since the last run and tells you "
            "what to place at the next open."
        )
        render_gfs_ledger_snapshot()
        st.divider()
        _registry_runner("gfs_live", "discover_gfs")
        _basket_action(latest_result("gfs_live"), "gfs")


def research_page() -> None:
    page_header(
        "Stock Research",
        "Choose parallel specialist coverage or the classic sequential supervisor.",
    )
    strategy_id = st.radio(
        "Research system",
        ["parallel_agents", "sequential_agents"],
        format_func=lambda value: registry.get_strategy(value).name,
        horizontal=True,
    )
    strategy = registry.get_strategy(strategy_id)
    defaults = {}
    if strategy_id == "parallel_agents":
        defaults["symbols"] = st.session_state.get("symbol_basket", [])
    with st.form(f"research_form_{strategy_id}"):
        params = render_strategy_params(
            strategy.param_specs(),
            key_prefix=f"research_{strategy_id}",
            defaults=defaults,
        )
        submitted = st.form_submit_button(
            "Run stock research", type="primary", use_container_width=True
        )
    if submitted:
        result = run_strategy(strategy_id, params)
    else:
        result = latest_result(strategy_id)
    if result:
        render_result(result)
        _basket_action(result, f"research_{strategy_id}")
        if strategy_id == "parallel_agents" and result.ok:
            _render_proposed_orders(
                result,
                float(params.get("portfolio_value") or 1_000_000),
            )


def swing_page() -> None:
    page_header(
        "Swing Desk",
        "Review open trades, evaluate the shared watchlist, and rotate capital.",
    )
    source = st.radio(
        "Position source",
        ["Manual editor", "Zerodha snapshot", "Upload JSON/CSV"],
        horizontal=True,
    )
    positions = _position_source(source)
    if source != "Zerodha snapshot":
        edited = st.data_editor(
            pd.DataFrame(positions),
            num_rows="dynamic",
            use_container_width=True,
            key="swing_position_editor",
        )
        positions = clean_editor_rows(edited, ("quantity", "buy_price"))
        if source == "Manual editor":
            st.session_state["manual_positions"] = positions
    elif positions:
        st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)

    strategy = registry.get_strategy("swing_trading")
    defaults = {"watchlist": st.session_state.get("symbol_basket", [])}
    with st.form("swing_strategy_form"):
        params = render_strategy_params(
            strategy.param_specs(),
            key_prefix="swing",
            exclude={"positions"},
            defaults=defaults,
        )
        submitted = st.form_submit_button(
            "Run swing review", type="primary", use_container_width=True
        )
    if submitted:
        params["positions"] = positions
        result = run_strategy("swing_trading", params)
    else:
        result = latest_result("swing_trading")
    if result:
        render_result(result)


def portfolio_page() -> None:
    page_header(
        "Portfolio Review",
        "Analyze concentration, risk, conviction, and concrete rebalancing actions.",
    )
    source = st.radio(
        "Holdings source",
        ["Manual editor", "Zerodha snapshot", "Upload JSON/CSV"],
        horizontal=True,
    )
    holdings = _holding_source(source)
    if source != "Zerodha snapshot":
        edited = st.data_editor(
            pd.DataFrame(holdings),
            num_rows="dynamic",
            use_container_width=True,
            key="portfolio_holding_editor",
        )
        holdings = clean_editor_rows(edited, ("quantity", "buy_price"))
        if source == "Manual editor":
            st.session_state["manual_holdings"] = holdings
    elif holdings:
        st.dataframe(pd.DataFrame(holdings), use_container_width=True, hide_index=True)

    if holdings:
        total_cost = sum(
            float(row["quantity"]) * float(row["buy_price"]) for row in holdings
        )
        current = sum(
            float(row["quantity"]) * float(row.get("last_price") or row["buy_price"])
            for row in holdings
        )
        summary = st.columns(3)
        summary[0].metric("Holdings", len(holdings))
        summary[1].metric("Cost basis", f"₹{total_cost:,.0f}")
        summary[2].metric("Current value", f"₹{current:,.0f}")

    strategy = registry.get_strategy("portfolio_analysis")
    with st.form("portfolio_strategy_form"):
        params = render_strategy_params(
            strategy.param_specs(),
            key_prefix="portfolio",
            exclude={"holdings"},
        )
        submitted = st.form_submit_button(
            "Run portfolio review", type="primary", use_container_width=True
        )
    if submitted:
        params["holdings"] = holdings
        result = run_strategy("portfolio_analysis", params)
    else:
        result = latest_result("portfolio_analysis")
    if result:
        render_result(result)


def backtest_page() -> None:
    page_header(
        "Backtest Lab",
        "Validate the swing playbook with point-in-time data and next-session fills.",
    )
    st.warning(
        "Historical results include modeled costs but do not guarantee future returns."
    )
    _registry_runner("swing_backtest", "backtest")


def broker_page() -> None:
    page_header(
        "Broker & Holdings",
        "Connect Zerodha for read-only holdings, positions, margins, and order status.",
    )
    st.success("Read-only boundary: this page cannot place, modify, or cancel orders.")
    try:
        broker = _broker()
    except Exception as exc:
        message = str(exc)
        if "Zerodha API key and secret required" in message:
            st.error("Kite Connect app credentials are not available to this app.")
            st.info(
                "The API key and secret are a one-time Kite Connect app "
                "configuration, separate from your daily browser login. Copy your "
                "existing `.env` into this worktree or set `ZERODHA_API_KEY` and "
                "`ZERODHA_API_SECRET` in the environment, then rerun the app."
            )
            st.code(
                "ZERODHA_API_KEY=your_kite_app_key\n"
                "ZERODHA_API_SECRET=your_kite_app_secret\n"
                "ZERODHA_CALLBACK_PORT=5678",
                language="text",
            )
            st.caption(
                "After that one-time setup, **Connect Zerodha in browser** opens "
                "Kite and completes the daily login automatically."
            )
        else:
            st.error(message)
        return

    if not broker.is_authenticated:
        st.warning("Zerodha is not authenticated for today.")
        st.caption(
            "The login opens in your browser and completes through the local "
            "Kite callback; no request token needs to be pasted."
        )
        if st.button("Connect Zerodha in browser", type="primary"):
            try:
                with st.spinner("Waiting for Zerodha browser login..."):
                    authenticated = broker.authenticate_in_browser()
                if authenticated:
                    st.success("Zerodha authenticated.")
                    st.rerun()
                else:
                    st.error("Authentication failed.")
            except Exception as exc:
                st.error(f"Zerodha login failed: {exc}")
        return

    st.success("Authenticated for the current trading day.")
    if st.button("Refresh broker snapshot", type="primary"):
        try:
            st.session_state["broker_profile"] = broker.profile()
            st.session_state["broker_cash"] = broker.available_cash()
            st.session_state["broker_holdings"] = broker.holdings_for_strategy()
            st.session_state["broker_positions"] = broker.positions_for_strategy()
            st.session_state["broker_orders"] = broker.orders()
            st.session_state["broker_refreshed_at"] = datetime.now().isoformat()
        except Exception as exc:
            st.error(f"Broker refresh failed: {exc}")

    holdings = st.session_state.get("broker_holdings", [])
    positions = st.session_state.get("broker_positions", [])
    orders = st.session_state.get("broker_orders", [])
    snapshot = st.columns(4)
    snapshot[0].metric(
        "Available cash", f"₹{st.session_state.get('broker_cash', 0):,.0f}"
    )
    snapshot[1].metric("Holdings", len(holdings))
    snapshot[2].metric("Open positions", len(positions))
    snapshot[3].metric("Today's orders", len(orders))
    refreshed = st.session_state.get("broker_refreshed_at")
    if refreshed:
        st.caption(f"Snapshot refreshed {refreshed[:19].replace('T', ' ')}")
    for title, rows in (
        ("Holdings", holdings),
        ("Open positions", positions),
        ("Today's orders", orders),
    ):
        if rows:
            st.subheader(title)
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def settings_page() -> None:
    page_header(
        "Settings & Strategy Catalog",
        "Configure local integrations and inspect every available strategy control.",
    )
    from core.llm import DEFAULT_COPILOT_MODEL

    copilot_model = os.getenv("COPILOT_MODEL", "").strip() or DEFAULT_COPILOT_MODEL
    readiness = [
        {
            "Capability": "GitHub Copilot CLI",
            "Status": "Ready" if shutil.which("copilot") else "Not found",
        },
        {
            "Capability": "GitHub Copilot SDK",
            "Status": "Ready" if find_spec("copilot") else "Not installed",
        },
        {
            "Capability": "Copilot model",
            "Status": copilot_model,
        },
        {
            "Capability": "Zerodha credentials",
            "Status": (
                "Ready"
                if os.getenv("ZERODHA_API_KEY") and os.getenv("ZERODHA_API_SECRET")
                else "Not configured"
            ),
        },
        {
            "Capability": "Free scraper",
            "Status": (
                "Enabled"
                if os.getenv("USE_FREE_SCRAPER", "true").lower() == "true"
                else "Disabled"
            ),
        },
    ]
    st.dataframe(pd.DataFrame(readiness), use_container_width=True, hide_index=True)

    with st.form("integration_settings"):
        model = st.text_input(
            "GitHub Copilot model",
            value=copilot_model,
            help=(
                "Model ID available to your Copilot subscription. "
                "The repository default is claude-opus-4.7."
            ),
        )
        free_scraper = st.checkbox(
            "Use free scraper",
            value=os.getenv("USE_FREE_SCRAPER", "true").lower() == "true",
        )
        save = st.form_submit_button("Apply for this app process")
    if save:
        os.environ["USE_FREE_SCRAPER"] = "true" if free_scraper else "false"
        if model.strip():
            os.environ["COPILOT_MODEL"] = model.strip()
        st.session_state["broker"] = None
        st.success("Copilot settings applied for this app process.")

    st.caption(
        "Copilot SDK uses your existing Copilot CLI login; no model API key is "
        "required. Zerodha app credentials are read from the environment."
    )

    st.subheader("Strategy catalog")
    for strategy_class in sorted(
        registry.list_strategies(), key=lambda item: (item.category.value, item.name)
    ):
        with st.expander(
            f"{strategy_class.name} · {strategy_class.category.value}",
            expanded=False,
        ):
            st.write(strategy_class.long_description or strategy_class.description)
            rows = [
                {
                    "Parameter": spec.name,
                    "Label": spec.label,
                    "Type": spec.type.value,
                    "Default": json.dumps(spec.default, default=str),
                    "Required": spec.required,
                    "Group": spec.group,
                    "Advanced": spec.advanced,
                    "Help": spec.help,
                }
                for spec in strategy_class.param_specs()
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _registry_runner(strategy_id: str, key_prefix: str) -> None:
    strategy = registry.get_strategy(strategy_id)
    st.subheader(strategy.name)
    st.write(strategy.description)
    with st.form(f"{key_prefix}_form"):
        params = render_strategy_params(
            strategy.param_specs(),
            key_prefix=key_prefix,
            defaults=(
                {"symbols": st.session_state.get("symbol_basket", [])}
                if strategy_id == "swing_backtest"
                else None
            ),
        )
        submitted = st.form_submit_button(
            f"Run {strategy.name}", type="primary", use_container_width=True
        )
    if submitted:
        result = run_strategy(strategy_id, params)
    else:
        result = latest_result(strategy_id)
    if result:
        render_result(result)


def _basket_action(result: StrategyResult | None, key: str) -> None:
    if not result or not result.ok:
        return
    symbols = result_symbols(result)
    if not symbols:
        return
    selected = st.multiselect(
        "Select ideas for the shared basket",
        symbols,
        default=symbols,
        key=f"{key}_basket_symbols",
    )
    if st.button("Add selected ideas to basket", key=f"{key}_basket_add"):
        add_symbols(selected)
        st.success(f"Added {len(selected)} symbols to the shared basket.")


def _render_proposed_orders(result: StrategyResult, portfolio_value: float) -> None:
    rows = []
    for symbol, decision in result.data.get("decisions", {}).items():
        if decision.get("action") == "HOLD":
            continue
        price = decision.get("entry_price") or decision.get("current_price")
        allocation = float(decision.get("position_size_pct") or 0)
        amount = portfolio_value * allocation / 100 if allocation else 0
        quantity = int(amount // price) if price and amount else None
        rows.append(
            {
                "symbol": symbol,
                "action": decision.get("action"),
                "quantity": quantity,
                "entry": price,
                "target": decision.get("target_price"),
                "stop": decision.get("stop_loss"),
                "confidence": decision.get("confidence"),
                "status": "PROPOSAL ONLY",
            }
        )
    if rows:
        st.subheader("Proposed orders")
        st.warning("These proposals are not sent to Zerodha.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _holding_source(source: str) -> list[dict]:
    if source == "Zerodha snapshot":
        rows = st.session_state.get("broker_holdings", [])
        if not rows:
            st.warning("Refresh the Broker page before using a Zerodha snapshot.")
        return rows
    if source == "Upload JSON/CSV":
        return _uploaded_rows("portfolio_upload")
    return st.session_state.get("manual_holdings", [])


def _position_source(source: str) -> list[dict]:
    if source == "Zerodha snapshot":
        rows = st.session_state.get("broker_positions", [])
        if not rows:
            st.warning("Refresh the Broker page before using a Zerodha snapshot.")
        return rows
    if source == "Upload JSON/CSV":
        return _uploaded_rows("positions_upload")
    return st.session_state.get("manual_positions", [])


def _uploaded_rows(key: str) -> list[dict]:
    upload = st.file_uploader("Upload JSON or CSV", type=["json", "csv"], key=key)
    if upload is None:
        return []
    try:
        payload = upload.getvalue()
        if upload.name.lower().endswith(".json"):
            value = json.loads(payload.decode("utf-8"))
            if not isinstance(value, list):
                raise ValueError("JSON input must be a list of rows")
            return value
        return pd.read_csv(io.BytesIO(payload)).to_dict("records")
    except Exception as exc:
        st.error(f"Could not read upload: {exc}")
        return []


def _broker():
    broker = st.session_state.get("broker")
    if broker is None:
        from zerodha.read_only import ReadOnlyZerodha

        broker = ReadOnlyZerodha()
        st.session_state["broker"] = broker
    return broker


# ── Kronos forecast visualization ───────────────────────────────────────────


def _parse_tickers(raw: str) -> list[str]:
    """Split a free-form ticker blob (commas / whitespace / newlines) into symbols."""
    seen: dict[str, None] = {}
    for chunk in raw.replace(",", " ").split():
        sym = chunk.strip().upper()
        if sym:
            seen.setdefault(sym, None)
    return list(seen.keys())


def _kronos_chart(fc) -> go.Figure:
    """History close line + forecast percentile cone (p10-p90) with a median path."""
    figure = go.Figure()
    hist = fc.history
    figure.add_trace(
        go.Scatter(
            x=list(hist.index),
            y=list(hist["close"]),
            name="History (close)",
            line={"color": "#4f7cff", "width": 2},
        )
    )

    # Anchor the forecast cone at the last actual close so it reads continuously.
    bands = fc.bands
    x_fc = [fc.last_date] + list(bands.index)

    def _series(col: str) -> list[float]:
        return [fc.last_close] + list(bands[col])

    # Outer cone p10–p90 (light) then inner p25–p75 (darker) as stacked fills.
    figure.add_trace(
        go.Scatter(x=x_fc, y=_series("p90"), name="p90", line={"width": 0}, showlegend=False)
    )
    figure.add_trace(
        go.Scatter(
            x=x_fc, y=_series("p10"), name="p10–p90", fill="tonexty",
            fillcolor="rgba(79,124,255,0.12)", line={"width": 0},
        )
    )
    figure.add_trace(
        go.Scatter(x=x_fc, y=_series("p75"), name="p75", line={"width": 0}, showlegend=False)
    )
    figure.add_trace(
        go.Scatter(
            x=x_fc, y=_series("p25"), name="p25–p75", fill="tonexty",
            fillcolor="rgba(79,124,255,0.25)", line={"width": 0},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_fc, y=_series("p50"), name="Median forecast",
            line={"color": "#f5a623", "width": 2, "dash": "dot"},
            mode="lines+markers",
        )
    )
    figure.update_layout(
        height=420,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        yaxis_title="Price (₹)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hovermode="x unified",
    )
    return figure


def _render_kronos_forecast(fc) -> None:
    plain = fc.symbol
    if not fc.ok:
        st.subheader(plain)
        st.warning(f"Could not forecast **{plain}**: {fc.error}")
        st.divider()
        return

    sig = fc.signal
    tone = {"BUY": "🟢", "HOLD": "🟡", "AVOID": "🔴"}.get(sig.direction, "⚪")
    st.subheader(f"{tone} {plain} — {sig.direction} ({sig.confidence} confidence)")

    row = st.columns(5)
    row[0].metric("Last close", f"₹{fc.last_close:,.2f}")
    row[1].metric("P(up)", f"{sig.prob_up:.0%}")
    row[2].metric("Expected return", f"{sig.expected_return:+.1%}")
    row[3].metric(f"Target ({fc.pred_len}d)", f"₹{sig.suggested_target:,.2f}")
    row[4].metric("Reward:Risk", f"{sig.reward_risk:.2f}:1")

    st.plotly_chart(_kronos_chart(fc), use_container_width=True)
    st.caption(sig.rationale)
    st.divider()


def kronos_page() -> None:
    page_header(
        "Kronos Forecast Lab",
        "Zero-shot OHLCV foundation-model price forecasts for any NSE ticker.",
    )
    st.warning(
        "Indicative only. Kronos is a general-purpose forecaster run zero-shot on "
        "daily NSE bars (out-of-distribution). Read the **shape and spread** of the "
        "forecast cone, not the exact price — absolute levels can be biased. Not "
        "investment advice; this app never places orders.",
        icon="⚠️",
    )

    raw = st.text_area(
        "Tickers",
        value=st.session_state.get("kronos_tickers", "RELIANCE, TCS, INFY"),
        help="One or more NSE symbols separated by commas, spaces, or new lines. "
        "'.NS' is added automatically.",
        height=80,
    )
    with st.expander("Model settings", expanded=False):
        cols = st.columns(3)
        pred_len = cols[0].slider("Forecast horizon (days)", 3, 30, 10)
        sample_paths = cols[1].slider("Sample paths", 5, 40, 20, help="More paths = smoother cone, slower on CPU.")
        history_bars = cols[2].slider("History window (bars)", 60, 400, 250)
        st.caption("Model: **Kronos-base** (102M) on CPU. First run downloads weights (~100MB).")

    if st.button("Run forecast", type="primary"):
        tickers = _parse_tickers(raw)
        if not tickers:
            st.error("Enter at least one ticker.")
            return
        st.session_state["kronos_tickers"] = raw
        try:
            from kronos.predictor import KronosUnavailable
            from kronos.viz import base_config, forecast_many_for_chart

            cfg = base_config(pred_len=pred_len, sample_paths=sample_paths)
            with st.status(
                f"Forecasting {len(tickers)} ticker(s) with Kronos-base…", expanded=True
            ) as status:
                st.write("Loading model + fetching price history (first run is slower)…")
                results = forecast_many_for_chart(
                    tickers, config=cfg, history_bars=history_bars
                )
                status.update(label="Forecast complete", state="complete", expanded=False)
            st.session_state["kronos_results"] = results
        except KronosUnavailable as exc:
            st.session_state.pop("kronos_results", None)
            st.error("Kronos model is not installed in this environment.")
            st.code(str(exc))
            return

    results = st.session_state.get("kronos_results")
    if results:
        st.caption(f"Showing {len(results)} forecast(s).")
        for fc in results:
            _render_kronos_forecast(fc)
