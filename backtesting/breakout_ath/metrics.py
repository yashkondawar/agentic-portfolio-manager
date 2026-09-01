"""Headline metrics for a finished ATH breakout run.

The maths lives in :mod:`backtesting.qtr_results.dossier`; this module just
picks the numbers the sleeve reports and returns them as plain floats so they
survive a round trip through JSON.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from backtesting.qtr_results import dossier as shared

from .config import AthBreakoutConfig


def summarise(cfg: AthBreakoutConfig, engine: Any) -> Dict[str, Any]:
    """Return the sleeve's headline metrics, gross of tax.

    Tax is applied by the dossier's reporting layer rather than the engine, so
    these figures are net of brokerage but before capital-gains tax.
    """
    log = engine.daily_log
    if not log:
        return {}

    calendar: List[date] = [date.fromisoformat(r["date"]) for r in log]
    equity = [float(r["equity"]) for r in log]
    rets = shared.daily_returns(equity)

    closed = list(engine.pf.closed)
    wins = [t for t in closed if t.pnl > 0]

    # The shared helpers report percentages; the sleeve reports fractions.
    def frac(value):
        return None if value is None else float(value) / 100.0

    return {
        "start_date": calendar[0].isoformat(),
        "end_date": calendar[-1].isoformat(),
        "sessions": len(calendar),
        "starting_capital": cfg.start_capital,
        "final_value": equity[-1],
        "absolute_return": equity[-1] / cfg.start_capital - 1.0,
        "cagr": frac(shared.cagr(equity, calendar[0], calendar[-1])),
        "max_drawdown": frac(shared.max_drawdown(equity)),
        "volatility": frac(shared.annual_vol(rets)),
        "sharpe": shared.sharpe(rets),
        "sortino": shared.sortino(rets),
        "total_fills": len(engine.pf.fills),
        "round_trips": len(closed),
        "open_positions": len(engine.pf.positions),
        "win_rate": len(wins) / len(closed) if closed else None,
        "avg_holding_days": (
            sum(t.holding_days for t in closed) / len(closed) if closed else None
        ),
        "mean_positions_open": sum(r["open_positions"] for r in log) / len(log),
        "mean_cash_pct": sum(r["cash"] / r["equity"] for r in log if r["equity"])
        / len(log),
        "brokerage_paid": sum(getattr(f, "cost", 0.0) for f in engine.pf.fills),
    }
