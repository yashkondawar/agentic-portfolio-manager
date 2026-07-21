"""
data.py
=======

Point-in-time data stores for the quarterly-results backtest.

Three sources are combined:

* **Prices**: daily OHLCV from yfinance, served as leak-free "as-of" slices. This
  reuses the swing backtest's :class:`PointInTimeData` verbatim (download once,
  slice per day; ``as_of(sym, day)`` returns only rows dated ``<= day``).
* **Fundamentals**: quarterly financials scraped ONCE per symbol from
  screener.in (the exact source the live ``qtr_results`` strategy verifies on),
  cached to disk. The scraped values are *as-reported* historicals that do not
  change, so restricting them to the quarter columns on/before a declaration date
  makes them point-in-time (see ``analysis.py``). Live/current fields (screener's
  "Current Price"/"Stock P/E") are deliberately NOT used for pricing — entries are
  priced from the historical OHLCV instead — so there is no look-ahead leak.
* **Sectors**: yfinance ``Ticker.info["sector"]``, cached to disk. Used only to
  cap sector concentration; a company's sector is fundamentally stable over the
  backtest window so today's snapshot is an acceptable proxy.

Why cache: screener is rate-limited (~1 request / 2 s) and realtime-only, so we
snapshot the universe once and reuse it for fast, offline, reproducible reruns.
"""

from __future__ import annotations

import logging
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Make the repo root importable so we can reuse the live scraper + swing store.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Reuse the swing backtest's point-in-time price store (identical needs).
from backtesting.swing_trading.data import PointInTimeData  # noqa: E402,F401

logger = logging.getLogger("backtest.qtr.data")


def _plain_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".NS", "").replace(".BO", "")


def _yf_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s.endswith(".NS") and not s.endswith(".BO"):
        s = f"{s}.NS"
    return s


class FundamentalsStore:
    """Scrape + cache screener.in quarterly fundamentals for a universe."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # plain symbol -> raw screener dict (top_ratios, quarterly_results, ...)
        self.raw: Dict[str, dict] = {}

    def _cache_path(self, tag: str) -> Path:
        return self.cache_dir / f"fundamentals_{tag}.pkl"

    def load_or_download(self, symbols: List[str], use_cache: bool = True) -> None:
        tag = f"{len(symbols)}sym"
        cache_path = self._cache_path(tag)

        if use_cache and cache_path.exists():
            logger.info("Loading cached fundamentals from %s", cache_path.name)
            with open(cache_path, "rb") as fh:
                self.raw = pickle.load(fh)
            logger.info("Fundamentals cache: %d symbols loaded.", len(self.raw))
            return

        from scraper.screener import scrape_fundamentals

        total = len(symbols)
        for i, sym in enumerate(symbols, start=1):
            plain = _plain_symbol(sym)
            if plain in self.raw:
                continue
            logger.info("Scraping fundamentals %d/%d: %s", i, total, plain)
            try:
                data = scrape_fundamentals(plain)
            except Exception as e:  # noqa: BLE001 - never let one name break the run
                logger.warning("Fundamentals scrape failed for %s (%s); skipping.", plain, e)
                continue
            if data and "error" not in data and data.get("quarterly_results"):
                self.raw[plain] = data

        logger.info("Scraped fundamentals for %d / %d symbols.", len(self.raw), total)
        with open(cache_path, "wb") as fh:
            pickle.dump(self.raw, fh)
        logger.info("Cached fundamentals to %s", cache_path.name)

    def get(self, symbol: str) -> Optional[dict]:
        return self.raw.get(_plain_symbol(symbol))

    def symbols(self) -> List[str]:
        return list(self.raw.keys())


class ResultsCalendarStore:
    """Fetch + cache the REAL quarterly-result declaration dates per symbol.

    The backtest otherwise estimates each result's declaration date as
    ``quarter_end + a per-symbol reporting lag`` — a plausible but fixed lag that
    can't capture the real per-quarter variation (a large cap may file 14 days
    after one quarter-end and 22 after the next). This store backfills the
    *actual* announcement dates straight from NSE's corporates-financial-results
    feed (see ``scraper.nse_events.historical_result_dates``) so every entry is
    timed to the real event.

    The mapping is ``plain symbol -> {quarter_end (month-end) -> broadcast date}``.
    Any symbol NSE can't resolve (e.g. a recent demerger) simply gets an empty
    map, and the engine transparently falls back to the estimated reporting lag —
    so the backtest never breaks on a data gap.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # plain symbol -> {quarter_end date -> declaration date}
        self.calendar: Dict[str, Dict] = {}

    def _cache_path(self, tag: str) -> Path:
        return self.cache_dir / f"result_dates_{tag}.pkl"

    def load_or_download(self, symbols: List[str], use_cache: bool = True) -> None:
        tag = f"{len(symbols)}sym"
        cache_path = self._cache_path(tag)

        if use_cache and cache_path.exists():
            logger.info("Loading cached result dates from %s", cache_path.name)
            with open(cache_path, "rb") as fh:
                self.calendar = pickle.load(fh)
            logger.info("Result-date cache: %d symbols loaded.", len(self.calendar))
            return

        from scraper.nse_events import historical_result_dates
        import time as _time

        total = len(symbols)
        resolved = 0
        for i, sym in enumerate(symbols, start=1):
            plain = _plain_symbol(sym)
            if plain in self.calendar:
                continue
            try:
                dates = historical_result_dates(plain)
            except Exception as e:  # noqa: BLE001 - one bad name must not break the run
                logger.warning("Result-date fetch failed for %s (%s); skipping.", plain, e)
                dates = {}
            self.calendar[plain] = dates
            if dates:
                resolved += 1
            if i % 25 == 0:
                logger.info("  … result dates %d/%d (%d resolved)", i, total, resolved)
            _time.sleep(0.25)  # be polite to NSE across a large universe

        logger.info("Fetched real result dates for %d / %d symbols.", resolved, total)
        with open(cache_path, "wb") as fh:
            pickle.dump(self.calendar, fh)
        logger.info("Cached result dates to %s", cache_path.name)

    def dates_for(self, symbol: str) -> Dict:
        """Return ``{quarter_end -> declaration date}`` for a symbol (may be empty)."""
        return self.calendar.get(_plain_symbol(symbol), {})

    def coverage(self) -> tuple:
        """(#symbols with >=1 real date, #total symbols) — for logging/diagnostics."""
        have = sum(1 for v in self.calendar.values() if v)
        return have, len(self.calendar)


class SectorStore:
    """Fetch + cache yfinance sector labels per symbol.

    Sector data drives the per-sector concentration cap. yfinance's
    ``Ticker.info`` returns a coarse-grained global sector (Energy, Financial
    Services, ...) which is fundamentally stable over a 1-year backtest, so a
    today-snapshot is an acceptable proxy for point-in-time. Any symbol whose
    sector can't be resolved is bucketed as ``"UNKNOWN"``.
    """

    _CACHE_NAME = "sectors_cache.pkl"

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sectors: Dict[str, str] = {}

    def _cache_path(self) -> Path:
        return self.cache_dir / self._CACHE_NAME

    def load_or_download(self, symbols: List[str], use_cache: bool = True) -> None:
        cache_path = self._cache_path()
        if use_cache and cache_path.exists():
            with open(cache_path, "rb") as fh:
                self.sectors = pickle.load(fh)
            logger.info("Sector cache: %d symbols loaded.", len(self.sectors))
        else:
            self.sectors = {}

        # Fill only symbols missing from cache — sector is stable, so this is
        # an amortised one-time cost across all reruns.
        missing = [s for s in symbols if _plain_symbol(s) not in self.sectors]
        if not missing:
            return

        import yfinance as yf

        logger.info("Fetching sectors for %d symbols from yfinance …", len(missing))
        for i, sym in enumerate(missing, start=1):
            plain = _plain_symbol(sym)
            try:
                info = yf.Ticker(_yf_symbol(sym)).info
                sector = (info or {}).get("sector") or "UNKNOWN"
            except Exception as e:  # noqa: BLE001
                logger.warning("Sector fetch failed for %s (%s); tagging UNKNOWN.", plain, e)
                sector = "UNKNOWN"
            self.sectors[plain] = sector.strip() or "UNKNOWN"
            if i % 20 == 0:
                logger.info("  … %d/%d", i, len(missing))
        with open(cache_path, "wb") as fh:
            pickle.dump(self.sectors, fh)
        logger.info("Sector cache updated (%d symbols total).", len(self.sectors))

    def get(self, symbol: str) -> str:
        return self.sectors.get(_plain_symbol(symbol), "UNKNOWN")
