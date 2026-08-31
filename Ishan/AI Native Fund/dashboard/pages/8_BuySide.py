"""BuySide — latest BuySideRecommendation + EPS x PE sensitivity heatmap.

research_reports (report_type='BUYSIDE') carries the rating/conviction
metadata; the actual eps_scenarios/pe_scenarios (5-element lists) live only
in the ingested agent output JSON, so this page pulls both and computes the
grid with the same pure `afund.research.sensitivity` functions the CLI uses
at ingestion time (never re-deriving the arithmetic by hand). DRAFT
watermark: sensitivity scenarios are the agent's judgment, not a
back-tested model.
"""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402
from afund.research.sensitivity import grid as sensitivity_grid  # noqa: E402
from afund.research.sensitivity import pct_upside  # noqa: E402

st.set_page_config(page_title="BuySide — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("BuySide")
st.warning("DRAFT — EPS/PE scenarios are agent judgment, not a back-tested model (CLAUDE.md).")

reports_df = shared.df_from_query(
    conn,
    "SELECT id, ticker, instrument_id, rating, as_of_date, status, created_at "
    "FROM research_reports WHERE report_type = 'BUYSIDE' ORDER BY as_of_date DESC, id DESC LIMIT 50",
)

if reports_df.empty:
    st.info(
        "No BUYSIDE research_reports yet. Run "
        "`.venv\\Scripts\\python -m afund.orchestrator.run --job buy_side_analysis`, then ingest the "
        "agent output with `--ingest-output`."
    )
    st.stop()

st.caption("Click a row to select a BuySide report.")
event = st.dataframe(
    reports_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "id": st.column_config.NumberColumn("ID", format="%d"),
        "ticker": st.column_config.TextColumn("Ticker"),
        "instrument_id": None,
        "rating": st.column_config.TextColumn("Rating"),
        "as_of_date": st.column_config.TextColumn("As of"),
        "status": st.column_config.TextColumn("Status"),
        "created_at": st.column_config.TextColumn("Created"),
    },
)

selected_rows = event.selection.rows if event and event.selection else []
if not selected_rows:
    st.info("Select a row above to view its detail.")
    st.stop()
selected_row = reports_df.iloc[selected_rows[0]]

st.markdown(f"## {selected_row['ticker']}")
col1, col2, col3 = st.columns(3)
col1.metric("Recommendation", selected_row["rating"] or "-")
col2.metric("As of", selected_row["as_of_date"])
col3.metric("Status", selected_row["status"] or "-")

output = shared.latest_agent_output(conn, "buy_side")
if output is None or output.get("ticker") != selected_row["ticker"]:
    # Best-effort: latest_agent_output only returns the single most recent
    # buy_side output; if it doesn't match the selected ticker, be honest
    # rather than showing the wrong scenario data.
    st.info(
        f"No ingested 'buy_side' output on file matching ticker={selected_row['ticker']!r} "
        "(only the most recent buy_side output is queryable from this page)."
    )
    st.stop()

st.markdown("**Rerating narrative**")
st.write(output.get("rerating_narrative", "-"))

if output.get("catalysts"):
    st.markdown("**Catalysts**")
    for c in output["catalysts"]:
        st.write(f"- {c}")

st.caption(f"Conviction: {output.get('conviction')}")
st.caption(f"Scenario reasoning: {output.get('scenario_reasoning', '-')}")
if output.get("invalidation_condition"):
    st.caption(f"Invalidation: {output['invalidation_condition']}")

eps_scenarios = output.get("eps_scenarios") or []
pe_scenarios = output.get("pe_scenarios") or []

if len(eps_scenarios) != 5 or len(pe_scenarios) != 5:
    st.warning("eps_scenarios/pe_scenarios are not both 5-element lists — cannot render the heatmap.")
    st.stop()

price_grid = sensitivity_grid(eps_scenarios, pe_scenarios)

instrument_id = selected_row["instrument_id"]
price_row = None
if instrument_id is not None:
    price_row = conn.execute(
        "SELECT close FROM daily_prices WHERE instrument_id = ? ORDER BY date DESC LIMIT 1",
        (int(instrument_id),),
    ).fetchone()

current_price = price_row["close"] if price_row else None

st.subheader("EPS x PE target-price grid")

if current_price:
    upside_grid = pct_upside(price_grid, current_price)
    annotations_text = [
        [f"₹{price_grid[i][j]:,.0f}<br>{upside_grid[i][j] * 100:+.0f}%" for j in range(5)]
        for i in range(5)
    ]
    st.caption(f"Current price: ₹{current_price:,.2f} (% upside/downside annotated per cell)")
else:
    annotations_text = [[f"₹{price_grid[i][j]:,.0f}" for j in range(5)] for i in range(5)]
    st.caption("No current price on file — showing target prices only (no % upside).")

fig = go.Figure(
    data=go.Heatmap(
        z=price_grid,
        x=[f"PE {pe:g}" for pe in pe_scenarios],
        y=[f"EPS {eps:g}" for eps in eps_scenarios],
        colorscale="RdYlGn",
        text=annotations_text,
        texttemplate="%{text}",
        hoverinfo="x+y+z",
    )
)
fig.update_layout(title=f"{selected_row['ticker']} — EPS x PE sensitivity (DRAFT)", height=500)
st.plotly_chart(fig, use_container_width=True)
