"""
engine.py
=========

The daily loop.

Ordering within a session - this is the whole ballgame for a trustworthy
backtest, so it is spelled out rather than implied:

1. **Fill queued exits at today's open.** These were decided from yesterday's
   close (RSI exits, time stops).
2. **Fill queued entries at today's open.** A signal generated at yesterday's
   close can never fill at yesterday's close.
3. **Manage open positions against today's OHLC.** Stops and price-level targets
   resolve intrabar (stop first when both are possible); indicator exits are
   observed and queued for tomorrow's open.
4. **Record equity**, marked to today's close.
5. **Scan for tomorrow's candidates** from today's close, gated by regime and
   sector, ranked, and queued.

No step ever consults a row dated after the day being simulated: entries and
exits read only the pre-computed causal panels, and every fill happens at a
price that is chronologically *after* the information that triggered it.
"""

import logging
import random
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from . import strategy
from .config import GFSConfig
from .panels import RegimePanel, SectorPanel, SymbolPanel
from .portfolio import Portfolio, Position
from .strategy import EntrySignal, ExitOp, FILL_NEXT_OPEN

logger = logging.getLogger("gfs.engine")


class GFSBacktestEngine:
    def __init__(
        self,
        cfg: GFSConfig,
        panels: Dict[str, SymbolPanel],
        sector_panel: SectorPanel,
        regime_panel: RegimePanel,
        qualify: pd.DataFrame,
        calendar: pd.DatetimeIndex,
        tax_config=None,
    ):
        self.cfg = cfg
        self.panels = panels
        self.sector_panel = sector_panel
        self.regime_panel = regime_panel
        self.qualify = qualify
        self.calendar = calendar
        self.pf = Portfolio(
            cash=cfg.starting_capital,
            commission_pct=cfg.commission_pct,
            slippage_bps=cfg.slippage_bps,
            cash_yield_pct=cfg.cash_yield_pct,
        )
        self.rng = random.Random(cfg.seed)
        self.pending_entries: List[EntrySignal] = []
        self.pending_exits: List[tuple] = []  # (symbol, ExitOp)
        # One list, one owner: the portfolio appends daily snapshots and the
        # engine exposes the same object, so the two can never drift apart.
        self.daily_log: List[dict] = self.pf.equity_curve
        self.signal_log: List[dict] = []
        self.rejections: Dict[str, int] = {}
        # Off by default. The live runner and every existing study must keep the
        # pre-tax behaviour they were validated against; only the dossier export
        # turns this on, and it does so in a run of its own.
        self.tax_config = tax_config
        self._tax_paid_total = 0.0
        self._tax_settled_fy: Optional[str] = None

    # ── helpers ──────────────────────────────────────────────────────────────

    def _reject(self, reason: str, n: int = 1) -> None:
        self.rejections[reason] = self.rejections.get(reason, 0) + n

    def _row(self, symbol: str, ts: pd.Timestamp) -> Optional[pd.Series]:
        panel = self.panels.get(symbol)
        return None if panel is None else panel.row(ts)

    def _rsi_triplet(self, row: Optional[pd.Series]) -> Optional[tuple]:
        """Daily/weekly/monthly RSI on one bar, for the exit record.

        The weekly and monthly values here are the same leak-free projections the
        entry used: as of this bar, only closed higher-timeframe candles count.
        """
        if row is None:
            return None
        def val(key: str) -> float:
            v = row.get(key)
            return 0.0 if v is None or pd.isna(v) else float(v)
        return (val("rsi_d"), val("rsi_w"), val("rsi_m"))

    def _price_lookup(self, ts: pd.Timestamp):
        def lookup(sym: str) -> Optional[float]:
            panel = self.panels.get(sym)
            if panel is None:
                return None
            frame = panel.frame
            sliced = frame["Close"].loc[:ts]
            if sliced.empty:
                return None
            return float(sliced.iloc[-1])

        return lookup

    # ── optional annual tax settlement ───────────────────────────────────────

    def _settle_tax_if_due(self, day: date, *, final: bool = False) -> None:
        """Pay the previous financial year's capital-gains bill, once, in April.

        Indian capital-gains tax on a financial year ending 31 March is settled
        in the following year. Modelling it as a single April debit is a
        simplification of advance-tax instalments, but it puts the cash outflow
        in the right year, which is what compounding cares about.

        The whole ledger is recomputed at each boundary rather than kept
        incrementally: loss set-off carries forward eight years, so a year's
        bill is not a function of that year alone. Recomputing is deterministic
        and forward-only, so the per-year numbers never change retroactively -
        we simply pay whatever has newly become due.

        ``final`` settles everything still outstanding on the last session.
        Without it the closing financial year's gains - whose bill only falls due
        the following April - would be reported untaxed, which flatters the final
        equity and therefore the CAGR by however good the last year happened to
        be. Tax on *unrealised* gains is correctly still not charged: nothing is
        owed until a position is sold.
        """
        if self.tax_config is None:
            return
        from . import taxes

        if final:
            fy = None
            due_trades = list(self.pf.closed)
        else:
            if day.month < 4:
                return
            fy = taxes.financial_year(day)
            if fy == self._tax_settled_fy:
                return
            # Only trades closed *before* this financial year are assessable now.
            due_trades = [
                t for t in self.pf.closed if taxes.financial_year(t.exit_date) != fy
            ]
            self._tax_settled_fy = fy
        if not due_trades:
            return
        table = taxes.apply_to_trades(
            due_trades, self.tax_config, use_recorded_costs=True
        )
        if table.empty:
            return
        by_year = taxes.capital_gains_by_year(table, self.tax_config)
        if by_year.empty:
            return
        owed = float(by_year["tax"].sum()) - self._tax_paid_total
        if owed <= 0:
            return
        self._tax_paid_total += self.pf.settle_tax(
            day, owed, fy or f"{taxes.financial_year(day)} (final settlement)"
        )

    # ── main loop ────────────────────────────────────────────────────────────

    def run(self, start: date, end: date) -> None:
        days = [
            ts
            for ts in self.calendar
            if start <= ts.date() <= end
        ]
        if not days:
            raise RuntimeError("No trading days in range - check dates and data.")
        logger.info(
            "GFS backtest %s -> %s | %d sessions | %d symbols",
            days[0].date(),
            days[-1].date(),
            len(days),
            len(self.panels),
        )

        for ts in days:
            day = ts.date()
            self.pf.accrue_cash_yield()
            self._settle_tax_if_due(day)
            self._fill_pending_exits(ts, day)
            opened = self._fill_pending_entries(ts, day)
            self._manage(ts, day)
            # Everything realised is assessed before the last mark, so the final
            # equity is genuinely net of tax rather than net of tax-so-far.
            if ts is days[-1]:
                self._settle_tax_if_due(day, final=True)
            regime_row = self.regime_panel.row(ts)
            self.pf.record_equity(
                day,
                self._price_lookup(ts),
                regime_ok=bool(regime_row["regime_ok"]) if regime_row is not None else False,
                breadth_pct=(
                    round(float(regime_row["breadth_pct"]), 2)
                    if regime_row is not None and not pd.isna(regime_row["breadth_pct"])
                    else None
                ),
                opened=opened,
            )
            self._scan(ts, day)

    # ── step 1: queued exits ─────────────────────────────────────────────────

    def _fill_pending_exits(self, ts: pd.Timestamp, day: date) -> None:
        if not self.pending_exits:
            return
        for symbol, op in self.pending_exits:
            if symbol not in self.pf.positions:
                continue
            row = self._row(symbol, ts)
            if row is None:
                # The name did not trade today; carry the intent forward rather
                # than inventing a fill price.
                continue
            quoted = float(row["Open"])
            self.pf.close_position(
                symbol,
                self.pf.sell_fill_price(quoted),
                day,
                op.reason,
                op.fraction,
                exit_rsi=self._rsi_triplet(row),
            )
        self.pending_exits = []

    # ── step 2: queued entries ───────────────────────────────────────────────

    def _fill_pending_entries(self, ts: pd.Timestamp, day: date) -> int:
        if not self.pending_entries:
            return 0
        signals = self.pending_entries
        self.pending_entries = []
        opened = 0
        lookup = self._price_lookup(ts)

        for sig in signals:
            if len(self.pf.positions) >= self.cfg.max_positions:
                self._reject("capacity")
                continue
            if sig.symbol in self.pf.positions:
                continue
            if not strategy.can_open_sector(
                sig.sector, self.pf.sector_exposure(), self.cfg
            ):
                self._reject("sector_cap")
                continue
            row = self._row(sig.symbol, ts)
            if row is None:
                self._reject("no_session")
                continue
            quoted = float(row["Open"])
            if quoted <= 0:
                self._reject("bad_price")
                continue

            fill = self.pf.buy_fill_price(quoted)
            # The stop is re-derived from the actual fill, not carried over from
            # the signal bar's close - otherwise an overnight gap silently
            # changes the risk the position was sized for.
            stop = strategy.stop_for(fill, row, self.cfg)
            if stop >= fill:
                self._reject("invalid_stop")
                continue

            equity = self.pf.total_equity(lookup)
            desired = strategy.size_position(fill, stop, equity, self.cfg)
            qty = self.pf.affordable_quantity(fill, desired)
            if qty <= 0:
                self._reject("insufficient_cash")
                continue

            pos = Position(
                symbol=sig.symbol,
                sector=sig.sector,
                quantity=qty,
                entry_price=fill,
                entry_date=day,
                stop_loss=stop,
                initial_stop=stop,
                target_price=strategy.target_for(fill, sig, self.cfg),
                atr_at_entry=sig.atr,
                entry_rsi_d=sig.rsi_d,
                entry_rsi_w=sig.rsi_w,
                entry_rsi_m=sig.rsi_m,
            )
            if self.pf.open_position(pos):
                opened += 1
                logger.debug(
                    "%s OPEN %s x%d @%.2f stop %.2f (RSI m/w/d %.0f/%.0f/%.0f)",
                    day, sig.symbol, qty, fill, stop, sig.rsi_m, sig.rsi_w, sig.rsi_d,
                )
        return opened

    # ── step 3: manage open positions ────────────────────────────────────────

    def _manage(self, ts: pd.Timestamp, day: date) -> None:
        for symbol in list(self.pf.positions.keys()):
            row = self._row(symbol, ts)
            if row is None:
                continue  # suspended / no session: carry the position
            pos = self.pf.positions[symbol]
            pos.mark(float(row["High"]), float(row["Low"]), float(row["Close"]))
            strategy.update_stop(pos, row, self.cfg)

            for op in strategy.evaluate_exits(pos, row, day, self.cfg):
                if op.fill == FILL_NEXT_OPEN:
                    self.pending_exits.append((symbol, op))
                    continue
                self.pf.close_position(
                    symbol,
                    self.pf.sell_fill_price(op.price),
                    day,
                    op.reason,
                    op.fraction,
                    exit_rsi=self._rsi_triplet(row),
                )
                if symbol not in self.pf.positions:
                    break

    # ── step 5: scan tomorrow's candidates ───────────────────────────────────

    def _scan(self, ts: pd.Timestamp, day: date) -> None:
        self.pending_entries = []
        if self.qualify.empty or ts not in self.qualify.index:
            return

        qualifying = self.qualify.loc[ts]
        symbols = list(qualifying.index[qualifying.to_numpy()])
        regime_ok = self.regime_panel.ok_on(ts)
        self.signal_log.append(
            {
                "date": day.isoformat(),
                "qualifying": len(symbols),
                "regime_ok": regime_ok,
                "open_positions": len(self.pf.positions),
            }
        )
        if not symbols:
            return
        if self.cfg.use_regime_filter and not regime_ok:
            self._reject("regime_closed", len(symbols))
            return

        capacity = self.cfg.max_positions - len(self.pf.positions)
        if capacity <= 0:
            self._reject("capacity", len(symbols))
            return

        sector_count = self.sector_panel.sector_count(ts)
        candidates: List[EntrySignal] = []
        for symbol in symbols:
            if symbol in self.pf.positions:
                continue
            panel = self.panels[symbol]
            row = panel.row(ts)
            if row is None:
                continue
            sector_rank = self.sector_panel.rank_of(panel.sector, ts)
            if self.cfg.use_sector_filter:
                if sector_rank is None:
                    self._reject("sector_unknown")
                    continue
                if sector_rank > self.cfg.sector_top_n:
                    self._reject("sector_weak")
                    continue
            sig = strategy.build_signal(
                symbol, panel.sector, row, day, sector_rank, sector_count,
                self.cfg, self.rng,
            )
            if sig is not None:
                candidates.append(sig)

        candidates.sort(key=lambda s: s.score, reverse=True)
        # Queue a little beyond capacity: some orders lapse (no session) or are
        # blocked by the sector cap at fill time.
        self.pending_entries = candidates[: capacity + 3]

    # ── reporting ────────────────────────────────────────────────────────────

    def signal_frequency(self) -> Dict[str, float]:
        """How often the setup even appears - the practical capacity question."""
        if not self.signal_log:
            return {}
        counts = [entry["qualifying"] for entry in self.signal_log]
        open_days = sum(1 for entry in self.signal_log if entry["regime_ok"])
        return {
            "sessions": len(counts),
            "avg_qualifying_per_day": round(sum(counts) / len(counts), 2),
            "max_qualifying_in_a_day": max(counts),
            "days_with_zero_signals": sum(1 for c in counts if c == 0),
            "pct_days_regime_open": round(open_days / len(counts) * 100.0, 1),
        }
