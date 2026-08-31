"""Stopgap daily orchestrator: `python -m afund.data.run_daily`.

Runs the cadence-appropriate pipelines in sequence against the real
database, using one shared connection, and prints a one-line summary per
job. This is intentionally simple — a real scheduler (cron / Task
Scheduler / an actual Orchestrator agent) is future scope; this module just
gives Phase 1 a single command that does "today's work" end to end.

Sequence (mirrors config/settings.yaml -> cadences):
  1. universe       — weekly (Monday only, per cadences.weekly_idea_cycle's
                       spirit; cheap enough to no-op safely on other days
                       too, but we skip it to avoid hammering the source
                       daily for something that only changes periodically)
  2. prices_daily   — every day
  3. amfi_nav       — every day
  4. news_rss       — every day
  5. index_valuation — every day (current-day snapshot only, no backfill)
  6. india_vix      — every day (Phase 8; recent-window fetch, see
                       afund.data.india_vix.backfill_history() for the
                       one-off 10y historical backfill)
  7. fii_dii        — every day (Phase 8; forward-accumulating only, see
                       afund.data.fii_dii module docstring)

financials / corp_actions / newsletters are intentionally NOT run here:
they're watchlist-scoped (empty watchlist by default) and/or monthly
cadence — running them daily against an empty watchlist would be a no-op
anyway, and screener.in/newsletter fetches are better triggered explicitly
(scripts/smoke_source.py) or by a future dedicated weekly/monthly job.
"""
from __future__ import annotations

import datetime as dt

from afund.data.amfi_nav import AmfiNavPipeline
from afund.data.fii_dii import FiiDiiPipeline
from afund.data.index_valuation import IndexValuationPipeline
from afund.data.india_vix import IndiaVixPipeline
from afund.data.news_rss import NewsRssPipeline
from afund.data.prices_yf import PricesPipeline
from afund.data.universe import UniversePipeline
from afund.db.connection import get_conn


def _print_job(result) -> None:
    status_line = f"[{result.status}] {result.job_name}: rows_written={result.rows_written}"
    if result.error:
        status_line += f" error={result.error.splitlines()[0]}"
    print(status_line)


def run_daily(run_universe: bool | None = None) -> list:
    """Run the daily pipeline sequence. Returns the list of JobResults.

    run_universe: None = auto (only run on Monday); True/False forces it.
    """
    conn = get_conn()
    results = []
    try:
        if run_universe is None:
            run_universe = dt.date.today().weekday() == 0  # Monday
        if run_universe:
            print("Running universe (weekly refresh)...")
            results.append(UniversePipeline(conn=conn).run())
        else:
            print("Skipping universe (not the weekly refresh day; pass run_universe=True to force).")

        print("Running prices_daily...")
        results.append(PricesPipeline(conn=conn).run())

        print("Running amfi_nav...")
        results.append(AmfiNavPipeline(conn=conn).run())

        print("Running news_rss...")
        results.append(NewsRssPipeline(conn=conn).run())

        print("Running index_valuation...")
        results.append(IndexValuationPipeline(conn=conn).run())

        print("Running india_vix...")
        results.append(IndiaVixPipeline(conn=conn).run())

        print("Running fii_dii...")
        results.append(FiiDiiPipeline(conn=conn).run())

        print("\n--- Daily run summary ---")
        for result in results:
            _print_job(result)

        return results
    finally:
        conn.close()


def main() -> None:
    run_daily()


if __name__ == "__main__":
    main()
