"""Task-oriented pages for the trader workbench."""

from __future__ import annotations

import io
import json
import os
import shutil
from datetime import datetime, time as dt_time, timezone
from importlib.util import find_spec

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import registry
from core import scheduler as scheduler_mod
from core import schedules as schedules_mod
from core.run_history import get_run, list_runs
from core.strategy import StrategyResult
from ui.components import (
    clean_editor_rows,
    format_run_timestamp,
    latest_result,
    latest_run_record,
    page_header,
    render_gfs_ledger_snapshot,
    render_qtr_ledger_snapshot,
    render_result,
    result_from_record,
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
    "schedules_page",
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
            st.session_state["broker_swing_positions"] = broker.swing_positions()
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


def _backend_readiness(choice) -> list[dict[str, str]]:
    """Readiness rows for the *selected* backend only.

    The previous table always reported Copilot CLI/SDK status, which told a
    native-backend user nothing useful and made a working setup look broken.
    """
    from core.agent.detect import API_KEY_MODELS

    if choice.backend == "copilot_cli":
        return [
            {
                "Capability": "Copilot CLI",
                "Status": "Ready" if shutil.which("copilot") else "Not found",
            },
            {
                "Capability": "Copilot SDK",
                "Status": "Ready" if find_spec("copilot") else "Not installed",
            },
            {
                "Capability": "Model",
                "Status": os.getenv("COPILOT_MODEL", "").strip() or "claude-opus-4.7",
            },
        ]

    if choice.backend == "native":
        keys = [
            label
            for env_var, _model, label in API_KEY_MODELS
            if os.getenv(env_var, "").strip()
        ]
        return [
            {
                "Capability": "LangChain",
                "Status": "Ready" if find_spec("langchain") else "Not installed",
            },
            {
                "Capability": "API key",
                "Status": ", ".join(keys) if keys else "None set",
            },
            {
                "Capability": "Model",
                "Status": os.getenv("AI_MODEL", "").strip() or "Not set",
            },
            {
                "Capability": "Web grounding",
                "Status": (
                    "Must be off for this backend"
                    if os.getenv("WEB_GROUNDING", "true").lower() == "true"
                    else "Off (correct)"
                ),
            },
        ]

    if choice.backend == "claude_code":
        from core.agent.detect import _claude_bundled_cli, _claude_cli

        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
        if api_key and token and os.getenv("CLAUDE_CODE_USE_API_KEY", "") not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            billing = "Subscription (API key withheld)"
        elif api_key:
            billing = "API key - billed per token"
        elif token:
            billing = "Subscription (Pro/Max allowance)"
        else:
            # An interactive `claude login` stores credentials outside the
            # environment, so this is "nothing visible here", not "broken".
            billing = "Using your `claude login`, if you have one"

        if _claude_bundled_cli():
            cli_status = "Ready (bundled with the SDK)"
        elif _claude_cli():
            cli_status = "Ready"
        else:
            cli_status = "Not found"

        return [
            {"Capability": "Claude Code CLI", "Status": cli_status},
            {
                "Capability": "Agent SDK",
                "Status": (
                    "Ready" if find_spec("claude_agent_sdk") else "Not installed"
                ),
            },
            {"Capability": "Billing", "Status": billing},
            {
                "Capability": "Model",
                "Status": os.getenv("CLAUDE_MODEL", "").strip()
                or "Chosen by your subscription",
            },
        ]

    return [{"Capability": choice.backend, "Status": "Not implemented yet"}]


def _render_backend_form(choice) -> None:
    """Provider selector plus only the fields that provider actually uses."""
    from core.agent import available_backends
    from core.agent.detect import API_KEY_MODELS
    from core.agent.settings import persist_settings

    backends = available_backends()
    labels = {
        "copilot_cli": "GitHub Copilot  ·  needs a subscription + the Copilot CLI",
        "native": "Direct API key  ·  Gemini / OpenAI / Anthropic / Ollama",
        "claude_code": "Claude Code  ·  use a Claude Pro/Max subscription",
    }

    with st.form("agent_backend"):
        selected = st.selectbox(
            "Model provider",
            backends,
            index=backends.index(choice.backend) if choice.backend in backends else 0,
            format_func=lambda name: labels.get(name, name),
        )

        copilot_model = st.text_input(
            "Copilot model",
            value=os.getenv("COPILOT_MODEL", "").strip() or "claude-opus-4.7",
            help="Model ID available to your Copilot subscription.",
        )
        ai_model = st.text_input(
            "Model (native backend)",
            value=os.getenv("AI_MODEL", "").strip()
            or (choice.model or "google_genai:gemini-2.5-pro"),
            help=(
                "Optional — inferred from whichever API key you set below. "
                "Override here, or set it for a local model. "
                "provider:model — e.g. google_genai:gemini-2.5-pro, "
                "openai:gpt-4o, anthropic:claude-sonnet-4-5, ollama:llama3.1"
            ),
        )
        claude_token = st.text_input(
            "Claude subscription token",
            value=os.getenv("CLAUDE_CODE_OAUTH_TOKEN", ""),
            type="password",
            help=(
                "For the Claude Code backend. Run `claude setup-token` in a "
                "terminal and paste the sk-ant-oat... value here. This uses "
                "your Pro/Max subscription instead of paying per token."
            ),
        )
        claude_model = st.text_input(
            "Claude model",
            value=os.getenv("CLAUDE_MODEL", ""),
            help=(
                "Optional. Leave blank to let your subscription choose - "
                "e.g. claude-sonnet-4-5."
            ),
        )
        key_values: dict[str, str] = {}
        for env_var, _model, label in API_KEY_MODELS:
            key_values[env_var] = st.text_input(
                f"{label} API key",
                value=os.getenv(env_var, ""),
                type="password",
                help="Stored in .env, which is git-ignored. Leave blank to skip.",
            )

        free_scraper = st.checkbox(
            "Use free scraper",
            value=os.getenv("USE_FREE_SCRAPER", "true").lower() == "true",
        )
        saved = st.form_submit_button("Save to .env", type="primary")

    if not saved:
        return

    updates: dict[str, str | None] = {
        "AI_AGENT_BACKEND": selected,
        "USE_FREE_SCRAPER": "true" if free_scraper else "false",
        "COPILOT_MODEL": copilot_model,
        "CLAUDE_CODE_OAUTH_TOKEN": claude_token,
        "CLAUDE_MODEL": claude_model,
        **key_values,
    }
    if selected == "native":
        updates["AI_MODEL"] = ai_model
        # The native backend has no browsing tool, so a request that demands
        # one is rejected before any tokens are spent. Flipping this for the
        # user is the difference between "it works" and an error they have no
        # way to interpret.
        updates["WEB_GROUNDING"] = "false"
    else:
        updates["AI_MODEL"] = None
        # ...and switching back must undo it. Copilot and Claude Code both
        # browse, and this form is the only thing that ever sets the flag, so
        # leaving it off would silently degrade every later report to
        # training-data recall with no sign on screen.
        updates["WEB_GROUNDING"] = "true"

    try:
        path = persist_settings(updates)
    except (OSError, ValueError) as exc:
        st.error(f"Could not save settings: {exc}")
        return

    st.session_state["broker"] = None
    st.success(f"Saved to {path}. Applied to this session too.")
    if selected == "native":
        st.info(
            "Web grounding was turned off automatically — the native backend "
            "has no built-in browsing. The scraper tools (live prices, "
            "fundamentals, technicals, news) still run."
        )
    if selected == "claude_code" and not claude_token.strip():
        st.warning(
            "No subscription token saved. Run `claude setup-token` in a "
            "terminal and paste the result above, otherwise this backend "
            "falls back to ANTHROPIC_API_KEY and bills you per token."
        )
    st.rerun()


def _render_connection_test() -> None:
    """Let the user prove the provider works before starting a long analysis.

    Without this the first feedback on a bad key arrives minutes into a run.
    """
    if not st.button("Test provider connection"):
        return
    from core.agent import AgentRequest, run_agent

    with st.spinner("Contacting the model…"):
        try:
            result = run_agent(
                AgentRequest(prompt="Reply with exactly: OK", label="probe")
            )
        except Exception as exc:  # noqa: BLE001 - surface any provider error verbatim
            st.error(f"{type(exc).__name__}: {exc}")
            return
    st.success(f"{result.backend} replied: {result.text.strip()[:200]}")


def settings_page() -> None:
    page_header(
        "Settings & Strategy Catalog",
        "Configure local integrations and inspect every available strategy control.",
    )
    from core.agent.detect import detect_backend

    choice = detect_backend()

    st.subheader("Model provider")
    if choice.explicit:
        st.caption(choice.reason)
    elif choice.resolved:
        st.info(f"Auto-detected **{choice.backend}**. {choice.reason}")
    else:
        st.warning(f"No provider configured. {choice.reason}")

    readiness = _backend_readiness(choice) + [
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

    _render_backend_form(choice)
    _render_connection_test()

    st.caption(
        "Settings are written to .env (git-ignored) and applied immediately. "
        "Strategy logic, prompts and scraper tools are identical on every "
        "provider — only the runner changes."
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
        result = latest_result(strategy_id, from_history=False)
        if result is None:
            result = _render_saved_run_notice(strategy_id)
    if result:
        render_result(result)


def _render_saved_run_notice(strategy_id: str) -> StrategyResult | None:
    """Surface the newest persisted run — typically last night's scheduled one."""
    record = latest_run_record(strategy_id)
    if not record:
        return None
    when = format_run_timestamp(record.get("created_at"))
    if record.get("status") == "completed":
        st.caption(f"Showing the saved run from {when}. Use the form to re-run it.")
    else:
        st.warning(f"The last run ({when}) did not complete. Re-run it below.")
    return result_from_record(record)


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
        # A swing trade is a delivery position, so it lives in the holdings book.
        # Kite's ``positions`` book only covers today's trades and is empty for a
        # delivery-only account, which is why this page used to report no
        # snapshot while the Portfolio page loaded fine.
        rows = st.session_state.get("broker_swing_positions") or st.session_state.get(
            "broker_positions", []
        )
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


def schedules_page() -> None:
    page_header(
        "Automation & Schedules",
        "Run the daily strategies unattended so the report is already in the "
        "database when the market opens. Every page can still re-run on demand.",
    )
    _scheduler_health()
    st.divider()

    rows = _load_schedules()
    st.subheader("Configured schedules")
    if not rows:
        st.info("No schedules yet. Add one below.")
    for schedule in rows:
        _schedule_card(schedule)

    st.divider()
    _schedule_editor(rows)
    st.divider()
    _schedule_guidance()


def _load_schedules() -> list:
    try:
        return schedules_mod.ensure_defaults()
    except Exception as exc:
        st.error(f"Could not read schedules: {exc}")
        return []


def _scheduler_health() -> None:
    age = scheduler_mod.heartbeat_age_seconds()
    beat = scheduler_mod.read_heartbeat()
    poll = int(beat.get("poll_seconds") or scheduler_mod.DEFAULT_POLL_SECONDS)
    status, detail, running = _health_verdict(age, poll)

    left, right = st.columns([1, 2])
    with left:
        st.metric("Background scheduler", status)
    with right:
        (st.success if running else st.warning)(detail)

    if not running:
        st.caption(
            "Schedules only fire while this process runs. Register it once and "
            "it starts with every logon, restarts itself if it dies, and keeps "
            "running whether or not this app is open:"
        )
        st.code("uv run python -m core.scheduler install-task", language="powershell")
        st.caption("Or start it by hand in a spare terminal:")
        st.code("uv run python -m core.scheduler", language="powershell")
        st.caption(f"Log file: `{scheduler_mod.log_path()}`")


def _health_verdict(age: float | None, poll: int) -> tuple[str, str, bool]:
    if age is None:
        return "Not running", "The scheduler has never checked in on this machine.", False
    if age <= max(120, poll * 4):
        return "Running", f"Last check-in {int(age)}s ago.", True
    return (
        "Stale",
        f"Last check-in was {_humanize_seconds(age)} ago — the process is not running.",
        False,
    )


def _humanize_seconds(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds < 5400:
        return f"{int(seconds // 60)}m"
    if seconds < 172800:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _schedule_card(schedule) -> None:
    with st.container(border=True):
        head, actions = st.columns([3, 1])
        with head:
            mark = ":green[Enabled]" if schedule.enabled else ":gray[Paused]"
            st.markdown(f"**{schedule.name}** · {mark}")
            st.caption(f"`{schedule.strategy_id}` — {schedule.describe()}")
        with actions:
            if st.button(
                "Run now",
                key=f"sched_run_{schedule.id}",
                use_container_width=True,
                type="primary",
            ):
                _run_schedule_now(schedule)

        following = schedule.next_occurrence(datetime.now(timezone.utc))
        cols = st.columns(3)
        cols[0].metric(
            "Next run",
            following.strftime("%a %d %b, %H:%M") if following else "never",
        )
        cols[1].metric("Last status", schedule.last_status or "never run")
        cols[2].metric("Last run", format_run_timestamp(schedule.last_run_at))

        if schedule.last_error:
            st.error(schedule.last_error)
        if schedule.params:
            st.caption(f"Parameters: `{json.dumps(schedule.params, default=str)}`")

        toggle, remove = st.columns([3, 1])
        with toggle:
            wanted = st.toggle(
                "Enabled",
                value=schedule.enabled,
                key=f"sched_enabled_{schedule.id}",
            )
            if wanted != schedule.enabled:
                schedules_mod.set_enabled(schedule.id, wanted)
                st.rerun()
        with remove:
            with st.popover("Delete", use_container_width=True):
                st.write(f"Delete **{schedule.name}**?")
                if st.button(
                    "Yes, delete", key=f"sched_del_{schedule.id}", type="primary"
                ):
                    schedules_mod.delete_schedule(schedule.id)
                    st.rerun()


def _run_schedule_now(schedule) -> None:
    with st.status(f"Running {schedule.name}...", expanded=True) as status:
        st.write(f"Executing `{schedule.strategy_id}` with the saved parameters.")
        result = scheduler_mod.run_schedule(schedule)
        if result.ok:
            status.update(label="Run completed", state="complete", expanded=False)
        else:
            status.update(label="Run failed", state="error", expanded=True)
    st.session_state.setdefault("latest_results", {})
    st.session_state["latest_results"][schedule.strategy_id] = result.to_dict()
    if result.ok:
        st.success("Saved to run history — the strategy page now shows this run.")
    else:
        st.error(result.error or "The strategy failed.")


def _schedule_editor(rows: list) -> None:
    st.subheader("Add or edit a schedule")
    options = {"➕ New schedule": None}
    options.update({f"{item.name} ({item.strategy_id})": item.id for item in rows})
    label = st.selectbox("Schedule", list(options), key="sched_editor_pick")
    current = next((item for item in rows if item.id == options[label]), None)

    strategy_ids = sorted(cls.id for cls in registry.list_strategies())
    if not strategy_ids:
        st.error("No strategies are registered.")
        return
    default_strategy = current.strategy_id if current else "gfs_live"
    if default_strategy not in strategy_ids:
        default_strategy = strategy_ids[0]
    strategy_id = st.selectbox(
        "Strategy",
        strategy_ids,
        index=strategy_ids.index(default_strategy),
        key=f"sched_strategy_{current.id if current else 'new'}",
    )

    try:
        strategy = registry.get_strategy(strategy_id)
    except KeyError as exc:
        st.error(str(exc))
        return
    st.caption(strategy.description)

    key_prefix = f"sched_form_{current.id if current else 'new'}_{strategy_id}"
    with st.form(f"{key_prefix}_wrapper"):
        name = st.text_input(
            "Name",
            value=current.name if current else strategy.name,
            key=f"{key_prefix}_name",
        )
        timing, days_col = st.columns(2)
        with timing:
            default_time = _parse_clock(current.run_at if current else "17:30")
            run_at = st.time_input(
                "Run at", value=default_time, step=300, key=f"{key_prefix}_time"
            )
            zones = _timezone_choices(current.timezone if current else None)
            timezone_name = st.selectbox(
                "Timezone", zones, index=0, key=f"{key_prefix}_tz"
            )
        with days_col:
            chosen_days = current.days_of_week if current else schedules_mod.WEEKDAYS
            picked = st.multiselect(
                "Days",
                list(schedules_mod.DAY_LABELS),
                default=[schedules_mod.DAY_LABELS[d] for d in chosen_days],
                key=f"{key_prefix}_days",
            )
            catch_up = st.number_input(
                "Catch-up window (minutes)",
                min_value=0,
                max_value=2880,
                value=int(
                    current.catch_up_minutes
                    if current
                    else schedules_mod.DEFAULT_CATCH_UP_MINUTES
                ),
                step=30,
                help=(
                    "If the machine was asleep at the scheduled time, still run "
                    "when it wakes up — as long as it is no later than this."
                ),
                key=f"{key_prefix}_catchup",
            )
        enabled = st.checkbox(
            "Enabled",
            value=current.enabled if current else True,
            key=f"{key_prefix}_enabled",
        )

        st.markdown("**Run parameters**")
        params = render_strategy_params(
            strategy.param_specs(),
            key_prefix=key_prefix,
            defaults=dict(current.params) if current else None,
        )
        saved = st.form_submit_button(
            "Save schedule", type="primary", use_container_width=True
        )

    if not saved:
        return
    try:
        schedules_mod.save_schedule(
            schedules_mod.Schedule(
                id=current.id if current else "",
                name=name,
                strategy_id=strategy_id,
                run_at=run_at.strftime("%H:%M"),
                days_of_week=tuple(
                    schedules_mod.DAY_LABELS.index(day) for day in picked
                ),
                timezone=timezone_name,
                enabled=enabled,
                catch_up_minutes=int(catch_up),
                params=strategy.coerce_params(params),
                created_at=current.created_at if current else "",
                last_fired_key=current.last_fired_key if current else None,
                last_run_at=current.last_run_at if current else None,
                last_run_id=current.last_run_id if current else None,
                last_status=current.last_status if current else None,
                last_error=current.last_error if current else None,
            )
        )
    except schedules_mod.ScheduleError as exc:
        st.error(str(exc))
        return
    st.success("Schedule saved.")
    st.rerun()


def _parse_clock(value: str) -> dt_time:
    try:
        hour, minute = (int(part) for part in str(value).split(":", 1))
        return dt_time(hour=hour, minute=minute)
    except (ValueError, TypeError):
        return dt_time(hour=17, minute=30)


def _timezone_choices(current: str | None) -> list[str]:
    zones = [schedules_mod.DEFAULT_TIMEZONE, "UTC", "America/New_York", "Europe/London"]
    if current and current in zones:
        zones.remove(current)
    if current:
        zones.insert(0, current)
    return zones


def _schedule_guidance() -> None:
    st.subheader("Why these default times")
    for spec in schedules_mod.DEFAULT_SCHEDULES:
        days = (
            "every day"
            if tuple(spec["days_of_week"]) == schedules_mod.ALL_DAYS
            else "Mon-Fri"
        )
        st.markdown(
            f"**{spec['name']}** — `{spec['run_at']} IST`, {days}\n\n{spec['why']}"
        )
