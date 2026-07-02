"""
engine.py
=========

The backtest loop. For each trading day it:

  1. FILLS pending entry orders (decided from the prior day's close) at today's OPEN.
  2. MANAGES open positions against today's OHLC (stop / target / trail / reversal /
     time-stop) — see ``strategy.evaluate_exits``.
  3. RECORDS the day's equity snapshot (marked to today's close).
  4. On the first trading day of each month, REBUILDS the watchlist using the
     point-in-time mechanical screen (``watchlist.build_watchlist_for``).
  5. GENERATES tomorrow's entry candidates from today's close, ranked best-first,
     respecting capacity / cash.

No future data is ever consulted: every indicator uses ``data.as_of(symbol, day)``
and all entries fill on the NEXT session's open.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional

from . import strategy
from .config import BacktestConfig
from .data import PointInTimeData
from .portfolio import Portfolio, Position
from .watchlist import (
    UniverseStock,
    _benchmark_ret_3m,
    build_watchlist_for,
    load_universe,
    watchlist_symbols,
)

logger = logging.getLogger("backtest.engine")


class BacktestEngine:
    def __init__(self, cfg: BacktestConfig, data: PointInTimeData,
                 universe: List[UniverseStock]):
        self.cfg = cfg
        self.data = data
        self.universe = universe
        self.pf = Portfolio(cash=cfg.starting_capital, commission_pct=cfg.commission_pct)
        self.watchlist: List[str] = []
        self.watchlist_log: List[dict] = []
        self.pending: List[strategy.EntrySignal] = []
        self.daily_log: List[dict] = []

    # ── helpers ──────────────────────────────────────────────────────────────
    def _rebalance_days(self, days: List[date]) -> set:
        out = set()
        last_ym = None
        for d in days:
            ym = (d.year, d.month)
            if ym != last_ym:
                out.add(d)
                last_ym = ym
        return out

    def _price_lookup(self, day: date):
        def lookup(sym: str) -> Optional[float]:
            bar = self.data.bar_on(sym, day)
            if bar is not None:
                return float(bar["Close"])
            sub = self.data.as_of(sym, day, lookback_rows=1)
            if sub is not None and not sub.empty:
                return float(sub["Close"].iloc[-1])
            return None
        return lookup

    # ── main loop ────────────────────────────────────────────────────────────
    def run(self, start: date, end: date) -> None:
        days = self.data.trading_days(start, end)
        if not days:
            raise SystemExit("No trading days in range — check dates / data.")
        rebal = self._rebalance_days(days)
        logger.info("Backtest %s → %s | %d trading days | %d monthly rebalances",
                    days[0], days[-1], len(days), len(rebal))

        for d in days:
            opened_today: set = set()

            # 1) Fill pending entries at today's OPEN.
            self._fill_pending(d, opened_today)

            # 2) Manage existing positions (exclude those opened today).
            self._manage(d, opened_today)

            # 3) Record equity (mark to today's close).
            snap = self.pf.record_equity(d, self._price_lookup(d))
            snap["watchlist_size"] = len(self.watchlist)
            self.daily_log.append(snap)

            # 4) Monthly watchlist rebuild.
            if d in rebal:
                self._rebuild_watchlist(d)

            # 5) Generate tomorrow's entry candidates from today's close.
            self._generate_pending(d)

    def _fill_pending(self, day: date, opened_today: set) -> None:
        if not self.pending:
            return
        lookup = self._price_lookup(day)
        equity = self.pf.total_equity(lookup)
        for sig in self.pending:
            if len(self.pf.positions) >= self.cfg.max_positions:
                break
            if sig.symbol in self.pf.positions:
                continue
            bar = self.data.bar_on(sig.symbol, day)
            if bar is None:
                continue  # no session for this name today; order lapses
            fill = float(bar["Open"])
            if fill <= 0:
                continue
            shares, stop, target = strategy.size_position(
                fill, sig.atr, equity, self.pf.cash, self.cfg
            )
            if shares <= 0:
                continue
            pos = Position(
                symbol=sig.symbol, quantity=shares, entry_price=fill, entry_date=day,
                stop_loss=stop, target_price=target, initial_stop=stop,
                atr_at_entry=sig.atr, setup=sig.setup,
            )
            if self.pf.open_position(pos):
                opened_today.add(sig.symbol)
                equity = self.pf.total_equity(lookup)  # refresh after cash use
                logger.debug("%s OPEN %s x%d @%.2f stop %.2f tgt %.2f (%s)",
                             day, sig.symbol, shares, fill, stop, target, sig.setup)
        self.pending = []

    def _manage(self, day: date, opened_today: set) -> None:
        for sym in list(self.pf.positions.keys()):
            if sym in opened_today:
                continue
            bar = self.data.bar_on(sym, day)
            if bar is None:
                continue  # halted / no session; carry the position
            df = self.data.as_of(sym, day, lookback_rows=300)
            if df is None or df.empty:
                continue
            pos = self.pf.positions[sym]
            ops = strategy.evaluate_exits(pos, bar, df, day, self.cfg)
            for op in ops:
                self.pf.close_position(sym, op.price, day, op.reason, op.fraction)

    def _rebuild_watchlist(self, day: date) -> None:
        ranked = build_watchlist_for(self.data, self.universe, day, self.cfg)
        self.watchlist = watchlist_symbols(ranked)
        self.watchlist_log.append({
            "date": day.isoformat(),
            "symbols": list(self.watchlist),
            "detail": [
                {"symbol": m.symbol, "industry": m.industry, "rsi": round(m.rsi, 1),
                 "ret_3m": round(m.ret_3m, 1) if m.ret_3m is not None else None,
                 "score": m.score}
                for m in ranked
            ],
        })
        logger.info("%s watchlist rebuilt: %d names: %s",
                    day, len(self.watchlist), ", ".join(self.watchlist[:12]))

    def _generate_pending(self, day: date) -> None:
        capacity = self.cfg.max_positions - len(self.pf.positions)
        if capacity <= 0 or not self.watchlist:
            self.pending = []
            return
        bench_ret_3m = _benchmark_ret_3m(self.data, day)
        candidates: List[strategy.EntrySignal] = []
        for sym in self.watchlist:
            if sym in self.pf.positions:
                continue
            df = self.data.as_of(sym, day, lookback_rows=300)
            if df is None or len(df) < 60:
                continue
            sig = strategy.compute_entry_signal(df, sym, self.cfg, bench_ret_3m)
            if sig is not None:
                candidates.append(sig)
        candidates.sort(key=lambda s: s.score, reverse=True)
        # Queue a little more than capacity (some may lapse / be unaffordable).
        self.pending = candidates[: capacity + 2]
