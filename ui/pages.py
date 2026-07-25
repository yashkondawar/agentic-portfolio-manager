"""Task-oriented pages for the trader workbench."""

from __future__ import annotations

import io
import json
import os
import shutil
from datetime import datetime
from importlib.util import find_spec

import pandas as pd
import streamlit as st

from core import registry
from core.run_history import get_run, list_runs
from core.strategy import StrategyResult
from ui.components import (
    clean_editor_rows,
    latest_result,
    page_header,
    render_result,
    result_symbols,
    run_strategy,
)
from ui.forms import render_strategy_params
from ui.state import add_symbols, clear_symbols


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
        "Screen broad universes and monitor fresh quarterly-result catalysts.",
    )
    watchlist_tab, results_tab = st.tabs(["Watchlist builder", "Quarterly results"])
    with watchlist_tab:
        _registry_runner("watchlist_curation", "discover_watchlist")
        _basket_action(latest_result("watchlist_curation"), "watchlist")
    with results_tab:
        _registry_runner("qtr_results", "discover_results")
        _basket_action(latest_result("qtr_results"), "quarterly")


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
    workflow = st.selectbox(
        "Workflow",
        ["breakout_52w_daily", "swing_trading"],
        format_func=lambda item: registry.get_strategy(item).name,
    )
    if workflow == "breakout_52w_daily":
        st.info(
            "This workflow uses its own persisted paper portfolio and does not "
            "read Zerodha holdings."
        )
        _registry_runner(workflow, "breakout_52w_daily")
        return

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
        "Validate deterministic trading systems with point-in-time data and next-session fills.",
    )
    st.warning(
        "Historical results include modeled costs but do not guarantee future returns."
    )
    strategy_id = st.selectbox(
        "Strategy",
        ["swing_backtest", "breakout_52w_backtest"],
        format_func=lambda item: registry.get_strategy(item).name,
    )
    _registry_runner(strategy_id, f"backtest_{strategy_id}")


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
                if strategy_id
                in {
                    "swing_backtest",
                    "breakout_52w_backtest",
                }
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
