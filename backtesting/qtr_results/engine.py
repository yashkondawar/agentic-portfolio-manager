"""
engine.py
=========

The quarterly-results backtest loop. For each trading day it:

  1. FILLS entries queued from the prior day (a result recognised yesterday) at
     today's OPEN — so every pick is priced at the historical price at that point
     in time, never at a current/future price.
  2. MANAGES open positions against today's OHLC (trailing stop / target /
     time-stop) via ``strategy.evaluate_exit`` — the OHLC-aware ledger.
  3. RECORDS the day's equity snapshot (marked to today's close).
  4. DISCOVERS result declarations whose (quarter-end + reporting-lag) filing date
     first becomes tradable today, VERIFIES each point-in-time on screener history
     (only quarters up to the declared one), SELECTS the strong ones and QUEUES
     them for tomorrow's open.

No future data is ever consulted: fundamentals are sliced to the declared quarter,
prices come from ``as_of`` slices, and all entries fill on the NEXT session's open.
"""

from __future__ import annotations

import bisect
import logging
from datetime import date
from typing import Dict, List, Optional, Tuple

from qtr_results.targets import build_target_plan

from . import analysis as an
from . import strategy
from .config import BacktestConfig
from .data import FundamentalsStore, PointInTimeData
from .portfolio import Portfolio

logger = logging.getLogger("backtest.qtr.engine")


class BacktestEngine:
    def __init__(
        self,
        cfg: BacktestConfig,
        prices: PointInTimeData,
        funds: FundamentalsStore,
    ):
        self.cfg = cfg
        self.prices = prices
        self.funds = funds
        self.pf = Portfolio(cash=cfg.starting_capital, commission_pct=cfg.commission_pct)
        # symbol -> (raw, quarters, metrics)
        self.parsed: Dict[str, Tuple[dict, list, dict]] = {}
        self.events_by_day: Dict[date, List[an.ResultEvent]] = {}
        self.pending: List[an.ResultEvent] = []
        self.daily_log: List[dict] = []
        self.event_log: List[dict] = []

    # ── price helpers ─────────────────────────────────────────────────────────
    def _price_lookup(self, day: date):
        def lookup(sym: str) -> Optional[float]:
            bar = self.prices.bar_on(sym, day)
            if bar is not None:
                return float(bar["Close"])
            sub = self.prices.as_of(sym, day, lookback_rows=1)
            if sub is not None and not sub.empty:
                return float(sub["Close"].iloc[-1])
            return None
        return lookup

    # ── precompute the result-event calendar ──────────────────────────────────
    def _prepare_events(self, calendar: List[date]) -> None:
        if not calendar:
            return
        first, last = calendar[0], calendar[-1]
        for sym in self.funds.symbols():
            if not self.prices.has(sym):
                continue  # can't fill/price this name — skip its events
            raw = self.funds.get(sym)
            quarters, metrics = an.parse_quarters(raw)
            if len(quarters) < 5:
                continue
            self.parsed[sym] = (raw, quarters, metrics)
            for ev in an.enumerate_events(
                sym, raw, quarters, reporting_lag_days=self.cfg.reporting_lag_days
            ):
                # First trading session on/after the assumed filing date.
                idx = bisect.bisect_left(calendar, ev.decl_date)
                if idx >= len(calendar):
                    continue
                signal_day = calendar[idx]
                if not (first <= signal_day <= last):
                    continue
                self.events_by_day.setdefault(signal_day, []).append(ev)
        logger.info(
            "Prepared %d result events across %d signal days.",
            sum(len(v) for v in self.events_by_day.values()), len(self.events_by_day),
        )

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self, start: date, end: date) -> None:
        calendar = self.prices.trading_days(start, end)
        if not calendar:
            raise SystemExit("No trading days in range — check dates / data.")
        self._prepare_events(calendar)
        logger.info("Backtest %s → %s | %d trading days", calendar[0], calendar[-1], len(calendar))

        for d in calendar:
            opened_today: set = set()
            self._fill_pending(d, opened_today)
            self._manage(d, opened_today)

            snap = self.pf.record_equity(d, self._price_lookup(d))
            snap["pending"] = len(self.pending)
            self.daily_log.append(snap)

            self._discover_and_queue(d)

    # ── 1) fills ──────────────────────────────────────────────────────────────
    def _fill_pending(self, day: date, opened_today: set) -> None:
        if not self.pending:
            return
        lookup = self._price_lookup(day)
        for ev in self.pending:
            if len(self.pf.positions) >= self.cfg.max_positions:
                break
            if self.pf.has_open(ev.symbol):
                continue
            bar = self.prices.bar_on(ev.symbol, day)
            if bar is None:
                continue  # no session for this name today; the order lapses
            fill = float(bar["Open"])
            if fill <= 0:
                continue

            raw, quarters, metrics = self.parsed[ev.symbol]
            analysis = an.analyze_event(raw, quarters, metrics, ev.q_idx, fill, cfg=self.cfg)
            if not analysis.is_strong:
                continue
            plan = build_target_plan(analysis, fill)
            if plan is None:
                continue

            equity = self.pf.total_equity(lookup)
            shares = strategy.size_position(
                fill, plan.trailing_stop_pct, equity, self.pf.cash, self.cfg
            )
            if shares <= 0:
                continue
            pos = strategy.make_position(
                ev.symbol, fill, day, shares, plan, analysis, ev.decl_date.isoformat()
            )
            if self.pf.open_position(pos):
                opened_today.add(ev.symbol)
                logger.debug("%s OPEN %s x%d @%.2f tgt %.2f stop %.2f (%s)",
                             day, ev.symbol, shares, fill, pos.target_price,
                             pos.stop_price, plan.method)
        self.pending = []

    # ── 2) exits ──────────────────────────────────────────────────────────────
    def _manage(self, day: date, opened_today: set) -> None:
        for sym in list(self.pf.positions.keys()):
            if sym in opened_today:
                continue
            bar = self.prices.bar_on(sym, day)
            if bar is None:
                continue  # halted / no session; carry the position
            pos = self.pf.positions[sym]
            op = strategy.evaluate_exit(pos, bar, day, self.cfg)
            if op is not None:
                self.pf.close_position(sym, op.price, day, op.reason)

    # ── 4) discovery + selection ──────────────────────────────────────────────
    def _discover_and_queue(self, day: date) -> None:
        events = self.events_by_day.get(day, [])
        if not events:
            self.pending = []
            return
        capacity = self.cfg.max_positions - len(self.pf.positions)
        if capacity <= 0:
            self.pending = []
            return

        scored: List[Tuple[float, an.ResultEvent, object]] = []
        for ev in events:
            if self.pf.has_open(ev.symbol):
                continue
            raw, quarters, metrics = self.parsed[ev.symbol]
            # Provisional analysis at today's close to gate + rank (price-agnostic
            # gate; the target is recomputed at the actual fill price tomorrow).
            close_px = self._price_lookup(day)(ev.symbol) or 0.0
            analysis = an.analyze_event(raw, quarters, metrics, ev.q_idx, close_px, cfg=self.cfg)
            self.event_log.append({
                "signal_date": day.isoformat(),
                "symbol": ev.symbol,
                "quarter": ev.quarter_label,
                "decl_date": ev.decl_date.isoformat(),
                "is_strong": analysis.is_strong,
                "strength": analysis.strength_score,
                "yoy_profit": analysis.yoy_profit_growth,
                "qoq_profit": analysis.qoq_profit_growth,
                "yoy_eps": analysis.yoy_eps_growth,
            })
            if analysis.is_strong:
                scored.append((analysis.strength_score, ev, analysis))

        scored.sort(key=lambda t: t[0], reverse=True)
        take = min(capacity, self.cfg.max_new_per_day)
        self.pending = [ev for _, ev, _ in scored[:take]]
