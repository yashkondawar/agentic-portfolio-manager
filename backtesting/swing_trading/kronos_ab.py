"""
kronos_ab.py
============

A/B harness: does the Kronos confirmation gate actually improve the swing
playbook? Runs the **same** point-in-time backtest twice over the **same** data
and window — once as the untouched baseline, once with the Kronos gate enabled —
and reports the deltas that matter (hit-rate, CAGR, drawdown, Sharpe, return per
unit of drawdown), plus how many candidates Kronos vetoed.

Prices are downloaded once and shared, so only the gated leg pays the forecast
cost. Everything stays leak-free because the gate only ever sees ``as_of`` slices
(see ``kronos_gate.py``).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Dict, Iterable, Optional

from .config import BacktestConfig
from .service import _build_universe_and_data, run_backtest

logger = logging.getLogger("backtest.kronos_ab")


def run_kronos_ab(
    cfg: BacktestConfig,
    *,
    symbols: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Run baseline vs. Kronos-gated backtests and return a comparison payload."""
    base_cfg = replace(cfg, use_kronos_gate=False)
    universe, market_data = _build_universe_and_data(base_cfg, symbols)

    logger.info("A/B: running BASELINE leg ...")
    baseline = run_backtest(
        base_cfg,
        write_outputs=False,
        market_data=market_data,
        universe=universe,
    )

    gated_cfg = replace(cfg, use_kronos_gate=True)
    logger.info("A/B: running KRONOS-GATED leg ...")
    gated = run_backtest(
        gated_cfg,
        write_outputs=False,
        market_data=market_data,
        universe=universe,
    )

    comparison = _compare(baseline["metrics"], gated["metrics"])
    gate_stats = _gate_stats(gated.get("gate_log", []))
    report = render_ab_report(
        baseline["metrics"], gated["metrics"], comparison, gate_stats, gated_cfg
    )
    return {
        "summary": report,
        "baseline_metrics": baseline["metrics"],
        "gated_metrics": gated["metrics"],
        "comparison": comparison,
        "gate_stats": gate_stats,
        "baseline_trades": baseline["trades"],
        "gated_trades": gated["trades"],
        "universe_size": baseline["universe_size"],
    }


# ── metric diffing ───────────────────────────────────────────────────────────
_DELTA_KEYS = (
    "total_return_pct",
    "cagr_pct",
    "max_drawdown_pct",
    "sharpe",
    "win_rate_pct",
    "profit_factor",
    "num_trades",
    "avg_holding_days",
    "avg_exposure_pct",
)


def _return_per_dd(m: Dict[str, Any]) -> Optional[float]:
    """CAGR per unit of max drawdown — a compact risk-adjusted score."""
    dd = abs(m.get("max_drawdown_pct") or 0.0)
    if dd <= 1e-9:
        return None
    return round((m.get("cagr_pct") or 0.0) / dd, 3)


def _compare(base: Dict[str, Any], gated: Dict[str, Any]) -> Dict[str, Any]:
    deltas: Dict[str, Any] = {}
    for key in _DELTA_KEYS:
        b, g = base.get(key), gated.get(key)
        if isinstance(b, (int, float)) and isinstance(g, (int, float)):
            deltas[key] = round(g - b, 3)
        else:
            deltas[key] = None
    deltas["return_per_dd_base"] = _return_per_dd(base)
    deltas["return_per_dd_gated"] = _return_per_dd(gated)
    deltas["verdict"] = _verdict(base, gated)
    return deltas


def _verdict(base: Dict[str, Any], gated: Dict[str, Any]) -> str:
    """A blunt call on whether the gate earned its keep.

    The gate has to improve BOTH selectivity (hit-rate) AND risk-adjusted
    return to pass — a higher win-rate that tanks total return is not a win.
    """
    b_hit = base.get("win_rate_pct") or 0.0
    g_hit = gated.get("win_rate_pct") or 0.0
    b_rpd = _return_per_dd(base)
    g_rpd = _return_per_dd(gated)
    b_cagr = base.get("cagr_pct") or 0.0
    g_cagr = gated.get("cagr_pct") or 0.0

    if gated.get("num_trades", 0) == 0:
        return "INCONCLUSIVE — gate vetoed every trade; loosen thresholds."
    hit_better = g_hit > b_hit + 0.5
    rpd_better = (b_rpd is not None and g_rpd is not None and g_rpd > b_rpd)
    cagr_better = g_cagr >= b_cagr - 1e-9

    if hit_better and rpd_better and cagr_better:
        return "PASS — higher hit-rate AND better risk-adjusted return. Promote to Phase 2."
    if hit_better and cagr_better:
        return "LEAN PASS — better hit-rate & return, risk-adjusted edge marginal."
    if g_hit > b_hit and g_cagr < b_cagr:
        return "MIXED — gate lifts hit-rate but cuts return (over-filtering winners)."
    return "FAIL — gate did not improve risk-adjusted outcomes on this window."


def _gate_stats(gate_log: list[dict]) -> Dict[str, Any]:
    total = len(gate_log)
    if total == 0:
        return {"evaluated": 0, "vetoed": 0, "kept": 0, "veto_rate_pct": 0.0}
    vetoed = sum(1 for r in gate_log if not r.get("allowed"))
    no_forecast = sum(1 for r in gate_log if r.get("reason") == "no_forecast")
    avoid = sum(1 for r in gate_log if r.get("direction") == "AVOID")
    return {
        "evaluated": total,
        "vetoed": vetoed,
        "kept": total - vetoed,
        "veto_rate_pct": round(vetoed / total * 100.0, 1),
        "no_forecast": no_forecast,
        "avoid_calls": avoid,
    }


# ── reporting ────────────────────────────────────────────────────────────────
def _fmt_delta(value: Optional[float], *, pct: bool = False, higher_better: bool = True) -> str:
    if value is None:
        return "—"
    arrow = ""
    if abs(value) > 1e-9:
        up = value > 0
        good = up if higher_better else not up
        arrow = " ✅" if good else " ⚠️"
    suffix = "%" if pct else ""
    return f"{value:+.2f}{suffix}{arrow}"


def render_ab_report(
    base: Dict[str, Any],
    gated: Dict[str, Any],
    cmp: Dict[str, Any],
    gate_stats: Dict[str, Any],
    cfg: BacktestConfig,
) -> str:
    if not base or not gated:
        return "No results — one or both legs produced no equity curve."

    def row(label, key, *, pct=False, higher_better=True):
        b, g = base.get(key), gated.get(key)
        bs = f"{b:.2f}" if isinstance(b, (int, float)) else "—"
        gs = f"{g:.2f}" if isinstance(g, (int, float)) else "—"
        return (
            f"| {label} | {bs} | {gs} | "
            f"{_fmt_delta(cmp.get(key), pct=pct, higher_better=higher_better)} |"
        )

    lines = [
        "# 🧪 Kronos Gate A/B — Swing Backtest",
        "",
        f"Gate: `{cfg.kronos_model}` · horizon **{cfg.kronos_pred_len}** · "
        f"paths **{cfg.kronos_sample_paths}** · min P(up) **{cfg.kronos_min_prob_up:.0%}** · "
        f"block AVOID **{cfg.kronos_block_avoid}**",
        "",
        f"**Verdict: {cmp.get('verdict')}**",
        "",
        "| Metric | Baseline | Kronos-gated | Δ |",
        "|---|---|---|---|",
        row("Total return %", "total_return_pct", pct=True),
        row("CAGR %", "cagr_pct", pct=True),
        row("Max drawdown %", "max_drawdown_pct", pct=True, higher_better=True),
        row("Sharpe", "sharpe"),
        row("Win rate %", "win_rate_pct", pct=True),
        row("Profit factor", "profit_factor"),
        row("Trades", "num_trades", higher_better=False),
        row("Avg holding (days)", "avg_holding_days", higher_better=False),
        row("Avg exposure %", "avg_exposure_pct", higher_better=False),
        "",
        "**Return per unit drawdown (CAGR ÷ |maxDD|):** "
        f"baseline {cmp.get('return_per_dd_base')} → gated {cmp.get('return_per_dd_gated')}",
        "",
        "### Gate activity",
        f"- Candidates evaluated: **{gate_stats.get('evaluated', 0)}**",
        f"- Vetoed: **{gate_stats.get('vetoed', 0)}** "
        f"({gate_stats.get('veto_rate_pct', 0)}%) · kept: {gate_stats.get('kept', 0)}",
        f"- Explicit AVOID calls: {gate_stats.get('avoid_calls', 0)} · "
        f"no-forecast (data gaps, not vetoed): {gate_stats.get('no_forecast', 0)}",
        "",
        "> Max drawdown Δ: a positive number means a *shallower* (better) drawdown. "
        "Interpret one window with caution — confirm across multiple periods and "
        "with realistic costs before trusting the edge.",
    ]
    return "\n".join(lines)


__all__ = ["run_kronos_ab", "render_ab_report"]
