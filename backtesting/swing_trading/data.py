"""
data.py
=======

Point-in-time price data store for the backtest.

Strategy:
  * Download daily OHLCV ONCE for the whole universe + benchmark, covering the
    backtest window PLUS a warmup buffer (so SMA200 / 52-week stats are warm on
    day one). Cache in SQLite (pickled {symbol: DataFrame} payload).
  * Serve per-day "as-of" slices: ``as_of(symbol, day)`` returns only the rows
    dated <= day. This is what guarantees the model never sees the future.

Why download-once-then-slice (instead of calling yfinance per simulated day):
  * Correctness: identical underlying series for every as-of cut.
  * Speed: one network pass instead of 250 * N calls.
  * Reproducibility / offline reruns from cache.
"""

from __future__ import annotations

import logging
import pickle
from hashlib import sha256
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from core.storage import get_cache, put_cache

logger = logging.getLogger("backtest.data")


def _yf_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s.endswith(".NS") and not s.endswith(".BO"):
        s = f"{s}.NS"
    return s


def _plain_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".NS", "").replace(".BO", "")


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
        dl_start = start - timedelta(days=warmup_days)
        dl_end = end + timedelta(days=2)
        requested_symbols = sorted({_cache_symbol(symbol) for symbol in symbols})
        tag = _cache_tag(symbols, benchmark, dl_start, dl_end)
        cache_path = self._cache_path(tag)

        entry = get_cache("backtest_prices", tag) if use_cache else None
        if entry is not None:
            logger.info("Loading cached prices from SQLite (%s)", tag)
            blob = pickle.loads(entry.payload)
            if (
                blob.get("requested_symbols") == requested_symbols
                and blob.get("benchmark_symbol") == benchmark
            ):
                self.frames = blob["frames"]
                self.benchmark = blob["benchmark"]
                logger.info("Cache: %d symbols + benchmark loaded.", len(self.frames))
                return
            logger.warning("Ignoring cache with mismatched universe metadata.")
        elif use_cache and cache_path.exists():
            logger.info("Importing legacy price cache %s", cache_path.name)
            with open(cache_path, "rb") as fh:
                blob = pickle.load(fh)
            put_cache("backtest_prices", tag, pickle.dumps(blob), format="pickle")
            if (
                blob.get("requested_symbols") == requested_symbols
                and blob.get("benchmark_symbol") == benchmark
            ):
                self.frames = blob["frames"]
                self.benchmark = blob["benchmark"]
                return

        import yfinance as yf

        # Benchmark first (also defines the trading calendar).
        logger.info("Downloading benchmark %s ...", benchmark)
        bench = yf.download(benchmark, start=dl_start, end=dl_end, interval="1d",
                            auto_adjust=True, progress=False, threads=True)
        self.benchmark = self._normalise(bench)

        yf_map = {_yf_symbol(s): _plain_symbol(s) for s in symbols}
        all_yf = list(yf_map.keys())
        total = len(all_yf)
        for i in range(0, total, chunk_size):
            chunk = all_yf[i:i + chunk_size]
            logger.info("Downloading prices %d-%d of %d ...",
                        i + 1, min(i + chunk_size, total), total)
            try:
                data = yf.download(chunk, start=dl_start, end=dl_end, interval="1d",
                                   auto_adjust=True, progress=False,
                                   group_by="ticker", threads=True)
            except Exception as e:  # noqa: BLE001
                logger.warning("Chunk download failed (%s); skipping.", e)
                continue
            for yfs in chunk:
                plain = yf_map[yfs]
                try:
                    sub = data[yfs] if len(chunk) > 1 else data
                except (KeyError, TypeError):
                    continue
                df = self._normalise(sub)
                if df is not None and not df.empty and len(df) >= 60:
                    self.frames[plain] = df

        logger.info("Downloaded %d / %d symbols with usable history.",
                    len(self.frames), total)

        blob = {
            "frames": self.frames,
            "benchmark": self.benchmark,
            "requested_symbols": requested_symbols,
            "benchmark_symbol": benchmark,
        }
        put_cache("backtest_prices", tag, pickle.dumps(blob), format="pickle")
        logger.info("Cached prices to SQLite (%s)", tag)

    @staticmethod
    def _normalise(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        df = df.copy()
        # Flatten potential MultiIndex columns (single-ticker downloads).
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[keep].dropna(subset=["Close"])
        # Make the index tz-naive python dates for clean comparison.
        idx = pd.to_datetime(df.index)
        try:
            idx = idx.tz_localize(None)
        except (TypeError, AttributeError):
            pass
        df.index = idx.normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df

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
