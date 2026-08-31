"""Company Fit — sortable/filterable view over the company_fit classification
table (Phase 12 universe screening). Bucket filter, sector filter, min-mcap
filter, plus a bucket histogram chart. Read-only per _shared.py convention;
the batch screener scrape and classification refresh both run via the CLI
(`python -m afund.data.financials --universe`, then
`python -m afund.orchestrator.run --job universe_fit_refresh`), never from
this page.
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

st.set_page_config(page_title="Company Fit — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("Company Fit")
st.warning(
    "DRAFT — fit_bucket rules and fit_score formula are unvalidated judgment calls "
    "(see src/afund/derive/company_fit.py module docstring), not back-tested (CLAUDE.md)."
)

dates_df = shared.df_from_query(
    conn, "SELECT DISTINCT as_of_date FROM company_fit ORDER BY as_of_date DESC"
)
if dates_df.empty:
    st.info(
        "No company_fit rows yet. Run the batch scrape "
        "(`.venv\\Scripts\\python -m afund.data.financials --universe`) then the classification refresh "
        "(`.venv\\Scripts\\python -m afund.orchestrator.run --job universe_fit_refresh`)."
    )
    st.stop()

as_of_options = dates_df["as_of_date"].tolist()
as_of = st.selectbox("As of", as_of_options)

full_df = shared.df_from_query(
    conn,
    """
    SELECT instrument_id, symbol, sector, kpi_sector, sector_phase, mcap, pe, roce, roe,
           ret_1y, pct_52w, flags, gates_passed, fit_bucket, fit_score
      FROM company_fit
     WHERE as_of_date = ?
    """,
    (as_of,),
)

if full_df.empty:
    st.info(f"No company_fit rows for as_of={as_of}.")
    st.stop()

# ---------------------------------------------------------------------------
# Bucket histogram
# ---------------------------------------------------------------------------

st.subheader("Bucket distribution")
bucket_counts = full_df["fit_bucket"].value_counts()
fig = go.Figure(go.Bar(x=bucket_counts.index, y=bucket_counts.values))
fig.update_layout(xaxis_title="fit_bucket", yaxis_title="count", height=350)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

st.subheader("Universe table")
col1, col2, col3 = st.columns(3)

bucket_choices = ["(all)"] + sorted(full_df["fit_bucket"].dropna().unique().tolist())
bucket_filter = col1.selectbox("Bucket", bucket_choices)

sector_choices = ["(all)"] + sorted(full_df["kpi_sector"].dropna().unique().tolist())
sector_filter = col2.selectbox("Sector (registry KPI slug)", sector_choices)

max_mcap = float(full_df["mcap"].max()) if full_df["mcap"].notna().any() else 0.0
min_mcap = col3.number_input("Min market cap", min_value=0.0, max_value=max_mcap if max_mcap > 0 else None, value=0.0, step=1000.0)

filtered = full_df.copy()
if bucket_filter != "(all)":
    filtered = filtered[filtered["fit_bucket"] == bucket_filter]
if sector_filter != "(all)":
    filtered = filtered[filtered["kpi_sector"] == sector_filter]
if min_mcap > 0:
    filtered = filtered[filtered["mcap"].fillna(0) >= min_mcap]

filtered = filtered.sort_values(by="mcap", ascending=False, na_position="last")

st.caption(f"{len(filtered)} of {len(full_df)} instruments shown. Click a row to see details.")
event = st.dataframe(
    filtered,
    use_container_width=True,
    height=420,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "instrument_id": None,
        "symbol": st.column_config.TextColumn("Symbol"),
        "sector": st.column_config.TextColumn("Sector"),
        "kpi_sector": st.column_config.TextColumn("KPI sector"),
        "sector_phase": st.column_config.TextColumn("Sector phase"),
        "mcap": st.column_config.NumberColumn("Mcap", format="%.0f"),
        "pe": st.column_config.NumberColumn("P/E", format="%.1f"),
        "roce": st.column_config.NumberColumn("ROCE", format="%.1f%%"),
        "roe": st.column_config.NumberColumn("ROE", format="%.1f%%"),
        "ret_1y": st.column_config.NumberColumn("Ret 1y", format="%.1f%%"),
        "pct_52w": st.column_config.NumberColumn("52w pos %", format="%.1f%%"),
        "flags": st.column_config.TextColumn("Flags"),
        "gates_passed": st.column_config.NumberColumn("Gates passed", format="%d"),
        "fit_bucket": st.column_config.TextColumn("Fit bucket"),
        "fit_score": st.column_config.ProgressColumn("Fit score", min_value=0, max_value=100, format="%.0f"),
    },
)

st.divider()

# ---------------------------------------------------------------------------
# Row-click drill-in -> compact detail strip + Micro KPI Screen link
# ---------------------------------------------------------------------------

st.subheader("Selected instrument")
selected_rows = event.selection.rows if event and event.selection else []
if not selected_rows:
    st.caption("No row selected — click a row in the table above to see details here.")
else:
    picked_row = filtered.iloc[selected_rows[0]]
    picked = picked_row["symbol"]
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Symbol", picked)
    d2.metric("Fit bucket", picked_row["fit_bucket"] or "-")
    d3.metric("Fit score", shared.fmt_num(picked_row["fit_score"], 0) if picked_row["fit_score"] is not None else "-")
    d4.metric("P/E", shared.fmt_num(picked_row["pe"]) if picked_row["pe"] is not None else "-")
    d5.metric("Sector phase", picked_row["sector_phase"] or "-")
    st.caption(f"Flags: {picked_row['flags'] or '-'} · Gates passed: {picked_row['gates_passed']}")
    st.page_link("pages/4_Micro_KPI_Screen.py", label=f"Open {picked} in Micro KPI Screen")
    st.caption("Micro KPI Screen defaults to its own instrument selector — pick the same symbol there.")
