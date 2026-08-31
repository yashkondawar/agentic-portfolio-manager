"""Smoke-test one Phase 1 data source live, with a deliberately small scope.

Usage:
    .venv\\Scripts\\python scripts\\smoke_source.py <name>

Names: universe, prices, index_valuation, amfi, news, financials,
       corp_actions, newsletters

Each runs the real pipeline against the real source (small scope: a
handful of tickers/symbols, not the full universe) and prints rows
written + a small sample, so you can eyeball that a source is still
working without waiting for a full production run.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from afund.db.connection import get_conn  # noqa: E402


def _print_result(result) -> None:
    print(f"job_name       : {result.job_name}")
    print(f"status         : {result.status}")
    print(f"rows_written   : {result.rows_written}")
    print(f"started_at     : {result.started_at}")
    print(f"finished_at    : {result.finished_at}")
    if result.error:
        print(f"error          : {result.error.splitlines()[0]}")
    sample = result.sample
    if isinstance(sample, list):
        print(f"sample (first 3 of {len(sample)}):")
        for item in sample[:3]:
            print(f"  {item}")
    elif sample is not None:
        print(f"sample: {str(sample)[:500]}")


def smoke_universe() -> None:
    from afund.data.universe import UniversePipeline

    conn = get_conn()
    result = UniversePipeline(conn=conn).run()
    _print_result(result)


def smoke_prices() -> None:
    from afund.data.prices_yf import PricesPipeline, get_active_instruments

    conn = get_conn()
    instruments = get_active_instruments(conn)[:5]
    if not instruments:
        print("No active instruments with yf_ticker found — run `universe` first.")
        return
    print(f"Scope: {[i['symbol'] for i in instruments]}")

    class _SmokePricesPipeline(PricesPipeline):
        def fetch(self):
            return instruments

    result = _SmokePricesPipeline(conn=conn, lookback_days=14).run()
    _print_result(result)


def smoke_index_valuation() -> None:
    from afund.data.index_valuation import IndexValuationPipeline

    conn = get_conn()
    result = IndexValuationPipeline(conn=conn, backfill_years=0).run()
    _print_result(result)


def smoke_amfi() -> None:
    from afund.data.amfi_nav import AmfiNavPipeline

    conn = get_conn()
    result = AmfiNavPipeline(conn=conn).run()
    _print_result(result)


def smoke_news() -> None:
    from afund.data.news_rss import NewsRssPipeline

    conn = get_conn()
    pipeline = NewsRssPipeline(conn=conn)
    result = pipeline.run()
    _print_result(result)
    if pipeline.feed_errors:
        print(f"feed_errors: {pipeline.feed_errors}")


def smoke_financials() -> None:
    from afund.data.financials import FinancialsPipeline

    conn = get_conn()
    result = FinancialsPipeline(conn=conn, symbols=["INFY"]).run()
    _print_result(result)


def smoke_corp_actions() -> None:
    from afund.data.corp_actions import CorpActionsPipeline

    conn = get_conn()
    result = CorpActionsPipeline(conn=conn, symbols=["INFY"]).run()
    _print_result(result)


def smoke_newsletters() -> None:
    from afund.data.newsletters import NewslettersPipeline

    conn = get_conn()
    result = NewslettersPipeline(conn=conn).run()
    _print_result(result)


SMOKE_FUNCS = {
    "universe": smoke_universe,
    "prices": smoke_prices,
    "index_valuation": smoke_index_valuation,
    "amfi": smoke_amfi,
    "news": smoke_news,
    "financials": smoke_financials,
    "corp_actions": smoke_corp_actions,
    "newsletters": smoke_newsletters,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SMOKE_FUNCS:
        names = ", ".join(SMOKE_FUNCS)
        print(f"Usage: python scripts/smoke_source.py <name>\nNames: {names}")
        sys.exit(1)

    name = sys.argv[1]
    print(f"=== smoke test: {name} ===")
    SMOKE_FUNCS[name]()


if __name__ == "__main__":
    main()
