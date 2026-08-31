"""Macro KPI Screen — knowledge/ KPI defs x macro_series/index_data/derived_series.

KPI selector, timeframe buttons (1y/3y/5y/10y/max), percentile-band shading,
orientation-colored current marker, and honest source_status/staleness
(never fabricates a series for a KPI whose source isn't wired yet).
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402
from knowledge.loader import load as load_knowledge  # noqa: E402

st.set_page_config(page_title="Macro KPI Screen — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("Macro KPI Screen")
st.caption("All framework thresholds shown here are DRAFT until back-tested (CLAUDE.md hard rule).")

try:
    knowledge = load_knowledge()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load knowledge/: {exc}")
    st.stop()

macro_kpis = {kid: k for kid, k in knowledge.kpis.items() if k.scope == "macro"}
if not macro_kpis:
    st.info("No macro KPIs defined in knowledge/data/kpis/.")
    st.stop()

kpi_id = st.selectbox("KPI", sorted(macro_kpis), format_func=lambda k: f"{k} ({macro_kpis[k].source_status})")
kpi = macro_kpis[kpi_id]

status_badge = {"available": "🟢", "derivable": "🟡", "manual": "🟠", "missing": "🔴"}.get(kpi.source_status, "⚪")
st.subheader(f"{status_badge} {kpi_id} — {kpi.source_status}")
st.write(kpi.formula)

meta_cols = st.columns(4)
meta_cols[0].metric("Orientation", kpi.orientation)
meta_cols[1].metric("Cadence", kpi.cadence)
meta_cols[2].metric("Lookback (yrs)", kpi.lookback_years)
meta_cols[3].metric("Cycle refs", ", ".join(kpi.cycle_refs) if kpi.cycle_refs else "-")

if kpi.thresholds:
    st.caption("Thresholds (DRAFT): " + ", ".join(f"{k}={v}" for k, v in kpi.thresholds.items()))

# ---------------------------------------------------------------------------
# Best-effort series resolution from the KPI's own `inputs[].source` prose —
# never fabricated: only macro_series / index_data pointers that regex-match
# a concrete series_code / index_name+field are plotted; anything else is
# reported honestly as not-yet-wired.
# ---------------------------------------------------------------------------

def _resolve_series(kpi_def) -> tuple[str, list[tuple[str, float]]] | None:
    for inp in kpi_def.inputs:
        if inp.status not in ("available", "derivable"):
            continue
        source_text = inp.source
        m = re.search(r"macro_series[,\s]+([A-Z0-9_]+)", source_text)
        if m:
            series_code = m.group(1)
            rows = conn.execute(
                "SELECT date, value FROM macro_series WHERE series_code = ? AND value IS NOT NULL ORDER BY date ASC",
                (series_code,),
            ).fetchall()
            if rows:
                return f"macro_series[{series_code}]", [(r["date"], r["value"]) for r in rows]
        m = re.search(r"index_data\s*\(index_name='([^']+)',\s*(\w+)", source_text)
        if m:
            index_name, field = m.group(1), m.group(2)
            if field in ("pe", "pb", "close", "div_yield"):
                rows = conn.execute(
                    f"SELECT date, {field} AS value FROM index_data WHERE index_name = ? AND {field} IS NOT NULL ORDER BY date ASC",
                    (index_name,),
                ).fetchall()
                if rows:
                    return f"index_data[{index_name}.{field}]", [(r["date"], r["value"]) for r in rows]
    return None


resolved = _resolve_series(kpi)

if resolved is None:
    st.warning(
        f"No queryable series wired for {kpi_id!r} yet (source_status={kpi.source_status}). "
        "Marking honestly as data_pending / missing rather than fabricating a chart."
    )
    st.stop()

series_label, series = resolved
st.caption(f"Series: `{series_label}` ({len(series)} points)")

# Timeframe buttons
timeframe = st.radio("Timeframe", ["1y", "3y", "5y", "10y", "max"], horizontal=True, index=2)
last_date = dt.date.fromisoformat(series[-1][0][:10])
if timeframe == "max":
    cutoff = None
else:
    years = {"1y": 1, "3y": 3, "5y": 5, "10y": 10}[timeframe]
    cutoff = (last_date - dt.timedelta(days=round(years * 365.25))).isoformat()

windowed = [(d, v) for d, v in series if cutoff is None or d >= cutoff]
if not windowed:
    st.info("No data points in the selected timeframe.")
    st.stop()

dates = [d for d, _ in windowed]
values = [v for _, v in windowed]
current_value = values[-1]

# Percentile band shading (based on the full history, not just the window,
# so the band is stable across timeframe clicks).
all_values = [v for _, v in series]
sorted_vals = sorted(all_values)
n = len(sorted_vals)
p10 = sorted_vals[int(0.10 * (n - 1))]
p50 = sorted_vals[int(0.50 * (n - 1))]
p90 = sorted_vals[int(0.90 * (n - 1))]
current_percentile = sum(1 for v in all_values if v <= current_value) / n * 100.0

fig = go.Figure()
fig.add_hrect(y0=min(all_values), y1=p10, fillcolor="LightSkyBlue", opacity=0.15, line_width=0)
fig.add_hrect(y0=p10, y1=p90, fillcolor="LightGrey", opacity=0.12, line_width=0)
fig.add_hrect(y0=p90, y1=max(all_values), fillcolor="LightSalmon", opacity=0.15, line_width=0)
fig.add_trace(go.Scatter(x=dates, y=values, mode="lines", name=kpi_id))

# Orientation-colored current marker: value_type/goldilocks_type -> neutral
# blue; fear_type inverted convention -> red (high = "bad"/capitulation).
marker_color = "crimson" if kpi.orientation == "fear_type" else "seagreen"
fig.add_trace(go.Scatter(
    x=[dates[-1]], y=[current_value], mode="markers", marker=dict(size=14, color=marker_color),
    name=f"current ({kpi.orientation})",
))
fig.update_layout(
    title=f"{kpi_id} — {timeframe} (current percentile vs full history: {current_percentile:.0f})",
    xaxis_title="Date", yaxis_title=kpi_id,
)
st.plotly_chart(fig, use_container_width=True)

col_a, col_b, col_c = st.columns(3)
col_a.metric("Current value", shared.fmt_num(current_value, 4))
col_b.metric("Percentile (full history)", f"{current_percentile:.0f}")
col_c.metric("As of", dates[-1])
