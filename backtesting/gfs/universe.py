"""
universe.py
===========

Universe construction, plus an explicit, honest account of its biases.

Index constituent lists are fetched from NSE as they stand **today**. There is
no free source of historical NSE index membership, and pretending otherwise
would be worse than naming the problem, so this module names it:

* **Survivorship bias.** Companies delisted, merged away or destroyed between
  the start of the window and today are absent. Their (usually terrible)
  returns never enter the sample.
* **Index-inclusion bias (the bigger one for a momentum-flavoured rule).** A
  stock is in today's Nifty 500 partly *because* it did well over the backtest
  window. Selecting on that and then measuring performance is circular.

Two mitigations are available here, neither perfect:

1. ``--universe nse_all`` uses NSE's full listed-equity file instead of an index.
   It still cannot resurrect delisted names, but it removes the
   index-membership circularity, which is the component most likely to
   manufacture a fake edge.
2. Whatever universe is chosen, every candidate must independently pass a
   point-in-time price / liquidity / volatility screen on the day it is
   considered, so a name that was a micro-cap penny stock in 2016 is not traded
   in 2016 merely because it is liquid in 2026.

The right way to read any result from this harness is therefore: **treat the
index-universe number as an optimistic upper bound, and the ``nse_all`` number
as the more defensible one.** :func:`universe_bias_note` returns exactly that
caveat so it can be printed alongside the metrics rather than buried here.
"""

import csv
import io
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("gfs.universe")

NSE_INDEX_URLS: Dict[str, str] = {
    "nifty50": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "niftynext50": "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv",
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
    "nifty500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "niftymidcap150": "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "niftysmallcap250": "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    "niftymidcap100": "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap100list.csv",
}

NSE_ALL_EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


@dataclass
class UniverseStock:
    symbol: str
    industry: str = "Unknown"
    company: str = ""


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=_HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def _rows_to_universe(rows, industry_key: str = "Industry") -> List[UniverseStock]:
    out: List[UniverseStock] = []
    for row in rows:
        symbol = (row.get("Symbol") or row.get("SYMBOL") or "").strip().upper()
        if not symbol:
            continue
        industry = (row.get(industry_key) or row.get("Industry") or "").strip()
        company = (row.get("Company Name") or row.get("NAME OF COMPANY") or "").strip()
        out.append(
            UniverseStock(
                symbol=symbol,
                industry=industry or "Unknown",
                company=company,
            )
        )
    return out


def load_index_universe(index_name: str) -> List[UniverseStock]:
    key = index_name.strip().lower()
    if key == "nse_all":
        return load_all_equity_universe()
    if key not in NSE_INDEX_URLS:
        available = ", ".join(sorted(NSE_INDEX_URLS) + ["nse_all"])
        raise ValueError(f"Unknown universe {index_name!r}. Available: {available}")
    logger.info("Fetching universe '%s' from NSE", key)
    rows = list(csv.DictReader(io.StringIO(_fetch(NSE_INDEX_URLS[key]))))
    universe = _rows_to_universe(rows)
    logger.info("Loaded %d symbols from %s", len(universe), key)
    return universe


def load_all_equity_universe() -> List[UniverseStock]:
    """Every equity currently listed on NSE's main board.

    Removes index-inclusion bias (though not survivorship). The file has no
    industry column, so sector-based gating degrades to a single bucket unless a
    sector map is supplied - see :func:`apply_sector_map`.
    """
    logger.info("Fetching full NSE equity list")
    rows = list(csv.DictReader(io.StringIO(_fetch(NSE_ALL_EQUITY_URL))))
    universe = []
    for row in rows:
        symbol = (row.get("SYMBOL") or "").strip().upper()
        series = (row.get(" SERIES") or row.get("SERIES") or "").strip().upper()
        if not symbol or (series and series != "EQ"):
            continue
        universe.append(
            UniverseStock(
                symbol=symbol,
                industry="Unknown",
                company=(row.get("NAME OF COMPANY") or "").strip(),
            )
        )
    logger.info("Loaded %d EQ-series symbols from the full NSE list", len(universe))
    return universe


def load_universe_file(path: Path) -> List[UniverseStock]:
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")
    seen = set()
    out: List[UniverseStock] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        for token in line.replace("\t", ",").split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in seen:
                seen.add(symbol)
                out.append(UniverseStock(symbol=symbol))
    if not out:
        raise ValueError(f"No symbols found in universe file: {path}")
    return out


def load_universe(cfg) -> List[UniverseStock]:
    """Resolve the configured universe, merging comma-separated index keys."""
    if cfg.universe_file is not None:
        universe = load_universe_file(Path(cfg.universe_file))
        return apply_sector_map(universe, cfg)

    keys = cfg.resolved_universe_keys()
    if not keys:
        raise ValueError("No universe specified")
    if len(keys) == 1:
        return load_index_universe(keys[0])

    seen = set()
    merged: List[UniverseStock] = []
    for key in keys:
        for item in load_index_universe(key):
            if item.symbol not in seen:
                seen.add(item.symbol)
                merged.append(item)
    logger.info("Merged universe %s -> %d unique symbols", keys, len(merged))
    return merged


def apply_sector_map(
    universe: List[UniverseStock], cfg, fallback_index: str = "nifty500"
) -> List[UniverseStock]:
    """Fill in missing industries from an index file that carries them.

    A universe with no sector labels silently disables the aerial view of the
    funnel, which would quietly change the strategy being tested. Borrowing
    labels from an index file is a present-day mapping (a company's sector
    rarely changes, so this is far less biased than membership itself).
    """
    if all(item.industry and item.industry != "Unknown" for item in universe):
        return universe
    try:
        reference = {item.symbol: item.industry for item in load_index_universe(fallback_index)}
    except Exception as exc:  # noqa: BLE001 - offline runs must still work
        logger.warning("Could not load sector map from %s (%s)", fallback_index, exc)
        return universe
    filled = 0
    for item in universe:
        if (not item.industry or item.industry == "Unknown") and item.symbol in reference:
            item.industry = reference[item.symbol]
            filled += 1
    logger.info("Filled %d missing sector labels from %s", filled, fallback_index)
    return universe


def universe_bias_note(cfg) -> str:
    """The caveat that belongs next to every number this harness produces."""
    keys = cfg.resolved_universe_keys()
    if cfg.universe_file is not None:
        source = f"custom file {Path(cfg.universe_file).name}"
        circular = "unknown (depends on how the file was built)"
    elif keys == ["nse_all"]:
        source = "all currently-listed NSE EQ-series stocks"
        circular = "no index-inclusion bias; survivorship bias remains"
    else:
        source = "/".join(keys) + " (today's constituents)"
        circular = (
            "index-inclusion bias IS present - membership today is partly a "
            "consequence of performance during the test window"
        )
    return (
        "UNIVERSE BIAS: "
        f"{source}. {circular}. Delisted and merged companies are absent from "
        "every variant, so all returns here are an optimistic upper bound. "
        "Compare an index run against an `nse_all` run to size the effect."
    )


def sector_counts(universe: List[UniverseStock]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in universe:
        counts[item.industry or "Unknown"] = counts.get(item.industry or "Unknown", 0) + 1
    return counts


def limit_universe(
    universe: List[UniverseStock], limit: Optional[int]
) -> List[UniverseStock]:
    """Deterministic head-truncation, for quick smoke runs only."""
    if not limit or limit <= 0 or limit >= len(universe):
        return universe
    logger.warning(
        "Universe truncated to the first %d symbols - results are NOT "
        "representative and must not be used for validation.",
        limit,
    )
    return universe[:limit]
