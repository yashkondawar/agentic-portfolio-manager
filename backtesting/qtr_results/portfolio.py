"""
portfolio.py
============

Book-keeping for the quarterly-results backtest: cash, open positions, the
realized trade log and the daily equity curve. Pure accounting — every trading
DECISION lives in ``strategy.py`` / ``engine.py``; this module only records the
consequences and applies a simple per-side commission.

The ``Position`` fields mirror the live ledger entry (``qtr_results.ledger``):
entry/target/trailing-stop, the ratcheting ``highest_price`` the trailing stop is
measured from, and the strategy metadata carried through to the trade log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    entry_date: date
    target_price: float
    target_pct: float
    trailing_stop_pct: float          # informational (approx. stop as % of entry)
    stop_distance: float              # absolute ₹ trailing-stop distance (ATR-based)
    stop_price: float
    highest_price: float            # ratchets up; trailing stop measured off this
    sector: str = "UNKNOWN"          # yfinance-derived sector for concentration cap
    result_quarter: str = ""
    result_date: str = ""
    method: str = "static"
    strength_score: float = 0.0
    rationale: str = ""
    # ── B10 anticipation-mode state ──────────────────────────────────────────
    awaiting_result: bool = False          # entered pre-declaration, result pending
    result_signal_date: Optional[date] = None  # day the result becomes known
    result_q_idx: int = -1                 # quarter index to grade on that day
    exit_at_open_reason: Optional[str] = None  # set to dump at next open (weak result)

    @property
    def invested(self) -> float:
        return self.quantity * self.entry_price

    def value(self, price: float) -> float:
        return self.quantity * price

    def pnl_pct(self, price: float) -> float:
        if not self.entry_price:
            return 0.0
        return (price - self.entry_price) / self.entry_price * 100.0


@dataclass
class ClosedTrade:
    symbol: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_date: date
    exit_date: date
    pnl: float
    pnl_pct: float
    exit_reason: str
    holding_days: int
    result_quarter: str
    method: str
    strength_score: float
    sector: str = "UNKNOWN"


@dataclass
class Portfolio:
    cash: float
    commission_pct: float = 0.05
    positions: Dict[str, Position] = field(default_factory=dict)
    closed: List[ClosedTrade] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)

    # ── Costs ─────────────────────────────────────────────────────────────────
    def _cost(self, notional: float) -> float:
        return notional * self.commission_pct / 100.0

    # ── Open ──────────────────────────────────────────────────────────────────
    def has_open(self, symbol: str) -> bool:
        return symbol in self.positions

    def open_position(self, pos: Position) -> bool:
        notional = pos.entry_price * pos.quantity
        cost = self._cost(notional)
        if notional + cost > self.cash + 1e-6:
            return False
        self.cash -= notional + cost
        self.positions[pos.symbol] = pos
        return True

    # ── Close (full) ──────────────────────────────────────────────────────────
    def close_position(
        self, symbol: str, exit_price: float, exit_date: date, reason: str
    ) -> Optional[ClosedTrade]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        qty = pos.quantity
        notional = exit_price * qty
        cost = self._cost(notional)
        self.cash += notional - cost
        # Net PnL charges BOTH legs' commission (entry cost was paid at open).
        entry_cost = self._cost(pos.entry_price * qty)
        pnl = (exit_price - pos.entry_price) * qty - cost - entry_cost
        trade = ClosedTrade(
            symbol=symbol,
            quantity=qty,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_date=pos.entry_date,
            exit_date=exit_date,
            pnl=pnl,
            pnl_pct=(exit_price - pos.entry_price) / pos.entry_price * 100.0,
            exit_reason=reason,
            holding_days=(exit_date - pos.entry_date).days,
            result_quarter=pos.result_quarter,
            method=pos.method,
            strength_score=pos.strength_score,
            sector=pos.sector,
        )
        self.closed.append(trade)
        del self.positions[symbol]
        return trade

    # ── Valuation ─────────────────────────────────────────────────────────────
    def deployed_value(self, price_lookup: Callable[[str], Optional[float]]) -> float:
        total = 0.0
        for sym, pos in self.positions.items():
            px = price_lookup(sym)
            total += pos.value(px if px is not None else pos.entry_price)
        return total

    def total_equity(self, price_lookup: Callable[[str], Optional[float]]) -> float:
        return self.cash + self.deployed_value(price_lookup)

    def sector_deployed(
        self, sector: str, price_lookup: Callable[[str], Optional[float]]
    ) -> float:
        """Rupee notional currently deployed in ``sector`` (marked to market)."""
        total = 0.0
        for pos in self.positions.values():
            if pos.sector != sector:
                continue
            px = price_lookup(pos.symbol)
            total += pos.value(px if px is not None else pos.entry_price)
        return total

    def record_equity(self, day: date, price_lookup: Callable[[str], Optional[float]]) -> dict:
        deployed = self.deployed_value(price_lookup)
        equity = self.cash + deployed
        snap = {
            "date": day.isoformat(),
            "equity": round(equity, 2),
            "cash": round(self.cash, 2),
            "deployed": round(deployed, 2),
            "open_positions": len(self.positions),
        }
        self.equity_curve.append(snap)
        return snap
