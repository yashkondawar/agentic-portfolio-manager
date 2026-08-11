"""Liquid-universe membership for the quarterly-results strategy.

On a busy earnings day NSE's event calendar returns 100+ result declarers, the
large majority of them illiquid micro-caps. The verification step
(``analyze_symbol`` -> screener.in) is capped (``max_analyze``), so if candidates
are truncated in raw calendar order the notable large/mid-caps that this strategy
actually wants (e.g. GESHIP) can be pushed past the cap by a wall of micro-caps
declared the same day.

This module provides a cheap, cached membership test against a broad *liquid*
universe -- the union of NSE's Nifty-500, Midcap-150 and Smallcap-250 index
constituents (~900 tradable names). Discovery uses it to RANK declarers so
liquid names are verified first; it never hard-drops a name, so a strong
off-index declarer is only deprioritised, not lost.

The constituent lists are fetched once and persisted to SQLite
with a daily TTL. Every failure degrades gracefully: a stale cache is reused, and
if no cache exists the membership test simply returns ``False`` for everything
(ranking becomes a no-op -- exactly today's behaviour), so discovery is never
broken by this layer.
"""

from __future__ import annotations

import csv
import io
import logging
import sqlite3
import time
import urllib.request
from typing import Set

from qtr_results import config
from core.storage import get_document, set_document

logger = logging.getLogger("qtr_results.universe")

# Broad liquid market = the three big tradable index buckets, unioned.
_INDEX_URLS = {
    "nifty500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "niftymidcap150": (
        "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv"
    ),
    "niftysmallcap250": (
        "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv"
    ),
}

_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_CACHE_PATH = config.STATE_DIR / "universe.json"
_CACHE_TTL_SECONDS = 24 * 3600  # refresh at most once/day

_members: Set[str] = set()
_loaded_at: float = 0.0


def _fetch_index(url: str) -> Set[str]:
    req = urllib.request.Request(url, headers=_HTTP_HEADERS)
    data = urllib.request.urlopen(req, timeout=45).read().decode("utf-8")
    rows = csv.DictReader(io.StringIO(data))
    return {
        (r.get("Symbol") or "").strip().upper()
        for r in rows
        if (r.get("Symbol") or "").strip()
    }


def _load_cache() -> Set[str]:
    try:
        raw = get_document("qtr_results", "liquid_universe")
    except sqlite3.Error as e:
        logger.warning("Could not read universe cache: %s", e)
        raw = None
    if raw is None and _CACHE_PATH.exists():
        try:
            import json

            raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            set_document("qtr_results", "liquid_universe", raw)
        except (OSError, ValueError, sqlite3.Error):
            raw = None
    syms = raw.get("symbols", []) if isinstance(raw, dict) else []
    return {str(s).strip().upper() for s in syms if str(s).strip()}


def _save_cache(symbols: Set[str]) -> None:
    try:
        set_document(
            "qtr_results",
            "liquid_universe",
            {
                "updated_at_epoch": time.time(),
                "symbols": sorted(symbols),
            },
        )
    except (OSError, ValueError, sqlite3.Error) as e:  # pragma: no cover
        logger.warning("Could not persist universe cache: %s", e)


def _cache_fresh() -> bool:
    try:
        raw = get_document("qtr_results", "liquid_universe")
    except sqlite3.Error as e:
        logger.warning("Could not inspect universe cache: %s", e)
        return False
    if not isinstance(raw, dict):
        return False
    try:
        return (time.time() - float(raw["updated_at_epoch"])) < _CACHE_TTL_SECONDS
    except (KeyError, TypeError, ValueError):
        return False


def liquid_universe() -> Set[str]:
    """Return the cached set of liquid NSE symbols (fetch once/day).

    Reuses a fresh in-memory copy, then a fresh SQLite cache, and only then
    hits NSE. Any network failure falls back to whatever cache exists (even if
    stale); if nothing exists it returns an empty set so ranking is a safe no-op.
    """
    global _members, _loaded_at
    now = time.time()
    if _members and (now - _loaded_at) < _CACHE_TTL_SECONDS:
        return _members

    if _cache_fresh():
        cached = _load_cache()
        if cached:
            _members, _loaded_at = cached, now
            return _members

    fetched: Set[str] = set()
    for name, url in _INDEX_URLS.items():
        try:
            fetched |= _fetch_index(url)
        except Exception as e:  # noqa: BLE001 - never break discovery on a fetch
            logger.warning("Universe fetch failed for %s (%s).", name, e)

    if fetched:
        _members, _loaded_at = fetched, now
        _save_cache(fetched)
        logger.info("Loaded %d liquid-universe symbols.", len(fetched))
        return _members

    # Total fetch failure: fall back to any cache (even stale), else empty.
    cached = _load_cache()
    _members, _loaded_at = cached, now
    if cached:
        logger.info("Using stale universe cache (%d symbols).", len(cached))
    else:
        logger.warning("No liquid-universe data; ranking disabled this run.")
    return _members


def is_liquid(symbol: str) -> bool:
    """True when ``symbol`` is in the broad liquid universe (empty set -> False)."""
    return (symbol or "").strip().upper() in liquid_universe()
