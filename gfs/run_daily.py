"""
run_daily.py
============

Command-line entrypoint for the nightly job::

    python -m gfs.run_daily

Run it after the NSE close (any time after ~16:00 IST; the bar store only has
today's candle once the exchange has published it). It replays every session
since the last run, saves the book, and prints the orders to place at the next
open.

Windows Task Scheduler
----------------------
Point a Basic Task at your interpreter with these settings:

* Program:   ``C:\\path\\to\\python.exe``
* Arguments: ``-m gfs.run_daily``
* Start in:  the repository root (this matters - the package is imported by path)

Exit codes: ``0`` success, ``1`` failure. A failure never writes the book, so a
crashed run cannot leave a half-updated portfolio behind; the next run simply
replays the same sessions.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from .config import LIVE_DEFAULTS, REGIME_MODES
from . import engine


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m gfs.run_daily",
        description="Run the live GFS strategy for one day (post market close).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Pretend today is this date (YYYY-MM-DD). Defaults to today.",
    )
    p.add_argument(
        "--bootstrap-from",
        type=date.fromisoformat,
        default=None,
        help=(
            "Only used when the book does not exist yet: replay from this date "
            "so the live book inherits a track record and any open positions."
        ),
    )
    p.add_argument(
        "--capital",
        type=float,
        default=LIVE_DEFAULTS["starting_capital"],
        help="Starting capital, used once when the book is created.",
    )
    p.add_argument("--universe", default=LIVE_DEFAULTS["universe_index"])
    p.add_argument("--s-rsi", type=float, default=LIVE_DEFAULTS["s_rsi_entry"])
    p.add_argument("--exit-rsi", type=float, default=LIVE_DEFAULTS["exit_rsi"])
    p.add_argument(
        "--shadow-exit-rsi",
        type=float,
        default=LIVE_DEFAULTS["shadow_exit_rsi"],
        help="Reported but never traded. 0 disables the shadow report.",
    )
    p.add_argument("--atr-mult", type=float, default=LIVE_DEFAULTS["atr_stop_mult"])
    p.add_argument(
        "--min-headroom", type=float, default=LIVE_DEFAULTS["min_headroom_pct"]
    )
    p.add_argument(
        "--regime-mode", choices=list(REGIME_MODES), default=LIVE_DEFAULTS["regime_mode"]
    )
    p.add_argument("--min-breadth", type=float, default=LIVE_DEFAULTS["min_breadth_pct"])
    p.add_argument("--max-positions", type=int, default=LIVE_DEFAULTS["max_positions"])
    p.add_argument(
        "--max-position-pct", type=float, default=LIVE_DEFAULTS["max_position_pct"]
    )
    p.add_argument("--sector-top-n", type=int, default=LIVE_DEFAULTS["sector_top_n"])
    p.add_argument("--max-per-sector", type=int, default=LIVE_DEFAULTS["max_per_sector"])
    p.add_argument("--cash-yield", type=float, default=LIVE_DEFAULTS["cash_yield_pct"])
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print, but do not persist anything.",
    )
    p.add_argument(
        "--reset-book",
        action="store_true",
        help="DESTRUCTIVE: delete the saved book (cash, positions, tradebook) first.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def params_from_args(args: argparse.Namespace) -> dict:
    return {
        "as_of": args.as_of,
        "bootstrap_from": args.bootstrap_from,
        "starting_capital": args.capital,
        "universe_index": args.universe,
        "s_rsi_entry": args.s_rsi,
        "exit_rsi": args.exit_rsi,
        "shadow_exit_rsi": args.shadow_exit_rsi,
        "atr_stop_mult": args.atr_mult,
        "min_headroom_pct": args.min_headroom,
        "regime_mode": args.regime_mode,
        "min_breadth_pct": args.min_breadth,
        "max_positions": args.max_positions,
        "max_position_pct": args.max_position_pct,
        "sector_top_n": args.sector_top_n,
        "max_per_sector": args.max_per_sector,
        "cash_yield_pct": args.cash_yield,
        "dry_run": args.dry_run,
        "reset_book": args.reset_book,
    }


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if args.reset_book and not args.dry_run:
        logging.getLogger("gfs.run_daily").warning(
            "--reset-book will erase the saved GFS book, including its tradebook."
        )
    try:
        result = engine.run(params_from_args(args))
    except Exception as exc:  # noqa: BLE001 - a scheduled job must report, not traceback
        logging.getLogger("gfs.run_daily").exception("GFS live run failed: %s", exc)
        return 1
    print(result["report"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
