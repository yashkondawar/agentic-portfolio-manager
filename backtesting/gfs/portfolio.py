"""
portfolio.py
============

Book-keeping only: cash, open positions, partial exits, the realized trade log
and the daily equity curve. Every trading *decision* lives in ``strategy.py``;
this module records consequences and applies costs.

Two things it does that the sibling swing-trading book does not:

* **Explicit slippage.** Commission alone flatters a strategy that buys names on
  the way down. Each fill is moved against us by ``slippage_bps`` in addition to
  the percentage commission.
* **MAE / MFE tracking** (Maximum Adverse / Favourable Excursion), recorded in
  R multiples of the trade's initial risk. This is the evidence needed to answer
  "is a 3-5% stop inside the noise?" - if winning trades routinely dip -1.5R
  before working, a tight stop is destroying the edge rather than protecting it.
"""

# NOTE: intentionally NOT using `from __future__ import annotations`. These
# dataclasses only reference concrete, already-imported types, and stringized
# annotations force dataclasses down a code path that crashes under loaders that
# do not register the module in sys.modules (mirrors swing_trading/portfolio.py).
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional


@dataclass
class Position:
    symbol: str
    sector: str
    quantity: float
    entry_price: float
    entry_date: date
    stop_loss: float
    initial_stop: float
    target_price: float
    atr_at_entry: float
    setup: str = "GFS"
    entry_rsi_d: float = 0.0
    entry_rsi_w: float = 0.0
    entry_rsi_m: float = 0.0
    original_quantity: float = 0.0
    partial_booked: bool = False
    highest_close: float = 0.0
    highest_high: float = 0.0
    lowest_low: float = 0.0

    @property
    def risk_per_share(self) -> float:
        return max(self.entry_price - self.initial_stop, 1e-9)

    def mfe_r(self) -> float:
        """Best unrealized excursion, in multiples of initial risk."""
        return (self.highest_high - self.entry_price) / self.risk_per_share

    def mae_r(self) -> float:
        """Worst unrealized excursion, in multiples of initial risk (<= 0)."""
        return (self.lowest_low - self.entry_price) / self.risk_per_share

    def mfe_pct(self) -> float:
        """Best unrealized excursion as a percentage of the entry price."""
        return (self.highest_high - self.entry_price) / self.entry_price * 100.0

    def mae_pct(self) -> float:
        """Worst unrealized excursion as a percentage of the entry price (<= 0)."""
        return (self.lowest_low - self.entry_price) / self.entry_price * 100.0

    def mark(self, high: float, low: float, close: float) -> None:
        self.highest_high = max(self.highest_high, high)
        self.lowest_low = min(self.lowest_low, low) if self.lowest_low else low
        self.highest_close = max(self.highest_close, close)


@dataclass
class ClosedTrade:
    symbol: str
    sector: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_date: date
    exit_date: date
    pnl: float
    pnl_pct: float
    r_multiple: float
    exit_reason: str
    holding_days: int
    setup: str
    entry_rsi_d: float
    entry_rsi_w: float
    entry_rsi_m: float
    mae_r: float
    mfe_r: float
    mae_pct: float
    mfe_pct: float
    partial: bool


@dataclass
class Portfolio:
    cash: float
    commission_pct: float = 0.05
    slippage_bps: float = 15.0
    positions: Dict[str, Position] = field(default_factory=dict)
    closed: List[ClosedTrade] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)

    # ── Costs ────────────────────────────────────────────────────────────────
    def _commission(self, notional: float) -> float:
        return abs(notional) * self.commission_pct / 100.0

    def buy_fill_price(self, quoted: float) -> float:
        """Quoted price moved against us (we pay up to get filled)."""
        return quoted * (1.0 + self.slippage_bps / 10_000.0)

    def sell_fill_price(self, quoted: float) -> float:
        """Quoted price moved against us (we give up ticks to get out)."""
        return quoted * (1.0 - self.slippage_bps / 10_000.0)

    # ── Open ─────────────────────────────────────────────────────────────────
    def affordable_quantity(self, fill_price: float, desired: float) -> float:
        """Largest whole-share quantity <= ``desired`` that the cash book covers."""
        if fill_price <= 0 or desired <= 0:
            return 0.0
        unit = fill_price * (1.0 + self.commission_pct / 100.0)
        return float(min(int(desired), int(self.cash / unit)))

    def open_position(self, pos: Position) -> bool:
        notional = pos.entry_price * pos.quantity
        cost = self._commission(notional)
        if pos.quantity <= 0 or notional + cost > self.cash + 1e-6:
            return False
        self.cash -= notional + cost
        pos.original_quantity = pos.quantity
        pos.highest_close = pos.entry_price
        pos.highest_high = pos.entry_price
        pos.lowest_low = pos.entry_price
        self.positions[pos.symbol] = pos
        return True

    # ── Close (full or partial) ──────────────────────────────────────────────
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
        if fraction >= 1.0:
            qty = pos.quantity
        else:
            qty = float(int(pos.quantity * fraction))
            # A partial that rounds to zero (or to everything) is not a partial.
            if qty <= 0 or qty >= pos.quantity:
                return None
        if qty <= 0:
            return None

        notional = exit_price * qty
        cost = self._commission(notional)
        self.cash += notional - cost
        pnl = (exit_price - pos.entry_price) * qty - cost
        risk_total = pos.risk_per_share * qty
        trade = ClosedTrade(
            symbol=symbol,
            sector=pos.sector,
            quantity=qty,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_date=pos.entry_date,
            exit_date=exit_date,
            pnl=pnl,
            pnl_pct=(exit_price - pos.entry_price) / pos.entry_price * 100.0,
            r_multiple=pnl / risk_total if risk_total > 0 else 0.0,
            exit_reason=reason,
            holding_days=(exit_date - pos.entry_date).days,
            setup=pos.setup,
            entry_rsi_d=pos.entry_rsi_d,
            entry_rsi_w=pos.entry_rsi_w,
            entry_rsi_m=pos.entry_rsi_m,
            mae_r=pos.mae_r(),
            mfe_r=pos.mfe_r(),
            mae_pct=pos.mae_pct(),
            mfe_pct=pos.mfe_pct(),
            partial=fraction < 1.0,
        )
        self.closed.append(trade)

        remaining = pos.quantity - qty
        if remaining <= 0:
            del self.positions[symbol]
        else:
            pos.quantity = remaining
            pos.partial_booked = True
        return trade

    # ── Valuation ────────────────────────────────────────────────────────────
    def deployed_value(self, price_lookup: Callable[[str], Optional[float]]) -> float:
        total = 0.0
        for sym, pos in self.positions.items():
            px = price_lookup(sym)
            total += pos.quantity * (px if px is not None else pos.entry_price)
        return total

    def total_equity(self, price_lookup: Callable[[str], Optional[float]]) -> float:
        return self.cash + self.deployed_value(price_lookup)

    def sector_exposure(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for pos in self.positions.values():
            counts[pos.sector] = counts.get(pos.sector, 0) + 1
        return counts

    def record_equity(
        self, day: date, price_lookup: Callable[[str], Optional[float]], **extra
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
        snap.update(extra)
        self.equity_curve.append(snap)
        return snap
