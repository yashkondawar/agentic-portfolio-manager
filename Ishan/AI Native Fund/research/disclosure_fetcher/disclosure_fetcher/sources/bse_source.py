"""
BSE is the primary source: it's the exchange's own regulatory disclosure
feed (via the unofficial-but-well-behaved `bse` PyPI package, which wraps
the same JSON endpoint bseindia.com's own announcements page calls, and
throttles itself to be polite to their servers). Everything a listed
company is required to file - results, presentations, transcripts, annual
reports, AGM notices, rating actions - eventually shows up here, which is
why it's tried before any generic web search.

Reference for the raw record shape this returns (NEWSID, NEWSSUB,
ATTACHMENTNAME, CATEGORYNAME, SUBCATNAME, NEWS_DT, ...):
https://github.com/BennyThadikaran/BseIndiaApi/blob/main/src/samples/announcements.json
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable

from bse.constants import CATEGORY

from disclosure_fetcher.config import BSE_CATEGORIES_TO_SCAN, KEYWORDS, SPECIAL_DISCLOSURE_HINTS
from disclosure_fetcher.models import Company, DocType, DocumentCandidate
from disclosure_fetcher.utils import (
    annual_label,
    annual_sort_key,
    extract_period_end_date,
    half_sort_key,
    half_year_label,
    matches_any,
    quarter_label,
    quarter_sort_key,
    recent_quarters,
)

logger = logging.getLogger(__name__)

ATTACH_LIVE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{name}"
ATTACH_HIS = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/{name}"

_CATEGORY_MAP = {
    "RESULT": CATEGORY.RESULT,
    "UPDATE": CATEGORY.UPDATE,
    "AGM": CATEGORY.AGM,
}

_MAX_PAGES_PER_CATEGORY = 40  # safety valve against unexpected pagination loops


def _classify(text: str) -> DocType | None:
    """Map a filing's title text to one of our doc types, or None if it's
    not something we care about (or looks like noise)."""
    if matches_any(text, KEYWORDS["noise"]):
        return None

    # Order matters: transcripts/presentations often *also* mention
    # "results" in passing ("...following the Q2 results, management held
    # an earnings call...") so check the more specific categories first.
    if matches_any(text, KEYWORDS["earnings_transcript"]):
        return DocType.EARNINGS_TRANSCRIPT
    if matches_any(text, KEYWORDS["investor_presentation"]):
        return DocType.INVESTOR_PRESENTATION
    if matches_any(text, KEYWORDS["annual_report"]):
        return DocType.ANNUAL_REPORT
    if matches_any(text, KEYWORDS["half_yearly_result"]):
        return DocType.HALF_YEARLY_RESULT
    if matches_any(text, KEYWORDS["quarterly_result"]):
        return DocType.QUARTERLY_RESULT
    if matches_any(text, SPECIAL_DISCLOSURE_HINTS):
        return DocType.SPECIAL_DISCLOSURE
    return None


def _period_for(doc_type: DocType, text: str, announced_on: date) -> tuple[str, str]:
    """Return (period_label, period_sort_key) for a classified filing.

    Prefers an explicit "...ended DD Month YYYY" date parsed out of the
    filing text (high confidence). Falls back to inferring the most
    recently-completed period as of the announcement date (lower
    confidence, but still usually right since companies file within their
    45-day SEBI LODR window).
    """
    period_end = extract_period_end_date(text)

    if doc_type == DocType.ANNUAL_REPORT:
        anchor = period_end or announced_on.replace(month=3, day=31)
        return annual_label(anchor), annual_sort_key(anchor)

    if doc_type == DocType.HALF_YEARLY_RESULT:
        anchor = period_end or announced_on
        return half_year_label(anchor), half_sort_key(anchor)

    if doc_type == DocType.QUARTERLY_RESULT:
        anchor = period_end or announced_on
        return quarter_label(anchor), quarter_sort_key(anchor)

    if doc_type == DocType.SPECIAL_DISCLOSURE:
        # Not tied to a reporting quarter at all - label by the event date.
        return f"Disclosure ({announced_on.isoformat()})", announced_on.isoformat()

    # Transcripts and investor presentations are tied to a quarter too -
    # infer from the announcement date itself (transcripts/ppts get filed
    # right around the results, so the nearest just-completed quarter as
    # of the announcement date is almost always the right one).
    recent = recent_quarters(1, as_of=announced_on, buffer_days=0)
    if recent:
        return recent[0]
    return quarter_label(announced_on), quarter_sort_key(announced_on)


def _confidence(doc_type: DocType, text: str, has_explicit_period: bool, has_attachment: bool) -> float:
    score = 0.5
    if has_attachment:
        score += 0.2
    else:
        score -= 0.4
    if has_explicit_period:
        score += 0.2
    if doc_type in (DocType.EARNINGS_TRANSCRIPT, DocType.INVESTOR_PRESENTATION):
        # These titles are usually unambiguous when they match at all.
        score += 0.1
    return max(0.0, min(1.0, score))


def _to_candidate(record: dict, company: Company, doc_type: DocType) -> DocumentCandidate | None:
    attachment = (record.get("ATTACHMENTNAME") or "").strip()
    if not attachment:
        return None  # nothing to download

    title = (record.get("HEADLINE") or record.get("NEWSSUB") or "").strip()
    combined_text = " ".join(
        str(record.get(k, "")) for k in ("NEWSSUB", "HEADLINE", "SUBCATNAME")
    )

    try:
        announced_on = datetime.strptime(
            (record.get("NEWS_DT") or record.get("DT_TM") or "")[:19],
            "%Y-%m-%dT%H:%M:%S",
        ).date()
    except ValueError:
        announced_on = date.today()

    period_end_found = extract_period_end_date(combined_text) is not None
    period_label, period_sort_key = _period_for(doc_type, combined_text, announced_on)

    return DocumentCandidate(
        doc_type=doc_type,
        company=company.name or company.query,
        period_label=period_label,
        period_sort_key=period_sort_key,
        title=title or f"{doc_type.value} ({period_label})",
        url=ATTACH_LIVE.format(name=attachment),
        source="BSE",
        announced_on=announced_on,
        heuristic_confidence=_confidence(doc_type, combined_text, period_end_found, True),
        raw={
            "newsid": record.get("NEWSID"),
            "attachhis_url": ATTACH_HIS.format(name=attachment),
            "category": record.get("CATEGORYNAME"),
            "subcategory": record.get("SUBCATNAME"),
        },
    )


def _fetch_category(bse_client, company: Company, category_value: str, from_date: date, to_date: date) -> Iterable[dict]:
    page_no = 1
    seen_ids: set = set()
    while page_no <= _MAX_PAGES_PER_CATEGORY:
        try:
            resp = bse_client.announcements(
                page_no=page_no,
                from_date=datetime.combine(from_date, datetime.min.time()),
                to_date=datetime.combine(to_date, datetime.min.time()),
                scripcode=company.bse_scrip_code,
                category=category_value,
            )
        except Exception as exc:
            logger.warning(
                "BSE announcements() failed for %s (category=%s, page=%s): %s",
                company.name, category_value, page_no, exc,
            )
            return

        rows = resp.get("Table") or []
        if not rows:
            return

        new_rows = [r for r in rows if r.get("NEWSID") not in seen_ids]
        if not new_rows:
            return  # BSE stopped returning anything new; avoid spinning

        for row in new_rows:
            seen_ids.add(row.get("NEWSID"))
            yield row

        page_no += 1


def fetch_bse_candidates(bse_client, company: Company, lookback_years: int = 6) -> list[DocumentCandidate]:
    """Pull Result / Company Update / AGM announcements for `company` over
    the last `lookback_years` years and turn the relevant ones into
    DocumentCandidate objects.

    Returns an empty list (with a warning logged) rather than raising, if
    the company has no resolvable BSE scrip code - callers should still
    try Screener + web search in that case.
    """
    if not company.bse_scrip_code:
        logger.warning("No BSE scrip code for %s - skipping BSE source.", company.query)
        return []

    to_date = date.today()
    from_date = to_date - timedelta(days=365 * lookback_years)

    candidates: list[DocumentCandidate] = []
    seen_newsids: set = set()

    for cat_key in BSE_CATEGORIES_TO_SCAN:
        category_value = _CATEGORY_MAP[cat_key]
        for record in _fetch_category(bse_client, company, category_value, from_date, to_date):
            newsid = record.get("NEWSID")
            if newsid in seen_newsids:
                continue
            seen_newsids.add(newsid)

            text = " ".join(
                str(record.get(k, "")) for k in ("NEWSSUB", "HEADLINE", "SUBCATNAME")
            )
            doc_type = _classify(text)
            if doc_type is None:
                continue

            candidate = _to_candidate(record, company, doc_type)
            if candidate is not None:
                candidates.append(candidate)

    logger.info("BSE source found %d candidates for %s", len(candidates), company.name)
    return candidates
