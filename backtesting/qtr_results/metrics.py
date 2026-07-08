"""
metrics.py
==========

Performance metrics + summary rendering for the quarterly-results backtest.

The metric maths (return, CAGR, max drawdown, Sharpe, win rate, profit factor,
exposure) is generic across strategies, so it reuses the swing backtest's
``compute_metrics`` verbatim; only the summary banner is specialised here.
"""

from __future__ import annotations

from typing import Dict, List

# Reuse the generic performance-stats computation from the swing backtest.
from backtesting.swing_trading.metrics import compute_metrics  # noqa: F401

from .portfolio import ClosedTrade


def render_summary(m: Dict[str, float], goal_return_pct: float) -> str:
    if not m:
        return "No results."
    pf = m["profit_factor"] if m["profit_factor"] is not None else "∞"
    goal_line = (
        f"✅ GOAL REACHED (+{goal_return_pct:g}%)"
        if m["goal_reached"]
        else f"❌ goal (+{goal_return_pct:g}%) not reached"
    )
    return "\n".join([
        "════════════════════════════════════════════════════════",
        " QUARTERLY-RESULTS BACKTEST — SUMMARY",
        "════════════════════════════════════════════════════════",
        f" Start equity        : ₹{m['start_equity']:,.2f}",
        f" End equity          : ₹{m['end_equity']:,.2f}",
        f" Total return        : {m['total_return_pct']:+.2f}%   ({goal_line})",
        f" CAGR                : {m['cagr_pct']:+.2f}%",
        f" Max drawdown        : {m['max_drawdown_pct']:.2f}%",
        f" Sharpe (rf=0)       : {m['sharpe']:.2f}",
        f" Avg exposure        : {m['avg_exposure_pct']:.1f}%",
        "────────────────────────────────────────────────────────",
        f" Trades closed       : {m['num_trades']}",
        f" Win rate            : {m['win_rate_pct']:.2f}%",
        f" Profit factor       : {pf}",
        f" Avg win / avg loss  : ₹{m['avg_win']:,.2f} / ₹{m['avg_loss']:,.2f}",
        f" Avg holding (days)  : {m['avg_holding_days']}",
        "════════════════════════════════════════════════════════",
    ])


def exit_reason_breakdown(closed: List[ClosedTrade]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for t in closed:
        out[t.exit_reason] = out.get(t.exit_reason, 0) + 1
    return out
