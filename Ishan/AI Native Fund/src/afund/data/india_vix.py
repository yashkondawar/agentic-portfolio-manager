"""India VIX daily pipeline — Phase 8 macro KPI sourcing.

Primary source: the `nse` PyPI library's NSE.fetch_historical_vix_data()
(see config/sources.yaml macro.nse_india_vix) — handles the NSE cookie
bootstrap internally. Falls back to yfinance ticker "^INDIAVIX" if the
`nse` library call raises (e.g. NSE blocking, library unavailable).

FINDING (Phase 8 live check): a single fetch_historical_vix_data() call
spanning a wide date range (e.g. 10 years) is silently truncated
server-side to a few hundred trading days rather than erroring or
returning the full range — confirmed live: requesting 2016-01-01 to
2026-07-03 in one call returned only 770 rows ending 2026-04-10, not the
full ~2,600 trading days expected. backfill_history() therefore chunks
the request into ~500-day windows and concatenates, matching the pattern
already established in afund.data.index_valuation for other NSE
endpoints with undocumented server-side range caps.

Feeds macro_series INDIA_VIX (daily). Wired into the daily job alongside
index_valuation per the Phase 8 plan, and consumed as a fear_type anchor
by the sentiment_breadth cycle (afund.cycles.anchors) alongside the
existing pct_above_200dma breadth metric.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from afund.data.base import Pipeline

# Live finding (Phase 8): NSE truncates each historical-VIX response to
# roughly ~145 rows regardless of the requested span (a 500-day chunk came
# back with only ~140 trading days and silent within-chunk gaps, leaving
# years at ~70 rows instead of ~250). 100 calendar days (~68 trading days)
# keeps every chunk safely under the cap.
CHUNK_DAYS = 100
BACKFILL_YEARS = 10


def _parse_nse_date(date_str: str) -> str:
    """'01-JUN-2026' -> '2026-06-01'."""
    return dt.datetime.strptime(date_str, "%d-%b-%Y").date().isoformat()


def parse_nse_vix_rows(rows: list[dict]) -> list[tuple[str, float]]:
    """Normalize the `nse` library's fetch_historical_vix_data() rows into
    [(date, close)]. Skips rows missing either field rather than fabricating."""
    parsed: list[tuple[str, float]] = []
    for row in rows:
        date_raw = row.get("EOD_TIMESTAMP")
        close = row.get("EOD_CLOSE_INDEX_VAL")
        if date_raw is None or close is None:
            continue
        try:
            date = _parse_nse_date(date_raw)
            value = float(close)
        except (ValueError, TypeError):
            continue
        parsed.append((date, value))
    parsed.sort(key=lambda r: r[0])
    return parsed


def _fetch_via_nse_library(from_date: dt.date, to_date: dt.date) -> list[tuple[str, float]]:
    from nse import NSE  # local import: optional dependency, only needed here

    all_rows: dict[str, float] = {}
    cursor = from_date
    while cursor <= to_date:
        chunk_end = min(cursor + dt.timedelta(days=CHUNK_DAYS), to_date)
        n = NSE(download_folder=".", server=False)
        try:
            rows = n.fetch_historical_vix_data(from_date=cursor, to_date=chunk_end)
        finally:
            n.exit()
        for date, value in parse_nse_vix_rows(rows):
            all_rows[date] = value
        cursor = chunk_end + dt.timedelta(days=1)
    return sorted(all_rows.items())


def _fetch_via_yfinance_fallback(years: int) -> list[tuple[str, float]]:
    import yfinance as yf

    ticker = yf.Ticker("^INDIAVIX")
    hist = ticker.history(period=f"{years}y")
    if hist is None or hist.empty:
        return []
    rows = []
    for idx, row in hist.iterrows():
        close = row.get("Close")
        if close == close:  # NaN guard
            rows.append((idx.strftime("%Y-%m-%d"), float(close)))
    return rows


class IndiaVixPipeline(Pipeline):
    """Daily India VIX fetch (recent window) + upsert. For a full historical
    backfill, use backfill_history() directly rather than run()."""

    job_name = "india_vix"

    def __init__(self, conn: sqlite3.Connection | None = None, lookback_days: int = 10):
        super().__init__(conn)
        self.lookback_days = lookback_days

    def fetch(self) -> list[tuple[str, float]]:
        to_date = dt.date.today()
        from_date = to_date - dt.timedelta(days=self.lookback_days)
        try:
            rows = _fetch_via_nse_library(from_date, to_date)
            if rows:
                return rows
        except Exception:
            pass
        return _fetch_via_yfinance_fallback(years=1)

    def parse(self, raw: list[tuple[str, float]]) -> list[tuple[str, float]]:
        return raw

    def upsert(self, parsed: list[tuple[str, float]]) -> int:
        written = 0
        for date, value in parsed:
            cur = self.conn.execute(
                """
                INSERT INTO macro_series (series_code, source, date, value, unit, freq)
                VALUES ('INDIA_VIX', 'NSE', ?, ?, 'index', 'D')
                ON CONFLICT(series_code, date) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source
                """,
                (date, value),
            )
            written += cur.rowcount
        self.conn.commit()
        return written


def backfill_history(conn: sqlite3.Connection | None = None, years: int = BACKFILL_YEARS) -> int:
    """One-off historical backfill (chunked NSE library calls, yfinance
    fallback on failure), writing directly via the same upsert logic as
    IndiaVixPipeline.upsert(). Returns rows written."""
    pipeline = IndiaVixPipeline(conn=conn)
    to_date = dt.date.today()
    from_date = to_date - dt.timedelta(days=365 * years)
    try:
        rows = _fetch_via_nse_library(from_date, to_date)
    except Exception:
        rows = []
    if not rows:
        rows = _fetch_via_yfinance_fallback(years=years)
    written = pipeline.upsert(rows)
    if pipeline._owns_conn:
        pipeline.conn.close()
    return written


if __name__ == "__main__":
    result = IndiaVixPipeline().run()
    print(result)
