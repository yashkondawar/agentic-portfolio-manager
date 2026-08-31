"""
Turn a free-text company name into the identifiers every other module
needs: a BSE scrip code (for the announcements API) and a Screener slug
(for the documents page).

Resolution order:
  1. BSE's own lookup endpoint (via the `bse` package) - authoritative,
     free, no external API key needed. Matches on name / symbol / ISIN /
     scrip code.
  2. Screener's lightweight company-search endpoint, to get the slug used
     in screener.in/company/<slug>/ URLs. This is a separate namespace
     from BSE's, so it's resolved independently and cross-checked by
     symbol where possible.
  3. If both of those fail (unusual - typically only for very obscure or
     recently-listed names), fall back to a plain web search + LLM read
     of the results to guess the scrip code. This last resort is wired up
     in pipeline.py, not here, since it needs the web_fallback + llm_agent
     modules.
"""
from __future__ import annotations

import logging
import re

import requests

from disclosure_fetcher.config import REQUEST_TIMEOUT
from disclosure_fetcher.models import Company

logger = logging.getLogger(__name__)

SCREENER_SEARCH_URL = "https://www.screener.in/api/company/search/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Verified against a live query (2026-07-09): Screener's /api/company/search/
# returns [] for "KPIT Technologies Ltd." (trailing period after "Ltd") but
# matches fine for "KPIT Technologies Ltd" (no period) - same for "Reliance
# Industries Ltd." vs "Ltd". This bites any caller whose company name comes
# from an official-register source (e.g. NSE/BSE listing data, which commonly
# writes "... Ltd." with the period) - normalize it away before querying so
# that's not a silent resolution failure. Does not touch periods elsewhere in
# the name (e.g. "L&T Finance Ltd." -> "L&T Finance Ltd", not "L&T Finance").
_TRAILING_LTD_PERIOD_RE = re.compile(r"\b(Ltd|Limited)\.\s*$", re.IGNORECASE)


def _normalize_company_query(name: str) -> str:
    return _TRAILING_LTD_PERIOD_RE.sub(lambda m: m.group(1), name).strip()


def resolve_via_bse(bse_client, name: str) -> Company:
    """Use bse.lookup() to resolve name/symbol/ISIN/scrip-code -> Company."""
    company = Company(query=name)
    lookup_text = _normalize_company_query(name)
    try:
        result = bse_client.lookup(lookup_text)
    except Exception as exc:  # network hiccup, bad input, etc.
        logger.warning("BSE lookup failed for %r: %s", name, exc)
        return company

    if not result:
        logger.info("BSE lookup returned no match for %r", name)
        return company

    company.name = result.get("company_name") or name
    company.nse_symbol = result.get("symbol")
    company.isin = result.get("isin")
    company.bse_scrip_code = result.get("bse_code") or result.get("scrip_code")
    return company


def resolve_via_screener(name: str, session: requests.Session | None = None) -> dict:
    """Hit Screener's public company-search endpoint.

    Returns the raw top match dict (typically has at least 'name' and
    'url' keys, url looking like '/company/TCS/consolidated/') or {} if
    nothing came back. This is a single, lightweight GET - not a crawl -
    so it stays well clear of anything Screener's terms of service would
    consider bulk scraping. If you plan to hit this a lot (many companies,
    on a schedule), use Screener's own official API instead:
    https://www.screener.in/api/docs/
    """
    session = session or requests.Session()
    try:
        resp = session.get(
            SCREENER_SEARCH_URL,
            params={"q": name},
            headers={"User-Agent": _UA},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Screener search failed for %r: %s", name, exc)
        return {}

    if not data:
        return {}
    # response is a list of {"id", "name", "url", "management", ...}
    return data[0] if isinstance(data, list) else data


def enrich_with_screener(company: Company, session: requests.Session | None = None) -> Company:
    """Fill in screener_slug / screener_url on an already-partially-resolved Company."""
    search_term = _normalize_company_query(company.nse_symbol or company.name or company.query)
    match = resolve_via_screener(search_term, session=session)

    if not match:
        return company

    url = match.get("url", "")
    # url looks like "/company/TCS/consolidated/" or "/company/id/12345/consolidated/"
    parts = [p for p in url.split("/") if p]
    if len(parts) >= 2 and parts[0] == "company":
        company.screener_slug = parts[1] if parts[1] != "id" else "/".join(parts[1:3])
    company.screener_url = f"https://www.screener.in{url}" if url else None

    if not company.name:
        company.name = match.get("name", company.query)

    return company


def resolve_company(name: str, bse_client, session: requests.Session | None = None) -> Company:
    """Full resolution: BSE first, then enrich with the Screener slug."""
    company = resolve_via_bse(bse_client, name)
    company = enrich_with_screener(company, session=session)

    if not company.is_resolved():
        logger.warning(
            "Could not resolve %r via BSE or Screener. The web-search "
            "fallback (pipeline._resolve_via_web_search) will try next.",
            name,
        )
    return company
