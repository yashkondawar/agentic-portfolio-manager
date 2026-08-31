"""Positions — open positions, weights, NAV vs benchmark."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402
from afund.portfolio import risk  # noqa: E402

st.set_page_config(page_title="Positions — AI-Native Fund", layout="wide")

conn = shared.get_conn()
settings = shared.get_settings()
portfolio_cfg = settings.get("portfolio", {})
CURRENCY = portfolio_cfg.get("currency", "INR")
INITIAL_CAPITAL = float(portfolio_cfg.get("initial_capital", 0))
BENCHMARK = portfolio_cfg.get("benchmark", "NIFTY 50")

st.title("Positions")

# ---------------------------------------------------------------------------
# NAV overview
# ---------------------------------------------------------------------------

nav_df = shared.df_from_query(
    conn, "SELECT date, total_nav, cash, market_value, daily_return FROM nav_history ORDER BY date ASC"
)

if nav_df.empty:
    st.info(
        "No NAV history yet. Run `.venv\\Scripts\\python -m afund.orchestrator.run --job daily_nav` "
        "to compute the first NAV snapshot."
    )
    total_nav, cash, total_return, today_return = INITIAL_CAPITAL, INITIAL_CAPITAL, 0.0, None
else:
    latest = nav_df.iloc[-1]
    total_nav = latest["total_nav"]
    cash = latest["cash"]
    total_return = (total_nav - INITIAL_CAPITAL) / INITIAL_CAPITAL if INITIAL_CAPITAL else None
    today_return = latest["daily_return"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total NAV", shared.fmt_money(total_nav, CURRENCY))
col2.metric("Cash", shared.fmt_money(cash, CURRENCY))
col3.metric("Total Return", shared.fmt_pct(total_return) if total_return is not None else "-")
col4.metric("Today's Return", shared.fmt_pct(today_return) if today_return is not None else "-")

if not nav_df.empty:
    bench_df = shared.df_from_query(
        conn, "SELECT date, close FROM index_data WHERE index_name = ? ORDER BY date ASC", (BENCHMARK,)
    )
    fig = go.Figure()
    rebased_nav = nav_df["total_nav"] / nav_df["total_nav"].iloc[0] * 100
    fig.add_trace(go.Scatter(x=nav_df["date"], y=rebased_nav, name="Portfolio NAV", mode="lines"))
    if not bench_df.empty:
        bench_start = bench_df[bench_df["date"] >= nav_df["date"].iloc[0]]
        if not bench_start.empty:
            base_close = bench_start["close"].iloc[0]
            bench_aligned = bench_df[bench_df["date"] >= bench_start["date"].iloc[0]]
            rebased_bench = bench_aligned["close"] / base_close * 100
            fig.add_trace(go.Scatter(x=bench_aligned["date"], y=rebased_bench, name=f"{BENCHMARK} (rebased)", mode="lines"))
    fig.update_layout(title="NAV vs Benchmark (rebased to 100)", xaxis_title="Date", yaxis_title="Index (100 = inception)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Chart will appear once nav_history has at least one row.")

st.divider()

# ---------------------------------------------------------------------------
# Positions table
# ---------------------------------------------------------------------------

try:
    snap = risk.snapshot(conn)
    positions_detail = snap["positions_detail"]
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not compute positions: {exc}")
    positions_detail = []

if not positions_detail:
    st.info(
        "No open positions. Trades are recorded via the CLI, e.g.:\n\n"
        "`.venv\\Scripts\\python -c \"from afund.db.connection import get_conn; "
        "from afund.portfolio.ledger import add_transaction; conn=get_conn(); "
        "add_transaction(conn, trade_date='YYYY-MM-DD', symbol_or_instrument_id='SYMBOL', "
        "side='BUY', qty=1, price=1.0)\"`"
    )
else:
    pos_df = pd.DataFrame(positions_detail)
    money_fmt = "₹%.2f" if CURRENCY == "INR" else f"{CURRENCY} %.2f"
    st.dataframe(
        pos_df,
        use_container_width=True,
        column_config={
            "symbol": st.column_config.TextColumn("Symbol"),
            "qty": st.column_config.NumberColumn("Qty", format="%.0f"),
            "avg_cost": st.column_config.NumberColumn("Avg Cost", format=money_fmt),
            "last_price": st.column_config.NumberColumn("Last Price", format=money_fmt),
            "market_value": st.column_config.NumberColumn("Market Value", format=money_fmt),
            "weight_pct": st.column_config.NumberColumn("Weight %", format="%.1f%%"),
            "unrealized_pnl": st.column_config.NumberColumn("Unrealized P&L", format=money_fmt),
            "unrealized_pnl_pct": st.column_config.NumberColumn("Unrealized P&L %", format="%.1f%%"),
        },
    )

    fig = go.Figure(data=[go.Pie(labels=pos_df["symbol"], values=pos_df["weight_pct"].fillna(0), hole=0.4)])
    fig.update_layout(title="Position Weights")
    st.plotly_chart(fig, use_container_width=True)
