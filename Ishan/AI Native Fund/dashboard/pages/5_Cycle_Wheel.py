"""Cycle Wheel — plotly polar chart of all 16 catalog cycles' latest
assessment for a selected scope, phase-colored, data_pending greyed, plus
the composite/alignment/EVI + allocation-band card. Holdings/watchlist are
positioned by their sector's phase in a companion table. DRAFT watermark
throughout (all thresholds unbacktested per CLAUDE.md)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402
from afund.cycles.assess import all_scopes  # noqa: E402
from afund.sectors import kpi_key_for_sector  # noqa: E402
from knowledge.loader import load as load_knowledge  # noqa: E402

st.set_page_config(page_title="Cycle Wheel — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("Cycle Wheel")
st.warning("DRAFT — cycle framework thresholds, phase multipliers, and allocation bands are unbacktested (CLAUDE.md).")

try:
    knowledge = load_knowledge()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load knowledge/: {exc}")
    st.stop()

scopes = all_scopes()
scope = st.selectbox("Scope", scopes)

latest_date_row = conn.execute(
    "SELECT MAX(as_of_date) AS d FROM cycle_assessments WHERE scope = ?", (scope,)
).fetchone()
as_of = latest_date_row["d"] if latest_date_row else None

if as_of is None:
    st.info(
        f"No cycle_assessments rows for scope={scope!r} yet. Run "
        "`.venv\\Scripts\\python -m afund.orchestrator.run --job weekly_cycle_assessment`."
    )
    st.stop()

rows = conn.execute(
    "SELECT * FROM cycle_assessments WHERE scope = ? AND as_of_date = ?", (scope, as_of)
).fetchall()
by_cycle = {r["cycle_id"]: dict(r) for r in rows}

PHASE_COLORS = {
    "euphoria": "#8e0152", "distribution": "#c51b7d", "denial": "#de77ae",
    "value": "#7fbc41", "deep_value": "#276419", "attractive_growth": "#4d9221",
    "momentum": "#b8e186", "optimism": "#e6f5d0",
}
PENDING_COLOR = "#d9d9d9"

cycle_defs = knowledge.catalog.cycles
n = len(cycle_defs)
theta = [i * 360.0 / n for i in range(n)]
labels = [c.name for c in cycle_defs]

radii, colors, hover = [], [], []
for c in cycle_defs:
    row = by_cycle.get(c.cycle_id)
    if row is None or row.get("data_pending"):
        radii.append(15)  # small stub bar so pending cycles are still visible
        colors.append(PENDING_COLOR)
        missing = json.loads(row["missing_kpis_json"]) if row and row.get("missing_kpis_json") else []
        note = row["note"] if row else "no assessment row"
        hover.append(f"{c.name}: data_pending (missing={missing})<br>{note}")
    else:
        pct = row["percentile"] or 0.0
        radii.append(max(pct, 5))
        colors.append(PHASE_COLORS.get(row["phase_id"], "#999999"))
        hover.append(
            f"{c.name}: phase={row['phase_id']} pct={pct:.0f} dir={row['direction']} "
            f"mom={row['momentum_state']}<br>{row['note'] or ''}"
        )

fig = go.Figure(
    go.Barpolar(
        r=radii, theta=theta, width=[360.0 / n * 0.85] * n,
        marker_color=colors, marker_line_color="white", marker_line_width=1,
        opacity=0.9, text=hover, hoverinfo="text",
    )
)
fig.update_layout(
    title=f"Cycle Wheel — {scope} (as of {as_of})",
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 100], ticksuffix=""),
        angularaxis=dict(tickmode="array", tickvals=theta, ticktext=labels, direction="clockwise"),
    ),
    showlegend=False,
    height=650,
)
wheel_event = st.plotly_chart(
    fig, use_container_width=True, on_select="rerun", selection_mode="points", key="cycle_wheel_chart"
)

legend_cols = st.columns(4)
phase_items = list(PHASE_COLORS.items())
for i, (phase_id, color) in enumerate(phase_items):
    legend_cols[i % 4].markdown(
        f"<span style='color:{color}'>⬤</span> {phase_id}", unsafe_allow_html=True
    )
st.caption("⬤ (grey) = data_pending — no live anchor yet for that catalog cycle.")

st.divider()

# ---------------------------------------------------------------------------
# Selected-wedge detail (click a cycle in the wheel above)
# ---------------------------------------------------------------------------

st.subheader("Selected cycle detail")
selected_points = (
    wheel_event.selection.points if wheel_event and wheel_event.selection else []
)
if not selected_points:
    st.caption("No wedge selected — click a cycle in the wheel above to see its detail here.")
else:
    point_index = selected_points[0]["point_index"]
    selected_cycle = cycle_defs[point_index]
    selected_row = by_cycle.get(selected_cycle.cycle_id)

    st.markdown(f"**{selected_cycle.name}** (`{selected_cycle.cycle_id}`)")
    if selected_row is None or selected_row.get("data_pending"):
        missing = (
            json.loads(selected_row["missing_kpis_json"])
            if selected_row and selected_row.get("missing_kpis_json")
            else []
        )
        st.info(f"data_pending — missing KPIs: {missing or 'unknown'}")
        st.caption((selected_row or {}).get("note") or "no assessment row")
    else:
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Percentile", shared.fmt_num(selected_row["percentile"]) if selected_row["percentile"] is not None else "-")
        sc2.metric("Direction", selected_row["direction"] or "-")
        sc3.metric("Momentum", selected_row["momentum_state"] or "-")
        sc4.metric("Narrative score", shared.fmt_num(selected_row["narrative_intensity_score"]) if selected_row["narrative_intensity_score"] is not None else "-")
        st.markdown(f"**Reconciled phase:** {selected_row['phase_id'] or 'unknown'}")
        if selected_row.get("reconciliation_quadrant"):
            st.caption(f"Reconciliation quadrant: {selected_row['reconciliation_quadrant']}")
        if selected_row["note"]:
            st.caption(selected_row["note"])

        # Filtered holdings/watchlist table for this cycle's scope, where applicable.
        settings_for_detail = shared.get_settings()
        watchlist_for_detail = settings_for_detail.get("universe", {}).get("watchlist", []) or []
        position_rows_for_detail = conn.execute(
            "SELECT i.symbol, i.sector FROM positions p JOIN instruments i ON i.id = p.instrument_id WHERE p.qty != 0"
        ).fetchall()
        holdings_for_detail = {r["symbol"]: r["sector"] for r in position_rows_for_detail}
        watch_rows_for_detail = conn.execute(
            "SELECT symbol, sector FROM instruments WHERE symbol IN ({})".format(
                ",".join("?" for _ in watchlist_for_detail)
            ) if watchlist_for_detail else "SELECT symbol, sector FROM instruments WHERE 0",
            tuple(watchlist_for_detail),
        ).fetchall()
        watch_for_detail = {r["symbol"]: r["sector"] for r in watch_rows_for_detail}

        scoped_rows = []
        for sym, sec in list(holdings_for_detail.items()) + [
            (s, se) for s, se in watch_for_detail.items() if s not in holdings_for_detail
        ]:
            slug = kpi_key_for_sector(sec)
            sym_scope = settings_for_detail.get("sector_index_map", {}).get(slug, "NIFTY 500")
            if sym_scope == scope:
                kind = "holding" if sym in holdings_for_detail else "watchlist"
                scoped_rows.append({"symbol": sym, "kind": kind, "sector": sec or "-"})

        if scope in ("NIFTY 50", "NIFTY 500"):
            st.caption(f"Scope '{scope}' is broad-market — see the full holdings/watchlist table below instead of a per-cycle filter.")
        elif not scoped_rows:
            st.caption(f"No holdings/watchlist instruments mapped to scope '{scope}'.")
        else:
            st.dataframe(scoped_rows, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Composite / alignment / EVI + allocation band card
# ---------------------------------------------------------------------------

composite_row = conn.execute(
    "SELECT * FROM composite_decisions WHERE scope = ? AND as_of_date = ?", (scope, as_of)
).fetchone()

st.subheader("Composite decision")
if composite_row is None:
    st.info("No composite_decisions row for this scope/date.")
else:
    c = dict(composite_row)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Regime", "UNKNOWN" if c["regime_unknown"] else c["regime_cluster"])
    col2.metric("Composite score", shared.fmt_num(c["composite_score"]) if c["composite_score"] is not None else "-")
    col3.metric("Alignment score", shared.fmt_num(c["alignment_score"]) if c["alignment_score"] is not None else "-")
    col4.metric("EVI", shared.fmt_num(c["evi_value"]) if c["evi_value"] is not None else "-")

    evi_missing = json.loads(c["evi_components_missing_json"] or "[]")
    if evi_missing:
        st.caption(f"EVI components missing: {evi_missing}")

    st.markdown(f"**Recommended action (DRAFT):** {c['recommended_action']}")
    if c["allocation_band_json"]:
        band = json.loads(c["allocation_band_json"])
        band_info = band.get("band", {})
        bcol1, bcol2, bcol3, bcol4 = st.columns(4)
        for col, key, label in (
            (bcol1, "equity_pct", "Equity"), (bcol2, "debt_pct", "Debt"),
            (bcol3, "gold_reits_pct", "Gold/REITs"), (bcol4, "cash_pct", "Cash"),
        ):
            rng = band_info.get(key, {})
            col.metric(label, f"{rng.get('min', '-')}-{rng.get('max', '-')}%")
        st.caption(f"Basis: {band.get('basis')} · yield_gap={band.get('yield_gap')}")
    st.caption(c["note"] or "")
    if c["requires_human_review"]:
        st.info("requires_human_review = true (cycle_framework.yaml governance: always HITL).")

st.divider()

# ---------------------------------------------------------------------------
# Holdings / watchlist positioned by sector phase
# ---------------------------------------------------------------------------

st.subheader("Holdings & watchlist by sector phase")

settings = shared.get_settings()
watchlist = settings.get("universe", {}).get("watchlist", []) or []

position_rows = conn.execute(
    "SELECT i.symbol, i.sector FROM positions p JOIN instruments i ON i.id = p.instrument_id WHERE p.qty != 0"
).fetchall()
holdings_symbols = {r["symbol"]: r["sector"] for r in position_rows}

watch_rows = conn.execute(
    "SELECT symbol, sector FROM instruments WHERE symbol IN ({}) ".format(
        ",".join("?" for _ in watchlist)
    ) if watchlist else "SELECT symbol, sector FROM instruments WHERE 0",
    tuple(watchlist),
).fetchall()
watch_sectors = {r["symbol"]: r["sector"] for r in watch_rows}

combined = [(sym, sec, "holding") for sym, sec in holdings_symbols.items()]
combined += [(sym, sec, "watchlist") for sym, sec in watch_sectors.items() if sym not in holdings_symbols]

if not combined:
    st.info("No holdings or watchlist instruments to position.")
else:
    table_rows = []
    for sym, sec, kind in combined:
        slug = kpi_key_for_sector(sec)
        sector_scope = settings.get("sector_index_map", {}).get(slug, "NIFTY 500")
        val_row = conn.execute(
            "SELECT phase_id, percentile, data_pending FROM cycle_assessments "
            "WHERE cycle_id = 'valuation_cycle' AND scope = ? ORDER BY as_of_date DESC LIMIT 1",
            (sector_scope,),
        ).fetchone()
        phase = "data_pending" if (val_row is None or val_row["data_pending"]) else val_row["phase_id"]
        pct = None if (val_row is None or val_row["data_pending"]) else val_row["percentile"]
        table_rows.append({
            "symbol": sym, "kind": kind, "sector": sec or "-", "sector_scope": sector_scope,
            "valuation_phase": phase, "percentile": shared.fmt_num(pct) if pct is not None else "-",
        })
    st.dataframe(table_rows, use_container_width=True)
