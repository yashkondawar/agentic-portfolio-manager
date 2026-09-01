"""The tradeable universe: NSE's published Nifty Total Market constituents.

The index file is fetched once and cached on disk. It carries the ``Industry``
label used throughout the sleeve, so the sector shown on a trade is NSE's own
classification rather than a guess from a price feed.
"""

from __future__ import annotations

import csv
import io
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

TOTAL_MARKET_URL = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
)

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
}

CACHE_PATH = Path(__file__).resolve().parent / "data_cache" / "nifty_total_market.csv"


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    industry: str
    company: str = ""

    @property
    def ticker(self) -> str:
        return f"{self.symbol}.NS"


def _parse(text: str) -> List[UniverseMember]:
    out: List[UniverseMember] = []
    seen = set()
    for row in csv.DictReader(io.StringIO(text)):
        symbol = (row.get("Symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(
            UniverseMember(
                symbol=symbol,
                industry=(row.get("Industry") or "Unknown").strip() or "Unknown",
                company=(row.get("Company Name") or "").strip(),
            )
        )
    return sorted(out, key=lambda m: m.symbol)


def load_universe(
    *, cache_path: Optional[Path] = None, refresh: bool = False
) -> List[UniverseMember]:
    """Constituents of the Nifty Total Market index.

    Served from the on-disk cache unless ``refresh`` is set, so a backtest run
    is reproducible and does not depend on NSE being reachable.
    """
    path = cache_path or CACHE_PATH
    if not refresh and path.exists():
        return _parse(path.read_text(encoding="utf-8"))

    logger.info("Fetching Nifty Total Market constituents from NSE")
    request = urllib.request.Request(TOTAL_MARKET_URL, headers=_HTTP_HEADERS)
    text = urllib.request.urlopen(request, timeout=60).read().decode("utf-8")
    members = _parse(text)
    if not members:
        raise RuntimeError("NSE returned an empty Nifty Total Market constituent list")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    logger.info("Cached %d constituents at %s", len(members), path)
    return members


def industry_map(members: Optional[List[UniverseMember]] = None) -> Dict[str, str]:
    """Ticker (``SYMBOL.NS``) to NSE industry label."""
    return {m.ticker: m.industry for m in (members or load_universe())}
