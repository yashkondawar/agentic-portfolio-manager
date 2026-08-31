"""Resumable historical price backfill for the full universe.

Usage:
    .venv\\Scripts\\python scripts\\backfill_prices.py [--period 10y] [--chunk-size 50] [--sleep 2]

Resumable: instruments already holding >= RESUMABLE_ROW_THRESHOLD rows in
daily_prices are skipped, so re-running after an interruption (rate limit,
network blip, Ctrl-C) picks up roughly where it left off. Progress is
printed after every chunk. Logs one job_runs row for the whole run
(job_name='prices_backfill').
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from afund.data.base import log_job_run  # noqa: E402
from afund.data.prices_yf import (  # noqa: E402
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_SLEEP_SECONDS,
    get_active_instruments,
    run_price_fetch,
)
from afund.db.connection import get_conn  # noqa: E402


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumable historical price backfill.")
    parser.add_argument("--period", default="10y", help="yfinance period string, e.g. 10y, 5y")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--sleep", type=float, default=DEFAULT_CHUNK_SLEEP_SECONDS)
    parser.add_argument(
        "--limit", type=int, default=None, help="Only process the first N instruments (testing)."
    )
    args = parser.parse_args()

    conn = get_conn()
    job_name = "prices_backfill"
    started_at = _now_iso()

    try:
        instruments = get_active_instruments(conn)
        if args.limit:
            instruments = instruments[: args.limit]

        print(f"Backfill starting: {len(instruments)} candidate instruments, period={args.period}")
        stats = run_price_fetch(
            conn,
            instruments,
            period=args.period,
            chunk_size=args.chunk_size,
            chunk_sleep_seconds=args.sleep,
            resumable=True,
            print_progress=True,
        )
        finished_at = _now_iso()
        print(
            f"Backfill done: fetched={stats.tickers_fetched} "
            f"skipped(resume)={stats.tickers_skipped_resume} "
            f"rows_upserted={stats.rows_upserted} rows_rejected={stats.rows_rejected}"
        )
        log_job_run(conn, job_name, "SUCCESS", stats.rows_upserted, started_at, finished_at, None)

        total_rows = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        distinct_instruments = conn.execute(
            "SELECT COUNT(DISTINCT instrument_id) FROM daily_prices"
        ).fetchone()[0]
        print(f"daily_prices total rows: {total_rows}, distinct instruments covered: {distinct_instruments}")
    except Exception as exc:  # noqa: BLE001
        finished_at = _now_iso()
        log_job_run(conn, job_name, "FAILED", 0, started_at, finished_at, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
