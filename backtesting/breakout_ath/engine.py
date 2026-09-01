"""The ATH breakout backtest loop.

One pass over the trading calendar. On each session, in order:

1. **Mark** every open position to the close and ratchet its anchor up.
2. **Exit** anything whose close is below its trailing stop, filled at that
   close. A gap straight through the stop is filled where the stock actually
   traded, so the realised loss can exceed ``sl_pct`` — that is deliberate, and
   is what a real stop would have done.
3. **Enter** the best-ranked eligible names into whatever slots are free.

Sizing is budgeted rather than share-based: the slot budget is recomputed from
equity at each reset boundary and then held fixed, so within a quarter every
new position is the same rupee size regardless of what the market did. When
cash has run short the budget is trimmed to what is actually available, which
is why a handful of positions each quarter come in smaller than the rest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

import pandas as pd

from backtesting.breakout_ath import signals
from backtesting.breakout_ath.config import AthBreakoutConfig
from backtesting.breakout_ath.portfolio import Portfolio

logger = logging.getLogger(__name__)

_RESET_FREQ = {"Q": "Q", "M": "M", "A": "Y", "Y": "Y"}


@dataclass
class PriceBundle:
    """Closes for the universe plus the benchmarks, aligned on one calendar."""

    closes: pd.DataFrame
    industries: Dict[str, str] = field(default_factory=dict)
    benchmark: Optional[pd.DataFrame] = None
    broad: Optional[pd.DataFrame] = None

    @property
    def frames(self) -> Dict[str, pd.DataFrame]:
        """Per-symbol frames, for the equal-weight universe benchmark."""
        return {
            col: self.closes[[col]].dropna().rename(columns={col: "Close"})
            for col in self.closes.columns
        }


def _reset_key(day: date, freq: str) -> object:
    """The bucket a day belongs to, or a constant when resets are disabled."""
    alias = _RESET_FREQ.get(freq)
    if alias is None:
        return "never"
    return pd.Period(pd.Timestamp(day), freq=alias)


class AthBreakoutEngine:
    """Runs the sleeve over a price bundle and records the result."""

    def __init__(self, cfg: AthBreakoutConfig, prices: PriceBundle) -> None:
        cfg.validate()
        self.cfg = cfg
        self.prices = prices
        self.pf = Portfolio(
            cash=cfg.start_capital,
            cost_rate=cfg.cost_rate,
            stop_multiple=cfg.stop_multiple,
        )
        self.daily_log: List[dict] = []
        self._budget = cfg.start_capital / cfg.max_positions
        self._budget_key: object = None

    # ── Setup ────────────────────────────────────────────────────────────────
    def _prepare(self) -> Sequence[pd.Timestamp]:
        cfg, closes = self.cfg, self.prices.closes
        # Aligning 750 names on one calendar leaves a NaN wherever a stock had
        # no bar, and a single NaN voids a 252-session rolling window. Features
        # are therefore computed on a forward-filled matrix — carrying a price
        # forward cannot change a running maximum — while eligibility is masked
        # back to sessions the stock actually traded, so a stale quote can never
        # manufacture a breakout.
        self.tradeable = closes.notna()
        self.filled = closes.ffill()
        self.entries = (
            signals.entry_matrix(
                self.filled, lookback=cfg.lookback, floor=cfg.ath_floor
            )
            & self.tradeable
        )
        self.ranks = signals.ranking_matrix(
            self.filled, cfg.selection_rule, cfg.momentum_lookback
        )
        self._stale = {symbol: 0 for symbol in closes.columns}
        calendar = closes.index
        if cfg.start_date is not None:
            calendar = calendar[calendar >= pd.Timestamp(cfg.start_date)]
        if cfg.end_date is not None:
            calendar = calendar[calendar <= pd.Timestamp(cfg.end_date)]
        return calendar

    # ── Per-day steps ────────────────────────────────────────────────────────
    def _mark(self, prices: Dict[str, float]) -> None:
        for symbol, pos in self.pf.positions.items():
            price = prices.get(symbol)
            if price is not None and price > 0.0:
                pos.mark(price, self.cfg.stop_multiple)

    def _exits(self, day: date, prices: Dict[str, float]) -> None:
        breached = [
            symbol
            for symbol, pos in self.pf.positions.items()
            if (price := prices.get(symbol)) is not None and price < pos.stop_level
        ]
        for symbol in breached:
            self.pf.close_position(
                symbol, price=prices[symbol], day=day, reason="TRAIL_SL"
            )

    def _track_staleness(self, live: pd.Series) -> None:
        traded = live.to_numpy()
        for symbol, is_live in zip(live.index, traded):
            self._stale[symbol] = 0 if is_live else self._stale[symbol] + 1

    def _delistings(self, day: date, prices: Dict[str, float]) -> None:
        """Book out anything that has simply stopped printing a price.

        A suspension, merger or delisting leaves the trailing stop unable to
        fire, so the position would otherwise be marked at a frozen price for
        the rest of the run. Held names that go quiet for a whole trading month
        are closed at their last traded price instead.
        """
        gone = [
            symbol
            for symbol in self.pf.positions
            if self._stale.get(symbol, 0) >= self.cfg.stale_exit_sessions
        ]
        for symbol in gone:
            price = prices.get(symbol)
            if price is None:
                continue
            self.pf.close_position(
                symbol, price=price, day=day, reason="CORPORATE_ACTION"
            )

    def _refresh_budget(self, day: date, prices: Dict[str, float]) -> None:
        key = _reset_key(day, self.cfg.slot_reset_freq)
        if key != self._budget_key:
            self._budget_key = key
            self._budget = self.pf.equity(prices) / self.cfg.max_positions

    def _entries(
        self, day: date, stamp: pd.Timestamp, prices: Dict[str, float]
    ) -> None:
        free = self.cfg.max_positions - len(self.pf.positions)
        if free <= 0 or self.pf.cash <= 0.0:
            return

        eligible = self.entries.loc[stamp]
        candidates = [
            symbol
            for symbol in eligible.index[eligible.to_numpy()]
            if symbol not in self.pf.positions and prices.get(symbol, 0.0) > 0.0
        ]
        if not candidates:
            return
        scores = self.ranks.loc[stamp]
        candidates.sort(key=lambda s: (-_score(scores.get(s)), s))

        industries = self.prices.industries
        for symbol in candidates[:free]:
            if self.pf.cash <= 0.0:
                break
            self.pf.open_position(
                symbol=symbol,
                industry=industries.get(symbol, "Unknown"),
                price=prices[symbol],
                day=day,
                budget=self._budget,
            )

    # ── Main loop ────────────────────────────────────────────────────────────
    def run(self) -> "AthBreakoutEngine":
        calendar = self._prepare()
        if len(calendar) == 0:
            raise ValueError("No trading sessions in the requested window")

        for stamp in calendar:
            day = stamp.date()
            row = self.filled.loc[stamp]
            live = self.tradeable.loc[stamp]
            prices = {s: float(p) for s, p in row.items() if pd.notna(p)}

            self._track_staleness(live)
            self._mark(prices)
            self._exits(day, prices)
            self._delistings(day, prices)
            self._refresh_budget(day, prices)
            self._entries(day, stamp, prices)

            deployed = self.pf.deployed(prices)
            equity = self.pf.cash + deployed
            self.daily_log.append(
                {
                    "date": day.isoformat(),
                    "equity": equity,
                    "cash": self.pf.cash,
                    "deployed": deployed,
                    "open_positions": len(self.pf.positions),
                }
            )

        self.pf.equity_curve = list(self.daily_log)
        logger.info(
            "ATH breakout: %d fills, %d round trips, %d still open",
            len(self.pf.fills),
            len(self.pf.closed),
            len(self.pf.positions),
        )
        return self

    # ── Reporting helpers ────────────────────────────────────────────────────
    @property
    def open_positions(self) -> List[dict]:
        """Marks for positions still open on the final session."""
        if not self.daily_log:
            return []
        last = pd.Timestamp(self.daily_log[-1]["date"])
        row = self.prices.closes.loc[last]
        out = []
        for symbol, pos in self.pf.positions.items():
            price = row.get(symbol)
            price = float(price) if pd.notna(price) else pos.entry_price
            exit_value = pos.quantity * price
            out.append(
                {
                    "ticker": symbol,
                    "industry": pos.industry,
                    "entry_date": pos.entry_date,
                    "exit_date": last.date(),
                    "hold_days": (last.date() - pos.entry_date).days,
                    "entry_px": pos.entry_price,
                    "exit_px": price,
                    "return_pct": (price / pos.entry_price - 1.0) * 100.0,
                    "qty": pos.quantity,
                    "invested": pos.entry_value,
                    "gross_pnl": exit_value - (pos.entry_value + pos.entry_cost),
                    "costs": pos.entry_cost,
                    "net_pnl": exit_value - pos.entry_value,
                    "st_gain": 0.0,
                    "lt_gain": 0.0,
                    "exit_reason": "OPEN",
                    "status": "open",
                }
            )
        return sorted(out, key=lambda r: (r["entry_date"], r["ticker"]))


def _score(value) -> float:
    """Rank score with missing momentum pushed to the bottom, not the top."""
    return float(value) if value is not None and pd.notna(value) else float("-inf")
