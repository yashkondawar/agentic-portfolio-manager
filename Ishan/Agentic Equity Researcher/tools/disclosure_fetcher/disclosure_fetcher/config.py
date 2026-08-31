"""
Central configuration for the disclosure fetcher.

Loads API keys from environment variables (via a .env file if present) and
defines the defaults used across the pipeline: how many documents of each
type to collect, how far back to look, which BSE announcement categories to
query, and the keyword heuristics used to pre-classify announcements before
they are handed to the LLM for confirmation.

Nothing in here talks to the network. It's pure settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # reads a .env file in the current working directory, if present


# --------------------------------------------------------------------------- #
# API keys / model selection
# --------------------------------------------------------------------------- #

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# gemini-2.5-flash is a good default: it's a stable (non-preview) model on
# Google's free tier as of mid-2026, fast, and cheap enough to run large
# batch-classification prompts on. Swap via env var if you want to try
# gemini-3.5-flash or gemini-3.1-flash-lite instead.
# IMPORTANT: do not use gemini-2.0-flash / gemini-2.0-flash-lite - Google
# shut those down on 1 June 2026.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Set to "1" to skip all LLM calls and rely purely on the keyword/regex
# heuristics below. Useful if you've exhausted your Gemini free-tier quota
# for the day but still want BSE + Screener results.
DISABLE_LLM = os.getenv("DISABLE_LLM", "0") == "1"

# --------------------------------------------------------------------------- #
# AI-Native Fund vendoring note (added when this package was vendored into
# research/disclosure_fetcher/ — see that folder's README "Fund integration"
# section for the full rationale).
#
# BSE + Screener are the key-free primary sources and always run — no flag
# needed. The Gemini-classification and Tavily/DuckDuckGo web-search-fallback
# stages are an OPT-IN extra, gated behind ENABLE_WEB_FALLBACK (default OFF)
# so the fund never silently makes an LLM/web-search call it wasn't asked to,
# and never requires google-genai/tavily-python/ddgs to be installed for the
# primary path. If a caller sets ENABLE_WEB_FALLBACK=1 (or passes
# enable_web_fallback=True to pipeline.run_pipeline) with NEITHER
# GEMINI_API_KEY nor TAVILY_API_KEY configured, pipeline.py raises a clear
# RuntimeError rather than quietly running a degraded fallback stage — the
# point of opting in is better coverage, so a no-key opt-in is treated as a
# misconfiguration to surface, not silently accepted. (DuckDuckGo needs no
# key, so setting just GEMINI_API_KEY or just TAVILY_API_KEY is enough to
# pass this check; each stage still degrades further within itself per the
# original README's graceful-degradation notes.)
# --------------------------------------------------------------------------- #
ENABLE_WEB_FALLBACK = os.getenv("ENABLE_WEB_FALLBACK", "0") == "1"


# --------------------------------------------------------------------------- #
# Output locations
# --------------------------------------------------------------------------- #

BASE_OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "downloads"))

REQUEST_TIMEOUT = 30          # seconds, for plain requests.get/post calls
INTER_REQUEST_DELAY = 0.6     # seconds, politeness delay between HTTP hits
MAX_DOWNLOAD_BYTES = 60 * 1024 * 1024   # refuse to save anything above 60 MB


# --------------------------------------------------------------------------- #
# How many of each document type to collect, and how far back to search.
# All of these can be overridden from the CLI (see main.py).
# --------------------------------------------------------------------------- #

@dataclass
class FetchTargets:
    annual_reports: int = 5
    quarterly_results: int = 8
    half_yearly_results: int = 4
    earnings_transcripts: int = 4
    investor_presentations: int = 4
    special_disclosures: int = 8

    # How many years back to pull BSE announcements for. 5 annual reports +
    # 8 quarters (~2 years) with slack for companies that report late.
    lookback_years: int = 6


DEFAULT_TARGETS = FetchTargets()


# --------------------------------------------------------------------------- #
# BSE announcement categories worth querying for this use case.
# (bse.constants.CATEGORY has more: AGM/EGM, Board Meeting, Corp. Action,
# Insider Trading/SAST, New Listing, Others - we only need these three.)
# --------------------------------------------------------------------------- #

BSE_CATEGORIES_TO_SCAN = ["RESULT", "UPDATE", "AGM"]


# --------------------------------------------------------------------------- #
# Keyword heuristics used to pre-classify a BSE/Screener announcement title
# before the LLM confirms it. These also act as the *only* classifier when
# DISABLE_LLM is set, so keep them reasonably strict.
#
# Matching is case-insensitive substring/regex matching against the
# announcement's subject line (NEWSSUB / HEADLINE / SUBCATNAME on BSE,
# link text on Screener).
# --------------------------------------------------------------------------- #

KEYWORDS = {
    "annual_report": [
        r"annual report",
        r"integrated report",
        r"business responsibility.*sustainability report",
    ],
    "quarterly_result": [
        r"un-?audited.*financial results?",
        r"financial results?.*quarter ended",
        r"results? for the quarter",
    ],
    "half_yearly_result": [
        r"half.?yearly",
        r"results? for the half year",
        r"six months ended",
    ],
    "earnings_transcript": [
        r"transcript",
        r"earnings call",
        r"analyst.*call",
        r"con\s?call",
    ],
    "investor_presentation": [
        r"investor presentation",
        r"analyst presentation",
        r"earnings presentation",
        r"\bppt\b",
    ],
    # Used only to *exclude* obvious noise from the "Result" category, e.g.
    # newspaper-publication filings that mention "financial results" in
    # passing but aren't the actual results document.
    "noise": [
        r"newspaper publication",
        r"advertisement",
        r"intimation of board meeting",
        r"trading window",
    ],
}

# Rough signal that an item is worth surfacing in the "special disclosures"
# bucket (credit rating actions, M&A, related-party stuff, resignations...).
# This list is intentionally broad; the LLM does the real filtering for
# materiality when it's available.
SPECIAL_DISCLOSURE_HINTS = [
    r"credit rating",
    r"rating (upgrade|downgrade|reaffirm)",
    r"acquisition",
    r"merger|demerger|scheme of arrangement",
    r"resignation of (director|cfo|ceo|company secretary)",
    r"related party transaction",
    r"preferential issue|qip|rights issue|open offer",
    r"regulatory action|show cause|penalty",
]
