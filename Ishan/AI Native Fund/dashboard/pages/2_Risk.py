"""Risk — portfolio risk metrics + cycle-adjusted position limit per holding."""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402
from afund.portfolio import risk  # noqa: E402

st.set_page_config(page_title="Risk — AI-Native Fund", layout="wide")

conn = shared.get_conn()
settings = shared.get_settings()
BENCHMARK = settings.get("portfolio", {}).get("benchmark", "NIFTY 50")
CURRENCY = settings.get("portfolio", {}).get("currency", "INR")

st.title("Risk")
st.caption("Framework thresholds (phase multipliers, sector caps) are DRAFT until back-tested per CLAUDE.md.")

try:
    snap = risk.snapshot(conn)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not compute risk snapshot: {exc}")
    snap = None

if snap is None:
    st.stop()

n = snap["observations"]
if snap["insufficient_history"]:
    st.warning(f"Insufficient history (n={n}) for return-based metrics that need >=30 daily observations.")

col1, col2, col3 = st.columns(3)
col1.metric("Annualized SD", shared.fmt_pct(snap["sd_annualized"]) if snap["sd_annualized"] is not None else f"insufficient history (n={n})")
col2.metric("VaR 95% (1d, %)", shared.fmt_pct(snap["var_95_1d_pct"]) if snap["var_95_1d_pct"] is not None else f"insufficient history (n={n})")
col3.metric("VaR 95% (1d, value)", shared.fmt_money(snap["var_95_1d_value"], CURRENCY) if snap["var_95_1d_value"] is not None else f"insufficient history (n={n})")

col4, col5, col6 = st.columns(3)
col4.metric("Max Drawdown", shared.fmt_num(snap["max_drawdown_pct"]) + "%" if snap["max_drawdown_pct"] is not None else f"insufficient history (n={n})")
col5.metric("Beta vs " + BENCHMARK, shared.fmt_num(snap["beta"]) if snap["beta"] is not None else f"insufficient history (n={n})")
col6.metric("Jensen's Alpha (ann.)", shared.fmt_pct(snap["jensens_alpha_annualized"]) if snap["jensens_alpha_annualized"] is not None else f"insufficient history (n={n})")

conc = snap["concentration"]
st.subheader("Concentration")
c1, c2, c3 = st.columns(3)
c1.metric("Positions", conc["position_count"])
c2.metric("HHI", shared.fmt_num(conc["hhi"], 4) if conc["hhi"] is not None else "-")
c3.metric("Top-5 Weight", shared.fmt_num(conc["top5_weight_pct"]) + "%" if conc["top5_weight_pct"] is not None else "-")

nav_df = shared.df_from_query(conn, "SELECT date, total_nav FROM nav_history ORDER BY date ASC")
if not nav_df.empty and len(nav_df) >= 2:
    peak = nav_df["total_nav"].cummax()
    drawdown = (nav_df["total_nav"] - peak) / peak * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=nav_df["date"], y=drawdown, name="Drawdown %", mode="lines", fill="tozeroy"))
    fig.update_layout(title="Drawdown", xaxis_title="Date", yaxis_title="Drawdown (%)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Drawdown chart needs at least 2 nav_history rows.")

st.divider()

# ---------------------------------------------------------------------------
# Cycle-adjusted position limit per holding (Phase 11 addition)
# ---------------------------------------------------------------------------

st.subheader("Cycle-adjusted position limits (DRAFT)")
st.caption(
    "max_single_position_pct adjusted by each holding's sector valuation-cycle phase multiplier "
    "(registry/rules/risk_limits.yaml -> phase_multipliers). Phase multipliers are DRAFT until back-tested."
)

positions_detail = snap["positions_detail"]
if not positions_detail:
    st.info("No open positions to compute cycle-adjusted limits for.")
else:
    rows = []
    for pos in positions_detail:
        symbol = pos["symbol"]
        instrument_row = conn.execute(
            "SELECT id, sector FROM instruments WHERE symbol = ? LIMIT 1", (symbol,)
        ).fetchone()
        instrument_id = instrument_row["id"] if instrument_row else None
        try:
            limit_info = risk.cycle_adjusted_limit(conn, instrument_id=instrument_id)
        except Exception as exc:  # noqa: BLE001
            rows.append({"symbol": symbol, "weight_pct": pos["weight_pct"], "error": str(exc)})
            continue
        weight_pct = pos["weight_pct"]
        breach = (
            weight_pct is not None
            and limit_info["adjusted_limit_pct"] is not None
            and weight_pct > limit_info["adjusted_limit_pct"]
        )
        rows.append({
            "symbol": symbol,
            "weight_pct": weight_pct,
            "phase_id": limit_info["phase_id"] or "unknown",
            "scope_used": limit_info["scope_used"] or "-",
            "base_limit_pct": limit_info["base_limit_pct"],
            "multiplier": limit_info["multiplier"],
            "adjusted_limit_pct": limit_info["adjusted_limit_pct"],
            "breach": "⚠️ OVER LIMIT" if breach else "OK",
        })
    st.dataframe(
        rows,
        use_container_width=True,
        column_config={
            "symbol": st.column_config.TextColumn("Symbol"),
            "weight_pct": st.column_config.NumberColumn("Weight %", format="%.1f%%"),
            "phase_id": st.column_config.TextColumn("Phase"),
            "scope_used": st.column_config.TextColumn("Scope used"),
            "base_limit_pct": st.column_config.NumberColumn("Base Limit %", format="%.1f%%"),
            "multiplier": st.column_config.NumberColumn("Multiplier", format="%.2fx"),
            "adjusted_limit_pct": st.column_config.NumberColumn("Adjusted Limit %", format="%.1f%%"),
            "breach": st.column_config.TextColumn("Breach"),
        },
    )
