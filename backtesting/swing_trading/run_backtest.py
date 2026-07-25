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
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from .config import BacktestConfig
from .service import run_backtest

logger = logging.getLogger("backtest.run")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Point-in-time swing-trading backtest.")
    p.add_argument("--start", help="YYYY-MM-DD (default: end - 1 year)")
    p.add_argument("--end", help="YYYY-MM-DD (default: today)")
    p.add_argument(
        "--capital", type=float, default=500_000.0, help="Starting capital ₹"
    )
    p.add_argument("--goal-pct", type=float, default=20.0, help="Goal return %%")
    p.add_argument(
        "--universe",
        default="nifty200",
        help="nifty50/100/200/500/midcap150/... (default nifty200)",
    )
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


def main() -> int:
    # Windows consoles default to cp1252 which can't encode ₹ / box-drawing chars.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = _parse_args()
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

    result = run_backtest(cfg, tag=args.tag)

    print("\n" + result["summary"])
    summary_path = result["artifacts"].get("summary.txt")
    if summary_path:
        print(f"\nResults written to: {Path(summary_path).parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
