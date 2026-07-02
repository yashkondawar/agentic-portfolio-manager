"""
run_backtest.py
===============

CLI entrypoint for the point-in-time swing-trading backtest.

Examples
--------
    # 1-year backtest ending today, Nifty 200 universe, ₹5L start, 20% goal
    python -m backtesting.swing_trading.run_backtest

    # Explicit window + bigger universe
    python -m backtesting.swing_trading.run_backtest \
        --start 2025-01-01 --end 2025-12-31 --universe nifty500

    # Reuse cached prices (offline), smaller universe for a quick run
    python -m backtesting.swing_trading.run_backtest --universe nifty100

Outputs (in backtesting/swing_trading/results/<run-tag>/):
    summary.txt / summary.json   — headline metrics vs the goal
    trades.csv                   — every closed trade with exit reason
    equity_curve.csv             — daily equity / cash / deployed
    watchlists.json              — the monthly point-in-time watchlists
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

from .config import DATA_CACHE_DIR, RESULTS_DIR, BacktestConfig
from .data import PointInTimeData
from .engine import BacktestEngine
from .metrics import compute_metrics, render_summary
from .watchlist import load_universe

logger = logging.getLogger("backtest.run")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Point-in-time swing-trading backtest.")
    p.add_argument("--start", help="YYYY-MM-DD (default: end - 1 year)")
    p.add_argument("--end", help="YYYY-MM-DD (default: today)")
    p.add_argument("--capital", type=float, default=500_000.0, help="Starting capital ₹")
    p.add_argument("--goal-pct", type=float, default=20.0, help="Goal return %%")
    p.add_argument("--universe", default="nifty200",
                   help="nifty50/100/200/500/midcap150/... (default nifty200)")
    p.add_argument("--universe-file", help="Custom universe file (one NSE symbol/line)")
    p.add_argument("--watchlist-size", type=int, default=20)
    p.add_argument("--max-positions", type=int, default=8)
    p.add_argument("--target-pct", type=float, default=20.0, help="Per-trade target %%")
    p.add_argument("--max-holding-days", type=int, default=30)
    p.add_argument("--risk-per-trade", type=float, default=2.0, help="2%% rule")
    p.add_argument("--no-cache", action="store_true", help="Force fresh download")
    p.add_argument("--tag", default=None, help="Override output run-tag")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def _resolve_dates(args) -> tuple[date, date]:
    end = date.fromisoformat(args.end) if args.end else date.today()
    if args.start:
        start = date.fromisoformat(args.start)
    else:
        start = end - timedelta(days=365)
    if start >= end:
        raise SystemExit("start must be before end")
    return start, end


def _write_outputs(out_dir: Path, cfg: BacktestConfig, engine: BacktestEngine,
                   metrics: dict, summary: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps({"config": _config_json(cfg), "metrics": metrics}, indent=2),
        encoding="utf-8",
    )

    # Trades.
    with open(out_dir / "trades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "setup", "quantity", "entry_date", "entry_price",
                    "exit_date", "exit_price", "pnl", "pnl_pct", "holding_days",
                    "exit_reason"])
        for t in engine.pf.closed:
            w.writerow([t.symbol, t.setup, t.quantity, t.entry_date.isoformat(),
                        round(t.entry_price, 2), t.exit_date.isoformat(),
                        round(t.exit_price, 2), round(t.pnl, 2), round(t.pnl_pct, 2),
                        t.holding_days, t.exit_reason])

    # Equity curve.
    with open(out_dir / "equity_curve.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "equity", "cash", "deployed", "open_positions", "watchlist_size"])
        for s in engine.daily_log:
            w.writerow([s["date"], s["equity"], s["cash"], s["deployed"],
                        s["open_positions"], s.get("watchlist_size", 0)])

    (out_dir / "watchlists.json").write_text(
        json.dumps(engine.watchlist_log, indent=2), encoding="utf-8"
    )

    # Still-open positions at the end (unrealized).
    open_rows = [
        {"symbol": p.symbol, "quantity": p.quantity, "entry_price": round(p.entry_price, 2),
         "entry_date": p.entry_date.isoformat(), "stop_loss": round(p.stop_loss, 2),
         "target_price": round(p.target_price, 2), "setup": p.setup}
        for p in engine.pf.positions.values()
    ]
    (out_dir / "open_positions.json").write_text(json.dumps(open_rows, indent=2), encoding="utf-8")


def _config_json(cfg: BacktestConfig) -> dict:
    d = asdict(cfg)
    for k, v in list(d.items()):
        if isinstance(v, (date, Path)):
            d[k] = str(v)
    return d


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
        watchlist_size=args.watchlist_size,
        max_positions=args.max_positions,
        target_profit_pct=args.target_pct,
        max_holding_days=args.max_holding_days,
        risk_per_trade_pct=args.risk_per_trade,
        use_cache=not args.no_cache,
    )

    logger.info("Loading universe '%s' ...", cfg.universe_index)
    universe = load_universe(cfg)
    logger.info("Universe: %d symbols", len(universe))

    data = PointInTimeData(DATA_CACHE_DIR)
    data.load_or_download(
        symbols=[u.symbol for u in universe],
        benchmark=cfg.benchmark,
        start=start, end=end, warmup_days=cfg.warmup_days,
        use_cache=cfg.use_cache,
    )
    if not data.frames:
        raise SystemExit("No price data downloaded — aborting.")

    engine = BacktestEngine(cfg, data, universe)
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
