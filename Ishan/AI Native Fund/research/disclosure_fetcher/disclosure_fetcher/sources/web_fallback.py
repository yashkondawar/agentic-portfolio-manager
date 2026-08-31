"""
Generic web-search fallback, used only to fill gaps BSE + Screener didn't
cover (a specific quarter's transcript that was never formally filed, an
investor presentation that only ever lived on the company's own IR page,
etc).

Tavily is tried first since its `include_domains` filtering and clean,
LLM-ready snippets make it much easier for the LLM validation step to do a
good job. If no Tavily key is configured, or a Tavily call errors out
(network issue, free-tier quota exhausted), this transparently falls back
to DuckDuckGo via the `ddgs` package, which needs no API key at all.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from disclosure_fetcher.config import REQUEST_TIMEOUT, TAVILY_API_KEY

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    engine: str  # "tavily" | "duckduckgo"


class WebSearchClient:
    """Unified search(...) interface over Tavily with a DuckDuckGo backup."""

    def __init__(self, tavily_api_key: str = TAVILY_API_KEY):
        self._tavily = None
        if tavily_api_key:
            try:
                from tavily import TavilyClient

                self._tavily = TavilyClient(api_key=tavily_api_key)
            except Exception as exc:
                logger.warning("Could not initialise Tavily client: %s", exc)

    def search(
        self, query: str, max_results: int = 5, include_domains: Optional[list[str]] = None
    ) -> list[SearchResult]:
        if self._tavily is not None:
            try:
                return self._search_tavily(query, max_results, include_domains)
            except Exception as exc:
                logger.warning("Tavily search failed (%s); falling back to DuckDuckGo.", exc)
        return self._search_duckduckgo(query, max_results, include_domains)

    def _search_tavily(
        self, query: str, max_results: int, include_domains: Optional[list[str]]
    ) -> list[SearchResult]:
        kwargs = {"query": query, "max_results": max_results}
        if include_domains:
            kwargs["include_domains"] = include_domains
        resp = self._tavily.search(**kwargs)
        out = []
        for r in resp.get("results", []):
            out.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    engine="tavily",
                )
            )
        return out

    def _search_duckduckgo(
        self, query: str, max_results: int, include_domains: Optional[list[str]]
    ) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except Exception as exc:
            logger.error("ddgs package not available: %s", exc)
            return []

        full_query = query
        if include_domains:
            # DuckDuckGo doesn't take a structured domain filter, so fold it
            # into the query string as an OR of site: filters.
            site_clause = " OR ".join(f"site:{d}" for d in include_domains)
            full_query = f"{query} ({site_clause})"

        try:
            with DDGS() as ddgs:
                raw = ddgs.text(full_query, max_results=max_results)
        except Exception as exc:
            logger.warning("DuckDuckGo search failed for %r: %s", full_query, exc)
            return []

        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
                engine="duckduckgo",
            )
            for r in raw
        ]


def fetch_page_text(url: str, session: Optional[requests.Session] = None, max_chars: int = 6000) -> str:
    """Grab a rough text snapshot of a landing page (e.g. a company's IR
    page) to hand to the LLM as extra context when validating a candidate.
    Best-effort only: returns "" on any failure rather than raising.
    """
    session = session or requests.Session()
    try:
        resp = session.get(url, headers={"User-Agent": _UA}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.info("Could not fetch page text for %s: %s", url, exc)
        return ""

    content_type = resp.headers.get("Content-Type", "")
    if "html" not in content_type and "text" not in content_type:
        return ""  # e.g. a PDF - handled separately by the downloader/pypdf path

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return text[:max_chars]
    except Exception as exc:
        logger.info("Could not parse page text for %s: %s", url, exc)
        return ""
