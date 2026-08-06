"""Discovery of companies that have just declared quarterly results.

Hybrid approach: the GitHub Copilot CLI (with web grounding) is asked to find
NSE companies that declared quarterly results on/around the run date from public
sources; it returns a machine-readable list of symbols that the mechanical
``analysis`` step then verifies on screener.in. A user-supplied watchlist can
seed/limit the search or serve as a no-LLM fallback.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from qtr_results import config
from qtr_results.copilot_runner import run_copilot
from qtr_results.util import dedupe_preserve, extract_json_block
from scraper.nse_events import (
    new_declared_from_calendar,
    new_declared_results,
    recent_declared_from_calendar,
    recent_declared_results,
)

logger = logging.getLogger("qtr_results.discovery")


def _build_discovery_prompt(
    as_of: date, lookback_days: int, watchlist: List[str]
) -> str:
    start = (as_of - timedelta(days=max(0, lookback_days - 1))).isoformat()
    end = as_of.isoformat()
    watch_line = (
        f"\nPrioritise / restrict to these symbols if relevant: {', '.join(watchlist)}.\n"
        if watchlist
        else ""
    )
    return f"""You are an equity research assistant for the Indian stock market (NSE).

# Today's Date
{end}

# Task
Find NSE-listed companies that DECLARED their quarterly (standalone or
consolidated) financial results between {start} and {end} (inclusive).

Start with the authoritative NSE feed via the `fetch_nse_declared_results` tool
(pass lookback_days covering this window) — those are confirmed filings. Then use
web search (Moneycontrol, Trendlyne, Business Standard, Economic Times, NSE/BSE)
to add any liquid mainboard names the feed may have missed.
{watch_line}
Only include companies whose results were actually announced in that window —
not merely scheduled. Prefer liquid, mainboard names. Return up to 40 companies.

For each company provide its NSE trading symbol (the exact ticker, e.g. RELIANCE,
TCS, INFY), the company name, and the result declaration date (YYYY-MM-DD).

# Output format
Respond with ONLY a short Markdown summary followed by a single ```json``` block
of this exact shape (no extra keys, valid JSON):

```json
{{"declarers": [{{"symbol": "SYMBOL", "company": "Company Name", "result_date": "YYYY-MM-DD"}}]}}
```
"""


def discover_result_declarers(
    *,
    as_of: Optional[date] = None,
    lookback_days: int = config.DEFAULT_LOOKBACK_DAYS,
    watchlist: Optional[List[str]] = None,
    use_llm: bool = True,
    use_nse: bool = True,
    nse_delta: bool = True,
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Discover companies that have just declared quarterly results.

    Merges up to three sources, tagging each candidate with the ``sources`` that
    surfaced it:

    * ``nse_filings`` — NSE corporates-financial-results feed (assured, actually
      declared). Enabled with ``use_nse``. When ``nse_delta`` is set (default),
      the full table is fetched once and diffed against a persistent seen-cache
      so only *newly* filed results are returned each day; otherwise a fixed
      ``lookback_days`` window is used.
    * ``web_search`` — Copilot CLI + web grounding. Enabled with ``use_llm``.
    * ``watchlist`` — user-supplied symbols.

    A non-empty ``watchlist`` restricts the result to exactly those symbols
    (each still annotated with whichever feeds confirm it). An empty watchlist
    returns the full discovered universe. Each source degrades gracefully.
    """
    as_of = as_of or date.today()
    watchlist = dedupe_preserve(watchlist or [])
    merged: Dict[str, Dict[str, Any]] = {}

    def _add(symbol: str, company: str, result_date: str, source: str) -> None:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            return
        entry = merged.get(symbol)
        if entry is None:
            merged[symbol] = {
                "symbol": symbol,
                "company": (company or "").strip(),
                "result_date": (result_date or as_of.isoformat()),
                "sources": [source],
            }
        else:
            if source not in entry["sources"]:
                entry["sources"].append(source)
            if company and not entry["company"]:
                entry["company"] = company.strip()

    # 1) Assured NSE declared-results feed.
    if use_nse:
        for r in _from_nse(lookback_days=lookback_days, as_of=as_of, delta=nse_delta):
            _add(r["symbol"], r.get("company", ""), r.get("result_date", ""), "nse_filings")

    # 2) LLM web-grounded search.
    if use_llm:
        for r in _from_llm(as_of=as_of, lookback_days=lookback_days, watchlist=watchlist, model=model):
            _add(r["symbol"], r.get("company", ""), r.get("result_date", ""), "web_search")

    # 3) Watchlist acts as an explicit scope / seed.
    if watchlist:
        for s in watchlist:
            _add(s, "", as_of.isoformat(), "watchlist")
        merged = {s: merged[s] for s in watchlist if s in merged}

    result = list(merged.values())
    logger.info(
        "Discovery: %d result-declarers (nse=%s, llm=%s, watchlist=%d).",
        len(result), use_nse, use_llm, len(watchlist),
    )
    return result


def _from_nse(*, lookback_days: int, as_of: date, delta: bool = True) -> List[Dict[str, Any]]:
    """Assured NSE declared-results, unioning two feeds (each degrades to []).

    * **event-calendar** (primary) -- fresh: carries result board meetings for
      the whole market dated the day they happen. The financial-results feed
      below is chronically stale/thin (it can freeze a symbol's latest quarter
      for months), so the calendar is what actually surfaces just-declared names
      like GESHIP on the day.
    * **corporates-financial-results** (secondary) -- the "confirmed filed"
      signal; kept because when it IS fresh it confirms the numbers were filed,
      not merely that a board meeting occurred.
    """
    merged: Dict[str, Dict[str, Any]] = {}

    def _merge(rows: List[Dict[str, Any]]) -> None:
        for r in rows:
            sym = str(r.get("symbol", "")).strip().upper()
            if sym and sym not in merged:
                merged[sym] = r

    # Primary: fresh event-calendar.
    try:
        if delta:
            _merge(
                new_declared_from_calendar(
                    cache_path=config.NSE_SEEN_PATH,
                    as_of=as_of,
                    max_age_days=max(7, lookback_days),
                )
            )
        else:
            _merge(recent_declared_from_calendar(lookback_days=lookback_days, as_of=as_of))
    except Exception as e:  # noqa: BLE001 - never let NSE break discovery
        logger.warning("NSE event-calendar discovery failed (%s).", e)

    # Secondary: financial-results feed (confirmed filings).
    try:
        if delta:
            _merge(
                new_declared_results(
                    cache_path=config.NSE_SEEN_PATH,
                    as_of=as_of,
                    max_age_days=max(7, lookback_days),
                )
            )
        else:
            _merge(recent_declared_results(lookback_days=lookback_days, as_of=as_of))
    except Exception as e:  # noqa: BLE001 - never let NSE break discovery
        logger.warning("NSE financial-results discovery failed (%s).", e)

    return list(merged.values())


def _from_llm(
    *, as_of: date, lookback_days: int, watchlist: List[str], model: Optional[str]
) -> List[Dict[str, Any]]:
    prompt = _build_discovery_prompt(as_of, lookback_days, watchlist)
    try:
        output = run_copilot(prompt, web_grounding=True, scraper_tools=True, model=model)
    except Exception as e:  # noqa: BLE001
        logger.warning("Discovery LLM run failed (%s).", e)
        return []

    parsed = extract_json_block(output) or {}
    declarers = parsed.get("declarers") if isinstance(parsed, dict) else None
    out: List[Dict[str, Any]] = []
    for item in declarers or []:
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol", "")).strip().upper()
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "company": str(item.get("company", "")).strip(),
            "result_date": str(item.get("result_date", "")).strip() or as_of.isoformat(),
        })
    return out

