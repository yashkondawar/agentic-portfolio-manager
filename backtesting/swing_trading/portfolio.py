"""
portfolio.py
============

Book-keeping for the backtest: cash, open positions, realized trade log and the
daily equity curve. Pure accounting — all trading DECISIONS live in
``strategy.py``; this module only records the consequences and applies costs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class CostModel:
    """Realistic Indian equity **delivery** (CNC) transaction costs.

    All ``*_pct`` values are a percentage of the traded notional. ``slippage_bps``
    models spread + market impact and is applied per side in basis points. STT and
    the exchange/SEBI/GST stack apply on both buy and sell; stamp duty is buy-only.
    """

    brokerage_pct: float = 0.0  # discount brokers: free delivery
    stt_pct: float = 0.1  # securities transaction tax, per side
    exchange_txn_pct: float = 0.00297  # NSE transaction charge
    sebi_pct: float = 0.0001  # SEBI turnover fee (₹10 / crore)
    gst_pct: float = 18.0  # GST on brokerage + exchange + SEBI
    stamp_duty_pct: float = 0.015  # buy side only
    slippage_bps: float = 5.0  # spread + impact, per side

    def charge(self, notional: float, side: str = "buy") -> float:
        if notional <= 0:
            return 0.0
        brokerage = notional * self.brokerage_pct / 100.0
        stt = notional * self.stt_pct / 100.0
        exchange = notional * self.exchange_txn_pct / 100.0
        sebi = notional * self.sebi_pct / 100.0
        gst = (brokerage + exchange + sebi) * self.gst_pct / 100.0
        stamp = notional * self.stamp_duty_pct / 100.0 if side == "buy" else 0.0
        slippage = notional * self.slippage_bps / 1e4
        return brokerage + stt + exchange + sebi + gst + stamp + slippage


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    entry_date: date
    stop_loss: float
    target_price: float
    initial_stop: float
    atr_at_entry: float
    setup: str = "Momentum"
    partial_booked: bool = False
    highest_close: float = 0.0  # for trailing-stop logic
    breakout_level: float = 0.0
    breakout_signal_date: Optional[date] = None
    highest_high: float = 0.0
    below_breakout_closes: int = 0
    bars_held: int = 0
    trailing_active: bool = False

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
    setup: str


@dataclass
class Portfolio:
    cash: float
    commission_pct: float = 0.05
    cost_model: Optional[CostModel] = None
    positions: Dict[str, Position] = field(default_factory=dict)
    closed: List[ClosedTrade] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)

    # ── Costs ─────────────────────────────────────────────────────────────────
    def _cost(self, notional: float, side: str = "buy") -> float:
        if self.cost_model is not None:
            return self.cost_model.charge(notional, side)
        return notional * self.commission_pct / 100.0

    # ── Open / add ────────────────────────────────────────────────────────────
    def can_afford(self, price: float, quantity: float) -> bool:
        notional = price * quantity
        return notional + self._cost(notional, "buy") <= self.cash + 1e-6

    def open_position(self, pos: Position) -> bool:
        notional = pos.entry_price * pos.quantity
        cost = self._cost(notional, "buy")
        if notional + cost > self.cash + 1e-6:
            return False
        self.cash -= notional + cost
        pos.highest_close = pos.entry_price
        self.positions[pos.symbol] = pos
        return True

    # ── Close (full or partial) ───────────────────────────────────────────────
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_date: date,
        reason: str,
        fraction: float = 1.0,
    ) -> Optional[ClosedTrade]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        qty = pos.quantity * fraction
        qty = float(int(qty)) if fraction < 1.0 else pos.quantity
        if qty <= 0:
            return None
        notional = exit_price * qty
        cost = self._cost(notional, "sell")
        self.cash += notional - cost
        entry_cost = self._cost(pos.entry_price * qty, "buy")
        pnl = (exit_price - pos.entry_price) * qty - entry_cost - cost
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
            setup=pos.setup,
        )
        self.closed.append(trade)

        remaining = pos.quantity - qty
        if remaining <= 0:
            del self.positions[symbol]
        else:
            pos.quantity = remaining
            pos.partial_booked = True
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

    def record_equity(
        self, day: date, price_lookup: Callable[[str], Optional[float]]
    ) -> dict:
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
