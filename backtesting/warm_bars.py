"""
backtesting/warm_bars.py
========================

Warm and inspect the shared daily bar store (``core.bars``).

Backtests populate the store automatically, so this is never required - it just
lets you do the slow network pass once, deliberately, instead of discovering it
mid-run. Warming the widest window and universe you expect to use makes every
later run over any sub-window a pure disk read.

    # one-time: pull ~8 years of Nifty 500 daily bars
    python -m backtesting.warm_bars --universe nifty500 --start 2018-01-01

    # top up to today (only the new bars are downloaded)
    python -m backtesting.warm_bars --universe nifty500 --start 2018-01-01

    # what is on disk?
    python -m backtesting.warm_bars --stats

    # a symbol looks wrong - forget it and refetch
    python -m backtesting.warm_bars --universe nifty500 --start 2018-01-01 \
        --drop RELIANCE TCS

Only raw daily OHLCV is stored. Weekly and monthly candles and every RSI are
derived from it at run time, deliberately - see the module docstring of
``core.bars`` for why persisting indicators would be a leak and invalidation
hazard rather than an optimisation.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

from core import bars
from .gfs.config import GFSConfig
from .gfs.universe import load_universe

logger = logging.getLogger("backtest.warm_bars")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warm-bars",
        description="Populate the shared daily bar store used by every backtest.",
    )
    parser.add_argument("--universe", default="nifty500",
                        help="nifty100 | nifty500 | nse_all (default: nifty500)")
    parser.add_argument("--symbols", nargs="*", default=None,
                        help="Explicit symbols instead of a universe file.")
    parser.add_argument("--benchmark", default="^NSEI")
    parser.add_argument("--start", type=_parse_date, default=None,
                        help="First calendar day to cover (default: 8 years back).")
    parser.add_argument("--end", type=_parse_date, default=None,
                        help="Last calendar day to cover (default: today).")
    parser.add_argument("--chunk-size", type=int, default=40)
    parser.add_argument("--force", action="store_true",
                        help="Refetch even where the store already has coverage.")
    parser.add_argument("--drop", nargs="*", default=None,
                        help="Forget these symbols before syncing.")
    parser.add_argument("--stats", action="store_true",
                        help="Print store contents and exit.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    if args.stats:
        _print_stats()
        return 0

    if args.drop:
        dropped = bars.drop_symbols(args.drop)
        logger.info("Dropped %d symbol(s) from the store.", dropped)

    end = args.end or date.today()
    start = args.start or (end - timedelta(days=365 * 8))
    if start >= end:
        logger.error("--start must be before --end.")
        return 2

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols if s.strip()]
    else:
        universe = load_universe(GFSConfig(universe_index=args.universe))
        symbols = [row.symbol for row in universe]
    if not symbols:
        logger.error("No symbols resolved; nothing to do.")
        return 2

    logger.info(
        "Syncing %d symbols + benchmark %s over %s -> %s",
        len(symbols), args.benchmark, start, end,
    )
    report = bars.sync(
        [*symbols, args.benchmark],
        start,
        end,
        chunk_size=args.chunk_size,
        force=args.force,
    )
    print()
    print("Bar sync:", report.summary())
    if report.rebased:
        preview = ", ".join(report.rebased[:10])
        more = "" if len(report.rebased) <= 10 else f" (+{len(report.rebased) - 10} more)"
        print(f"  re-based by a corporate action, refetched: {preview}{more}")
    if report.failed:
        print(f"  failed: {len(report.failed)} symbol(s)")
    print()
    _print_stats()
    return 0


def _print_stats() -> None:
    stats = bars.store_stats()
    print("Daily bar store")
    print(f"  symbols with data   : {stats['symbols']:,}")
    print(f"  total bars          : {stats['bars']:,}")
    print(f"  date span           : {stats['first_day']} -> {stats['last_day']}")
    print(f"  symbols with no data: {stats['symbols_without_data']:,}")


if __name__ == "__main__":
    raise SystemExit(main())
