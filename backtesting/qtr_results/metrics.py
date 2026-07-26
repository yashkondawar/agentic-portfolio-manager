"""
metrics.py
==========

Performance metrics + summary rendering for the quarterly-results backtest.

The generic metric maths (return, CAGR, max drawdown, Sharpe, win rate, profit
factor, exposure) is reused verbatim from the swing backtest's ``compute_metrics``.
This module adds the pieces an honest earnings-alpha evaluation needs:

* **Deflated Sharpe** — discounts the Sharpe for how many configs were tried, so a
  curve-fit result can't masquerade as an edge (see ``validation.deflated_sharpe_ratio``).
* **Hedged block** — the beta-hedged equity curve's own metrics, i.e. the strategy's
  *alpha* stripped of market direction (the real out-of-sample test).

The summary banner now **leads with Sharpe / deflated Sharpe**, not the CAGR-vs-goal
line, to reflect that the objective is risk-adjusted, selection-bias-aware return —
not a headline CAGR target.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# Reuse the generic performance-stats computation from the swing backtest.
from backtesting.swing_trading.metrics import compute_metrics  # noqa: F401

from .portfolio import ClosedTrade
from .validation import deflated_sharpe_ratio


def daily_returns(equity_curve: List[dict]) -> List[float]:
    """Per-day equity returns from an equity curve (skips non-positive rows)."""
    rets: List[float] = []
    for i in range(1, len(equity_curve)):
        prev = float(equity_curve[i - 1]["equity"])
        cur = float(equity_curve[i]["equity"])
        if prev > 0:
            rets.append(cur / prev - 1.0)
    return rets


def enrich_metrics(
    metrics: Dict[str, float],
    equity_curve: List[dict],
    *,
    num_trials: int = 1,
) -> Dict[str, float]:
    """Add the deflated Sharpe (selection-bias-aware) to a metrics dict.

    ``num_trials`` is the number of configurations explored to arrive at this one;
    passing the honest count is what makes the deflated Sharpe meaningful. Returns a
    NEW dict (does not mutate the input).
    """
    out = dict(metrics)
    dsr = deflated_sharpe_ratio(daily_returns(equity_curve), num_trials=num_trials)
    out["deflated_sharpe"] = round(dsr, 4) if dsr is not None else None
    out["num_trials"] = num_trials
    return out


def hedged_metrics(
    hedged_curve: List[dict],
    closed: List[ClosedTrade],
    starting_capital: float,
    goal_capital: float,
    *,
    num_trials: int = 1,
) -> Dict[str, float]:
    """Metrics for the beta-hedged equity curve — the strategy's market-neutral
    alpha. Reuses the same generic computation so the two curves are comparable."""
    m = compute_metrics(hedged_curve, closed, starting_capital, goal_capital)
    return enrich_metrics(m, hedged_curve, num_trials=num_trials)


def exit_reason_breakdown(closed: List[ClosedTrade]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for t in closed:
        out[t.exit_reason] = out.get(t.exit_reason, 0) + 1
    return out


def render_summary(
    m: Dict[str, float],
    goal_return_pct: float,
    hedged: Optional[Dict[str, float]] = None,
) -> str:
    if not m:
        return "No results."
    pf = m["profit_factor"] if m["profit_factor"] is not None else "∞"
    goal_line = (
        f"✅ GOAL REACHED (+{goal_return_pct:g}%)"
        if m["goal_reached"]
        else f"❌ goal (+{goal_return_pct:g}%) not reached"
    )
    dsr = m.get("deflated_sharpe")
    dsr_str = f"{dsr:.3f}" if isinstance(dsr, (int, float)) else "n/a"
    lines = [
        "════════════════════════════════════════════════════════",
        " QUARTERLY-RESULTS BACKTEST — SUMMARY",
        "════════════════════════════════════════════════════════",
        "  RISK-ADJUSTED (primary objective)",
        f" Sharpe (rf=0)       : {m['sharpe']:.2f}",
        f" Deflated Sharpe     : {dsr_str}   (trials={m.get('num_trials', 1)})",
        f" Max drawdown        : {m['max_drawdown_pct']:.2f}%",
        f" Profit factor       : {pf}",
        f" Win rate            : {m['win_rate_pct']:.2f}%",
        "────────────────────────────────────────────────────────",
        "  RETURN (context, not the target)",
        f" Start equity        : ₹{m['start_equity']:,.2f}",
        f" End equity          : ₹{m['end_equity']:,.2f}",
        f" Total return        : {m['total_return_pct']:+.2f}%   ({goal_line})",
        f" CAGR                : {m['cagr_pct']:+.2f}%",
        f" Avg exposure        : {m['avg_exposure_pct']:.1f}%",
        "────────────────────────────────────────────────────────",
        f" Trades closed       : {m['num_trades']}",
        f" Avg win / avg loss  : ₹{m['avg_win']:,.2f} / ₹{m['avg_loss']:,.2f}",
        f" Avg holding (days)  : {m['avg_holding_days']}",
    ]
    if hedged:
        hdsr = hedged.get("deflated_sharpe")
        hdsr_str = f"{hdsr:.3f}" if isinstance(hdsr, (int, float)) else "n/a"
        lines += [
            "────────────────────────────────────────────────────────",
            "  BETA-HEDGED ALPHA (market-direction removed — the real test)",
            f" Hedged return       : {hedged['total_return_pct']:+.2f}%",
            f" Hedged Sharpe       : {hedged['sharpe']:.2f}",
            f" Hedged defl. Sharpe : {hdsr_str}",
            f" Hedged max drawdown : {hedged['max_drawdown_pct']:.2f}%",
        ]
    lines.append("════════════════════════════════════════════════════════")
    return "\n".join(lines)
