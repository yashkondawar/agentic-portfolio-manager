"""
Orchestrates a full run for one company:

  1. Resolve the company (BSE lookup -> Screener slug; web-search+LLM as a
     last resort, with the LLM's guess always re-verified against BSE's
     own lookup before it's trusted).
  2. Pull candidates from BSE (primary) and Screener (bonus, best-effort).
  3. Batch-validate everything found so far through Gemini (skipped
     gracefully if no API key / quota is available).
  4. Work out which doc_type x period slots are still empty relative to
     the requested targets, and for each gap: generate search queries,
     search Tavily (DuckDuckGo backup), and validate the hits.
  5. Pick winners per doc type up to the target counts, preferring BSE >
     Screener > web search, and higher confidence, when there's a choice.
  6. Download everything selected and write a manifest.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from disclosure_fetcher.config import (
    BASE_OUTPUT_DIR,
    ENABLE_WEB_FALLBACK,
    GEMINI_API_KEY,
    INTER_REQUEST_DELAY,
    TAVILY_API_KEY,
    FetchTargets,
)
from disclosure_fetcher.company_resolver import enrich_with_screener, resolve_company, resolve_via_bse
from disclosure_fetcher.downloader import download_candidate, write_manifest
from disclosure_fetcher.models import Company, DocType, DocumentCandidate, PipelineResult
from disclosure_fetcher.sources import bse_source, screener_source
from disclosure_fetcher.utils import recent_annual_years, recent_halves, recent_quarters

logger = logging.getLogger(__name__)

_SOURCE_RANK = {"BSE": 0, "Screener": 1, "WebSearch": 2}


# --------------------------------------------------------------------------- #
# Fund vendoring note: LLM (Gemini) classification and the Tavily/DuckDuckGo
# web-search fallback are optional extras gated by ENABLE_WEB_FALLBACK
# (default OFF — see config.py). BSE + Screener need neither. These two
# no-op stand-ins are used on the disabled path so `google-genai`,
# `tavily-python`, and `ddgs` never need to be installed/imported unless a
# caller explicitly opts in.
# --------------------------------------------------------------------------- #


class _NullLLMAgent:
    """Stand-in for llm_agent.LLMAgent when ENABLE_WEB_FALLBACK is off (or no
    Gemini key is set) — always reports unavailable, never imports google-genai."""

    available = False
    disabled = True

    def generate_search_queries(self, *a, **kw):
        return []

    def classify_items(self, *a, **kw):
        return {}

    def extract_company_identifier(self, *a, **kw):
        return None


class _NullWebSearchClient:
    """Stand-in for sources.web_fallback.WebSearchClient when
    ENABLE_WEB_FALLBACK is off — always returns no results, never imports
    tavily/ddgs."""

    def __init__(self, *a, **kw):
        pass

    def search(self, *a, **kw):
        return []


def _check_fallback_keys(gemini_api_key: str, tavily_api_key: str) -> None:
    """enable_web_fallback=True with neither key configured is treated as a
    misconfiguration, not a silent degrade — the whole point of opting in is
    better gap-fill coverage than the key-free BSE+Screener path already
    gets. (DuckDuckGo itself needs no key; either key alone is enough to
    pass this check and let the run proceed with whatever degradation the
    individual llm_agent/web_fallback modules already handle internally.)
    """
    if not gemini_api_key and not tavily_api_key:
        raise RuntimeError(
            "enable_web_fallback=True (or ENABLE_WEB_FALLBACK=1) but neither "
            "GEMINI_API_KEY nor TAVILY_API_KEY is set. Set at least one in "
            ".env (see disclosure_fetcher/.env.example), or leave "
            "ENABLE_WEB_FALLBACK unset/0 to use the key-free BSE+Screener-only "
            "path."
        )


def _make_llm_agent(gemini_api_key: str, disable_llm: bool, enable_web_fallback: bool):
    if not enable_web_fallback:
        return _NullLLMAgent()
    from disclosure_fetcher.llm_agent import LLMAgent

    return LLMAgent(api_key=gemini_api_key, disabled=disable_llm)


def _make_web_search_client(tavily_api_key: str, enable_web_fallback: bool):
    if not enable_web_fallback:
        return _NullWebSearchClient()
    from disclosure_fetcher.sources.web_fallback import WebSearchClient

    return WebSearchClient(tavily_api_key=tavily_api_key)


# --------------------------------------------------------------------------- #
# Company resolution, including the web-search last resort
# --------------------------------------------------------------------------- #

def _resolve_via_web_search(
    company_query: str, bse_client, llm, web, session: requests.Session
) -> Company:
    """Only reached if BSE's own lookup *and* Screener's search both came up
    empty - unusual for anything actually listed. Requires the LLM (there's
    no safe non-LLM way to turn free-text search snippets into a scrip
    code), and always re-verifies the LLM's guess against BSE's own lookup
    before trusting it.
    """
    empty = Company(query=company_query)
    if not llm.available:
        return empty

    results = web.search(f'"{company_query}" BSE scrip code NSE symbol screener.in', max_results=5)
    if not results:
        return empty

    snippets = [f"{r.title}: {r.snippet}" for r in results if r.snippet]
    extracted = llm.extract_company_identifier(company_query, snippets)
    if not extracted or extracted.confidence < 0.5:
        return empty

    candidate = extracted.bse_scrip_code or extracted.nse_symbol
    if not candidate:
        return empty

    verified = resolve_via_bse(bse_client, candidate)
    if not verified.is_resolved():
        logger.warning("Web-search-assisted guess %r for %r did not verify against BSE.", candidate, company_query)
        return empty

    verified.query = company_query
    return enrich_with_screener(verified, session=session)


# --------------------------------------------------------------------------- #
# Merging / deduping candidates from multiple sources
# --------------------------------------------------------------------------- #

_CONFIDENCE_GAP = 0.2  # how much better final_confidence has to be to override source authority


def _better(a: DocumentCandidate, b: DocumentCandidate) -> bool:
    """True if `a` should win over `b` for the same (doc_type, period) slot.

    A big confidence gap overrides everything (we'd rather keep a
    validated web-search hit than a BSE title the LLM flagged as probably
    wrong). Within a comparable confidence band, prefer the more
    authoritative source: BSE > Screener > WebSearch.
    """
    gap = a.final_confidence - b.final_confidence
    if abs(gap) > _CONFIDENCE_GAP:
        return gap > 0
    return _SOURCE_RANK.get(a.source, 9) < _SOURCE_RANK.get(b.source, 9)


def _dedupe(candidates: list[DocumentCandidate]) -> list[DocumentCandidate]:
    """One candidate per (doc_type, period) - see `_better` for the rule."""
    best: dict[tuple, DocumentCandidate] = {}
    for c in candidates:
        key = c.dedupe_key()
        current = best.get(key)
        if current is None or _better(c, current):
            best[key] = c
    return list(best.values())


# --------------------------------------------------------------------------- #
# LLM validation of an already-typed candidate pool (BSE + Screener hits)
# --------------------------------------------------------------------------- #

def _llm_validate_pool(llm, company_name: str, candidates: list[DocumentCandidate]) -> None:
    """Mutates `candidates` in place, filling in llm_confidence/llm_reasoning.
    Deliberately does NOT let the LLM rewrite period_label/doc_type - our
    own deterministic fiscal-calendar math is the source of truth for
    those; the LLM's job is only to say whether a title really matches
    what we think it is.
    """
    items = [
        {
            "index": i,
            "title": c.title,
            "source": c.source,
            "doc_type_guess": c.doc_type.value,
            "period_label_guess": c.period_label,
        }
        for i, c in enumerate(candidates)
    ]
    verdicts = llm.classify_items(company_name, items)
    for i, c in enumerate(candidates):
        v = verdicts.get(i)
        if v is None:
            continue
        c.llm_reasoning = v.reasoning
        c.llm_confidence = v.confidence if v.is_relevant else min(0.15, v.confidence)


# --------------------------------------------------------------------------- #
# Gap detection + web-search fallback for a single (doc_type, period) slot
# --------------------------------------------------------------------------- #

def _expected_periods(doc_type: DocType, targets: FetchTargets) -> list[tuple[str, str]]:
    if doc_type == DocType.ANNUAL_REPORT:
        return recent_annual_years(targets.annual_reports)
    if doc_type == DocType.QUARTERLY_RESULT:
        return recent_quarters(targets.quarterly_results)
    if doc_type == DocType.HALF_YEARLY_RESULT:
        return recent_halves(targets.half_yearly_results)
    if doc_type == DocType.EARNINGS_TRANSCRIPT:
        return recent_quarters(targets.earnings_transcripts)
    if doc_type == DocType.INVESTOR_PRESENTATION:
        return recent_quarters(targets.investor_presentations)
    return []  # special_disclosure isn't slotted to a calendar period


def _target_count(doc_type: DocType, targets: FetchTargets) -> int:
    return {
        DocType.ANNUAL_REPORT: targets.annual_reports,
        DocType.QUARTERLY_RESULT: targets.quarterly_results,
        DocType.HALF_YEARLY_RESULT: targets.half_yearly_results,
        DocType.EARNINGS_TRANSCRIPT: targets.earnings_transcripts,
        DocType.INVESTOR_PRESENTATION: targets.investor_presentations,
        DocType.SPECIAL_DISCLOSURE: targets.special_disclosures,
    }[doc_type]


_FILE_EXTENSIONS = (".pdf", ".ppt", ".pptx", ".doc", ".docx")


def _search_gap(
    llm,
    web,
    company: Company,
    doc_type: DocType,
    period_label: str,
    period_sort_key: str,
) -> list[DocumentCandidate]:
    queries = llm.generate_search_queries(company.name, doc_type.value, period_label)

    hits = []
    seen_urls: set[str] = set()
    for q in queries:
        for r in web.search(q, max_results=5):
            if r.url in seen_urls:
                continue
            seen_urls.add(r.url)
            hits.append(r)
        time.sleep(INTER_REQUEST_DELAY)

    # Only consider things that look like an actual document, not a landing
    # page - we want files we can download and validate, not HTML to parse
    # further (that path exists in web_fallback.fetch_page_text if you want
    # to extend this to follow IR-page landing links).
    hits = [h for h in hits if h.url.lower().endswith(_FILE_EXTENSIONS)]
    if not hits:
        return []

    items = [
        {
            "index": i,
            "title": h.title,
            "source": f"WebSearch:{h.engine}",
            "doc_type_guess": doc_type.value,
            "period_label_guess": period_label,
            "context": h.snippet,
        }
        for i, h in enumerate(hits)
    ]
    verdicts = llm.classify_items(company.name, items)

    out = []
    for i, h in enumerate(hits):
        v = verdicts.get(i)
        if v is not None:
            if not v.is_relevant:
                continue
            confidence, reasoning = v.confidence, v.reasoning
        elif not llm.available:
            # No LLM at all: keep it, but clearly mark it unverified so a
            # human reviewing manifest.csv knows to double check it.
            confidence, reasoning = 0.3, "LLM unavailable - unverified web search hit, please review"
        else:
            continue  # LLM ran but gave no verdict on this one - skip it

        out.append(
            DocumentCandidate(
                doc_type=doc_type,
                company=company.name,
                period_label=period_label,
                period_sort_key=period_sort_key,
                title=h.title,
                url=h.url,
                source="WebSearch",
                heuristic_confidence=0.3,
                llm_confidence=confidence,
                llm_reasoning=reasoning,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

def run_pipeline(
    company_query: str,
    targets: Optional[FetchTargets] = None,
    output_dir: Optional[Path] = None,
    disable_llm: bool = False,
    gemini_api_key: str = GEMINI_API_KEY,
    tavily_api_key: str = TAVILY_API_KEY,
    min_confidence: float = 0.4,
    enable_web_fallback: bool = ENABLE_WEB_FALLBACK,
) -> PipelineResult:
    """Run the full BSE + Screener (+ optional LLM/web-search fallback)
    pipeline for one company.

    `enable_web_fallback` (default: config.ENABLE_WEB_FALLBACK, itself
    default OFF) gates BOTH the Gemini classification stage and the
    Tavily/DuckDuckGo web-search gap-filling stage — the fund's key-free
    primary path is BSE + Screener only. When it's False, `google-genai`,
    `tavily-python`, and `ddgs` are never imported; candidates keep their
    keyword-heuristic confidence and unresolved gaps are simply reported
    in `result.warnings` instead of being searched for on the open web.
    """
    if enable_web_fallback:
        _check_fallback_keys(gemini_api_key, tavily_api_key)

    targets = targets or FetchTargets()
    output_base = Path(output_dir) if output_dir else BASE_OUTPUT_DIR

    session = requests.Session()
    llm = _make_llm_agent(gemini_api_key, disable_llm, enable_web_fallback)
    web = _make_web_search_client(tavily_api_key, enable_web_fallback)

    from bse import BSE

    bse_client = BSE(download_folder=str(output_base / "_bse_cache"))

    # --- Stage 0: resolve the company ---
    company = resolve_company(company_query, bse_client, session=session)
    if not company.is_resolved():
        company = _resolve_via_web_search(company_query, bse_client, llm, web, session)

    result = PipelineResult(company=company)
    if not company.is_resolved():
        result.warnings.append(
            f"Could not resolve '{company_query}' to a BSE-listed company via BSE, "
            "Screener, or a web-search fallback. Try the exact BSE/NSE trading "
            "symbol (e.g. 'TCS', 'INFY') or the full legal registered name."
        )
        return result

    logger.info(
        "Resolved '%s' -> name=%s, BSE=%s, Screener=%s",
        company_query, company.name, company.bse_scrip_code, company.screener_slug,
    )

    # --- Stage 1+2: BSE (primary) + Screener (bonus) ---
    candidates = bse_source.fetch_bse_candidates(bse_client, company, lookback_years=targets.lookback_years)
    time.sleep(INTER_REQUEST_DELAY)
    candidates += screener_source.fetch_screener_candidates(company, session=session)
    candidates = _dedupe(candidates)

    if not candidates:
        result.warnings.append(
            "BSE + Screener returned nothing at all. This can happen for very "
            "recently listed companies, or if BSE is rate-limiting this IP."
            + (
                " The web-search fallback below will still try to fill every slot."
                if enable_web_fallback
                else " Web-search fallback is disabled (enable_web_fallback=False) "
                "so no further gap-filling will be attempted."
            )
        )

    if not enable_web_fallback:
        result.warnings.append(
            "Web-search fallback disabled (key-free BSE+Screener-only mode): "
            "any doc_type/period gaps below reflect what BSE + Screener actually "
            "had, not a search failure. Set ENABLE_WEB_FALLBACK=1 (and provide "
            "GEMINI_API_KEY/TAVILY_API_KEY for best results) to fill gaps from "
            "the open web."
        )

    # --- Stage 3: LLM validation of what BSE/Screener found ---
    _llm_validate_pool(llm, company.name, candidates)

    # --- Stage 4: find gaps and fill them via web search (no-op when
    # enable_web_fallback is False — llm/web are Null stand-ins) ---
    for doc_type in DocType:
        target_n = _target_count(doc_type, targets)
        if target_n <= 0:
            continue

        expected = _expected_periods(doc_type, targets)
        if expected:
            found_keys = {
                c.period_sort_key
                for c in candidates
                if c.doc_type == doc_type and c.final_confidence >= min_confidence
            }
            missing = [(label, key) for label, key in expected if key not in found_keys]
        else:
            # special_disclosure: no fixed slots, just check whether we're
            # under target count and, if so, run one broad query.
            existing = sum(1 for c in candidates if c.doc_type == doc_type and c.final_confidence >= min_confidence)
            missing = [("recent material disclosures", "n/a")] if existing < target_n else []

        for period_label, period_sort_key in missing:
            filler = _search_gap(llm, web, company, doc_type, period_label, period_sort_key)
            candidates.extend(filler)

    candidates = _dedupe(candidates)

    # --- Stage 5: pick winners per doc type, most recent first, up to target ---
    selected: list[DocumentCandidate] = []
    for doc_type in DocType:
        target_n = _target_count(doc_type, targets)
        if target_n <= 0:
            continue
        pool = [
            c for c in candidates
            if c.doc_type == doc_type and c.final_confidence >= min_confidence
        ]
        # Most recent period first; higher confidence first as a tiebreak
        # (in practice periods are already unique post-dedupe, but keep
        # this correct rather than relying on that).
        pool.sort(key=lambda c: (c.period_sort_key, c.final_confidence), reverse=True)
        selected.extend(pool[:target_n])

    # --- Stage 6: download + manifest ---
    company_dir = output_base / company.slug
    for candidate in selected:
        ok = download_candidate(candidate, company_dir, session=session)
        candidate.accepted = ok
        if ok:
            result.downloaded.append(candidate)
        time.sleep(INTER_REQUEST_DELAY)

    result.candidates = candidates
    manifest_path = write_manifest(candidates, company_dir)
    result.manifest_path = str(manifest_path)

    for doc_type in DocType:
        target_n = _target_count(doc_type, targets)
        if target_n <= 0:
            continue
        got = sum(1 for c in result.downloaded if c.doc_type == doc_type)
        if got < target_n:
            result.warnings.append(
                f"{doc_type.value}: found {got}/{target_n}. "
                + (
                    "Note: half-yearly results are normal only for SME-platform "
                    "or debt-listed issuers - a main-board company reporting "
                    "quarterly is expected to show 0 here."
                    if doc_type == DocType.HALF_YEARLY_RESULT and got == 0
                    else "Check manifest.csv for lower-confidence candidates "
                    "that were found but not auto-accepted."
                )
            )

    return result
