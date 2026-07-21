"""Tier-2 LLM qualitative conviction scoring for shortlisted result-declarers.

The mechanical pipeline (`analyze_symbol` → ``is_strong`` growth thresholds +
debt gate) is a cheap, high-recall pre-filter: it answers *"did this company post
a strong-looking quarter on a clean balance sheet?"*. But the raw screener numbers
are largely priced-in, so they separate eventual winners from losers only weakly.

This module adds the judgement a skilled manual trader applies on top of the
numbers: read the *actual filing* (results PDF / investor presentation / concall),
gauge order-book / revenue-visibility, check whether the beat is operational or a
one-off, and scan for recent bad news in the stock or sector. It reuses the
existing Copilot-CLI runner (web grounding + scraper MCP), so the LLM can fetch
point-in-time evidence itself.

The output is a structured :class:`ConvictionVerdict` (conviction 0-1 + a buy/
watch/skip call + the qualitative reasons). The engine uses it to *gate*, *rank*
and *shape the exit plan* of the already-mechanically-qualified shortlist — it can
only remove or size picks, never add un-vetted names. Every failure path degrades
to a neutral verdict so a run is never broken by the qualitative step.

The core :func:`evaluate_conviction` takes an injectable ``verdict_fn`` so a
point-in-time-safe evidence provider can be substituted for backtesting later; by
default it calls the live LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from qtr_results import config
from qtr_results.copilot_runner import run_copilot
from qtr_results.util import extract_json_block

logger = logging.getLogger("qtr_results.conviction")

VerdictFn = Callable[[str], str]  # prompt -> raw LLM output


@dataclass
class ConvictionVerdict:
    """Structured qualitative read of one shortlisted candidate."""

    conviction: Optional[float] = None  # 0-1; None => neutral / unavailable
    verdict: str = "watch"              # "buy" | "watch" | "skip"
    order_book: str = ""
    guidance: str = ""
    one_off_flags: List[str] = field(default_factory=list)
    positives: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    summary: str = ""
    sources: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def passes_gate(self) -> bool:
        """Whether this candidate survives the conviction gate.

        A neutral verdict (no LLM score, e.g. the layer is disabled or the call
        failed) always passes so the pipeline falls back to mechanical-only
        behaviour. When a score IS present it must clear MIN_CONVICTION and not be
        an explicit "skip".
        """
        if self.verdict == "skip":
            return False
        if self.conviction is None:
            return True
        return self.conviction >= config.MIN_CONVICTION

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _build_conviction_prompt(candidate: Dict[str, Any], analysis: Any, as_of: date) -> str:
    """Point-in-time qualitative-scoring prompt for a single candidate."""
    sym = candidate.get("symbol", "")
    company = candidate.get("company") or getattr(analysis, "company_name", "") or sym
    result_date = candidate.get("result_date") or as_of.isoformat()
    quarter = getattr(analysis, "latest_quarter", "") or "the latest quarter"

    # The mechanical numbers we already computed — give the LLM the same figures a
    # trader would read off the result, so it can judge quality, not re-derive them.
    def _pct(v: Optional[float]) -> str:
        return f"{v:+.1f}%" if isinstance(v, (int, float)) else "n/a"

    metrics = (
        f"- Net profit YoY: {_pct(getattr(analysis, 'yoy_profit_growth', None))}\n"
        f"- Net profit QoQ: {_pct(getattr(analysis, 'qoq_profit_growth', None))}\n"
        f"- Sales YoY: {_pct(getattr(analysis, 'yoy_sales_growth', None))}\n"
        f"- EPS YoY: {_pct(getattr(analysis, 'yoy_eps_growth', None))}\n"
        f"- OPM change YoY: "
        f"{getattr(analysis, 'margin_delta_pp', None):+.1f}pp"
        if isinstance(getattr(analysis, "margin_delta_pp", None), (int, float))
        else "- OPM change YoY: n/a"
    )
    de = getattr(analysis, "debt_to_equity", None)
    de_line = f"- Debt/Equity: {de:.2f}\n" if isinstance(de, (int, float)) else ""

    return f"""You are a seasoned Indian-equities (NSE) analyst judging whether a
quarterly-results momentum trade is high-conviction. A cheap mechanical screen has
ALREADY confirmed {company} ({sym}) posted a strong-looking {quarter} result on a
clean balance sheet. Your job is the qualitative judgement the numbers alone miss.

# As-of date
{result_date} (evaluate using only information available on/before this date; do
NOT use hindsight about how the stock subsequently moved).

# Mechanical figures already verified
{metrics}
{de_line}
# What to investigate (use web search + the scraper tools)
1. THE ACTUAL FILING — find {sym}'s {quarter} results PDF, investor presentation
   and/or earnings-call (concall) transcript (NSE/BSE announcements, the company's
   investor-relations page, Screener, Trendlyne). Read management's commentary.
2. ORDER BOOK / REVENUE VISIBILITY — order-book size, book-to-bill, order inflows,
   capacity additions, guidance for coming quarters. Strong, growing visibility is
   the single biggest edge for this strategy.
3. EARNINGS QUALITY — is the profit growth OPERATIONAL, or flattered by other
   income, a low/one-off tax rate, exceptional items or a one-time gain? Flag any
   such one-offs.
4. RED FLAGS — recent negative news on the company (auditor/governance concerns,
   promoter pledging, large insider selling, litigation) OR on its SECTOR
   (regulatory headwinds, demand slowdown, commodity/margin pressure).
5. SECTOR / DEMAND BACKDROP — is the sector in an up-cycle or under pressure right
   now?

# Scoring
Weigh the above into a single conviction score in [0,1]:
- 0.75-1.0  strong order book / clear guidance / clean operational beat / no red flags
- 0.45-0.75 decent but mixed (some caveats)
- < 0.45    weak visibility, one-off-driven beat, or material red flags
Set "verdict" to "buy" (conviction >= 0.6), "watch" (0.45-0.6) or "skip" (< 0.45
or a serious red flag regardless of the beat).

# Output format
Respond with a brief Markdown summary, then EXACTLY one ```json``` block of this
shape (valid JSON, no extra keys):

```json
{{"conviction": 0.0, "verdict": "buy|watch|skip", "order_book": "one line",
"guidance": "one line", "one_off_flags": ["..."], "positives": ["..."],
"risks": ["..."], "summary": "one-sentence thesis"}}
```
"""


def _parse_verdict(output: str) -> ConvictionVerdict:
    parsed = extract_json_block(output) or {}
    if not isinstance(parsed, dict):
        return ConvictionVerdict(error="unparseable LLM output")

    conviction: Optional[float]
    try:
        raw = parsed.get("conviction")
        conviction = float(raw) if raw is not None else None
        if conviction is not None:
            conviction = max(0.0, min(1.0, conviction))
    except (TypeError, ValueError):
        conviction = None

    verdict = str(parsed.get("verdict", "watch")).strip().lower()
    if verdict not in ("buy", "watch", "skip"):
        verdict = "watch"

    def _as_list(key: str) -> List[str]:
        val = parsed.get(key)
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    return ConvictionVerdict(
        conviction=conviction,
        verdict=verdict,
        order_book=str(parsed.get("order_book", "")).strip(),
        guidance=str(parsed.get("guidance", "")).strip(),
        one_off_flags=_as_list("one_off_flags"),
        positives=_as_list("positives"),
        risks=_as_list("risks"),
        summary=str(parsed.get("summary", "")).strip(),
    )


def evaluate_conviction(
    candidate: Dict[str, Any],
    analysis: Any,
    *,
    as_of: Optional[date] = None,
    model: Optional[str] = None,
    verdict_fn: Optional[VerdictFn] = None,
) -> ConvictionVerdict:
    """Score one shortlisted candidate's qualitative conviction.

    ``verdict_fn`` maps a prompt to raw LLM output; it defaults to the live
    Copilot-CLI runner (web grounding + scraper MCP). A point-in-time-safe
    provider can be injected for backtesting. Any failure returns a neutral
    verdict (``conviction=None``) which passes the gate and leaves the exit plan
    at its default band, so the run degrades to mechanical-only behaviour.
    """
    as_of = as_of or date.today()
    sym = candidate.get("symbol", "?")
    prompt = _build_conviction_prompt(candidate, analysis, as_of)

    fn = verdict_fn or (
        lambda p: run_copilot(
            p, web_grounding=True, scraper_tools=True, model=model or config.CONVICTION_MODEL
        )
    )
    try:
        output = fn(prompt)
    except Exception as e:  # noqa: BLE001 - never let the qualitative step break a run
        logger.warning("Conviction LLM run failed for %s (%s); neutral verdict.", sym, e)
        return ConvictionVerdict(error=str(e))

    verdict = _parse_verdict(output)
    logger.info(
        "Conviction %s: score=%s verdict=%s (%s)",
        sym,
        f"{verdict.conviction:.2f}" if verdict.conviction is not None else "n/a",
        verdict.verdict,
        verdict.summary[:80],
    )
    return verdict
