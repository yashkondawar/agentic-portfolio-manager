"""Book-keeping for the ATH breakout sleeve: cash, positions, fills, trades.

Pure accounting — every trading decision lives in :mod:`engine`. Two details
are specific to this sleeve and are worth stating plainly, because they change
the arithmetic:

* Sizing is *budgeted*, but shares are WHOLE. A slot is handed a rupee budget
  and buys the largest whole number of shares whose cost plus brokerage fits
  inside it. Indian exchanges do not trade fractional equity, so a backtest that
  buys 0.149 shares is measuring a portfolio nobody could have held. Whatever
  the budget cannot cover stays in cash rather than being spent.
* Cost basis is ``quantity x entry price`` and the brokerage is paid on top, so
  net PnL on a round trip is
  ``exit_value - exit_cost - entry_value - entry_cost``. Both commissions are
  charged, and cash moves by exactly the same amount the trade did.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


def whole_share_quantity(budget: float, price: float, cost_rate: float) -> int:
    """Largest whole share count whose value plus brokerage fits in ``budget``.

    Returns 0 when even one share is unaffordable, which is a real constraint
    rather than an edge case: at a 100k book across 28 slots the budget is about
    3,571 rupees, and a name printing 23,830 simply cannot be bought. The caller
    decides what to do about that -- here it is reported honestly as zero.
    """
    if budget <= 0.0 or price <= 0.0:
        return 0
    return int(math.floor(budget / (price * (1.0 + cost_rate))))


@dataclass
class Position:
    """An open holding, with the ratcheting anchor its stop is measured from."""

    symbol: str
    industry: str
    quantity: int
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
    quantity: int
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
    quantity: int
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
    #: Entries declined because one share cost more than the slot budget. Kept
    #: so the run can report how much of the universe its capital locked it out
    #: of, instead of the constraint disappearing into a lower trade count.
    unaffordable: int = 0

    #: Entries declined because the book was already deployed down to loose
    #: change, even though the slot budget itself would have covered a share.
    #: This is the ordinary tail of a full book, not a capital-adequacy limit,
    #: so it is counted apart from ``unaffordable``.
    cash_blocked: int = 0

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
        """Buy whole shares of ``symbol`` within ``budget``, brokerage included.

        Returns ``None`` when not even one share fits, so the caller can offer
        the slot to the next candidate rather than leaving it idle.
        """
        if symbol in self.positions or price <= 0.0:
            return None
        affordable = min(budget, self.cash)
        quantity = whole_share_quantity(affordable, price, self.cost_rate)
        if quantity < 1:
            # Two very different refusals hide behind "could not buy a share",
            # and conflating them makes the count useless for sizing capital.
            # A slot budget too small for one share is a real capital-adequacy
            # limit; a book already deployed down to loose change is just the
            # normal tail of a full book. Count them apart.
            if whole_share_quantity(budget, price, self.cost_rate) < 1:
                self.unaffordable += 1
            elif affordable > 0.0:
                self.cash_blocked += 1
            return None

        value = quantity * price
        cost = value * self.cost_rate
        self.cash -= value + cost
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

        gross_pnl = exit_value - pos.entry_value
        costs = pos.entry_cost + exit_cost
        net_pnl = gross_pnl - costs
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
            costs=costs,
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

