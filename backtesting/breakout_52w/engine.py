"""Daily simulation loop for the 52-week breakout strategy."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, timedelta
from typing import List, Optional

from backtesting.swing_trading.data import PointInTimeData
from backtesting.swing_trading.portfolio import Portfolio, Position
from backtesting.swing_trading.watchlist import UniverseStock

from . import strategy
from .calendar import EarningsCalendar
from .config import BreakoutConfig

logger = logging.getLogger("backtest.breakout_52w.engine")


class BreakoutEngine:
    def __init__(
        self,
        cfg: BreakoutConfig,
        data: PointInTimeData,
        universe: List[UniverseStock],
        earnings: EarningsCalendar,
    ):
        self.cfg = cfg
        self.data = data
        self.universe = universe
        self.earnings = earnings
        self.pf = Portfolio(
            cash=cfg.starting_capital, commission_pct=cfg.commission_pct
        )
        self.pending: List[strategy.EntrySignal] = []
        self.daily_log: list[dict] = []
        self.signal_log: list[dict] = []
        self.calendar_days: list[date] = []
        self.breakout_candidates = self._index_breakout_candidates()

    def _index_breakout_candidates(self) -> dict[date, list[UniverseStock]]:
        candidates: dict[date, list[UniverseStock]] = {}
        minimum_ratio = 1.0 + self.cfg.min_breakout_pct / 100.0
        for item in self.universe:
            frame = self.data.frames.get(item.symbol)
            if frame is None or frame.empty:
                continue
            prior_high = (
                frame["High"]
                .shift(1)
                .rolling(
                    self.cfg.breakout_lookback,
                    min_periods=self.cfg.breakout_lookback,
                )
                .max()
            )
            close = frame["Close"]
            hits = frame.index[
                (close > prior_high) & (close >= prior_high * minimum_ratio)
            ]
            for timestamp in hits:
                candidates.setdefault(timestamp.date(), []).append(item)
        return candidates

    def _price_lookup(self, day: date):
        def lookup(symbol: str) -> Optional[float]:
            bar = self.data.bar_on(symbol, day)
            if bar is not None:
                return float(bar["Close"])
            history = self.data.as_of(symbol, day, lookback_rows=1)
            if history is not None and not history.empty:
                return float(history["Close"].iloc[-1])
            return None

        return lookup

    def _opening_price_lookup(self, day: date):
        def lookup(symbol: str) -> Optional[float]:
            bar = self.data.bar_on(symbol, day)
            if bar is not None:
                return float(bar["Open"])
            history = self.data.as_of(symbol, day - timedelta(days=1), lookback_rows=1)
            if history is not None and not history.empty:
                return float(history["Close"].iloc[-1])
            return None

        return lookup

    def _regime_allows_entries(self, day: date) -> bool:
        return strategy.market_regime_allows_entries(
            self.data.benchmark_as_of(day), self.cfg
        )

    def _open_risk(self) -> float:
        return sum(
            max(position.entry_price - position.stop_loss, 0.0) * position.quantity
            for position in self.pf.positions.values()
        )

    def run(self, start: date, end: date) -> None:
        forward_days = max(10, self.cfg.earnings_blackout_sessions * 3)
        self.calendar_days = self.data.trading_days(
            start, end + timedelta(days=forward_days)
        )
        days = [day for day in self.calendar_days if day <= end]
        if not days:
            raise RuntimeError("No trading days in range - check dates and data")

        for day in days:
            opened_today: set[str] = set()
            self._fill_pending(day, opened_today)
            self._manage_positions(day, opened_today)
            snap = self.pf.record_equity(day, self._price_lookup(day))
            equity = snap["equity"]
            snap["open_risk_pct"] = round(
                self._open_risk() / equity * 100.0 if equity else 0.0, 3
            )
            snap["regime_allows_entries"] = self._regime_allows_entries(day)
            self.daily_log.append(snap)
            self._generate_pending(day)

    def _fill_pending(self, day: date, opened_today: set[str]) -> None:
        if not self.pending:
            return
        lookup = self._opening_price_lookup(day)
        equity = self.pf.total_equity(lookup)
        for signal in self.pending:
            if len(self.pf.positions) >= self.cfg.max_positions:
                break
            if signal.symbol in self.pf.positions:
                continue
            bar = self.data.bar_on(signal.symbol, day)
            if bar is None:
                continue
            fill = float(bar["Open"])
            if not (
                signal.breakout_level
                < fill
                <= signal.breakout_level + self.cfg.max_extension_atr * signal.atr
            ):
                continue
            shares, stop = strategy.size_position(
                fill,
                signal,
                equity,
                self.pf.cash,
                self._open_risk(),
                self.cfg,
            )
            if shares <= 0:
                continue
            position = Position(
                symbol=signal.symbol,
                quantity=shares,
                entry_price=fill,
                entry_date=day,
                stop_loss=stop,
                target_price=strategy.profit_target(fill, signal.atr, self.cfg),
                initial_stop=stop,
                atr_at_entry=signal.atr,
                setup="52W Breakout",
                breakout_level=signal.breakout_level,
                breakout_signal_date=signal.signal_date,
                highest_high=fill,
            )
            if self.pf.open_position(position):
                opened_today.add(signal.symbol)
                equity = self.pf.total_equity(lookup)
                low = float(bar["Low"])
                high = float(bar["High"])
                if low <= stop:
                    self.pf.close_position(signal.symbol, stop, day, "ENTRY-DAY-STOP")
                    opened_today.discard(signal.symbol)
                elif high >= position.target_price:
                    self.pf.close_position(
                        signal.symbol,
                        position.target_price,
                        day,
                        "ENTRY-DAY-TARGET",
                    )
                    opened_today.discard(signal.symbol)
        self.pending = []

    def _manage_positions(self, day: date, opened_today: set[str]) -> None:
        for symbol in list(self.pf.positions):
            if symbol in opened_today:
                continue
            bar = self.data.bar_on(symbol, day)
            history = self.data.as_of(symbol, day, lookback_rows=300)
            if bar is None or history is None or history.empty:
                continue
            position = self.pf.positions[symbol]
            for operation in strategy.evaluate_exit(position, bar, history, self.cfg):
                self.pf.close_position(symbol, operation.price, day, operation.reason)

    def _generate_pending(self, day: date) -> None:
        capacity = self.cfg.max_positions - len(self.pf.positions)
        if capacity <= 0 or not self._regime_allows_entries(day):
            self.pending = []
            return

        candidates: list[strategy.EntrySignal] = []
        for item in self.breakout_candidates.get(day, []):
            symbol = item.symbol
            if symbol in self.pf.positions:
                continue
            if self.data.bar_on(symbol, day) is None:
                continue
            if self.cfg.enforce_earnings_blackout and self.earnings.has_event_within(
                symbol,
                day,
                self.calendar_days,
                self.cfg.earnings_blackout_sessions,
            ):
                continue
            history = self.data.as_of(symbol, day, lookback_rows=400)
            signal = strategy.compute_entry_signal(
                history,
                self.data.benchmark_as_of(day),
                symbol,
                day,
                self.cfg,
            )
            if signal is not None:
                candidates.append(signal)

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        self.pending = candidates[: capacity + 2]
        self.signal_log.extend(asdict(candidate) for candidate in candidates)
