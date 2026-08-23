"""
data.py
=======

Point-in-time price data store for the backtest.

Strategy:
  * Ensure daily OHLCV for the whole universe + benchmark is present in the
    shared bar store (``core.bars``), covering the backtest window PLUS a warmup
    buffer (so SMA200 / 52-week stats are warm on day one), then read it back.
    The store holds one row per (symbol, day), so a second run over a different
    window or universe re-uses everything already on disk and downloads only the
    genuinely missing bars.
  * Serve per-day "as-of" slices: ``as_of(symbol, day)`` returns only the rows
    dated <= day. This is what guarantees the model never sees the future.

Why download-once-then-slice (instead of calling yfinance per simulated day):
  * Correctness: identical underlying series for every as-of cut.
  * Speed: one network pass instead of 250 * N calls.
  * Reproducibility / offline reruns from the store.
"""

from __future__ import annotations

import logging
import pickle
from hashlib import sha256
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from core import bars
from core.storage import get_cache

logger = logging.getLogger("backtest.data")

#: Symbols with fewer sessions than this are treated as having no usable history.
MIN_USABLE_ROWS = 60


def _yf_symbol(symbol: str) -> str:
    """Deprecated shim; the bar store owns symbol normalisation now."""
    return bars.yf_symbol(symbol)


def _plain_symbol(symbol: str) -> str:
    return bars.plain_symbol(symbol)


def _cache_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith((".NS", ".BO")):
        return normalized
    return f"{normalized}.NS"


def _cache_tag(
    symbols: List[str],
    benchmark: str,
    download_start: date,
    download_end: date,
) -> str:
    requested_symbols = sorted({_cache_symbol(symbol) for symbol in symbols})
    cache_identity = "|".join([benchmark, *requested_symbols])
    identity_hash = sha256(cache_identity.encode("utf-8")).hexdigest()[:12]
    return (
        f"{len(requested_symbols)}sym_{identity_hash}_"
        f"{download_start.isoformat()}_{download_end.isoformat()}"
    )


class PointInTimeData:
    """Holds full daily OHLCV per symbol and serves leak-free as-of slices."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.frames: Dict[str, pd.DataFrame] = {}   # plain symbol -> OHLCV df (tz-naive index)
        self.benchmark: Optional[pd.DataFrame] = None
        self._trading_days: Optional[List[date]] = None

    # ── Download / cache ──────────────────────────────────────────────────────

    def _cache_path(self, tag: str) -> Path:
        return self.cache_dir / f"prices_{tag}.pkl"

    def load_or_download(
        self,
        symbols: List[str],
        benchmark: str,
        start: date,
        end: date,
        warmup_days: int,
        use_cache: bool = True,
        chunk_size: int = 40,
    ) -> None:
        """Populate `frames` and `benchmark` for [start - warmup, end].

        Backed by the shared per-symbol bar store, so only bars not already on
        disk are downloaded. The legacy range-keyed blob cache is still read
        (and migrated into the store) so existing caches are not wasted.
        """
        dl_start = start - timedelta(days=warmup_days)
        dl_end = end + timedelta(days=2)
        requested_symbols = sorted({_cache_symbol(symbol) for symbol in symbols})
        wanted = [_plain_symbol(s) for s in symbols]

        if use_cache:
            self._migrate_legacy_cache(
                symbols, requested_symbols, benchmark, dl_start, dl_end
            )

        to_sync = [*wanted, benchmark]
        if use_cache:
            report = bars.sync(to_sync, dl_start, dl_end, chunk_size=chunk_size)
        else:
            report = bars.sync(
                to_sync, dl_start, dl_end, chunk_size=chunk_size, force=True
            )
        logger.info("Bar store: %s", report.summary())

        self.frames = bars.read_bars(
            wanted, dl_start, dl_end, min_rows=MIN_USABLE_ROWS
        )
        self.benchmark = bars.read_symbol(benchmark, dl_start, dl_end)
        self._trading_days = None
        logger.info(
            "Loaded %d / %d symbols with usable history.", len(self.frames), len(wanted)
        )

    def _migrate_legacy_cache(
        self,
        symbols: List[str],
        requested_symbols: List[str],
        benchmark: str,
        dl_start: date,
        dl_end: date,
    ) -> None:
        """Fold a matching pre-bar-store cache into the store, once.

        The old cache is keyed by the exact universe and window, so it hits only
        for an identical rerun - but when it does, it saves a full download.
        Migrated bars are still drift-checked on any later top-up.
        """
        tag = _cache_tag(symbols, benchmark, dl_start, dl_end)
        blob = None
        entry = get_cache("backtest_prices", tag)
        if entry is not None:
            blob = pickle.loads(entry.payload)
        else:
            legacy = self._cache_path(tag)
            if legacy.exists():
                with open(legacy, "rb") as fh:
                    blob = pickle.load(fh)
        if not blob:
            return
        if (
            blob.get("requested_symbols") != requested_symbols
            or blob.get("benchmark_symbol") != benchmark
        ):
            return

        frames = blob.get("frames") or {}
        known = bars.coverage([*frames.keys(), benchmark])
        migrated = 0
        for sym, df in frames.items():
            if bars.plain_symbol(sym) in known:
                continue
            bars.write_bars(sym, df, dl_start, dl_end)
            migrated += 1
        bench = blob.get("benchmark")
        if bench is not None and bars.plain_symbol(benchmark) not in known:
            bars.write_bars(benchmark, bench, dl_start, dl_end)
            migrated += 1
        if migrated:
            logger.info("Migrated %d symbols from the legacy price cache.", migrated)

    # ── As-of access ──────────────────────────────────────────────────────────

    def symbols(self) -> List[str]:
        return list(self.frames.keys())

    def has(self, symbol: str) -> bool:
        return _plain_symbol(symbol) in self.frames

    def full(self, symbol: str) -> Optional[pd.DataFrame]:
        return self.frames.get(_plain_symbol(symbol))

    def as_of(
        self, symbol: str, day: date, lookback_rows: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """Rows dated <= `day`. Optionally limited to the last `lookback_rows`."""
        df = self.frames.get(_plain_symbol(symbol))
        if df is None:
            return None
        ts = pd.Timestamp(day).normalize()
        sliced = df.loc[:ts]
        if sliced.empty:
            return None
        if lookback_rows is not None:
            sliced = sliced.tail(lookback_rows)
        return sliced

    def bar_on(self, symbol: str, day: date) -> Optional[pd.Series]:
        """The OHLCV row for an EXACT trading day (None if no session that day)."""
        df = self.frames.get(_plain_symbol(symbol))
        if df is None:
            return None
        ts = pd.Timestamp(day).normalize()
        if ts in df.index:
            return df.loc[ts]
        return None

    def next_session(self, symbol: str, day: date) -> Optional[date]:
        """First trading day STRICTLY AFTER `day` for this symbol."""
        df = self.frames.get(_plain_symbol(symbol))
        if df is None:
            return None
        ts = pd.Timestamp(day).normalize()
        future = df.index[df.index > ts]
        if len(future) == 0:
            return None
        return future[0].date()

    def benchmark_as_of(self, day: date) -> Optional[pd.DataFrame]:
        if self.benchmark is None:
            return None
        return self.benchmark.loc[:pd.Timestamp(day).normalize()]

    # ── Trading calendar (from benchmark, falls back to union of symbols) ─────

    def trading_days(self, start: date, end: date) -> List[date]:
        if self._trading_days is None:
            if self.benchmark is not None and not self.benchmark.empty:
                idx = self.benchmark.index
            else:
                # Union of all symbol session dates.
                all_idx = pd.DatetimeIndex([])
                for df in self.frames.values():
                    all_idx = all_idx.union(df.index)
                idx = all_idx
            self._trading_days = [d.date() for d in idx]
        s = start if isinstance(start, date) else start
        return [d for d in self._trading_days if s <= d <= end]
