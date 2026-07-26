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
from . import ranking, signals
from . import strategy
from .config import BacktestConfig
from .data import FundamentalsStore, PointInTimeData, ResultsCalendarStore, SectorStore
from .portfolio import Portfolio, Position

logger = logging.getLogger("backtest.qtr.engine")


class BacktestEngine:
    def __init__(
        self,
        cfg: BacktestConfig,
        prices: PointInTimeData,
        funds: FundamentalsStore,
        sectors: Optional[SectorStore] = None,
        calendar: Optional[ResultsCalendarStore] = None,
    ):
        self.cfg = cfg
        self.prices = prices
        self.funds = funds
        self.sectors = sectors
        self.calendar = calendar
        self.pf = Portfolio(cash=cfg.starting_capital, commission_pct=cfg.commission_pct)
        # symbol -> (raw, quarters, metrics)
        self.parsed: Dict[str, Tuple[dict, list, dict]] = {}
        self.events_by_day: Dict[date, List[an.ResultEvent]] = {}
        self.pending: List[an.ResultEvent] = []
        # B10 anticipation: entry_day -> [(event, its result signal_day)]
        self.anticip_by_day: Dict[date, List[Tuple[an.ResultEvent, date]]] = {}
        self.pending_anticip: List[Tuple[an.ResultEvent, date]] = []
        self.daily_log: List[dict] = []
        self.event_log: List[dict] = []
        # Per-event filter tallies for the summary output.
        self.filter_stats: Dict[str, int] = {}

    def _bump(self, reason: str) -> None:
        self.filter_stats[reason] = self.filter_stats.get(reason, 0) + 1

    def _sector_of(self, sym: str) -> str:
        return self.sectors.get(sym) if self.sectors else "UNKNOWN"

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
        n_real = n_est = 0
        use_real = self.cfg.use_real_decl_dates and self.calendar is not None
        for sym in self.funds.symbols():
            if not self.prices.has(sym):
                continue  # can't fill/price this name — skip its events
            raw = self.funds.get(sym)
            quarters, metrics = an.parse_quarters(raw)
            if len(quarters) < 5:
                continue
            self.parsed[sym] = (raw, quarters, metrics)
            real_dates = self.calendar.dates_for(sym) if use_real else None
            for ev in an.enumerate_events(
                sym,
                raw,
                quarters,
                reporting_lag_min=self.cfg.reporting_lag_min,
                reporting_lag_max=self.cfg.reporting_lag_max,
                real_decl_dates=real_dates,
            ):
                # Reject events whose declaration date is outside the backtest
                # window. Without this guard, bisect_left returns 0 for any
                # decl_date before `first`, silently piling every stale quarter
                # from screener history onto Day 1.
                if ev.decl_date < first or ev.decl_date > last:
                    continue
                # Clean-regime option: trade only events with a REAL NSE date.
                if self.cfg.real_dates_only and not ev.decl_date_real:
                    continue
                # First trading session on/after the declaration date. When the
                # real announcement was after market close (the norm), the fill
                # happens the NEXT session's open — handled by _fill_pending.
                idx = bisect.bisect_left(calendar, ev.decl_date)
                if idx >= len(calendar):
                    continue
                signal_day = calendar[idx]
                self.events_by_day.setdefault(signal_day, []).append(ev)
                if ev.decl_date_real:
                    n_real += 1
                else:
                    n_est += 1
                # B10 — schedule a pre-declaration anticipation entry N sessions
                # ahead of the result. Needs the exact day, so only real-dated
                # events qualify (an estimated lag would misplace the entry).
                if self.cfg.anticipation_mode and ev.decl_date_real:
                    e_idx = idx - self.cfg.anticipation_lead_days
                    if e_idx >= 0:
                        entry_day = calendar[e_idx]
                        self.anticip_by_day.setdefault(entry_day, []).append((ev, signal_day))
        logger.info(
            "Prepared %d result events across %d signal days "
            "(%d real NSE dates, %d estimated-lag fallbacks).",
            sum(len(v) for v in self.events_by_day.values()), len(self.events_by_day),
            n_real, n_est,
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
            self._process_result_exits(d)   # B10: dump weak-result positions at open
            if self.cfg.anticipation_mode:
                self._fill_anticipation(d, opened_today)
            else:
                self._fill_pending(d, opened_today)
            self._manage(d, opened_today)

            snap = self.pf.record_equity(d, self._price_lookup(d))
            snap["pending"] = len(self.pending) + len(self.pending_anticip)
            self.daily_log.append(snap)

            if self.cfg.anticipation_mode:
                self._evaluate_results(d)       # grade results known as-of today
                self._discover_anticipation(d)  # queue pre-result entries for tomorrow
            else:
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
                self._bump("no_fill_bar")
                continue  # no session for this name today; the order lapses
            fill = float(bar["Open"])
            if fill <= 0:
                continue

            raw, quarters, metrics = self.parsed[ev.symbol]
            analysis = an.analyze_event(raw, quarters, metrics, ev.q_idx, fill, cfg=self.cfg)
            # Legacy path gates the fill on the absolute "strong" threshold. The
            # cross-sectional path already selected on relative rank, so it does
            # not re-impose that absolute gate here.
            if not self.cfg.cross_sectional and not analysis.is_strong:
                self._bump("weak_at_fill")
                continue
            plan = build_target_plan(analysis, fill)
            if plan is None and self.cfg.cross_sectional:
                # No PE anchor (banks/PSUs/holding cos): fall back to a static
                # target so a ranked pick is still takeable. The time-stop is the
                # primary exit in the cross-sectional design; the target is a cap.
                from qtr_results.targets import TargetPlan
                plan = TargetPlan(
                    method="static",
                    entry_price=fill,
                    target_pct=self.cfg.target_max_pct,
                    target_price=round(fill * (1 + self.cfg.target_max_pct / 100.0), 2),
                    trailing_stop_pct=0.0,  # informational; ATR stop set in make_position
                    raw_upside_pct=None,
                )
            if plan is None:
                continue

            # Re-clamp the PE-rerating target to the backtest's OWN band. The
            # live ``build_target_plan`` clamps to the live 10-20% band; when the
            # backtest is configured with a wider ``target_max_pct`` this lets
            # high-conviction winners run past 20% instead of booking early.
            if plan.method == "pe_rerating" and plan.raw_upside_pct is not None:
                from qtr_results.util import clamp as _clamp
                band_pct = _clamp(
                    plan.raw_upside_pct, self.cfg.target_min_pct, self.cfg.target_max_pct
                )
                if abs(band_pct - plan.target_pct) > 1e-9:
                    plan.target_pct = band_pct
                    plan.target_price = round(fill * (1 + band_pct / 100.0), 2)

            # B6 — override the live static-tier target with the tighter backtest
            # tiers (no PE anchor ⇒ don't be greedy).
            if plan.method == "static":
                new_pct = strategy.clamp_static_target(analysis.strength_score, self.cfg)
                if abs(new_pct - plan.target_pct) > 1e-9:
                    plan.target_pct = new_pct
                    plan.target_price = round(fill * (1 + new_pct / 100.0), 2)

            # B3 — PE-percentile guard: if the pre-result PE is already in the
            # top decile of the trailing distribution, cap the target at the
            # lower band. We use the full price history frame for the ranking.
            frame = self.prices.full(ev.symbol)
            pe_pct = an.pe_percentile(
                frame, quarters, metrics, ev.q_idx, day,
                reporting_lag_days=(self.cfg.reporting_lag_min + self.cfg.reporting_lag_max) // 2,
                history_years=self.cfg.pe_history_years,
            )
            if pe_pct is not None and pe_pct >= self.cfg.pe_pct_cap_threshold:
                capped = min(plan.target_pct, self.cfg.pe_pct_target_cap)
                if capped < plan.target_pct:
                    plan.target_pct = capped
                    plan.target_price = round(fill * (1 + capped / 100.0), 2)
                self._bump("pe_percentile_capped")

            # ATR-based stop distance, computed strictly from bars BEFORE the
            # entry day (point-in-time). We fetch (atr_period + 5) sessions up
            # to and including ``day`` then drop today's bar, so the ATR uses
            # only completed pre-entry sessions.
            hist = self.prices.as_of(
                ev.symbol, day, lookback_rows=self.cfg.atr_period + 5
            )
            if hist is not None and len(hist) > 1:
                pre_entry = hist.iloc[:-1]
            else:
                pre_entry = None
            atr = strategy.compute_atr(pre_entry, self.cfg.atr_period) if pre_entry is not None else None
            stop_distance = strategy.resolve_stop_distance(fill, atr, self.cfg)

            equity = self.pf.total_equity(lookup)

            # B5 — sector cap: skip if this entry would push same-sector notional
            # above ``max_sector_pct`` of equity.
            sector = self._sector_of(ev.symbol)
            sector_cap = equity * self.cfg.max_sector_pct / 100.0
            sector_used = self.pf.sector_deployed(sector, lookup)

            shares = strategy.size_position(
                fill, stop_distance, equity, self.pf.cash, self.cfg
            )
            if shares <= 0:
                self._bump("no_capacity")
                continue
            # Trim shares to respect the sector cap (never go below 0).
            headroom = max(sector_cap - sector_used, 0.0)
            max_by_sector = int(headroom // fill) if fill > 0 else 0
            if max_by_sector < shares:
                if max_by_sector <= 0:
                    self._bump("sector_cap")
                    continue
                shares = max_by_sector

            pos = strategy.make_position(
                ev.symbol, fill, day, shares, plan, analysis, ev.decl_date.isoformat(),
                stop_distance, sector,
            )
            if self.pf.open_position(pos):
                opened_today.add(ev.symbol)
                logger.debug("%s OPEN %s x%d @%.2f tgt %.2f stop %.2f dist %.2f (%s, sector=%s, pe_pct=%s)",
                             day, ev.symbol, shares, fill, pos.target_price,
                             pos.stop_price, stop_distance, plan.method, sector,
                             f"{pe_pct:.0f}" if pe_pct is not None else "n/a")
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

    # ── B10: pre-declaration anticipation entry/exit ──────────────────────────
    def _process_result_exits(self, day: date) -> None:
        """Dump positions flagged (weak result) at today's open."""
        for sym in list(self.pf.positions.keys()):
            pos = self.pf.positions[sym]
            if not pos.exit_at_open_reason:
                continue
            bar = self.prices.bar_on(sym, day)
            if bar is None:
                continue  # no session today; keep the flag, try next day
            self.pf.close_position(sym, float(bar["Open"]), day, pos.exit_at_open_reason)

    def _fill_anticipation(self, day: date, opened_today: set) -> None:
        """Fill queued pre-declaration entries at today's open (no result gate —
        we enter on the pre-run-up signal; the result is graded later)."""
        if not self.pending_anticip:
            return
        lookup = self._price_lookup(day)
        for ev, signal_day in self.pending_anticip:
            if len(self.pf.positions) >= self.cfg.max_positions:
                break
            if self.pf.has_open(ev.symbol):
                continue
            bar = self.prices.bar_on(ev.symbol, day)
            if bar is None:
                self._bump("no_fill_bar")
                continue
            fill = float(bar["Open"])
            if fill <= 0:
                continue

            hist = self.prices.as_of(ev.symbol, day, lookback_rows=self.cfg.atr_period + 5)
            pre_entry = hist.iloc[:-1] if hist is not None and len(hist) > 1 else None
            atr = strategy.compute_atr(pre_entry, self.cfg.atr_period) if pre_entry is not None else None
            stop_distance = strategy.resolve_stop_distance(fill, atr, self.cfg)

            equity = self.pf.total_equity(lookup)
            sector = self._sector_of(ev.symbol)
            sector_cap = equity * self.cfg.max_sector_pct / 100.0
            sector_used = self.pf.sector_deployed(sector, lookup)
            shares = strategy.size_position(fill, stop_distance, equity, self.pf.cash, self.cfg)
            if shares <= 0:
                self._bump("no_capacity")
                continue
            headroom = max(sector_cap - sector_used, 0.0)
            max_by_sector = int(headroom // fill) if fill > 0 else 0
            if max_by_sector < shares:
                if max_by_sector <= 0:
                    self._bump("sector_cap")
                    continue
                shares = max_by_sector

            # Pre-result position: NO target yet (set far away so only the ATR
            # trailing stop can exit before the result); target is set when the
            # result is graded strong in _evaluate_results.
            pos = Position(
                symbol=ev.symbol, quantity=shares, entry_price=round(fill, 2),
                entry_date=day, target_price=round(fill * 100.0, 2), target_pct=0.0,
                trailing_stop_pct=round(stop_distance / fill * 100.0, 2) if fill else 0.0,
                stop_distance=round(stop_distance, 4), stop_price=round(fill - stop_distance, 2),
                highest_price=round(fill, 2), sector=sector,
                result_quarter=ev.quarter_label, result_date=ev.decl_date.isoformat(),
                method="anticipation", strength_score=0.0,
                rationale="pre-declaration run-up",
                awaiting_result=True, result_signal_date=signal_day, result_q_idx=ev.q_idx,
            )
            if self.pf.open_position(pos):
                opened_today.add(ev.symbol)
                self._bump("anticip_entered")
        self.pending_anticip = []

    def _evaluate_results(self, day: date) -> None:
        """Grade the result for any pre-result position whose declaration is now
        known (signal_day <= today): STRONG (and low-debt) rides on with a target,
        WEAK is flagged for an immediate next-open exit."""
        for sym in list(self.pf.positions.keys()):
            pos = self.pf.positions[sym]
            if not pos.awaiting_result or pos.result_signal_date is None:
                continue
            if day < pos.result_signal_date:
                continue
            raw, quarters, metrics = self.parsed[sym]
            px = self._price_lookup(day)(sym) or pos.entry_price
            analysis = an.analyze_event(raw, quarters, metrics, pos.result_q_idx, px, cfg=self.cfg)
            pos.awaiting_result = False
            pos.result_quarter = analysis.latest_quarter

            # Apply the SAME quality gate as standard mode: a strong result in an
            # over-levered balance sheet is not a "good" result we want to ride.
            qm = an.quality_metrics(raw, quarters[pos.result_q_idx])
            apply_debt = self.cfg.apply_quality_to_financials or not qm.is_financial
            debt_ok = not (
                self.cfg.max_debt_to_equity is not None and apply_debt
                and qm.debt_to_equity is not None
                and qm.debt_to_equity > self.cfg.max_debt_to_equity
            )
            if analysis.is_strong and debt_ok:
                plan = build_target_plan(analysis, px)
                if plan is not None:
                    tgt_pct = plan.target_pct
                    if plan.method == "static":
                        tgt_pct = strategy.clamp_static_target(analysis.strength_score, self.cfg)
                    pos.target_pct = tgt_pct
                    pos.target_price = round(px * (1 + tgt_pct / 100.0), 2)
                    pos.method = plan.method
                pos.strength_score = analysis.strength_score
                # Re-anchor the trailing stop to the POST-result price so the ride
                # starts fresh from where the stock actually is now — not the
                # pre-result run-up peak (which would leave the stop above price
                # and knock us straight out).
                pos.highest_price = round(px, 2)
                pos.stop_price = round(px - pos.stop_distance, 2)
                self._bump("anticip_result_strong")
            else:
                pos.exit_at_open_reason = "weak_result"
                self._bump("anticip_result_weak")

    def _discover_anticipation(self, day: date) -> None:
        """Queue pre-declaration entries: events whose entry day is today and
        whose pre-run-up (relative strength vs benchmark) clears the threshold."""
        events = self.anticip_by_day.get(day, [])
        capacity = self.cfg.max_positions - len(self.pf.positions)
        if not events or capacity <= 0:
            self.pending_anticip = []
            return
        if not strategy.market_regime_ok(self.prices.benchmark_as_of(day), self.cfg):
            self._bump("market_regime_off")
            self.pending_anticip = []
            return

        bench_bars = self.prices.benchmark_as_of(day)
        scored: List[Tuple[float, an.ResultEvent, date]] = []
        for ev, signal_day in events:
            if self.pf.has_open(ev.symbol) or ev.symbol not in self.parsed:
                continue
            bars = self.prices.as_of(
                ev.symbol, day, lookback_rows=max(self.cfg.anticipation_rs_lookback + 5, 30)
            )
            rs = strategy.pre_declaration_rs(bars, bench_bars, self.cfg.anticipation_rs_lookback)
            liquid = strategy.liquidity_ok(bars, self.cfg.min_liquidity_median_20d)
            self.event_log.append({
                "signal_date": day.isoformat(), "symbol": ev.symbol,
                "quarter": ev.quarter_label, "decl_date": ev.decl_date.isoformat(),
                "decl_date_real": ev.decl_date_real, "is_strong": "", "strength": "",
                "yoy_profit": "", "qoq_profit": "", "yoy_eps": "",
                "confirmed": "", "confirmed_reason": "anticip", "liquid": liquid,
                "debt_to_equity": None, "roce": None, "pre_rs": rs,
            })
            if rs is None:
                self._bump("anticip_no_rs")
                continue
            if rs < self.cfg.anticipation_min_rs:
                self._bump("anticip_weak_runup")
                continue
            if not liquid:
                self._bump("illiquid")
                continue
            scored.append((rs, ev, signal_day))

        scored.sort(key=lambda t: t[0], reverse=True)
        take = min(capacity, self.cfg.max_new_per_day)
        self.pending_anticip = [(ev, sd) for _, ev, sd in scored[:take]]

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

        # B9 — market-regime throttle: don't open fresh earnings-momentum longs
        # while the benchmark is below its trend SMA (correlated-drawdown guard).
        # Point-in-time: benchmark_as_of(day) is rows dated <= the signal day.
        if not strategy.market_regime_ok(self.prices.benchmark_as_of(day), self.cfg):
            self._bump("market_regime_off")
            self.pending = []
            return

        scored: List[Tuple[float, an.ResultEvent, object]] = []
        candidates: List[ranking.Candidate] = []
        bench_bars = self.prices.benchmark_as_of(day) if self.cfg.use_sue else None
        for ev in events:
            if self.pf.has_open(ev.symbol):
                continue
            raw, quarters, metrics = self.parsed[ev.symbol]
            # Provisional analysis at today's close to gate + rank (price-agnostic
            # gate; the target is recomputed at the actual fill price tomorrow).
            close_px = self._price_lookup(day)(ev.symbol) or 0.0
            analysis = an.analyze_event(raw, quarters, metrics, ev.q_idx, close_px, cfg=self.cfg)

            # B4 / B7 — signal-day confirmation + liquidity filter. Both use
            # bars strictly on/before the signal day (no look-ahead).
            bars = self.prices.as_of(
                ev.symbol, day,
                lookback_rows=max(self.cfg.trend_ma_period + 10, 30),
            )
            confirmed, reason = strategy.signal_day_confirmed(bars, self.cfg)
            liquid = strategy.liquidity_ok(bars, self.cfg.min_liquidity_median_20d)

            # B8 — point-in-time balance-sheet quality (leverage + ROCE).
            qm = an.quality_metrics(raw, ev.quarter_label)

            # Earnings-SURPRISE signals (ideal-state redesign): SUE from the EPS
            # history, plus the declaration-day abnormal return. Point-in-time —
            # SUE uses quarters <= q_idx, the reaction uses bars <= signal day.
            sue = reaction = None
            if self.cfg.use_sue:
                eps_series = an._series(metrics, "eps")
                sue = signals.compute_sue(
                    eps_series, quarters, ev.q_idx, window=self.cfg.sue_window
                )
                reaction = signals.announcement_reaction(
                    bars, bench_bars, lookback=self.cfg.reaction_lookback
                )

            self.event_log.append({
                "signal_date": day.isoformat(),
                "symbol": ev.symbol,
                "quarter": ev.quarter_label,
                "decl_date": ev.decl_date.isoformat(),
                "decl_date_real": ev.decl_date_real,
                "is_strong": analysis.is_strong,
                "strength": analysis.strength_score,
                "yoy_profit": analysis.yoy_profit_growth,
                "qoq_profit": analysis.qoq_profit_growth,
                "yoy_eps": analysis.yoy_eps_growth,
                "confirmed": confirmed,
                "confirmed_reason": reason,
                "liquid": liquid,
                "debt_to_equity": qm.debt_to_equity,
                "roce": qm.roce,
                "sue": sue,
                "reaction": reaction,
            })

            # ── Cross-sectional path (opt-in) ─────────────────────────────────
            # Rank the day's field against itself instead of gating on absolute
            # thresholds. Leverage is a graded tilt here, NOT a hard reject, so the
            # only hard gates that remain are the market-microstructure ones
            # (liquidity + trend confirmation) plus a computable signal.
            if self.cfg.cross_sectional:
                if not liquid:
                    self._bump("illiquid")
                    continue
                if not confirmed:
                    self._bump(f"unconfirmed_{reason or 'na'}")
                    continue
                signal_val = sue if sue is not None else analysis.strength_score
                if signal_val is None:
                    self._bump("no_signal")
                    continue
                candidates.append(ranking.Candidate(
                    symbol=ev.symbol,
                    sue=sue,
                    reaction=reaction,
                    strength_score=analysis.strength_score,
                    debt_to_equity=qm.debt_to_equity,
                    is_financial=qm.is_financial,
                    payload=ev,
                ))
                continue

            # ── Legacy absolute-threshold path (default, unchanged) ───────────
            if not analysis.is_strong:
                self._bump("weak_result")
                continue
            if not liquid:
                self._bump("illiquid")
                continue
            if not confirmed:
                self._bump(f"unconfirmed_{reason or 'na'}")
                continue

            # B8 — reject over-levered / low-quality balance sheets. Banks/NBFCs
            # are exempt from the debt gate unless explicitly enabled; a missing
            # value never rejects (data-gap safe).
            apply_debt = self.cfg.apply_quality_to_financials or not qm.is_financial
            if (
                self.cfg.max_debt_to_equity is not None
                and apply_debt
                and qm.debt_to_equity is not None
                and qm.debt_to_equity > self.cfg.max_debt_to_equity
            ):
                self._bump("high_debt")
                continue
            if (
                self.cfg.min_roce is not None
                and apply_debt
                and qm.roce is not None
                and qm.roce < self.cfg.min_roce
            ):
                self._bump("low_roce")
                continue

            scored.append((analysis.strength_score, ev, analysis))

        take = min(capacity, self.cfg.max_new_per_day)
        if self.cfg.cross_sectional:
            ranked = ranking.composite_scores(
                candidates,
                w_sue=self.cfg.w_sue,
                w_reaction=self.cfg.w_reaction,
                w_quality=self.cfg.w_quality,
            )
            picks = ranking.select_top(
                ranked,
                top_quantile=self.cfg.top_quantile,
                cap=take,
                min_score=self.cfg.min_composite_score,
            )
            if picks:
                self._bump("xsection_selected")
            self.pending = [p.payload for p in picks]
            return

        scored.sort(key=lambda t: t[0], reverse=True)
        self.pending = [ev for _, ev, _ in scored[:take]]
