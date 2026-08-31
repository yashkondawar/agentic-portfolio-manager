"""
Shared data structures passed between modules.

Plain dataclasses are used for internal domain objects. Pydantic models
(used only for talking to Gemini's structured-output mode) live in
llm_agent.py, not here, to keep this module dependency-light.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


class DocType(str, Enum):
    ANNUAL_REPORT = "annual_report"
    QUARTERLY_RESULT = "quarterly_result"
    HALF_YEARLY_RESULT = "half_yearly_result"
    EARNINGS_TRANSCRIPT = "earnings_transcript"
    INVESTOR_PRESENTATION = "investor_presentation"
    SPECIAL_DISCLOSURE = "special_disclosure"


@dataclass
class Company:
    """Everything we know about the company after resolution."""

    query: str                              # what the user typed
    name: str = ""                          # canonical name, once resolved
    bse_scrip_code: Optional[str] = None
    nse_symbol: Optional[str] = None
    isin: Optional[str] = None
    screener_slug: Optional[str] = None     # e.g. "TCS" for /company/TCS/
    screener_url: Optional[str] = None
    website: Optional[str] = None

    @property
    def slug(self) -> str:
        """Filesystem-safe folder name for this company."""
        base = self.name or self.query
        keep = "".join(c if c.isalnum() or c in " -_" else "" for c in base)
        return keep.strip().replace(" ", "_")[:60] or "company"

    def is_resolved(self) -> bool:
        return bool(self.bse_scrip_code or self.screener_slug)


@dataclass
class DocumentCandidate:
    """A document we've found and might download."""

    doc_type: DocType
    company: str
    period_label: str                # human label, e.g. "Q2 FY25", "FY2024"
    period_sort_key: str             # sortable key, e.g. "2024-Q2", "2024-FY"
    title: str
    url: str
    source: str                      # "BSE" | "Screener" | "WebSearch"
    announced_on: Optional[date] = None
    heuristic_confidence: float = 0.0     # 0-1, from keyword/date matching
    llm_confidence: Optional[float] = None  # 0-1, filled in after LLM review
    llm_reasoning: str = ""
    accepted: bool = False           # final go/no-go after all checks
    local_path: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def final_confidence(self) -> float:
        return self.llm_confidence if self.llm_confidence is not None else self.heuristic_confidence

    def dedupe_key(self) -> tuple[str, str]:
        return (self.doc_type.value, self.period_sort_key)


@dataclass
class PipelineResult:
    company: Company
    candidates: list[DocumentCandidate] = field(default_factory=list)
    downloaded: list[DocumentCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest_path: Optional[str] = None

    def counts_by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.downloaded:
            out[c.doc_type.value] = out.get(c.doc_type.value, 0) + 1
        return out
