"""Micro KPI Screen — instrument selector -> derived_ratios/financials history
+ price summary. Shows whatever is actually stored (derived_ratios metric
names don't yet 1:1 map to every knowledge/ micro KPI id — sector_kpi=1 rows
are flagged so it's clear which ones are registry sector KPIs vs generic
per-instrument ratios)."""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402
from afund.sectors import kpi_key_for_sector  # noqa: E402
from knowledge.loader import load as load_knowledge  # noqa: E402

st.set_page_config(page_title="Micro KPI Screen — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("Micro KPI Screen")

symbols = shared.list_active_symbols(conn)
if not symbols:
    st.info("No active instruments yet. Run the daily_data job (Home page) to populate the universe.")
    st.stop()

symbol = st.selectbox("Instrument", symbols)
instrument = conn.execute(
    "SELECT id, symbol, name, sector, instrument_type FROM instruments WHERE symbol = ? LIMIT 1", (symbol,)
).fetchone()
instrument_id = instrument["id"]
sector = instrument["sector"]
kpi_sector_slug = kpi_key_for_sector(sector)

st.subheader(f"{instrument['symbol']} — {instrument['name'] or '(no name on file)'}")
st.caption(f"Sector: {sector or '-'} (registry KPI slug: {kpi_sector_slug}) · Type: {instrument['instrument_type']}")

# ---------------------------------------------------------------------------
# Price summary
# ---------------------------------------------------------------------------

st.subheader("Price summary")
price_row = conn.execute(
    "SELECT date, close, volume FROM daily_prices WHERE instrument_id = ? ORDER BY date DESC LIMIT 1",
    (instrument_id,),
).fetchone()
if price_row is None:
    st.info("No price history yet for this instrument.")
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Last close", shared.fmt_num(price_row["close"], 2))
    col2.metric("Volume", shared.fmt_num(price_row["volume"], 0) if price_row["volume"] is not None else "-")
    col3.metric("As of", price_row["date"])

price_hist = shared.df_from_query(
    conn,
    "SELECT date, close FROM daily_prices WHERE instrument_id = ? ORDER BY date ASC",
    (instrument_id,),
)
if not price_hist.empty:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=price_hist["date"], y=price_hist["close"], mode="lines", name="Close"))
    fig.update_layout(title="Price history", xaxis_title="Date", yaxis_title="Close")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# derived_ratios history
# ---------------------------------------------------------------------------

st.subheader("Derived ratios")
metrics_df = shared.df_from_query(
    conn,
    "SELECT DISTINCT metric_name, sector_kpi FROM derived_ratios WHERE instrument_id = ? ORDER BY metric_name",
    (instrument_id,),
)
if metrics_df.empty:
    st.info("No derived_ratios rows for this instrument yet.")
else:
    metric_name = st.selectbox(
        "Metric",
        metrics_df["metric_name"].tolist(),
        format_func=lambda m: m + (" (sector KPI)" if metrics_df.loc[metrics_df.metric_name == m, "sector_kpi"].iloc[0] else ""),
    )
    hist = shared.df_from_query(
        conn,
        "SELECT as_of_date, metric_value FROM derived_ratios WHERE instrument_id = ? AND metric_name = ? ORDER BY as_of_date ASC",
        (instrument_id, metric_name),
    )
    if hist.empty:
        st.info("No history for this metric.")
    else:
        latest = hist.iloc[-1]
        st.metric(f"Latest {metric_name}", shared.fmt_num(latest["metric_value"]), help=f"as of {latest['as_of_date']}")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist["as_of_date"], y=hist["metric_value"], mode="lines+markers", name=metric_name))
        fig.update_layout(title=f"{metric_name} history", xaxis_title="Date", yaxis_title=metric_name)
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# financials_quarterly history
# ---------------------------------------------------------------------------

st.subheader("Quarterly financials")
fin_df = shared.df_from_query(
    conn,
    "SELECT period_end, statement_type, revenue, ebitda, operating_profit, net_profit, eps "
    "FROM financials_quarterly WHERE instrument_id = ? ORDER BY period_end ASC",
    (instrument_id,),
)
if fin_df.empty:
    st.info("No financials_quarterly rows for this instrument yet.")
else:
    st.dataframe(fin_df, use_container_width=True)

# ---------------------------------------------------------------------------
# Honest pointer to the registry sector KPI vocabulary + knowledge/ micro defs
# ---------------------------------------------------------------------------

try:
    knowledge = load_knowledge()
    micro_kpis = [k for k in knowledge.kpis.values() if k.scope == "sector"]
    sector_matches = [k for k in micro_kpis if k.registry_xref and kpi_sector_slug in (k.registry_xref or "")]
    if sector_matches:
        st.caption(
            f"knowledge/ defines {len(sector_matches)} micro KPI(s) for sector '{kpi_sector_slug}' "
            f"(status: {', '.join(sorted({k.source_status for k in sector_matches}))}) — "
            "not all are wired to a live derived_ratios column yet; see knowledge/data/kpis/micro/."
        )
except Exception:  # noqa: BLE001 — this footer is best-effort only
    pass
