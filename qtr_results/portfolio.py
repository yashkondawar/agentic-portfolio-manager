"""Capital overlay for the live quarterly-results strategy.

The live strategy was previously a pure signal tracker with no money model, so
it emitted no quantity, no rupee amount and no risk figure. This module adds the
same capital layer the backtest uses -- a persisted cash balance plus the exact
risk-based sizing rule -- so every pick now carries a concrete share count,
invested amount and rupee risk, and the book respects a max open-position count.

State lives in ``state/portfolio.json``:
    {"starting_capital": 500000.0, "cash": 483210.0, "realized_pnl": 12345.0}

``cash`` is decremented (incl. commission) when a position is opened and credited
back (net of commission) when it closes. ``equity`` = cash + marked value of the
open book. Everything degrades safely: a missing/corrupt file re-seeds from the
configured ``STARTING_CAPITAL``.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qtr_results import config

logger = logging.getLogger("qtr_results.portfolio")


@dataclass
class Portfolio:
    starting_capital: float
    cash: float
    realized_pnl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "starting_capital": round(self.starting_capital, 2),
            "cash": round(self.cash, 2),
            "realized_pnl": round(self.realized_pnl, 2),
        }


def load_portfolio(starting_capital: Optional[float] = None) -> Portfolio:
    """Load the persisted portfolio, seeding a fresh one on first use.

    ``starting_capital`` (from the run params) seeds a brand-new portfolio; an
    existing file keeps its own starting_capital so history is stable across runs.
    """
    seed = starting_capital if starting_capital is not None else config.STARTING_CAPITAL
    if not config.PORTFOLIO_PATH.exists():
        return Portfolio(starting_capital=seed, cash=seed)
    try:
        raw = json.loads(config.PORTFOLIO_PATH.read_text(encoding="utf-8"))
        return Portfolio(
            starting_capital=float(raw.get("starting_capital", seed)),
            cash=float(raw.get("cash", seed)),
            realized_pnl=float(raw.get("realized_pnl", 0.0)),
        )
    except (ValueError, OSError, TypeError) as e:
        logger.warning("Could not read portfolio (%s); re-seeding from ₹%.0f.", e, seed)
        return Portfolio(starting_capital=seed, cash=seed)


def save_portfolio(pf: Portfolio) -> None:
    config.ensure_state_dir()
    config.PORTFOLIO_PATH.write_text(
        json.dumps(pf.to_dict(), indent=2), encoding="utf-8"
    )


def _cost(notional: float) -> float:
    return abs(notional) * config.COMMISSION_PCT / 100.0


def marked_equity(pf: Portfolio, open_positions: List[Dict[str, Any]]) -> float:
    """Cash + last-marked value of the open book (falls back to entry price)."""
    book = 0.0
    for p in open_positions:
        qty = p.get("quantity") or 0
        price = p.get("last_price") or p.get("entry_price") or 0.0
        book += qty * price
    return pf.cash + book


def size_position(
    entry_price: float,
    stop_distance: float,
    equity: float,
    cash: float,
    *,
    risk_per_trade_pct: float,
    max_position_pct: float,
) -> int:
    """Shares to buy under the risk rule + concentration + cash caps.

    ``stop_distance`` is the absolute ₹ per-share risk (ATR-based). Returns 0 when
    the trade is not takeable with the current capital. Mirrors the backtest's
    ``strategy.size_position`` exactly so live and backtest size identically.
    """
    if entry_price <= 0 or stop_distance <= 0:
        return 0
    risk_budget = equity * risk_per_trade_pct / 100.0
    shares = math.floor(risk_budget / stop_distance)
    max_notional = equity * max_position_pct / 100.0
    shares = min(shares, math.floor(max_notional / entry_price))
    affordable = math.floor((cash * 0.999) / entry_price)
    shares = min(shares, affordable)
    return max(shares, 0)


def apply_buy(pf: Portfolio, entry_price: float, quantity: int) -> float:
    """Debit cash for a buy (notional + commission); returns invested notional."""
    notional = entry_price * quantity
    pf.cash -= notional + _cost(notional)
    return notional


def apply_close(pf: Portfolio, exit_price: float, quantity: int) -> None:
    """Credit cash for a close (proceeds net of commission)."""
    proceeds = exit_price * quantity
    pf.cash += proceeds - _cost(proceeds)


def record_realized(pf: Portfolio, entry_price: float, exit_price: float, quantity: int) -> None:
    """Accumulate realised P&L (net of both-side commission) for reporting."""
    gross = (exit_price - entry_price) * quantity
    pf.realized_pnl += gross - _cost(entry_price * quantity) - _cost(exit_price * quantity)
