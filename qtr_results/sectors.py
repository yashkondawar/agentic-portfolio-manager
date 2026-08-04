"""Live per-symbol sector lookup for the quarterly-results strategy.

The sector-relative debt gate (see ``config.sector_debt_cap``) needs the coarse
yfinance sector of each shortlisted candidate. This module resolves it lazily
and caches the result on disk so the daily run pays the yfinance cost for a
symbol at most once. Any failure degrades to ``"UNKNOWN"`` (the caller then
falls back to the flat debt floor) so a network hiccup never breaks a run.

Only names that already passed the cheap mechanical growth filters reach this
lookup, so the number of yfinance calls per run is tiny (the shortlist), not the
whole scanned universe.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Dict, Optional

from qtr_results import config

logger = logging.getLogger("qtr_results.sectors")

# state/sector_cache.json — persists resolved sectors across daily runs.
_CACHE_PATH = config.STATE_DIR / "sector_cache.json"
_LOCK = threading.Lock()
_CACHE: Optional[Dict[str, str]] = None


def _plain(symbol: str) -> str:
    return symbol.strip().upper().replace(".NS", "").replace(".BO", "")


def _yf_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s.endswith(".NS") and not s.endswith(".BO"):
        s = f"{s}.NS"
    return s


def _load_cache() -> Dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    data: Dict[str, str] = {}
    try:
        if _CACHE_PATH.exists():
            with open(_CACHE_PATH, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = {str(k): str(v) for k, v in loaded.items()}
    except Exception as e:  # noqa: BLE001 - a corrupt cache must not break a run
        logger.warning("Sector cache read failed (%s); starting empty.", e)
        data = {}
    _CACHE = data
    return _CACHE


def _save_cache(cache: Dict[str, str]) -> None:
    try:
        config.ensure_state_dir()
        with open(_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2, sort_keys=True)
    except Exception as e:  # noqa: BLE001 - caching is best-effort
        logger.warning("Sector cache write failed (%s); continuing.", e)


def _fetch_sector(symbol: str) -> str:
    """Resolve a symbol's coarse yfinance sector; ``"UNKNOWN"`` on any failure."""
    try:
        import yfinance as yf

        info = yf.Ticker(_yf_symbol(symbol)).info
        sector = (info or {}).get("sector") or "UNKNOWN"
        return str(sector).strip() or "UNKNOWN"
    except Exception as e:  # noqa: BLE001 - never let a lookup break the run
        logger.warning("Sector fetch failed for %s (%s); tagging UNKNOWN.", symbol, e)
        return "UNKNOWN"


def sector_for(symbol: str) -> str:
    """Return the cached/looked-up yfinance sector for ``symbol``.

    Resolves once per symbol then serves from the on-disk cache. Degrades to
    ``"UNKNOWN"`` (never raises) so the debt gate can fall back to the flat
    floor when a sector cannot be resolved.
    """
    plain = _plain(symbol)
    with _LOCK:
        cache = _load_cache()
        cached = cache.get(plain)
        if cached:
            return cached
    sector = _fetch_sector(plain)
    with _LOCK:
        cache = _load_cache()
        cache[plain] = sector
        _save_cache(cache)
    return sector
