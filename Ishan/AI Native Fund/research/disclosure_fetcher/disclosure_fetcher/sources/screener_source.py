"""
Screener.in enrichment source.

Screener aggregates a "Documents" section on every company page with
three sub-lists worth mining: Annual Reports (PDF, one per FY), Concalls
(each with Transcript / PPT / Recording links), and Credit Ratings. It's a
convenient single-page cross-check on top of BSE, but it is a *bonus*
source, not the backbone of this tool:

  - It's a single lightweight GET per company (not a crawl), which keeps
    this well clear of anything resembling bulk scraping - but if you plan
    to run this over many companies on a schedule, use Screener's own
    official (if limited) API instead: https://www.screener.in/api/docs/
    and check their current Terms of Service for your use case.
  - Screener's HTML structure isn't officially documented and can change
    at any time, so every extraction step below is wrapped defensively:
    if a selector stops matching, this returns fewer (or zero) candidates
    rather than raising, and the rest of the pipeline (BSE + web search)
    just picks up the slack.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from disclosure_fetcher.config import REQUEST_TIMEOUT
from disclosure_fetcher.models import Company, DocType, DocumentCandidate
from disclosure_fetcher.utils import (
    annual_label,
    annual_sort_key,
    matches_any,
    recent_quarters,
)

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_YEAR_RANGE_RE = re.compile(r"(20\d{2})\s*[-/]\s*(\d{2,4})")
_YEAR_RE = re.compile(r"(20\d{2})")


def _fy_end_year_from_text(text: str) -> Optional[int]:
    m = _YEAR_RANGE_RE.search(text)
    if m:
        start, end_part = int(m.group(1)), m.group(2)
        return int(end_part) if len(end_part) == 4 else (start // 100) * 100 + int(end_part)
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def _nearby_date(tag) -> Optional[date]:
    """Look a couple of levels up the DOM for something date-shaped."""
    from dateutil import parser as dateparser

    node = tag
    for _ in range(4):
        if node is None:
            break
        text = node.get_text(" ", strip=True) if hasattr(node, "get_text") else ""
        if text:
            try:
                # fuzzy=True lets it pick a date out of a longer sentence
                return dateparser.parse(text, fuzzy=True, dayfirst=True).date()
            except (ValueError, OverflowError, TypeError):
                pass
        node = getattr(node, "parent", None)
    return None


def _fetch_page(slug: str, session: requests.Session) -> Optional[BeautifulSoup]:
    for path in (f"/company/{slug}/consolidated/", f"/company/{slug}/"):
        url = f"https://www.screener.in{path}"
        try:
            resp = session.get(url, headers={"User-Agent": _UA}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200 and resp.text:
                return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as exc:
            logger.warning("Screener fetch failed for %s: %s", url, exc)
    return None


def _documents_container(soup: BeautifulSoup):
    container = soup.find(id="documents")
    if container is not None:
        return container
    # Defensive fallback: any element whose id/class mentions "document"
    container = soup.find(id=re.compile("document", re.I))
    if container is not None:
        return container
    logger.info("Could not locate a #documents section; scanning the full page instead.")
    return soup


def _extract_annual_reports(container, company_name: str) -> list[DocumentCandidate]:
    out = []
    try:
        for a in container.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf"):
                continue
            context = a.get_text(" ", strip=True)
            parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
            if not matches_any(context + " " + parent_text, [r"annual report"]):
                # only counts as an annual report if the word appears nearby;
                # otherwise it's probably a concall PPT/transcript PDF instead
                fy_year = _fy_end_year_from_text(context) or _fy_end_year_from_text(parent_text)
                if fy_year is None:
                    continue
            fy_year = _fy_end_year_from_text(context) or _fy_end_year_from_text(parent_text)
            if fy_year is None:
                continue
            anchor_date = date(fy_year, 3, 31)
            out.append(
                DocumentCandidate(
                    doc_type=DocType.ANNUAL_REPORT,
                    company=company_name,
                    period_label=annual_label(anchor_date),
                    period_sort_key=annual_sort_key(anchor_date),
                    title=context or f"Annual Report FY{str(fy_year)[-2:]}",
                    url=href if href.startswith("http") else f"https://www.screener.in{href}",
                    source="Screener",
                    announced_on=None,
                    heuristic_confidence=0.6,
                )
            )
    except Exception as exc:
        logger.warning("Failed parsing Screener annual reports: %s", exc)
    return out


def _extract_concall_docs(container, company_name: str) -> list[DocumentCandidate]:
    out = []
    try:
        for a in container.find_all("a", href=True):
            text = a.get_text(" ", strip=True).lower()
            href = a["href"]

            if "transcript" in text:
                doc_type = DocType.EARNINGS_TRANSCRIPT
            elif "ppt" in text or "presentation" in text:
                doc_type = DocType.INVESTOR_PRESENTATION
            else:
                continue  # skip "REC"/recording links and anything else

            event_date = _nearby_date(a)
            if event_date is None:
                continue  # can't place it in a quarter, so skip rather than guess

            recent = recent_quarters(1, as_of=event_date, buffer_days=0)
            if not recent:
                continue
            period_label, period_sort_key = recent[0]

            out.append(
                DocumentCandidate(
                    doc_type=doc_type,
                    company=company_name,
                    period_label=period_label,
                    period_sort_key=period_sort_key,
                    title=a.get_text(" ", strip=True) or doc_type.value,
                    url=href if href.startswith("http") else f"https://www.screener.in{href}",
                    source="Screener",
                    announced_on=event_date,
                    heuristic_confidence=0.55,
                )
            )
    except Exception as exc:
        logger.warning("Failed parsing Screener concall docs: %s", exc)
    return out


def _extract_credit_ratings(container, company_name: str) -> list[DocumentCandidate]:
    out = []
    try:
        for a in container.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if not matches_any(text, [r"rating"]):
                continue
            href = a["href"]
            event_date = _nearby_date(a) or date.today()
            out.append(
                DocumentCandidate(
                    doc_type=DocType.SPECIAL_DISCLOSURE,
                    company=company_name,
                    period_label=f"Rating update ({event_date.isoformat()})",
                    period_sort_key=event_date.isoformat(),
                    title=text or "Credit rating update",
                    url=href if href.startswith("http") else f"https://www.screener.in{href}",
                    source="Screener",
                    announced_on=event_date,
                    heuristic_confidence=0.5,
                )
            )
    except Exception as exc:
        logger.warning("Failed parsing Screener credit ratings: %s", exc)
    return out


def fetch_screener_candidates(company: Company, session: requests.Session | None = None) -> list[DocumentCandidate]:
    """Best-effort single-page fetch of a company's Screener Documents tab.

    Returns [] (with a warning logged) if the company has no screener_slug,
    the page can't be fetched, or nothing recognisable is found - never
    raises, since this is a bonus source layered on top of BSE.
    """
    if not company.screener_slug:
        logger.info("No Screener slug for %s - skipping Screener source.", company.query)
        return []

    session = session or requests.Session()
    soup = _fetch_page(company.screener_slug, session)
    if soup is None:
        logger.warning("Could not fetch Screener page for %s", company.query)
        return []

    container = _documents_container(soup)
    name = company.name or company.query

    candidates = (
        _extract_annual_reports(container, name)
        + _extract_concall_docs(container, name)
        + _extract_credit_ratings(container, name)
    )
    logger.info("Screener source found %d candidates for %s", len(candidates), name)
    return candidates
