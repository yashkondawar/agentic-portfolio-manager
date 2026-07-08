"""
data.py
=======

Point-in-time data stores for the quarterly-results backtest.

Two sources — both already used by this repo — are combined:

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
