"""
metrics.py
==========

Performance metrics + report rendering for the backtest: total/period return,
CAGR, max drawdown, win rate, profit factor, average trade, exposure, and a
summary against the stated capital goal.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Dict, List

from .portfolio import ClosedTrade


def compute_metrics(
    equity_curve: List[dict],
    closed: List[ClosedTrade],
    starting_capital: float,
    goal_capital: float,
) -> Dict[str, float]:
    if not equity_curve:
        return {}

    start_eq = starting_capital
    end_eq = equity_curve[-1]["equity"]
    total_return_pct = (end_eq / start_eq - 1.0) * 100.0

    d0 = date.fromisoformat(equity_curve[0]["date"])
    d1 = date.fromisoformat(equity_curve[-1]["date"])
    years = max((d1 - d0).days / 365.25, 1e-9)
    cagr = ((end_eq / start_eq) ** (1 / years) - 1.0) * 100.0 if start_eq > 0 else 0.0

    # Max drawdown on the equity curve.
    peak = -math.inf
    max_dd = 0.0
    for snap in equity_curve:
        eq = snap["equity"]
        peak = max(peak, eq)
        if peak > 0:
            dd = (eq - peak) / peak * 100.0
            max_dd = min(max_dd, dd)

    # Daily-return based volatility / Sharpe / Sortino (rough, rf=0).
    rets = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["equity"]
        cur = equity_curve[i]["equity"]
        if prev > 0:
            rets.append(cur / prev - 1.0)
    daily_vol = 0.0
    annual_vol = 0.0
    downside_dev = 0.0
    sortino = 0.0
    if len(rets) > 1:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        daily_vol = std
        annual_vol = std * math.sqrt(252)
        sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0.0
        # Downside deviation uses only sub-zero daily returns (rf=0 target).
        downs = [r for r in rets if r < 0]
        if downs:
            downside_dev = math.sqrt(sum(r * r for r in downs) / len(rets))
        sortino = (mean / downside_dev * math.sqrt(252)) if downside_dev > 0 else 0.0
    else:
        sharpe = 0.0

    # Trade stats.
    n = len(closed)
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    win_rate = (len(wins) / n * 100.0) if n else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    avg_win = (gross_win / len(wins)) if wins else 0.0
    avg_loss = (-gross_loss / len(losses)) if losses else 0.0
    avg_hold = (sum(t.holding_days for t in closed) / n) if n else 0.0

    # Average exposure (deployed / equity).
    exp = [s["deployed"] / s["equity"] for s in equity_curve if s["equity"] > 0]
    avg_exposure = (sum(exp) / len(exp) * 100.0) if exp else 0.0

    return {
        "start_equity": round(start_eq, 2),
        "end_equity": round(end_eq, 2),
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "daily_vol_pct": round(daily_vol * 100.0, 3),
        "annual_vol_pct": round(annual_vol * 100.0, 2),
        "downside_dev_pct": round(downside_dev * 100.0, 3),
        "num_trades": n,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_holding_days": round(avg_hold, 1),
        "avg_exposure_pct": round(avg_exposure, 1),
        "goal_capital": round(goal_capital, 2),
        "goal_reached": bool(end_eq >= goal_capital),
    }


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
        " SWING BACKTEST — SUMMARY",
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
