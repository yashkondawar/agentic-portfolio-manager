"""Book-keeping for the ATH breakout sleeve: cash, positions, fills, trades.

Pure accounting — every trading decision lives in :mod:`engine`. Two details
are specific to this sleeve and are worth stating plainly, because they change
the arithmetic:

* Sizing is *budgeted*, not share-based. A slot is handed a rupee budget, the
  brokerage is taken **out of** that budget, and whatever is left buys
  fractional shares. Cash therefore falls by the whole budget on entry.
* Because the entry commission was already deducted from the budget, it is not
  part of the cost basis. Net PnL on the way out is
  ``exit_value - exit_cost - entry_value``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class Position:
    """An open holding, with the ratcheting anchor its stop is measured from."""

    symbol: str
    industry: str
    quantity: float
    entry_price: float
    entry_date: date
    entry_value: float
    entry_cost: float
    anchor: float
    stop_level: float

    def value(self, price: float) -> float:
        return self.quantity * price

    def mark(self, price: float, stop_multiple: float) -> None:
        """Ratchet the anchor to a new closing high and re-derive the stop."""
        if price > self.anchor:
            self.anchor = price
            self.stop_level = price * stop_multiple


@dataclass
class ClosedTrade:
    symbol: str
    industry: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_date: date
    exit_date: date
    pnl: float
    pnl_pct: float
    exit_reason: str
    holding_days: int
    gross_pnl: float
    costs: float
    entry_value: float
    exit_value: float

    @property
    def sector(self) -> str:
        """Alias so the shared dossier helpers can read the label."""
        return self.industry


@dataclass
class Fill:
    """One executed leg, journalled in order so the blotter is chronological."""

    seq: int
    day: date
    symbol: str
    industry: str
    side: str
    reason: str
    quantity: float
    price: float
    value: float
    cost: float
    cash_after: float
    entry_price: float
    anchor: float
    stop_level: float
    net_pnl: float = 0.0
    holding_days: int = 0

    @property
    def sector(self) -> str:
        """Alias so the shared dossier helpers can read the label."""
        return self.industry


@dataclass
class Portfolio:
    cash: float
    cost_rate: float = 0.0025
    stop_multiple: float = 0.84
    positions: Dict[str, Position] = field(default_factory=dict)
    closed: List[ClosedTrade] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)

    # ── Valuation ────────────────────────────────────────────────────────────
    def deployed(self, prices: Dict[str, float]) -> float:
        total = 0.0
        for symbol, pos in self.positions.items():
            price = prices.get(symbol)
            total += pos.value(price if price is not None else pos.entry_price)
        return total

    def equity(self, prices: Dict[str, float]) -> float:
        return self.cash + self.deployed(prices)

    def _journal(self, **kwargs) -> Fill:
        fill = Fill(seq=len(self.fills) + 1, **kwargs)
        self.fills.append(fill)
        return fill

    # ── Open ─────────────────────────────────────────────────────────────────
    def open_position(
        self,
        *,
        symbol: str,
        industry: str,
        price: float,
        day: date,
        budget: float,
        reason: str = "ENTRY",
    ) -> Optional[Position]:
        """Spend ``budget`` on ``symbol``; the commission comes out of it."""
        if symbol in self.positions or price <= 0.0:
            return None
        budget = min(budget, self.cash)
        if budget <= 0.0:
            return None
        cost = budget * self.cost_rate
        value = budget - cost
        quantity = value / price
        if quantity <= 0.0:
            return None

        self.cash -= budget
        pos = Position(
            symbol=symbol,
            industry=industry,
            quantity=quantity,
            entry_price=price,
            entry_date=day,
            entry_value=value,
            entry_cost=cost,
            anchor=price,
            stop_level=price * self.stop_multiple,
        )
        self.positions[symbol] = pos
        self._journal(
            day=day,
            symbol=symbol,
            industry=industry,
            side="BUY",
            reason=reason,
            quantity=quantity,
            price=price,
            value=value,
            cost=cost,
            cash_after=self.cash,
            entry_price=price,
            anchor=pos.anchor,
            stop_level=pos.stop_level,
        )
        return pos

    # ── Close ────────────────────────────────────────────────────────────────
    def close_position(
        self, symbol: str, *, price: float, day: date, reason: str
    ) -> Optional[ClosedTrade]:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return None

        exit_value = pos.quantity * price
        exit_cost = exit_value * self.cost_rate
        self.cash += exit_value - exit_cost

        net_pnl = exit_value - exit_cost - pos.entry_value
        gross_pnl = exit_value - (pos.entry_value + pos.entry_cost)
        holding_days = (day - pos.entry_date).days
        trade = ClosedTrade(
            symbol=symbol,
            industry=pos.industry,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            exit_price=price,
            entry_date=pos.entry_date,
            exit_date=day,
            pnl=net_pnl,
            pnl_pct=(price / pos.entry_price - 1.0) * 100.0,
            exit_reason=reason,
            holding_days=holding_days,
            gross_pnl=gross_pnl,
            costs=pos.entry_cost + exit_cost,
            entry_value=pos.entry_value,
            exit_value=exit_value,
        )
        self.closed.append(trade)
        self._journal(
            day=day,
            symbol=symbol,
            industry=pos.industry,
            side="SELL",
            reason=reason,
            quantity=pos.quantity,
            price=price,
            value=exit_value,
            cost=exit_cost,
            cash_after=self.cash,
            entry_price=pos.entry_price,
            anchor=pos.anchor,
            stop_level=pos.stop_level,
            net_pnl=net_pnl,
            holding_days=holding_days,
        )
        return trade
