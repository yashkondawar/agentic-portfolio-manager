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
from .data import FundamentalsStore, PointInTimeData
from .engine import BacktestEngine
from .metrics import compute_metrics, exit_reason_breakdown, render_summary

logger = logging.getLogger("backtest.qtr.run")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Point-in-time quarterly-results backtest.")
    p.add_argument("--start", help="YYYY-MM-DD (default: end - 1 year)")
    p.add_argument("--end", help="YYYY-MM-DD (default: today)")
    p.add_argument("--capital", type=float, default=500_000.0, help="Starting capital ₹")
    p.add_argument("--goal-pct", type=float, default=20.0, help="Goal return %%")
    p.add_argument("--universe", default="nifty200",
                   help="nifty50/100/200/500/midcap150/... (default nifty200)")
    p.add_argument("--universe-file", help="Custom universe file (one NSE symbol/line)")
    p.add_argument("--max-symbols", type=int, default=None,
                   help="Cap universe size (quick runs / lighter scraping)")
    p.add_argument("--reporting-lag-days", type=int, default=45,
                   help="Assumed days from quarter-end to result declaration")
    p.add_argument("--max-new-per-day", type=int, default=5)
    p.add_argument("--max-positions", type=int, default=10)
    p.add_argument("--max-holding-days", type=int, default=None,
                   help="Override the holding window (default: live 21 days)")
    p.add_argument("--risk-per-trade", type=float, default=2.0, help="2%% rule")
    p.add_argument("--min-yoy-profit-growth", type=float, default=None)
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
                   metrics: dict, summary: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = dict(metrics)
    metrics["exit_reasons"] = exit_reason_breakdown(engine.pf.closed)

    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps({"config": _config_json(cfg), "metrics": metrics}, indent=2),
        encoding="utf-8",
    )

    with open(out_dir / "trades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "result_quarter", "method", "strength", "quantity",
                    "entry_date", "entry_price", "exit_date", "exit_price",
                    "pnl", "pnl_pct", "holding_days", "exit_reason"])
        for t in engine.pf.closed:
            w.writerow([t.symbol, t.result_quarter, t.method, round(t.strength_score, 1),
                        t.quantity, t.entry_date.isoformat(), round(t.entry_price, 2),
                        t.exit_date.isoformat(), round(t.exit_price, 2), round(t.pnl, 2),
                        round(t.pnl_pct, 2), t.holding_days, t.exit_reason])

    with open(out_dir / "equity_curve.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "equity", "cash", "deployed", "open_positions", "pending"])
        for s in engine.daily_log:
            w.writerow([s["date"], s["equity"], s["cash"], s["deployed"],
                        s["open_positions"], s.get("pending", 0)])

    with open(out_dir / "events.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["signal_date", "symbol", "quarter", "decl_date", "is_strong",
                    "strength", "yoy_profit", "qoq_profit", "yoy_eps"])
        for e in engine.event_log:
            w.writerow([e["signal_date"], e["symbol"], e["quarter"], e["decl_date"],
                        e["is_strong"], e["strength"], e["yoy_profit"],
                        e["qoq_profit"], e["yoy_eps"]])

    open_rows = [
        {"symbol": p.symbol, "quantity": p.quantity, "entry_price": round(p.entry_price, 2),
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
        reporting_lag_days=args.reporting_lag_days,
        max_new_per_day=args.max_new_per_day,
        max_positions=args.max_positions,
        risk_per_trade_pct=args.risk_per_trade,
        use_cache=not args.no_cache,
    )
    if args.max_holding_days is not None:
        cfg.max_holding_days = args.max_holding_days
    if args.min_yoy_profit_growth is not None:
        cfg.min_yoy_profit_growth = args.min_yoy_profit_growth

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

    engine = BacktestEngine(cfg, prices, funds)
    engine.run(start, end)

    metrics = compute_metrics(
        engine.daily_log, engine.pf.closed, cfg.starting_capital, cfg.goal_capital()
    )
    summary = render_summary(metrics, cfg.goal_return_pct)

    tag = args.tag or f"{cfg.universe_index}_{start.isoformat()}_{end.isoformat()}"
    out_dir = RESULTS_DIR / tag
    _write_outputs(out_dir, cfg, engine, metrics, summary)

    print("\n" + summary)
    print(f"\nResults written to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
