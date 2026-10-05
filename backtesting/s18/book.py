"""Persistent S18 state machine.

The research engine is the replay authority where its prose is ambiguous:
tax-year rollover precedes today's gains, S2 review precedes funding, and cash
shortfalls are shared by slot weight. No reference implementation is imported.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING
import math

import numpy as np

from .config import COST, SCHEMA_VERSION, S18Config, validate_capital

if TYPE_CHECKING:
    from .data import PreparedMarket

TRADE_COLUMNS = [
    "combo",
    "tranche",
    "symbol",
    "sleeve",
    "bought_as",
    "moved_to_S1_on",
    "entry_date",
    "exit_date",
    "entry_px",
    "exit_px",
    "cost_basis",
    "gain",
    "ret_pct",
    "reason",
]


def tax_on(st: float, lt: float, cf_st: float, cf_lt: float):
    """Reference Indian set-off pools, no exemption or loss-expiry modelling."""
    if lt < 0:
        cf_lt -= lt
        lt = 0.0
    if st < 0:
        loss = -st
        st = 0.0
        offset = min(loss, lt)
        lt -= offset
        cf_st += loss - offset
    offset = min(cf_st, st)
    st -= offset
    cf_st -= offset
    offset = min(cf_lt, lt)
    lt -= offset
    cf_lt -= offset
    offset = min(cf_st, lt)
    lt -= offset
    cf_st -= offset
    return 0.20 * st + 0.125 * lt, cf_st, cf_lt


@dataclass
class Position:
    gid: int
    qty: float
    basis: float
    peak: float
    entry_row: int
    s1_since: int
    sleeve: str
    bought_as: str
    promoted_row: int = -1
    armed: bool = False
    queued_sell_reason: str = ""


@dataclass
class Book:
    config: S18Config
    tranche: str
    cash: float = 1.0
    positions: list[Position] = field(default_factory=list)
    queued_buys: list[dict] = field(default_factory=list)
    allowed_history: list[float] = field(default_factory=list)
    realised_st: float = 0.0
    realised_lt: float = 0.0
    carry_st: float = 0.0
    carry_lt: float = 0.0
    tax_paid: float = 0.0
    model_cost: float = 0.0
    last_row: int = -1
    last_date: str = ""
    trades: list[dict] = field(default_factory=list)
    trade_identities: list[str] = field(default_factory=list)
    fills: list[dict] = field(default_factory=list)
    tax_ledger: list[dict] = field(default_factory=list)
    equity: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.tranche not in ("A", "B"):
            raise ValueError("Tranche must be A or B")
        if not math.isfinite(self.cash):
            raise ValueError("Book cash must be finite")

    @classmethod
    def from_cash(cls, config: S18Config, tranche: str, capital: float):
        return cls(config, tranche, validate_capital(capital))

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, state: dict):
        values = deepcopy(state)
        if values.pop("schema_version", None) != SCHEMA_VERSION:
            raise ValueError("Unsupported S18 book schema; replay is required")
        values["config"] = S18Config(**values["config"])
        values["positions"] = [Position(**p) for p in values["positions"]]
        return cls(**values)

    def _gain(self, p: Position, gain: float, market: PreparedMarket, row: int):
        days = int(
            (market.dates[row] - market.dates[p.entry_row]) / np.timedelta64(1, "D")
        )
        if days > 365:
            self.realised_lt += gain
        else:
            self.realised_st += gain

    def _trade(self, p, market, row, px, basis, gain, reason):
        entry_basis_px = p.basis / p.qty
        return {
            "combo": self.config.combo,
            "tranche": self.tranche,
            "symbol": market.symbols[p.gid],
            "sleeve": p.sleeve,
            "bought_as": p.bought_as,
            "moved_to_S1_on": (
                str(market.dates[p.promoted_row]) if p.promoted_row >= 0 else ""
            ),
            "entry_date": str(market.dates[p.entry_row]),
            "exit_date": str(market.dates[row]),
            "entry_px": entry_basis_px * (1 - COST),
            "exit_px": float(px),
            "cost_basis": basis,
            "gain": gain,
            "ret_pct": 100 * (px * (1 - COST) / entry_basis_px - 1),
            "reason": reason,
        }

    def _fill(self, p, market, row, side, px, qty, amount, reason, cost):
        self.fills.append(
            {
                "fill_id": f"{self.tranche}-{len(self.fills) + 1}",
                "date": str(market.dates[row]),
                "identity": market.identities[p.gid],
                "symbol": market.symbols[p.gid],
                "tranche": self.tranche,
                "side": side,
                "sleeve": p.sleeve,
                "qty": qty,
                "price": float(px),
                "amount": amount,
                "reason": reason,
                "model_cost": cost,
                "actual_charges": None,
            }
        )

    def _sell(self, index, market, row, px, reason, fraction=1.0):
        p = self.positions[index]
        q, b = p.qty * fraction, p.basis * fraction
        proceeds = q * px * (1 - COST)
        cost = q * px * COST
        gain = proceeds - b
        self._gain(p, gain, market, row)
        self.cash += proceeds
        self.model_cost += cost
        self.trades.append(self._trade(p, market, row, px, b, gain, reason))
        self.trade_identities.append(market.identities[p.gid])
        self._fill(p, market, row, "SELL", px, q, proceeds, reason, cost)
        if reason == "tax sale":
            p.qty -= q
            p.basis -= b
        else:
            # Research storage uses swap removal; preserve order for tied ranks.
            self.positions[index] = self.positions[-1]
            self.positions.pop()

    def _open(self, market: PreparedMarket, row: int):
        first_april = (
            self.last_date[5:7] == "03" and str(market.dates[row])[5:7] == "04"
        )
        due = 0.0
        if first_april:
            due, cf_st, cf_lt = tax_on(
                self.realised_st, self.realised_lt, self.carry_st, self.carry_lt
            )
            self.tax_ledger.append(
                {
                    "tranche": self.tranche,
                    "payment_date": str(market.dates[row]),
                    "financial_year_end": int(str(market.dates[row])[:4]),
                    "realised_st": self.realised_st,
                    "realised_lt": self.realised_lt,
                    "carry_st_in": self.carry_st,
                    "carry_lt_in": self.carry_lt,
                    "carry_st_out": cf_st,
                    "carry_lt_out": cf_lt,
                    "tax": due,
                }
            )
            self.carry_st, self.carry_lt = cf_st, cf_lt
            self.realised_st = self.realised_lt = 0.0
        j = 0
        while j < len(self.positions):
            p = self.positions[j]
            if row > market.last_rows[p.gid]:
                self._sell(j, market, row, market.close[row, p.gid], "delisted")
            elif p.queued_sell_reason and market.tradable[row, p.gid]:
                self._sell(
                    j, market, row, market.open[row, p.gid], p.queued_sell_reason
                )
            else:
                j += 1
        if first_april:
            self.cash -= due
            self.tax_paid += due
            if self.cash < 0:
                val = sum(
                    p.qty * market.open[row, p.gid]
                    for p in self.positions
                    if market.tradable[row, p.gid]
                )
                if val > 0:
                    fraction = min(1.0, -self.cash / (val * (1 - COST)))
                    for j, p in enumerate(self.positions):
                        if market.tradable[row, p.gid]:
                            self._sell(
                                j,
                                market,
                                row,
                                market.open[row, p.gid],
                                "tax sale",
                                fraction,
                            )
        if self.queued_buys:
            nav_open = self.cash + sum(
                p.qty * market.open[row, p.gid] for p in self.positions
            )
            target = nav_open / self.config.n
            for sleeve in ("S1", "S2"):
                self._buy_sleeve(market, row, sleeve, target)
        self.queued_buys = []

    def _buy_sleeve(self, market, row, sleeve, target):
        weight = lambda g: self.config.weight(g, market.n_stocks)
        slots = self.config.n - sum(
            weight(p.gid) for p in self.positions if p.sleeve == "S1"
        )
        if sleeve == "S2":
            slots -= sum(p.sleeve == "S2" for p in self.positions)
        held = {p.gid for p in self.positions}
        selected = []
        total_weight = 0.0
        for order in self.queued_buys:
            g, w = order["gid"], order["weight"]
            if order["sleeve"] != sleeve or g in held:
                continue
            if not market.tradable[row, g] or row > market.last_rows[g]:
                continue
            if total_weight + w > slots:
                continue
            selected.append((g, w))
            total_weight += w
        done = 0.0
        for g, w in selected:
            if self.cash <= 1e-12:
                break
            amount = min(target * w, self.cash * w / (total_weight - done))
            px = market.open[row, g]
            if px <= 0 or not math.isfinite(px):
                raise ValueError(f"Invalid fill price for {market.symbols[g]}")
            p = Position(
                g,
                amount * (1 - COST) / px,
                amount,
                float(px),
                row,
                row,
                sleeve,
                sleeve,
            )
            self.positions.append(p)
            self.cash -= amount
            self.model_cost += amount * COST
            self._fill(p, market, row, "BUY", px, p.qty, amount, "entry", amount * COST)
            done += w

    def _stops_and_floors(self, market, row):
        j = 0
        while j < len(self.positions):
            p = self.positions[j]
            if p.sleeve == "S1" and p.armed and market.tradable[row, p.gid]:
                stop = p.peak * (1 - self.config.stop_fraction)
                if market.low[row, p.gid] <= stop:
                    self._sell(
                        j,
                        market,
                        row,
                        min(market.open[row, p.gid], stop),
                        "trailing stop",
                    )
                    continue
            j += 1
        for p in self.positions:
            close = market.close[row, p.gid]
            if market.tradable[row, p.gid]:
                p.peak = max(p.peak, float(close))
            if p.sleeve != "S1" or p.queued_sell_reason:
                continue
            age = row - p.s1_since
            gain = p.qty * close / p.basis - 1 if p.basis > 0 else -1.0
            if (age >= 63 and gain < 0.10) or (
                self.config.combo == "P20" and age >= 126 and gain < 0.20
            ):
                p.queued_sell_reason = "floor"

    def decide(self, market: PreparedMarket, row: int, review: bool, order):
        n = self.config.n
        rank = market.sell_rank[row]
        rank2 = market.s2_sell_rank[row]
        if review:
            for p in self.positions:
                if p.sleeve == "S1":
                    p.armed = bool(rank[p.gid] > 3 * n)
        held = {p.gid: p for p in self.positions}
        s1_slots = sum(
            self.config.weight(p.gid, market.n_stocks)
            for p in self.positions
            if p.sleeve == "S1"
        )
        wanted = 0 if market.risk_off[row] else max(0, n - s1_slots)
        reserved = 0
        gate = market.sc15 if self.config.tiered else market.x63
        for raw_gid in order:
            if reserved >= wanted or raw_gid < 0:
                break
            g = int(raw_gid)
            w = self.config.weight(g, market.n_stocks)
            p = held.get(g)
            if p is not None and p.sleeve == "S1":
                continue
            if rank[g] > 3 * n or not gate[row, g] or reserved + w > wanted:
                continue
            if p is not None:
                p.sleeve = "S1"
                p.s1_since = p.promoted_row = row
                p.armed = False
                p.queued_sell_reason = ""
            else:
                self.queued_buys.append({"gid": g, "sleeve": "S1", "weight": w})
            reserved += w
        n1 = s1_slots + reserved
        clearing = n1 >= self.config.clear_threshold
        allowed = 0 if clearing else max(0, n - n1)
        cap = min([allowed, *self.allowed_history])
        self.allowed_history = [*self.allowed_history, allowed][-5:]
        # Monthly momentum reasons take precedence over clear/fund reasons.
        n_review_exits = 0
        if review:
            for p in self.positions:
                if p.sleeve == "S2" and rank2[p.gid] > 15 + 2 * n:
                    p.queued_sell_reason = "momentum"
                    n_review_exits += 1
        s2 = [p for p in self.positions if p.sleeve == "S2"]
        excess = sum(not p.queued_sell_reason for p in s2) - allowed
        funded = 0
        while excess > 0:
            candidates = [p for p in s2 if not p.queued_sell_reason]
            if not candidates:
                break
            worst = max(candidates, key=lambda p: rank2[p.gid])
            worst.queued_sell_reason = "clear S2" if clearing else "fund S1"
            funded += 1
            excess -= 1
        if not review:
            return
        want2 = cap - (len(s2) - n_review_exits - funded)
        queued = {o["gid"] for o in self.queued_buys}
        for raw_gid in market.s2_buy_order[row, 15:]:
            if want2 <= 0 or raw_gid < 0:
                break
            g = int(raw_gid)
            if g in held or g in queued or rank2[g] > 15 + 2 * n:
                continue
            self.queued_buys.append({"gid": g, "sleeve": "S2", "weight": 1})
            want2 -= 1

    def step(
        self,
        market: PreparedMarket,
        row: int,
        *,
        review: bool,
        order,
        initial: bool = False,
        decisions: bool = True,
    ):
        if row < 0 or row >= len(market.dates):
            raise ValueError("S18 row is outside the supplied session panel")
        if self.last_row >= 0 and row != self.last_row + 1:
            raise ValueError("S18 sessions must be processed once, in order")
        if initial and (self.last_row >= 0 or self.positions or self.queued_buys):
            raise ValueError("Initial session requires a new cash book")
        if not initial:
            self._open(market, row)
            self._stops_and_floors(market, row)
        nav = self.cash
        s2_value = 0.0
        for p in self.positions:
            value = p.qty * market.close[row, p.gid]
            nav += value
            if p.sleeve == "S2":
                s2_value += value
        self.equity.append(
            {
                "date": str(market.dates[row]),
                "nav": nav,
                "cash": self.cash,
                "positions": len(self.positions),
                "s2_value": s2_value,
            }
        )
        if decisions:
            self.decide(market, row, review, order)
        self.last_row, self.last_date = row, str(market.dates[row])
        if not all(math.isfinite(v) for v in (self.cash, nav)):
            raise ValueError("Non-finite S18 book value")

    def open_trades(self, market: PreparedMarket) -> list[dict]:
        result = []
        for p in self.positions:
            px = market.close[self.last_row, p.gid]
            gain = p.qty * px * (1 - COST) - p.basis
            result.append(
                self._trade(p, market, self.last_row, px, p.basis, gain, "open at end")
            )
        return result

    def holdings(self, market: PreparedMarket) -> list[dict]:
        return [
            {
                "combo": self.config.combo,
                "tranche": self.tranche,
                "identity": market.identities[p.gid],
                "symbol": market.symbols[p.gid],
                **asdict(p),
                "close": float(market.close[self.last_row, p.gid]),
                "value": p.qty * float(market.close[self.last_row, p.gid]),
                "entry_date": str(market.dates[p.entry_row]),
                "s1_since_date": str(market.dates[p.s1_since]),
                "stop": p.peak * (1 - self.config.stop_fraction) if p.armed else None,
            }
            for p in self.positions
        ]
