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
from typing import Any, Callable, Dict, List, Optional, Tuple

from qtr_results import config
from qtr_results.copilot_runner import run_copilot
from qtr_results.util import extract_json_block

logger = logging.getLogger("qtr_results.conviction")

VerdictFn = Callable[[str], str]  # prompt -> raw LLM output

#: Bump on any change to the question asked. Verdicts are only comparable to
#: other verdicts produced by the same prompt, so the version is journalled with
#: every row; without it the history silently mixes incompatible samples.
PROMPT_VERSION = "2026-09-v2-evidence"

# ── Closed vocabularies ──────────────────────────────────────────────────────
# The model reports OBSERVATIONS from a fixed set; it never reports a score.
# See `_derive_conviction` for why.

BEAT_QUALITY = ("operational", "mixed", "one_off", "unknown")
ORDER_BOOK = ("strong", "adequate", "weak", "not_applicable", "unknown")
GUIDANCE = ("raised", "maintained", "lowered", "none_given", "unknown")
SECTOR_BACKDROP = ("tailwind", "neutral", "headwind", "unknown")

#: Flags severe enough to veto on their own, regardless of how good the quarter
#: looked. These are solvency- and integrity-level problems, where the reported
#: numbers themselves stop being trustworthy.
SEVERE_RED_FLAGS = frozenset({
    "auditor_concern", "governance_concern", "regulatory_action", "debt_stress",
})

RED_FLAGS = frozenset({
    "auditor_concern", "governance_concern", "regulatory_action", "debt_stress",
    "promoter_pledge_high", "insider_selling", "material_litigation",
    "receivables_stress", "customer_concentration", "demand_slowdown",
    "margin_pressure",
})

#: Evidence -> score contributions, applied to a neutral 0.50 base.
#:
#: These weights are a JUDGEMENT CALL and are not yet validated against
#: outcomes -- there is not enough matured live history to fit them (the layer
#: had made 48 evaluations, 9 rejections, none older than ~30 days against a
#: 90-day horizon). They are deliberately modest so the gate stays close to
#: "veto the clearly bad" rather than pretending to rank precisely.
#:
#: Because `verdict_log` stores the COMPONENTS and not just the resulting score,
#: these weights can be re-fitted from the accumulated record later without
#: re-running a single LLM call.
_W_BEAT = {"operational": 0.18, "mixed": -0.02, "one_off": -0.28, "unknown": 0.0}
_W_BOOK = {"strong": 0.14, "adequate": 0.04, "weak": -0.14,
           "not_applicable": 0.0, "unknown": 0.0}
_W_GUIDANCE = {"raised": 0.10, "maintained": 0.02, "lowered": -0.16,
               "none_given": 0.0, "unknown": 0.0}
_W_SECTOR = {"tailwind": 0.07, "neutral": 0.0, "headwind": -0.12, "unknown": 0.0}

_PENALTY_PER_FLAG = 0.10
_MAX_FLAG_PENALTY = 0.25
_NEUTRAL_BASE = 0.50
_BUY_THRESHOLD = 0.60


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
    #: The categorical evidence the score was derived from. Journalled so the
    #: weights above can be re-fitted from history later.
    components: Dict[str, Any] = field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION

    @property
    def passes_gate(self) -> bool:
        """Whether this candidate survives the conviction gate.

        A neutral verdict (no score, e.g. the layer is disabled or the call
        failed) always passes so the pipeline falls back to mechanical-only
        behaviour. When a score IS present it must clear MIN_CONVICTION and not
        be an explicit "skip".
        """
        if self.verdict == "skip":
            return False
        if self.conviction is None:
            return True
        return self.conviction >= config.MIN_CONVICTION

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _derive_conviction(
    components: Dict[str, Any]
) -> Tuple[Optional[float], str, List[str]]:
    """Turn categorical evidence into a score, a verdict and the reasons.

    The score is computed HERE, not by the model, because a model told where the
    cut-offs are will park its answer just inside whichever bucket it wants. The
    live record showed exactly that: with the old prompt naming 0.75 / 0.6 /
    0.45, every accepted name scored 0.66-0.68 and every rejected one 0.38-0.43.
    A number that only ever takes two values carries no more information than
    the word next to it, yet it was being multiplied into the ranking key and
    (until this change) into the holding window.

    Asking only for observations from a closed vocabulary removes the anchor:
    there is no numeric target to drift toward, and the same evidence always
    produces the same score.

    Returns ``(score, verdict, reasons)``; score is ``None`` when the model
    supplied no usable evidence at all, which the caller treats as neutral.
    """
    beat = components.get("beat_quality")
    book = components.get("order_book")
    guide = components.get("guidance")
    sector = components.get("sector_backdrop")
    flags = [f for f in (components.get("red_flags") or []) if f in RED_FLAGS]

    known = [v for v in (beat, book, guide, sector)
             if v not in (None, "", "unknown")]
    if not known and not flags:
        return None, "watch", ["no usable evidence returned"]

    reasons: List[str] = []
    severe = sorted(set(flags) & SEVERE_RED_FLAGS)
    if severe:
        return 0.0, "skip", [f"severe red flag: {f}" for f in severe]

    score = _NEUTRAL_BASE
    for label, value, table in (
        ("beat", beat, _W_BEAT), ("order book", book, _W_BOOK),
        ("guidance", guide, _W_GUIDANCE), ("sector", sector, _W_SECTOR),
    ):
        delta = table.get(value or "unknown", 0.0)
        score += delta
        if delta:
            reasons.append(f"{label} {value} {delta:+.2f}")

    if flags:
        penalty = min(len(flags) * _PENALTY_PER_FLAG, _MAX_FLAG_PENALTY)
        score -= penalty
        reasons.append(f"{len(flags)} red flag(s) -{penalty:.2f}")

    score = round(max(0.0, min(1.0, score)), 3)
    if score < config.MIN_CONVICTION:
        verdict = "skip"
    elif score >= _BUY_THRESHOLD:
        verdict = "buy"
    else:
        verdict = "watch"
    return score, verdict, reasons


def _build_conviction_prompt(candidate: Dict[str, Any], analysis: Any, as_of: date) -> str:
    """Point-in-time qualitative-evidence prompt for a single candidate."""
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

    return f"""You are a seasoned Indian-equities (NSE) analyst gathering evidence on
whether a quarterly-results momentum trade is likely to FAIL. A cheap mechanical
screen has ALREADY confirmed {company} ({sym}) posted a strong-looking {quarter}
result on a clean balance sheet. Those headline numbers are largely priced in, so
re-reading them adds nothing. Your job is to find the things the numbers hide.

Bias your effort toward DISCONFIRMING evidence. The screen is high-recall and
most of its losers look excellent on the figures above; the edge is in spotting
which strong-looking quarter is not what it appears to be.

# As-of date
{result_date} (use only information available on/before this date; do NOT use
hindsight about how the stock subsequently moved).

# Mechanical figures already verified
{metrics}
{de_line}
# Evidence to gather (use web search + the scraper tools; cite what you used)
1. THE ACTUAL FILING — find {sym}'s {quarter} results PDF, investor presentation
   and/or earnings-call transcript (NSE/BSE announcements, the company's
   investor-relations page, Screener, Trendlyne). Read management's commentary.
2. EARNINGS QUALITY — is the profit growth OPERATIONAL, or flattered by other
   income, a low or one-off tax rate, an exceptional item, a forex gain or an
   asset sale? Compare EBITDA growth against net-profit growth: when net profit
   sprints ahead of EBITDA, the beat is usually below the operating line.
3. ORDER BOOK / REVENUE VISIBILITY — order-book size, book-to-bill, inflows,
   capacity additions. Report "not_applicable" for business models that do not
   carry an order book (most banks, NBFCs, FMCG, retail) — absence of an order
   book is NOT weakness, and scoring it as weakness would penalise whole sectors
   for their business model.
4. GUIDANCE — did management raise, maintain or lower guidance, or give none?
5. RED FLAGS — auditor or governance concerns, promoter pledging, insider
   selling, litigation, regulatory action, debt or receivables stress, customer
   concentration, sector demand slowdown, margin pressure.
6. SECTOR BACKDROP — is the sector in an up-cycle or under pressure right now?

# Reporting rules
- Report only what you can SUPPORT from a source you actually consulted.
- Use "unknown" when you could not establish something. "unknown" is a valid,
  cost-free answer and is strongly preferred over a guess: a fabricated
  observation is worse than a missing one, because it is scored as if it were
  evidence.
- Do NOT output any conviction score, rating or probability. Report observations
  only; the score is computed from them downstream.

# Output format
Respond with a brief Markdown summary of what you found and where, then EXACTLY
one ```json``` block of this shape (valid JSON, no extra keys):

```json
{{"beat_quality": "operational|mixed|one_off|unknown",
"order_book": "strong|adequate|weak|not_applicable|unknown",
"guidance": "raised|maintained|lowered|none_given|unknown",
"sector_backdrop": "tailwind|neutral|headwind|unknown",
"red_flags": ["auditor_concern|governance_concern|regulatory_action|debt_stress|promoter_pledge_high|insider_selling|material_litigation|receivables_stress|customer_concentration|demand_slowdown|margin_pressure"],
"one_off_items": ["specific one-off that flattered the quarter, if any"],
"positives": ["..."], "risks": ["..."],
"sources": ["url or document actually consulted"],
"summary": "one-sentence thesis"}}
```
"""


def _choice(parsed: Dict[str, Any], key: str, allowed: Tuple[str, ...]) -> str:
    value = str(parsed.get(key, "")).strip().lower().replace("-", "_")
    return value if value in allowed else "unknown"


def _parse_verdict(output: str) -> ConvictionVerdict:
    parsed = extract_json_block(output) or {}
    if not isinstance(parsed, dict):
        return ConvictionVerdict(error="unparseable LLM output")

    def _as_list(key: str) -> List[str]:
        val = parsed.get(key)
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    raw_flags = [f.strip().lower().replace("-", "_") for f in _as_list("red_flags")]
    flags = [f for f in raw_flags if f in RED_FLAGS]
    dropped = sorted(set(raw_flags) - RED_FLAGS - {"none", ""})
    if dropped:
        logger.debug("Ignoring out-of-vocabulary red flags: %s", dropped)

    components: Dict[str, Any] = {
        "beat_quality": _choice(parsed, "beat_quality", BEAT_QUALITY),
        "order_book": _choice(parsed, "order_book", ORDER_BOOK),
        "guidance": _choice(parsed, "guidance", GUIDANCE),
        "sector_backdrop": _choice(parsed, "sector_backdrop", SECTOR_BACKDROP),
        "red_flags": flags,
    }
    conviction, verdict, reasons = _derive_conviction(components)
    components["score_reasons"] = reasons

    return ConvictionVerdict(
        conviction=conviction,
        verdict=verdict,
        order_book=components["order_book"],
        guidance=components["guidance"],
        one_off_flags=_as_list("one_off_items"),
        positives=_as_list("positives"),
        risks=_as_list("risks"),
        summary=str(parsed.get("summary", "")).strip(),
        sources=_as_list("sources"),
        components=components,
    )


def evaluate_conviction(
    candidate: Dict[str, Any],
    analysis: Any,
    *,
    as_of: Optional[date] = None,
    model: Optional[str] = None,
    verdict_fn: Optional[VerdictFn] = None,
    journal: bool = True,
) -> ConvictionVerdict:
    """Score one shortlisted candidate's qualitative conviction.

    ``verdict_fn`` maps a prompt to raw LLM output; it defaults to the live
    Copilot-CLI runner (web grounding + scraper MCP). A point-in-time-safe
    provider can be injected for backtesting. Any failure returns a neutral
    verdict (``conviction=None``) which passes the gate, so the run degrades to
    mechanical-only behaviour.

    Every evaluation is journalled to :mod:`qtr_results.verdict_log` (including
    failures) so the gate can actually be evaluated later; set ``journal=False``
    in tests or dry runs.
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
        verdict = ConvictionVerdict(error=str(e))
    else:
        verdict = _parse_verdict(output)
        logger.info(
            "Conviction %s: score=%s verdict=%s (%s)",
            sym,
            f"{verdict.conviction:.2f}" if verdict.conviction is not None else "n/a",
            verdict.verdict,
            verdict.summary[:80],
        )

    if journal:
        from qtr_results import verdict_log

        verdict_log.record_verdict(
            verdict,
            symbol=str(sym),
            decision_date=as_of,
            prompt_version=PROMPT_VERSION,
            company=str(candidate.get("company") or ""),
            quarter=str(getattr(analysis, "latest_quarter", "") or ""),
            result_date=str(candidate.get("result_date") or ""),
        )
    return verdict

