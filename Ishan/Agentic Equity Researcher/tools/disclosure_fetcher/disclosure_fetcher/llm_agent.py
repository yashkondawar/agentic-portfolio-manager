"""
Gemini integration: the two jobs the user asked an LLM to do.

  1. Query generation - given "we're missing the Q2 FY25 investor
     presentation for Persistent Systems", write 2-4 good, targeted web
     search queries.
  2. Candidate validation - given a batch of things we *found* (from BSE,
     Screener, or a web search), confirm each one's doc type and period,
     score confidence, and give a one-line reason - the "go/no-go" gate
     before anything gets downloaded.

Uses the current (2026) `google-genai` SDK with Pydantic structured output
so responses come back as typed objects, not hand-parsed JSON strings.
Everything here degrades gracefully: if no GEMINI_API_KEY is set, a call
fails, or the free-tier quota is exhausted for the day, callers fall back
to template queries / the pre-existing keyword-based heuristic confidence
instead of crashing the run.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from disclosure_fetcher.config import DISABLE_LLM, GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

BATCH_SIZE = 20  # items per classification call - keeps prompts + free-tier RPM manageable


# --------------------------------------------------------------------------- #
# Structured output schemas
# --------------------------------------------------------------------------- #

class GeneratedQueries(BaseModel):
    queries: list[str] = Field(description="2 to 4 short, targeted web search query strings")


class ItemClassification(BaseModel):
    index: int = Field(description="the index of the item being classified, copied from the input")
    is_relevant: bool = Field(description="true only if this really is the requested document type and period")
    doc_type: str = Field(description="one of: annual_report, quarterly_result, half_yearly_result, "
                                       "earnings_transcript, investor_presentation, special_disclosure, irrelevant")
    period_label: str = Field(description='normalized period label, e.g. "Q2 FY25", "FY2024", "H1 FY25"')
    confidence: float = Field(description="0.0 to 1.0")
    reasoning: str = Field(description="one short sentence explaining the call")


class ClassificationBatch(BaseModel):
    results: list[ItemClassification]


class ExtractedIdentifier(BaseModel):
    bse_scrip_code: str = Field(description="6-digit BSE scrip code if mentioned anywhere, else empty string")
    nse_symbol: str = Field(description="NSE trading symbol if mentioned anywhere, else empty string")
    confidence: float = Field(description="0.0 to 1.0, how sure you are this identifies the right company")


def _retryable(exc: BaseException) -> bool:
    # Retry on Gemini API errors (covers 429 rate limits and 5xx) but not on
    # our own programming errors.
    try:
        from google.genai.errors import APIError
        return isinstance(exc, APIError)
    except ImportError:
        return False


class LLMAgent:
    def __init__(self, api_key: str = GEMINI_API_KEY, model: str = GEMINI_MODEL, disabled: bool = DISABLE_LLM):
        self.model = model
        self.client = None
        self.disabled = disabled or not api_key

        if not self.disabled:
            try:
                from google import genai

                self.client = genai.Client(api_key=api_key)
            except Exception as exc:
                logger.warning("Could not initialise Gemini client - continuing without LLM: %s", exc)
                self.disabled = True

    @property
    def available(self) -> bool:
        return not self.disabled and self.client is not None

    # ------------------------------------------------------------------ #
    # Query generation
    # ------------------------------------------------------------------ #

    def generate_search_queries(
        self, company_name: str, doc_type: str, period_label: str, hint: str = ""
    ) -> list[str]:
        fallback = self._fallback_queries(company_name, doc_type, period_label)
        if not self.available:
            return fallback

        prompt = (
            f"I need to find a specific corporate disclosure document for an Indian "
            f"listed company, to download its PDF.\n"
            f"Company: {company_name}\n"
            f"Document type: {doc_type}\n"
            f"Period: {period_label}\n"
            + (f"Extra context: {hint}\n" if hint else "")
            + "\nWrite 2 to 4 short web search engine queries (not full sentences) "
            "most likely to surface the actual PDF or its official listing page. "
            "Prefer queries that include the exact company name in quotes, the "
            "period, and either 'filetype:pdf' or a likely official domain "
            "(bseindia.com, nseindia.com, or the company's own investor-relations "
            "pages). Do not explain your choices, just return the queries."
        )
        try:
            result = self._generate(prompt, GeneratedQueries)
            queries = [q for q in (result.queries if result else []) if q.strip()]
            return queries or fallback
        except Exception as exc:
            logger.warning("Gemini query generation failed, using template queries: %s", exc)
            return fallback

    @staticmethod
    def _fallback_queries(company_name: str, doc_type: str, period_label: str) -> list[str]:
        doc_phrase = doc_type.replace("_", " ")
        return [
            f'"{company_name}" {doc_phrase} {period_label} filetype:pdf',
            f'"{company_name}" {doc_phrase} {period_label} site:bseindia.com',
            f'"{company_name}" investor relations {doc_phrase} {period_label}',
        ]

    # ------------------------------------------------------------------ #
    # Candidate / result validation (batched)
    # ------------------------------------------------------------------ #

    def classify_items(self, company_name: str, items: list[dict]) -> dict[int, ItemClassification]:
        """items: list of {index, title, source, doc_type_guess, period_label_guess, context}

        Returns a dict keyed by `index` (only for items the model actually
        responded on - callers should treat missing indices as "LLM had no
        opinion" and fall back to the pre-existing heuristic score).
        """
        if not items:
            return {}
        if not self.available:
            return {}

        out: dict[int, ItemClassification] = {}
        for start in range(0, len(items), BATCH_SIZE):
            batch = items[start : start + BATCH_SIZE]
            try:
                out.update(self._classify_batch(company_name, batch))
            except Exception as exc:
                logger.warning("Gemini classification batch failed (items %s): %s", [i["index"] for i in batch], exc)
            time.sleep(0.2)  # small courtesy gap between batches
        return out

    def _classify_batch(self, company_name: str, batch: list[dict]) -> dict[int, ItemClassification]:
        lines = []
        for item in batch:
            lines.append(
                f"- index={item['index']} | guessed_type={item.get('doc_type_guess','?')} | "
                f"guessed_period={item.get('period_label_guess','?')} | source={item.get('source','?')} | "
                f"title=\"{item.get('title','')[:200]}\""
                + (f" | extra=\"{item['context'][:300]}\"" if item.get("context") else "")
            )
        prompt = (
            f"Company: {company_name}\n\n"
            "Below is a list of candidate corporate disclosure documents found while "
            "searching BSE, Screener.in, and the open web. For EACH item, confirm "
            "whether it genuinely is the guessed document type and reporting period, "
            "or correct it if the title suggests otherwise (e.g. a 'guessed_type' of "
            "quarterly_result whose title actually says 'Newspaper Publication' or "
            "'Board Meeting Intimation' is NOT a real result document and should be "
            "marked is_relevant=false). Normalize period_label to a clean form like "
            "'Q2 FY25', 'FY2024', or 'H1 FY25'. Give a confidence from 0 to 1 and one "
            "short reason.\n\nItems:\n" + "\n".join(lines)
        )
        result = self._generate(prompt, ClassificationBatch)
        if result is None:
            return {}
        return {r.index: r for r in result.results}

    def extract_company_identifier(self, company_query: str, snippets: list[str]) -> Optional[ExtractedIdentifier]:
        """Last-resort helper for company resolution: read a handful of web
        search snippets and pull out a BSE scrip code / NSE symbol.

        IMPORTANT: callers must treat the result as a *proposal only* and
        re-verify it against BSE's own lookup() before trusting it - never
        wire this straight into a download path. Getting a scrip code
        wrong here means silently fetching the wrong company's filings.
        """
        if not self.available or not snippets:
            return None
        prompt = (
            f'I am trying to identify the BSE scrip code or NSE symbol for the '
            f'Indian listed company "{company_query}". Here are some web search '
            f"results:\n\n" + "\n---\n".join(snippets[:6]) + "\n\n"
            "If any of these clearly identify the right company's BSE scrip code "
            "(a numeric code, commonly 6 digits) or NSE symbol, extract it. If "
            "nothing here is clearly about this specific company, return empty "
            "strings and low confidence rather than guessing."
        )
        try:
            return self._generate(prompt, ExtractedIdentifier)
        except Exception as exc:
            logger.warning("Gemini identifier extraction failed: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Low-level call with retry
    # ------------------------------------------------------------------ #

    @retry(
        retry=retry_if_exception(_retryable),
        stop=stop_after_attempt(4),
        wait=wait_random_exponential(multiplier=1, max=30),
        reraise=True,
    )
    def _generate(self, prompt: str, schema: type[BaseModel]) -> Optional[BaseModel]:
        from google.genai import types

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.1,
            ),
        )
        return response.parsed
