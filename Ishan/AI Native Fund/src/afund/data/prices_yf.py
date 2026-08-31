"""Daily prices pipeline via yfinance, plus the resumable backfill engine.

Both the daily job and the backfill in scripts/backfill_prices.py share
`download_and_upsert_chunk()` / `PricesPipeline` here: batch yf.download()
calls in chunks (default ~50 tickers), sleep between chunks to stay polite,
reject bad rows (close<=0 or NaN), and upsert into daily_prices with
source='yfinance' (INSERT OR IGNORE keyed on (instrument_id, date), so
re-running is always safe).
"""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
import time
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from afund.data.base import Pipeline

DEFAULT_CHUNK_SIZE = 50
DEFAULT_CHUNK_SLEEP_SECONDS = 2.0
RESUMABLE_ROW_THRESHOLD = 2400  # ~10y of trading days; instruments at/above this are skipped on resume


@dataclass
class FetchStats:
    rows_upserted: int = 0
    rows_rejected: int = 0
    tickers_fetched: int = 0
    tickers_skipped_resume: int = 0


def _chunked(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def get_active_instruments(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All active instruments that have a yf_ticker (STOCK/ETF/INDEX)."""
    return conn.execute(
        """
        SELECT id, symbol, yf_ticker, instrument_type
          FROM instruments
         WHERE active = 1 AND yf_ticker IS NOT NULL AND yf_ticker != ''
        """
    ).fetchall()


def get_row_counts(conn: sqlite3.Connection) -> dict[int, int]:
    """instrument_id -> count of daily_prices rows already stored."""
    rows = conn.execute(
        "SELECT instrument_id, COUNT(*) AS n FROM daily_prices GROUP BY instrument_id"
    ).fetchall()
    return {row["instrument_id"]: row["n"] for row in rows}


def _clean_frame(df: pd.DataFrame) -> tuple[list[tuple], int]:
    """Turn a per-ticker OHLCV DataFrame (Date index, columns
    Open/High/Low/Close/Adj Close/Volume) into a list of row tuples, applying
    the data-quality guard (reject close<=0 or NaN). Returns (rows, rejects).
    """
    rows: list[tuple] = []
    rejects = 0
    for idx, r in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        close = r.get("Close")
        if close is None or (isinstance(close, float) and math.isnan(close)) or close <= 0:
            rejects += 1
            continue
        open_ = r.get("Open")
        high = r.get("High")
        low = r.get("Low")
        adj_close = r.get("Adj Close")
        volume = r.get("Volume")

        def _clean(v):
            if v is None:
                return None
            if isinstance(v, float) and math.isnan(v):
                return None
            return float(v)

        vol_clean = None
        if volume is not None and not (isinstance(volume, float) and math.isnan(volume)):
            vol_clean = int(volume)

        rows.append(
            (
                date_str,
                _clean(open_),
                _clean(high),
                _clean(low),
                _clean(close),
                _clean(adj_close),
                vol_clean,
            )
        )
    return rows, rejects


def download_chunk(tickers: list[str], period: str | None = None, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Download OHLCV for a chunk of yf tickers. Either `period` or `start`/`end`."""
    kwargs = dict(
        tickers=tickers,
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
        actions=False,
    )
    if period:
        kwargs["period"] = period
    else:
        kwargs["start"] = start
        kwargs["end"] = end
    return yf.download(**kwargs)


def upsert_prices_for_ticker(
    conn: sqlite3.Connection, instrument_id: int, rows: list[tuple]
) -> int:
    """INSERT OR IGNORE rows into daily_prices for one instrument. Returns count inserted."""
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO daily_prices
            (instrument_id, date, open, high, low, close, adj_close, volume, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'yfinance')
        """,
        [(instrument_id, *row) for row in rows],
    )
    return conn.total_changes - before


def run_price_fetch(
    conn: sqlite3.Connection,
    instruments: list[sqlite3.Row],
    *,
    period: str | None = None,
    start: str | None = None,
    end: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_sleep_seconds: float = DEFAULT_CHUNK_SLEEP_SECONDS,
    resumable: bool = False,
    print_progress: bool = False,
) -> FetchStats:
    """Core batch engine shared by the daily job and the backfill script."""
    stats = FetchStats()

    if resumable:
        row_counts = get_row_counts(conn)
        filtered = [
            inst for inst in instruments if row_counts.get(inst["id"], 0) < RESUMABLE_ROW_THRESHOLD
        ]
        stats.tickers_skipped_resume = len(instruments) - len(filtered)
        instruments = filtered

    by_ticker = {inst["yf_ticker"]: inst for inst in instruments}
    tickers = list(by_ticker.keys())
    chunks = _chunked(tickers, chunk_size)

    for chunk_idx, chunk in enumerate(chunks, start=1):
        try:
            df = download_chunk(chunk, period=period, start=start, end=end)
        except Exception:
            # A whole-chunk failure (e.g. transient network error) should not
            # kill the run — skip this chunk and continue with the next.
            if print_progress:
                print(f"  chunk {chunk_idx}/{len(chunks)}: download FAILED, skipping")
            continue

        for ticker in chunk:
            inst = by_ticker[ticker]
            try:
                if len(chunk) == 1:
                    ticker_df = df
                else:
                    if ticker not in df.columns.get_level_values(0):
                        continue
                    ticker_df = df[ticker]
                ticker_df = ticker_df.dropna(how="all")
                if ticker_df.empty:
                    continue
                rows, rejects = _clean_frame(ticker_df)
                inserted = upsert_prices_for_ticker(conn, inst["id"], rows)
                stats.rows_upserted += inserted
                stats.rows_rejected += rejects
                stats.tickers_fetched += 1
            except Exception:
                continue

        conn.commit()
        if print_progress:
            print(
                f"  chunk {chunk_idx}/{len(chunks)} done "
                f"(cumulative rows={stats.rows_upserted}, rejects={stats.rows_rejected})"
            )
        if chunk_idx < len(chunks):
            time.sleep(chunk_sleep_seconds)

    return stats


class PricesPipeline(Pipeline):
    """Daily incremental price fetch: last ~7 calendar days (covers weekends/
    holidays) for every active instrument with a yf_ticker."""

    job_name = "prices_daily"

    def __init__(self, conn: sqlite3.Connection | None = None, lookback_days: int = 7):
        super().__init__(conn)
        self.lookback_days = lookback_days

    def fetch(self) -> list[sqlite3.Row]:
        return get_active_instruments(self.conn)

    def parse(self, raw: list[sqlite3.Row]) -> list[sqlite3.Row]:
        return raw  # no separate parse step; run_price_fetch does fetch+parse+upsert together

    def upsert(self, parsed: list[sqlite3.Row]) -> int:
        end = dt.date.today() + dt.timedelta(days=1)
        start = end - dt.timedelta(days=self.lookback_days)
        stats = run_price_fetch(
            self.conn,
            parsed,
            start=start.isoformat(),
            end=end.isoformat(),
            resumable=False,
        )
        return stats.rows_upserted
