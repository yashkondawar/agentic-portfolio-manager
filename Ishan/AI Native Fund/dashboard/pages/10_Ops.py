"""Ops — agent_runs cost by role/model + job_runs, rolling 5-day window
(same convention as Home's status board)."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402

st.set_page_config(page_title="Ops — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("Ops")
st.caption(f"Rolling {shared.ROLLING_WINDOW_DAYS}-day window for job/agent runs; cost totals below are all-time.")

st.subheader("Agent runs — tokens/cost by role & model (all-time)")
agent_cost_df = shared.df_from_query(
    conn,
    "SELECT role, model, status, COUNT(*) as n, SUM(input_tokens) as input_tokens, "
    "SUM(output_tokens) as output_tokens, SUM(cost_usd) as cost_usd "
    "FROM agent_runs GROUP BY role, model, status ORDER BY role, model, status",
)
if agent_cost_df.empty:
    st.info("No agent runs yet (PREPARED/COMPLETED rows appear once an agent-driven job runs).")
else:
    st.dataframe(
        agent_cost_df,
        use_container_width=True,
        column_config={
            "role": st.column_config.TextColumn("Role"),
            "model": st.column_config.TextColumn("Model"),
            "status": st.column_config.TextColumn("Status"),
            "n": st.column_config.NumberColumn("Runs", format="%d"),
            "input_tokens": st.column_config.NumberColumn("Input Tokens", format="%d"),
            "output_tokens": st.column_config.NumberColumn("Output Tokens", format="%d"),
            "cost_usd": st.column_config.NumberColumn("Cost (USD)", format="$%.4f"),
        },
    )
    total_cost = agent_cost_df["cost_usd"].fillna(0).sum()
    st.metric("Total cost (USD, all-time)", f"${total_cost:,.4f}")

st.divider()

st.subheader(f"Agent runs — rolling {shared.ROLLING_WINDOW_DAYS}-day window")
agents = shared.agent_runs_rolling(conn)
if not agents["recent"]:
    st.info("No agent runs in the rolling window.")
else:
    st.dataframe(agents["recent"], use_container_width=True)
if agents["older_count"]:
    st.caption(f"{agents['older_count']} older agent run(s) not shown.")

st.divider()

st.subheader(f"Job runs — rolling {shared.ROLLING_WINDOW_DAYS}-day window")
jobs = shared.job_runs_rolling(conn)
if not jobs["recent"]:
    st.info("No job runs in the rolling window.")
else:
    st.dataframe(jobs["recent"], use_container_width=True)
if jobs["older_count"]:
    st.caption(f"{jobs['older_count']} older job run(s) not shown.")
