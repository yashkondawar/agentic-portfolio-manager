"""Backfill as-filed NSE quarterly results into the durable store.

Walks NSE's announcement archive one calendar quarter at a time and writes
every filing for the requested universe. Safe to interrupt and re-run: both
completed windows and individual fetch attempts are recorded, so a resumed run
skips work it already did.

    uv run python -m scraper.backfill_nse_fundamentals --from-year 2012
    uv run python -m scraper.backfill_nse_fundamentals --status
"""
from __future__ import annotations

import argparse
import logging
import pickle
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scraper import nse_fundamentals as nf
from scraper import fundamentals_store

logger = logging.getLogger("scraper.backfill_nse")

DEFAULT_CACHE = (
    Path(__file__).resolve().parents[1]
    / "backtesting" / "qtr_results" / "fundamentals_cache"
    / "fundamentals_500sym.pkl"
)


def announcement_windows(
    from_year: int, until: date
) -> List[Tuple[date, date]]:
    """Calendar quarters of *announcement* dates, covering the range with no gaps.

    Filings are indexed by when they were broadcast, not by the period they
    report, so the walk is over announcement time.
    """
    windows: List[Tuple[date, date]] = []
    for year in range(from_year, until.year + 1):
        for start_month in (1, 4, 7, 10):
            start = date(year, start_month, 1)
            end_month = start_month + 2
            last_day = 31 if end_month in (3, 12) else 30
            end = date(year, end_month, last_day)
            if start > until:
                break
            windows.append((start, min(end, until)))
    return windows


def universe_symbols(cache_path: Path) -> List[str]:
    with cache_path.open("rb") as fh:
        return sorted(pickle.load(fh))


def _rows_by_symbol_quarter(rows: Sequence[dict]) -> Dict[Tuple[str, str], List[dict]]:
    """Group index rows, consolidated first so it is tried first."""
    grouped: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        period_end = nf.parse_nse_date(row.get("toDate"))
        if not symbol or period_end is None:
            continue
        grouped.setdefault((symbol, period_end.isoformat()), []).append(row)
    for candidates in grouped.values():
        candidates.sort(
            key=lambda r: str(r.get("consolidated", "")).strip().lower()
            != "consolidated"
        )
    return grouped


def _filing_urls(row: dict) -> List[str]:
    urls = []
    xbrl = str(row.get("xbrl", "") or "").strip()
    if xbrl and nf._looks_like_xbrl(xbrl):
        urls.append(xbrl)
    detail = str(row.get("resultDetailedDataLink", "") or "").strip()
    if detail:
        urls.append(detail if detail.startswith("http") else nf._BASE + detail)
    return urls


def backfill_window(
    connection,
    from_date: date,
    to_date: date,
    wanted: Optional[set],
    seen_urls: set,
    *,
    both_bases: bool = False,
) -> Tuple[int, int]:
    """Fetch one announcement window. Returns (filings considered, rows stored)."""
    rows = nf.list_filings(from_date, to_date)
    if wanted:
        rows = [
            r for r in rows
            if str(r.get("symbol", "")).strip().upper() in wanted
        ]
    grouped = _rows_by_symbol_quarter(rows)

    stored: List[nf.QuarterlyResult] = []
    skipped = 0
    for (symbol, _), candidates in grouped.items():
        for row in candidates:
            urls = _filing_urls(row)
            if urls and all(u in seen_urls for u in urls):
                skipped += 1
                if not both_bases:
                    break
                continue
            parsed = nf.fetch_result(row)
            for url in urls:
                seen_urls.add(url)
                fundamentals_store.record_attempt(
                    connection, url, symbol, ok=parsed is not None and parsed.url == url
                )
            if parsed is not None:
                stored.append(parsed)
                # One good basis per quarter is enough; consolidated was first.
                if not both_bases:
                    break

    written = fundamentals_store.store_results(connection, stored)
    connection.commit()
    logger.info(
        "%s..%s: %d filings, %d parsed, %d already done.",
        from_date, to_date, len(grouped), written, skipped,
    )
    return len(grouped), written


def run(
    from_year: int,
    until: date,
    *,
    symbols: Optional[Sequence[str]],
    rate: float,
    resume: bool = True,
    both_bases: bool = False,
) -> None:
    nf.MIN_REQUEST_INTERVAL = rate
    connection = fundamentals_store.open_store()
    try:
        done = fundamentals_store.completed_windows(connection) if resume else set()
        seen = fundamentals_store.attempted_urls(connection) if resume else set()
        wanted = {s.strip().upper() for s in symbols} if symbols else None
        windows = announcement_windows(from_year, until)
        pending = [w for w in windows if (w[0].isoformat(), w[1].isoformat()) not in done]
        logger.info(
            "%d windows total, %d already complete, %d to do. "
            "%d URLs previously attempted.",
            len(windows), len(windows) - len(pending), len(pending), len(seen),
        )

        started = time.time()
        for i, (start, end) in enumerate(pending, start=1):
            filings, written = backfill_window(
                connection, start, end, wanted, seen, both_bases=both_bases
            )
            fundamentals_store.mark_window(connection, start, end, filings, written)
            elapsed = time.time() - started
            remaining = (elapsed / i) * (len(pending) - i)
            logger.info(
                "  [%d/%d] elapsed %.1f min, ~%.1f min left.",
                i, len(pending), elapsed / 60.0, remaining / 60.0,
            )
        print_status(connection)
    finally:
        connection.close()


def print_status(connection) -> None:
    stats = fundamentals_store.coverage(connection)
    windows = len(fundamentals_store.completed_windows(connection))
    print(
        f"\nStored {stats.get('rows', 0):,} filings for "
        f"{stats.get('symbols', 0):,} symbols across {windows} windows.\n"
        f"  quarters : {stats.get('first_quarter')} -> {stats.get('last_quarter')}\n"
        f"  with a real announcement timestamp: {stats.get('dated', 0):,}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2012)
    parser.add_argument(
        "--until", default=None, help="ISO date; defaults to today."
    )
    parser.add_argument(
        "--symbols-from", type=Path, default=DEFAULT_CACHE,
        help="Pickle whose keys are the universe. Use --all-symbols for everything.",
    )
    parser.add_argument("--all-symbols", action="store_true")
    parser.add_argument(
        "--rate", type=float, default=0.12,
        help="Minimum seconds between requests. NSE sustains ~14/s; the "
             "default of ~8/s leaves headroom.",
    )
    parser.add_argument(
        "--both-bases", action="store_true",
        help="Fetch standalone as well as consolidated. Roughly doubles the "
             "scrape for data the strategy does not use.",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--status", action="store_true", help="Report and exit.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.status:
        connection = fundamentals_store.open_store()
        try:
            print_status(connection)
        finally:
            connection.close()
        return 0

    symbols = None
    if not args.all_symbols:
        if not args.symbols_from.exists():
            parser.error(f"universe pickle not found: {args.symbols_from}")
        symbols = universe_symbols(args.symbols_from)
        logger.info("Universe: %d symbols from %s", len(symbols), args.symbols_from.name)

    until = date.fromisoformat(args.until) if args.until else date.today()
    run(
        args.from_year,
        until,
        symbols=symbols,
        rate=args.rate,
        resume=not args.no_resume,
        both_bases=args.both_bases,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
