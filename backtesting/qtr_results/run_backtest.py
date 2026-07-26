"""
run_backtest.py
===============

CLI entrypoint for the point-in-time quarterly-results backtest.

Examples
--------
    # 1-year backtest ending today, Nifty 200 universe, ₹5L start, 20% goal
    python -m backtesting.qtr_results.run_backtest

    # Explicit window + bigger universe
    python -m backtesting.qtr_results.run_backtest \
        --start 2025-01-01 --end 2025-12-31 --universe nifty500

    # Reuse cached prices + fundamentals (offline), quick run on a small universe
    python -m backtesting.qtr_results.run_backtest --universe nifty50 --max-symbols 30

Outputs (in backtesting/qtr_results/results/<run-tag>/):
    summary.txt / summary.json   — headline metrics vs the goal (+ full config)
    trades.csv                   — every closed trade with exit reason
    equity_curve.csv             — daily equity / cash / deployed
    events.csv                   — every discovered result event + its verdict
    open_positions.json          — positions still open at the end of the window
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from .config import FUND_CACHE_DIR, PRICE_CACHE_DIR, RESULTS_DIR, BacktestConfig
from .data import FundamentalsStore, PointInTimeData, ResultsCalendarStore, SectorStore
from .engine import BacktestEngine
from .hedge import HedgeConfig, apply_beta_hedge, hedged_equity_series, realized_book_beta
from .metrics import (
    compute_metrics,
    enrich_metrics,
    exit_reason_breakdown,
    hedged_metrics,
    render_summary,
)

logger = logging.getLogger("backtest.qtr.run")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Point-in-time quarterly-results backtest.")
    p.add_argument("--start", help="YYYY-MM-DD (default: end - 1 year)")
    p.add_argument("--end", help="YYYY-MM-DD (default: today)")
    p.add_argument("--capital", type=float, default=500_000.0, help="Starting capital ₹")
    p.add_argument("--goal-pct", type=float, default=20.0, help="Goal return %%")
    p.add_argument("--universe", default="nifty200",
                   help="nifty50/100/200/500/midcap150/smallcap250/... (default nifty200). "
                        "Comma-separate to scan a UNION, e.g. 'nifty500,niftysmallcap250' "
                        "to reach the mid/small-cap earnings-drift zone.")
    p.add_argument("--universe-file", help="Custom universe file (one NSE symbol/line)")
    p.add_argument("--max-symbols", type=int, default=None,
                   help="Cap universe size (quick runs / lighter scraping)")
    p.add_argument("--reporting-lag-min", type=int, default=15,
                   help="Min days from quarter-end to result declaration (stagger low)")
    p.add_argument("--reporting-lag-max", type=int, default=45,
                   help="Max days from quarter-end to result declaration (stagger high)")
    p.add_argument("--max-new-per-day", type=int, default=5)
    p.add_argument("--max-positions", type=int, default=10)
    p.add_argument("--max-holding-days", type=int, default=None,
                   help="Override the holding window (default: 90)")
    p.add_argument("--atr-period", type=int, default=14,
                   help="ATR lookback period in sessions (default: 14)")
    p.add_argument("--atr-stop-multiplier", type=float, default=6.0,
                   help="Trailing-stop distance = ATR × this multiplier (default: 6.0 — "
                        "the regime-stable ride-the-wave setting; use 2.5-3 for a tighter, "
                        "shorter-horizon swing).")
    p.add_argument("--risk-per-trade", type=float, default=2.0, help="2%% rule")
    p.add_argument("--max-position-pct", type=float, default=None,
                   help="Per-name concentration cap %% of equity (default 20). Raising it "
                        "deploys more of the idle cash into the few concurrent picks.")
    p.add_argument("--min-yoy-profit-growth", type=float, default=None)
    p.add_argument("--target-max-pct", type=float, default=None,
                   help="Upper bound of the PE-rerating target band %% (default 20). "
                        "Raising it lets high-conviction winners run further.")
    p.add_argument("--target-min-pct", type=float, default=None,
                   help="Lower bound of the PE-rerating target band %% (default 10).")
    p.add_argument("--trail-only", action="store_true",
                   help="Ride-the-wave exit: DISABLE the fixed profit target and let "
                        "winners run until the ATR trailing stop (or time-stop) fires. "
                        "NOW ON BY DEFAULT (the fixed +20%% cap clipped the few real "
                        "runners); this flag is retained for explicitness. Use "
                        "--keep-target to restore the capped behavior.")
    p.add_argument("--keep-target", action="store_true",
                   help="Restore the fixed PE-rerating profit target (the pre-redesign "
                        "capped exit), overriding the default ride-the-wave behavior.")
    p.add_argument("--commission-pct", type=float, default=None,
                   help="Per-side commission %% (default 0.20 = ~40 bps rt)")
    p.add_argument("--pe-pct-threshold", type=float, default=None,
                   help="Percentile above which PE is deemed stretched (default 80)")
    p.add_argument("--pe-pct-target-cap", type=float, default=None,
                   help="Target cap when PE percentile is stretched (default 10%%)")
    p.add_argument("--max-sector-pct", type=float, default=None,
                   help="Per-sector concentration cap %% (default 30)")
    p.add_argument("--min-liquidity-cr", type=float, default=None,
                   help="Min 20-day median rupee turnover in ₹ crore (default 5)")
    p.add_argument("--max-debt-to-equity", type=float, default=None,
                   help="B8: reject names whose point-in-time debt/equity exceeds this "
                        "(Borrowings ÷ (Equity+Reserves)); banks/NBFCs exempt. Off by default.")
    p.add_argument("--min-roce", type=float, default=None,
                   help="B8: reject names whose point-in-time ROCE %% is below this. Off by default.")
    p.add_argument("--quality-on-financials", action="store_true",
                   help="Also apply the debt/ROCE gate to banks/NBFCs (default: exempt).")
    p.add_argument("--regime-filter", action="store_true",
                   help="B9: only open new positions when the benchmark is above its "
                        "regime SMA (correlated-drawdown guard).")
    p.add_argument("--regime-ma-period", type=int, default=None,
                   help="Benchmark SMA period for the regime filter (default 200).")
    p.add_argument("--regime-require-slope", action="store_true",
                   help="Also require the benchmark SMA to be non-declining.")
    p.add_argument("--disable-confirmation", action="store_true",
                   help="Disable signal-day confirmation filters (B4)")
    p.add_argument("--no-real-dates", action="store_true",                   help="Disable real NSE declaration dates; use the estimated "
                        "reporting-lag stagger for every event instead.")
    p.add_argument("--real-dates-only", action="store_true",
                   help="Trade ONLY events that have a real NSE declaration date "
                        "(drops hash-lag fallbacks — a clean-timing window).")
    p.add_argument("--anticipation-mode", action="store_true",
                   help="B10: enter N sessions BEFORE the result on a pre-run-up "
                        "signal; ride if the result is strong, dump next open if weak.")
    p.add_argument("--anticipation-lead-days", type=int, default=None,
                   help="Trading sessions before the declaration to enter (default 10).")
    p.add_argument("--anticipation-min-rs", type=float, default=None,
                   help="Min pre-declaration relative strength vs benchmark to enter "
                        "(e.g. 0.06 = +6%% over the lookback). Default 0.06.")
    p.add_argument("--anticipation-rs-lookback", type=int, default=None,
                   help="Lookback (sessions) for the pre-declaration RS signal (default 20).")
    p.add_argument("--decl-source", choices=["financial-results", "event-calendar"],
                   default="financial-results",
                   help="Real declaration-date source: 'financial-results' (per-symbol "
                        "NSE archive) or 'event-calendar' (bulk board-meeting calendar; "
                        "freshest quarters, use for a real past-N-months backtest).")
    # ── Ideal-state redesign (opt-in; defaults preserve legacy behavior) ──────
    p.add_argument("--use-sue", action="store_true",
                   help="Compute Standardized Unexpected Earnings (surprise vs the "
                        "company's own EPS trend) and the declaration-day reaction; "
                        "surfaced on events.csv and used as the primary signal under "
                        "--cross-sectional.")
    p.add_argument("--sue-window", type=int, default=None,
                   help="Trailing quarters for the SUE drift/vol estimate (default 8).")
    p.add_argument("--reaction-lookback", type=int, default=None,
                   help="Sessions for the declaration-day abnormal-return leg (default 1).")
    p.add_argument("--cross-sectional", action="store_true",
                   help="Rank the day's declarers against each other by a composite "
                        "z-score (SUE + reaction + graded leverage tilt) and buy the top "
                        "quantile, instead of buying every name over an absolute threshold. "
                        "Implies --use-sue.")
    p.add_argument("--top-quantile", type=float, default=None,
                   help="Fraction of the day's ranked field to buy under --cross-sectional "
                        "(default 0.20 = top quintile).")
    p.add_argument("--min-composite-score", type=float, default=None,
                   help="Optional absolute floor on the composite z-score (a weak season "
                        "then deploys less). Off by default.")
    p.add_argument("--w-sue", type=float, default=None, help="Composite weight: SUE (default 0.5)")
    p.add_argument("--w-reaction", type=float, default=None,
                   help="Composite weight: declaration reaction (default 0.3)")
    p.add_argument("--w-quality", type=float, default=None,
                   help="Composite weight: leverage tilt (default 0.2)")
    p.add_argument("--hedge", action="store_true",
                   help="Overlay a short-index BETA HEDGE on the equity curve to isolate "
                        "the PEAD alpha (the honest out-of-sample test). Adds a hedged "
                        "block to the summary + a hedged equity column.")
    p.add_argument("--hedge-ratio", type=float, default=None,
                   help="Fraction of the book's beta to short (default 1.0 = neutralize).")
    p.add_argument("--market-neutral", action="store_true",
                   help="Shortcut for --hedge --hedge-ratio 1.0 (fully beta-neutral book).")
    p.add_argument("--num-trials", type=int, default=None,
                   help="Number of configs explored, for the DEFLATED Sharpe penalty. "
                        "Set honestly (default 1).")
    p.add_argument("--no-cache", action="store_true", help="Force fresh downloads")
    p.add_argument("--tag", default=None, help="Override output run-tag")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def _resolve_dates(args) -> tuple[date, date]:
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=365)
    if start >= end:
        raise SystemExit("start must be before end")
    return start, end


def _config_json(cfg: BacktestConfig) -> dict:
    d = asdict(cfg)
    for k, v in list(d.items()):
        if isinstance(v, (date, Path)):
            d[k] = str(v)
    return d


def _write_outputs(out_dir: Path, cfg: BacktestConfig, engine: BacktestEngine,
                   metrics: dict, summary: str, hedged: dict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = dict(metrics)
    metrics["exit_reasons"] = exit_reason_breakdown(engine.pf.closed)
    metrics["filter_stats"] = dict(sorted(engine.filter_stats.items()))

    payload = {"config": _config_json(cfg), "metrics": metrics}
    if hedged is not None:
        payload["hedged_metrics"] = hedged

    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    with open(out_dir / "trades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "sector", "result_quarter", "method", "strength", "quantity",
                    "entry_date", "entry_price", "exit_date", "exit_price",
                    "pnl", "pnl_pct", "holding_days", "exit_reason"])
        for t in engine.pf.closed:
            # Sector is stored on the (now closed) Position — pull it from the
            # ClosedTrade's parent position if we recorded it; else UNKNOWN.
            sector = getattr(t, "sector", None) or "UNKNOWN"
            w.writerow([t.symbol, sector, t.result_quarter, t.method, round(t.strength_score, 1),
                        t.quantity, t.entry_date.isoformat(), round(t.entry_price, 2),
                        t.exit_date.isoformat(), round(t.exit_price, 2), round(t.pnl, 2),
                        round(t.pnl_pct, 2), t.holding_days, t.exit_reason])

    with open(out_dir / "equity_curve.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        has_hedge = bool(engine.daily_log) and "hedged_equity" in engine.daily_log[0]
        header = ["date", "equity", "cash", "deployed", "open_positions", "pending"]
        if has_hedge:
            header += ["hedge_notional", "hedge_pnl", "hedged_equity"]
        w.writerow(header)
        for s in engine.daily_log:
            row = [s["date"], s["equity"], s["cash"], s["deployed"],
                   s["open_positions"], s.get("pending", 0)]
            if has_hedge:
                row += [s.get("hedge_notional", 0.0), s.get("hedge_pnl", 0.0),
                        s.get("hedged_equity", s["equity"])]
            w.writerow(row)

    with open(out_dir / "events.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["signal_date", "symbol", "quarter", "decl_date", "decl_date_real",
                    "is_strong", "strength", "yoy_profit", "qoq_profit", "yoy_eps",
                    "confirmed", "confirmed_reason", "liquid",
                    "debt_to_equity", "roce", "pre_rs", "sue", "reaction"])
        for e in engine.event_log:
            w.writerow([e["signal_date"], e["symbol"], e["quarter"], e["decl_date"],
                        e.get("decl_date_real"),
                        e["is_strong"], e["strength"], e["yoy_profit"],
                        e["qoq_profit"], e["yoy_eps"],
                        e.get("confirmed"), e.get("confirmed_reason"), e.get("liquid"),
                        e.get("debt_to_equity"), e.get("roce"), e.get("pre_rs"),
                        e.get("sue"), e.get("reaction")])

    open_rows = [
        {"symbol": p.symbol, "sector": p.sector, "quantity": p.quantity,
         "entry_price": round(p.entry_price, 2),
         "entry_date": p.entry_date.isoformat(), "stop_price": round(p.stop_price, 2),
         "target_price": round(p.target_price, 2), "result_quarter": p.result_quarter,
         "method": p.method, "strength": round(p.strength_score, 1)}
        for p in engine.pf.positions.values()
    ]
    (out_dir / "open_positions.json").write_text(json.dumps(open_rows, indent=2), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    # Windows consoles default to cp1252 which can't encode ₹ / box-drawing chars.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    start, end = _resolve_dates(args)

    cfg = BacktestConfig(
        starting_capital=args.capital,
        goal_return_pct=args.goal_pct,
        start_date=start,
        end_date=end,
        universe_index=args.universe,
        universe_file=Path(args.universe_file) if args.universe_file else None,
        max_symbols=args.max_symbols,
        reporting_lag_min=args.reporting_lag_min,
        reporting_lag_max=args.reporting_lag_max,
        max_new_per_day=args.max_new_per_day,
        max_positions=args.max_positions,
        risk_per_trade_pct=args.risk_per_trade,
        atr_period=args.atr_period,
        atr_stop_multiplier=args.atr_stop_multiplier,
        use_cache=not args.no_cache,
    )
    if args.max_holding_days is not None:
        cfg.max_holding_days = args.max_holding_days
    if args.min_yoy_profit_growth is not None:
        cfg.min_yoy_profit_growth = args.min_yoy_profit_growth
    if args.target_max_pct is not None:
        cfg.target_max_pct = args.target_max_pct
    if args.target_min_pct is not None:
        cfg.target_min_pct = args.target_min_pct
    if args.trail_only:
        cfg.disable_profit_target = True
    if args.keep_target:
        cfg.disable_profit_target = False
    if args.commission_pct is not None:
        cfg.commission_pct = args.commission_pct
    if args.pe_pct_threshold is not None:
        cfg.pe_pct_cap_threshold = args.pe_pct_threshold
    if args.pe_pct_target_cap is not None:
        cfg.pe_pct_target_cap = args.pe_pct_target_cap
    if args.max_sector_pct is not None:
        cfg.max_sector_pct = args.max_sector_pct
    if args.min_liquidity_cr is not None:
        cfg.min_liquidity_median_20d = args.min_liquidity_cr * 1e7  # crore → rupees
    if args.max_debt_to_equity is not None:
        cfg.max_debt_to_equity = args.max_debt_to_equity
    if args.min_roce is not None:
        cfg.min_roce = args.min_roce
    if args.quality_on_financials:
        cfg.apply_quality_to_financials = True
    if args.max_position_pct is not None:
        cfg.max_position_pct = args.max_position_pct
    if args.regime_filter:
        cfg.regime_filter = True
    if args.regime_ma_period is not None:
        cfg.regime_ma_period = args.regime_ma_period
    if args.regime_require_slope:
        cfg.regime_require_slope = True
    if args.disable_confirmation:
        cfg.require_signal_day_green = False
        cfg.require_uptrend = False
    if args.no_real_dates:
        cfg.use_real_decl_dates = False
    if args.real_dates_only:
        cfg.real_dates_only = True
    if args.anticipation_mode:
        cfg.anticipation_mode = True
    if args.anticipation_lead_days is not None:
        cfg.anticipation_lead_days = args.anticipation_lead_days
    if args.anticipation_min_rs is not None:
        cfg.anticipation_min_rs = args.anticipation_min_rs
    if args.anticipation_rs_lookback is not None:
        cfg.anticipation_rs_lookback = args.anticipation_rs_lookback
    # ── Ideal-state redesign knobs (opt-in) ──────────────────────────────────
    if args.use_sue or args.cross_sectional:
        cfg.use_sue = True
    if args.sue_window is not None:
        cfg.sue_window = args.sue_window
    if args.reaction_lookback is not None:
        cfg.reaction_lookback = args.reaction_lookback
    if args.cross_sectional:
        cfg.cross_sectional = True
    if args.top_quantile is not None:
        cfg.top_quantile = args.top_quantile
    if args.min_composite_score is not None:
        cfg.min_composite_score = args.min_composite_score
    if args.w_sue is not None:
        cfg.w_sue = args.w_sue
    if args.w_reaction is not None:
        cfg.w_reaction = args.w_reaction
    if args.w_quality is not None:
        cfg.w_quality = args.w_quality
    if args.market_neutral:
        cfg.hedge_enabled = True
        cfg.hedge_ratio = 1.0
    if args.hedge:
        cfg.hedge_enabled = True
    if args.hedge_ratio is not None:
        cfg.hedge_ratio = args.hedge_ratio
    if args.num_trials is not None:
        cfg.num_trials = args.num_trials

    # Universe (reuses the live curator's loaders — same as the swing backtest).
    from backtesting.swing_trading.watchlist import load_universe
    universe = load_universe(cfg)
    symbols = [u.symbol for u in universe]
    if cfg.max_symbols:
        symbols = symbols[: cfg.max_symbols]
    logger.info("Universe '%s': %d symbols", cfg.universe_index, len(symbols))

    # Fundamentals (screener.in, cached once).
    funds = FundamentalsStore(FUND_CACHE_DIR)
    funds.load_or_download(symbols, use_cache=cfg.use_cache)
    if not funds.raw:
        raise SystemExit("No fundamentals scraped — aborting.")

    # Prices (yfinance, cached once). Only names we actually have fundamentals for.
    prices = PointInTimeData(PRICE_CACHE_DIR)
    prices.load_or_download(
        symbols=funds.symbols(), benchmark=cfg.benchmark,
        start=start, end=end, warmup_days=cfg.warmup_days, use_cache=cfg.use_cache,
    )
    if not prices.frames:
        raise SystemExit("No price data downloaded — aborting.")

    # Sectors (yfinance, cached once) — used for the per-sector concentration cap.
    sectors = SectorStore(FUND_CACHE_DIR)
    sectors.load_or_download(funds.symbols(), use_cache=cfg.use_cache)

    # Real result-declaration dates (NSE, cached once). When enabled, each event
    # is timed to the actual announcement instead of an estimated reporting lag;
    # missing symbols/quarters transparently fall back to the lag estimate.
    calendar = None
    if cfg.use_real_decl_dates:
        calendar = ResultsCalendarStore(FUND_CACHE_DIR)
        if args.decl_source == "event-calendar":
            # Bulk source: the whole market's board-meeting calendar over the
            # backtest window (freshest quarters; a few month-chunked requests).
            calendar.load_from_event_calendar(
                funds.symbols(), start, end, use_cache=cfg.use_cache
            )
        else:
            calendar.load_or_download(funds.symbols(), use_cache=cfg.use_cache)
        have, tot = calendar.coverage()
        logger.info("Real result dates resolved for %d / %d symbols.", have, tot)

    engine = BacktestEngine(cfg, prices, funds, sectors=sectors, calendar=calendar)
    engine.run(start, end)

    metrics = compute_metrics(
        engine.daily_log, engine.pf.closed, cfg.starting_capital, cfg.goal_capital()
    )
    metrics = enrich_metrics(metrics, engine.daily_log, num_trials=cfg.num_trials)

    # ── Beta-hedge overlay (opt-in): isolate the PEAD alpha from market direction.
    hedged = None
    if cfg.hedge_enabled:
        book_beta = cfg.hedge_book_beta
        if cfg.hedge_use_measured_beta:
            measured = realized_book_beta(engine.daily_log, prices.benchmark)
            if measured is not None and measured > 0:
                book_beta = measured
                logger.info("Measured book beta = %.2f (used for the hedge).", measured)
        hcfg = HedgeConfig(
            enabled=True,
            hedge_ratio=cfg.hedge_ratio,
            book_beta=book_beta,
            commission_pct=cfg.hedge_commission_pct,
            annual_carry_pct=cfg.hedge_annual_carry_pct,
        )
        overlaid = apply_beta_hedge(engine.daily_log, prices.benchmark, hcfg)
        engine.daily_log = overlaid  # carry the hedge columns into equity_curve.csv
        hedged = hedged_metrics(
            hedged_equity_series(overlaid), engine.pf.closed,
            cfg.starting_capital, cfg.goal_capital(), num_trials=cfg.num_trials,
        )

    summary = render_summary(metrics, cfg.goal_return_pct, hedged=hedged)

    tag = args.tag or f"{cfg.universe_index}_{start.isoformat()}_{end.isoformat()}"
    tag = tag.replace(",", "+").replace(" ", "")
    out_dir = RESULTS_DIR / tag
    _write_outputs(out_dir, cfg, engine, metrics, summary, hedged=hedged)

    print("\n" + summary)
    print(f"\nResults written to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
