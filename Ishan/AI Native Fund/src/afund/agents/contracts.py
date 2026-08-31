"""Pydantic v2 output contracts for every agent role.

These models are the AUTHORITATIVE contract — where a `.claude/agents/<role>.md`
I/O section is looser or drifted from what's defined here, the .md was
tightened to match (not the other way around). `validate_output()` is the
single entry point the orchestrator's ingestion path uses to turn an agent's
raw JSON reply into a validated model instance, or raise a clear
ContractViolation.

Nothing here calls an LLM or touches the database — pure parsing/validation.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ContractViolation(ValueError):
    """Raised by validate_output() when a payload fails contract validation
    (either malformed JSON or a pydantic ValidationError). Carries a
    human-readable summary in str(exc)."""


# ---------------------------------------------------------------------------
# facts vs interpretation (shared — used by synthesis, critique,
# sector_researcher and buy_side)
# ---------------------------------------------------------------------------
#
# A fact is a published quantity or a disclosed mechanism: checkable, and the
# same for everyone. A reading is `fact + conditioning variable + sector
# convention -> verdict`, and two readings of one fact are BOTH legitimate when
# each names its conditioner. "P/E 30 is expensive" against a 10-year median of
# 18 and "P/E 30 is cheap" at a PEG of 1.0 are arithmetic on identical
# disclosed numbers; what separates them is which variable is doing the work
# and what evidence settles it.
#
# The vocabulary below is closed and governed:
#   registry/rules/interpretation_frames.yaml   (fund, governed tier)
#   research/equity_researcher/config/sector_registry.yaml
#                                              -> interpretation_vocabulary
# `scripts/check_interpretation_frames.py --check` asserts the ER tokens stay a
# subset of the fund rule. Prose: knowledge/references/methodology/
# facts_vs_interpretation.md; corpus evidence: the ER subsystem's
# docs/OPINION_VS_ANALYSIS.md section 7.
#
# Literals rather than a free string because the whole point is that a reading
# must name a variable from a list someone can argue with. A model that accepts
# any string accepts "because the story is good", which is the failure mode.

ConditioningVariable = Literal[
    "growth_rate",
    "growth_durability",
    "incremental_roce",
    "sustainable_roe",
    "cycle_position",
    "earnings_base_quality",
    "capital_intensity",
    "terminal_value_share",
    "balance_sheet_risk",
    "accounting_basis",
    "own_history_anchor",
    "peer_set_choice",
]

# What may settle a divergence. Exactly four types, plus a sentinel for "we
# looked and there is nothing". Tone, consensus, "the market is wrong" and
# analyst conviction are deliberately absent — they are the things that feel
# like evidence and are not.
DiscriminatorType = Literal[
    "historical_distribution",
    "peer_distribution",
    "disclosed_mechanism",
    "forward_observable",
    "none_available",
]


class FactClaim(BaseModel):
    """A checkable quantity or disclosed mechanism. No adjective belongs here —
    if a reader could disagree with it, it is a Reading, not a FactClaim."""
    claim: str = Field(min_length=1)
    source: str = Field(min_length=1)
    as_of: str | None = None


class Reading(BaseModel):
    """One defensible interpretation of a fact. `conditioning_variable` is what
    makes it defensible; a verdict that names none is an unearned adjective."""
    verdict: str = Field(min_length=1)
    conditioning_variable: ConditioningVariable
    reasoning: str = Field(min_length=1)
    who_holds_it: str | None = None


class DivergenceCase(BaseModel):
    """One fact, at least two defensible readings, and what settles them.

    `resolved=False` is a legitimate, and often the honest, outcome — it is not
    a failure to be papered over. An unresolved divergence becomes a disclosed
    load-bearing assumption; deleting it, or quietly adopting one reading as
    though it were the fact, is the thing this model exists to prevent.
    """
    fact: str = Field(min_length=1)
    fact_source: str | None = None
    readings: list[Reading] = Field(min_length=2)
    discriminator_type: DiscriminatorType | None = None
    discriminator: str | None = None
    resolved: bool = False
    our_reading: str = Field(min_length=1)
    sector_convention_applied: str | None = None
    materiality: Literal["high", "medium", "low"] | None = None

    @model_validator(mode="after")
    def _unresolved_needs_no_discriminator_but_resolved_does(self) -> "DivergenceCase":
        # Mirrors check 18 in the ER red-team (prompts/34 Part 1b): claiming a
        # divergence is settled while naming nothing that settles it is the
        # exact move the ledger exists to catch. `none_available` is honest and
        # allowed — it just cannot coexist with resolved=True.
        if self.resolved:
            if self.discriminator_type in (None, "none_available"):
                raise ValueError(
                    "resolved=True requires a discriminator_type of "
                    "historical_distribution, peer_distribution, disclosed_mechanism "
                    "or forward_observable"
                )
            if not (self.discriminator or "").strip():
                raise ValueError("resolved=True requires non-empty discriminator evidence")
        return self


# ---------------------------------------------------------------------------
# news_processor
# ---------------------------------------------------------------------------


class NewsItemRow(BaseModel):
    news_item_id: int | None = None
    event_scope: Literal["MICRO", "MACRO"]
    tag: str
    impact: Literal["POSITIVE", "NEGATIVE", "NA"]
    description: str = Field(max_length=400)
    event_date: str
    source: str
    url: str | None = None


class NewsProcessorOutput(BaseModel):
    items: list[NewsItemRow] = Field(default_factory=list)
    injection_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# idea_gen
# ---------------------------------------------------------------------------


class CandidateIdea(BaseModel):
    instrument: str
    direction: Literal["LONG", "AVOID"]
    entry_door: Literal["TOP_DOWN", "BOTTOM_UP"]
    strategy_tag: str = Field(min_length=1)
    thesis: str
    invalidation_condition: str = Field(min_length=10)
    confidence: float = Field(ge=0, le=1)


class IdeaGenOutput(BaseModel):
    ideas: list[CandidateIdea] = Field(default_factory=list)
    no_ideas_reason: str | None = None


# ---------------------------------------------------------------------------
# synthesis
# ---------------------------------------------------------------------------


class SynthesisOutput(BaseModel):
    instrument: str
    house_view: str
    supporting_logic: list[str] = Field(default_factory=list)
    confidence_tier: Literal["HIGH", "MEDIUM", "LOW"]
    load_bearing_assumptions: list[str] = Field(default_factory=list)
    # Additive (facts/interpretation layer). Optional and empty-by-default so
    # every existing synthesis payload still validates. `supporting_logic` is
    # deliberately untouched: these two split it into what is checkable and
    # what is a reading of it, without removing the field agents already write.
    facts_relied_on: list[FactClaim] = Field(default_factory=list)
    interpretations: list[Reading] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# critique
# ---------------------------------------------------------------------------


class NarrativeCritique(BaseModel):
    flaws_found: list[str] = Field(default_factory=list)
    strongest_counter_argument: str = Field(min_length=10)
    circular_reasoning_flags: list[str] = Field(default_factory=list)


class QuantModelCritique(BaseModel):
    flaws_found: list[str] = Field(default_factory=list)
    most_aggressive_input: str | None = None
    sensitivity_note: str | None = None


class PremortemBlock(BaseModel):
    """Phase 10 — cycle_framework.yaml governance mandate: assume 12-24
    months have passed and the position underperformed; work backward to
    the most plausible reason (mean reversion failing to play out, thesis
    invalidated, regime shift, etc.) rather than restating known risks.
    REQUIRED (non-None) whenever the critique packet carries
    requires_premortem: true (see orchestrator/context.py); optional
    otherwise so existing non-flagged critiques keep validating."""
    failure_modes: list[str] = Field(default_factory=list)
    most_plausible_failure: str = Field(min_length=10)
    probability_qualitative: Literal["LOW", "MEDIUM", "HIGH"]
    kill_conditions: list[str] = Field(default_factory=list)


class UnresolvedDivergence(BaseModel):
    """A divergence the critique could not settle. Recording it is the point:
    an unsettled reading that the thesis nonetheless depends on is a
    load-bearing assumption, and the reader is entitled to know which ones
    those are."""
    fact: str = Field(min_length=1)
    our_reading: str = Field(min_length=1)
    why_unresolved: str = Field(min_length=1)
    what_would_settle_it: str | None = None
    materiality: Literal["high", "medium", "low"] | None = None


class CritiqueOutput(BaseModel):
    instrument: str
    narrative_critique: NarrativeCritique
    quant_model_critique: QuantModelCritique
    competing_thesis: str
    revised_confidence: Literal["HIGHER", "UNCHANGED", "LOWER", "MUCH_LOWER"]
    premortem: PremortemBlock | None = None
    # Additive (facts/interpretation layer). `opinion_audit` keys are the
    # check ids from the ER subsystem's docs/OPINION_VS_ANALYSIS.md section 4
    # (1-15: is opinion masquerading as analysis; 16-18: has legitimate
    # divergence been flattened into a single reading). None, not {}, when the
    # audit was not run — an empty dict would read as "audited, nothing found".
    opinion_audit: dict[str, Literal["PASS", "FAIL", "NA"]] | None = None
    banned_reasoning_hits: list[str] = Field(default_factory=list)
    unresolved_divergences: list[UnresolvedDivergence] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# risk_mgmt
# ---------------------------------------------------------------------------


class LimitCheck(BaseModel):
    rule: str
    status: Literal["PASS", "FAIL", "NA"]
    detail: str


class RiskMgmtOutput(BaseModel):
    instrument: str
    verdict: Literal["CLEARED", "CLEARED_WITH_CONDITIONS", "BLOCKED"]
    conditions: list[str] = Field(default_factory=list)
    limit_checks: list[LimitCheck] = Field(default_factory=list)
    look_through_note: str | None = None


# ---------------------------------------------------------------------------
# allocator
# ---------------------------------------------------------------------------


class AllocatorOutput(BaseModel):
    instrument: str
    vehicle: Literal["DIRECT_STOCK", "ETF", "INDEX_FUND", "MUTUAL_FUND"]
    proposed_weight_pct: float = Field(ge=0, le=100)
    sizing_rationale: str
    cash_after_pct: float | None = None


# ---------------------------------------------------------------------------
# fund_manager
# ---------------------------------------------------------------------------


class FundManagerOutput(BaseModel):
    instrument: str | None = None
    action: Literal["NEW", "ADD", "REDUCE", "EXIT", "HOLD", "MONITOR_ONLY"]
    strategy_tag: str
    conviction: float = Field(ge=0, le=1)
    thesis_restatement: str
    strongest_counter_and_response: str
    invalidation_condition: str = Field(min_length=10)
    evidence_chain: list[str] = Field(default_factory=list)
    size_or_weight_pct: float | None = None
    calibration_note: str | None = None
    # Phase 10 — the JUDGMENT subset of cycle_framework.yaml's
    # governance.checklist (items tagged type: judgment — e.g. "is the
    # invalidation condition still specific and falsifiable", "has the
    # narrative changed since entry" — that a deterministic rule can't
    # evaluate). Keyed by the same checklist item names used by
    # orchestrator.escalation.mechanical_checklist() for the mechanical
    # subset; run.py's ingestion merges both dicts into one decision_log
    # record. Optional: an agent that has nothing judgment-relevant to add
    # (e.g. a HOLD/MONITOR_ONLY with no checklist-worthy judgment calls)
    # may omit this entirely.
    checklist_status: dict[str, Literal["PASS", "FAIL", "NA"]] | None = None

    @model_validator(mode="after")
    def _size_required_for_new_or_add(self) -> "FundManagerOutput":
        if self.action in ("NEW", "ADD") and self.size_or_weight_pct is None:
            raise ValueError("size_or_weight_pct is required when action is NEW or ADD")
        return self


# ---------------------------------------------------------------------------
# equity_researcher (external subsystem — research/equity_researcher/, bridged
# via src/afund/research/er_adapter.py)
# ---------------------------------------------------------------------------


class SectorKpiReadout(BaseModel):
    metric: str
    value: float | None = None
    trend: Literal["up", "down", "flat"] | None = None
    comment: str | None = None


class EquityResearchNote(BaseModel):
    ticker: str | None = None
    as_of_date: str | None = None
    status: Literal["OK", "NOT_IMPLEMENTED"]
    rating: Literal["BULLISH", "NEUTRAL", "BEARISH"] | None = None
    conviction: float | None = None
    thesis: str | None = None
    key_drivers: list[str] = Field(default_factory=list)
    sector_kpi_readout: list[SectorKpiReadout] = Field(default_factory=list)
    valuation: dict | None = None
    risks: list[str] = Field(default_factory=list)
    invalidation_condition: str | None = None
    sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# sector_researcher
# ---------------------------------------------------------------------------


class SectorCompanyRow(BaseModel):
    symbol: str
    pe: float | None = None
    roce: float | None = None
    roe: float | None = None
    ret_1y: float | None = None
    cycle_phase: str | None = None
    note: str | None = None


class SectorResearchNote(BaseModel):
    sector: str
    as_of_date: str
    cycle_phase: str | None = None
    cycle_confidence: float | None = None
    competitive_landscape: str
    value_chain_note: str
    comparison_table: list[SectorCompanyRow] = Field(default_factory=list)
    top_picks: list[str] = Field(default_factory=list)
    avoid_list: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    # Additive (facts/interpretation layer). `competitive_landscape` and
    # `value_chain_note` keep their existing narrative role — these split out
    # the checkable claims underneath them and record where the sector's
    # convention admits two readings of the same number (a P/E of 25 that is
    # indefensible for a primary smelter is defensible for a recycler because
    # the conditioner differs, not because the industry does).
    facts: list[FactClaim] = Field(default_factory=list)
    interpretations: list[Reading] = Field(default_factory=list)
    divergence_cases: list[DivergenceCase] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# buy_side
# ---------------------------------------------------------------------------


class BuySideRecommendation(BaseModel):
    ticker: str
    recommendation: Literal["BUY", "ACCUMULATE", "HOLD", "REDUCE", "AVOID"]
    conviction: float = Field(ge=0.0, le=1.0)
    rerating_narrative: str
    catalysts: list[str] = Field(default_factory=list)
    eps_scenarios: list[float] = Field(min_length=5, max_length=5)
    pe_scenarios: list[float] = Field(min_length=5, max_length=5)
    scenario_reasoning: str
    base_target_price: float | None = None
    invalidation_condition: str = Field(min_length=10)
    # Additive (Phase 11 — EPS-bridge doctrine): which EPS-bridge rules
    # (research/equity_researcher/tools/eps_bridge_check.py rule_ids, e.g.
    # "eps_growth_20pct", "interest_vs_ebit_growth", "dilution_consecutive")
    # the agent judges held, given eps_bridge_check.json in the packet.
    # Optional -- older tickers / handoffs predating this artifact still
    # validate with this left None; never fabricate a verdict the checker
    # didn't actually compute.
    eps_bridge_summary: dict[str, Literal["PASS", "FAIL", "NA"]] | None = None
    # Additive (facts/interpretation layer). `pe_scenarios` says WHAT multiple
    # we are paying; these say WHY that multiple is defensible and who would
    # disagree. `multiple_conditioner` is the direct answer to "is a P/E of 30
    # expensive?" — it is expensive against `own_history_anchor` and cheap
    # against `growth_rate` at PEG 1, and the recommendation has to say which
    # one it is underwriting. `sector_playbook` is the ER tier-2 slug from the
    # valuation handoff (32 of them; the fund's own 8 slugs are families).
    # All optional: handoffs predating the ledger still validate, and an empty
    # ledger is honest where a full one would be fabricated.
    sector_playbook: str | None = None
    primary_multiple: str | None = None
    multiple_conditioner: ConditioningVariable | None = None
    interpretation_ledger: list[DivergenceCase] = Field(default_factory=list)
    opinion_audit: dict[str, Literal["PASS", "FAIL", "NA"]] | None = None

    @field_validator("eps_scenarios", "pe_scenarios")
    @classmethod
    def _must_be_ascending(cls, v: list[float]) -> list[float]:
        if list(v) != sorted(v):
            raise ValueError("scenario list must be ascending")
        return v


# ---------------------------------------------------------------------------
# macro_digest
# ---------------------------------------------------------------------------


class MacroNote(BaseModel):
    tag_value: str
    content: str = Field(max_length=1200)
    source_ref: str


class MacroDigestOutput(BaseModel):
    publisher: str
    period: str
    macro_notes: list[MacroNote] = Field(min_length=1, max_length=12)
    regime_read: str | None = None
    injection_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# meta_research
# ---------------------------------------------------------------------------


class MetaResearchProposal(BaseModel):
    target_file: str
    change_type: Literal["PROMPT_EDIT", "RULE_CHANGE", "WORKFLOW_CHANGE"]
    rationale: str
    proposed_diff: str


class MetaResearchOutput(BaseModel):
    period: str
    patterns_found: list[str] = Field(default_factory=list)
    proposals: list[MetaResearchProposal] = Field(default_factory=list)
    calibration_summary: str | None = None


# ---------------------------------------------------------------------------
# narrative_intensity (Phase 7 cycle engine)
# ---------------------------------------------------------------------------


class NarrativeIntensityOutput(BaseModel):
    """Qualitative overlay per cycle_framework.yaml / source doc section
    2.5: reads permanence/impairment narratives and price-narrative
    divergence for one cycle-assessment scope, scored -100..+100. Ingested
    via orchestrator/run.py's _ingest_narrative_intensity, which UPDATEs the
    matching cycle_assessments row(s) rather than inserting new ones."""
    scope: str
    as_of_date: str
    narrative_intensity_score: float = Field(ge=-100, le=100)
    permanence_narratives: list[str] = Field(default_factory=list)
    impairment_narratives: list[str] = Field(default_factory=list)
    divergence_note: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    injection_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# role -> model registry + validate_output()
# ---------------------------------------------------------------------------

ROLE_MODELS: dict[str, type[BaseModel]] = {
    "news_processor": NewsProcessorOutput,
    "idea_gen": IdeaGenOutput,
    "synthesis": SynthesisOutput,
    "critique": CritiqueOutput,
    "risk_mgmt": RiskMgmtOutput,
    "allocator": AllocatorOutput,
    "fund_manager": FundManagerOutput,
    "equity_researcher": EquityResearchNote,
    "sector_researcher": SectorResearchNote,
    "buy_side": BuySideRecommendation,
    "macro_digest": MacroDigestOutput,
    "meta_research": MetaResearchOutput,
    "narrative_intensity": NarrativeIntensityOutput,
}


def _strip_json_fences(text: str) -> str:
    """Strip a ```json ... ``` (or bare ``` ... ```) fenced block wrapper, if
    present, and return the inner text. Leaves plain JSON text untouched."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines:
        return stripped
    # Drop the opening fence line (```json or ```).
    lines = lines[1:]
    # Drop a trailing fence line, if present.
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def validate_output(role: str, payload: str | dict) -> BaseModel:
    """Validate `payload` (a JSON string or already-parsed dict) against the
    contract for `role`. Returns the validated model instance.

    Raises ContractViolation (a ValueError subclass) if:
      - `role` has no known contract,
      - `payload` is a string that isn't valid JSON (after stripping an
        optional ```json fenced block wrapper),
      - the parsed payload fails pydantic validation for the role's model.
    """
    if role not in ROLE_MODELS:
        raise ContractViolation(f"No output contract registered for role {role!r}. Known roles: {sorted(ROLE_MODELS)}")

    model = ROLE_MODELS[role]

    if isinstance(payload, str):
        text = _strip_json_fences(payload)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ContractViolation(f"role={role}: payload is not valid JSON: {exc}") from exc
    else:
        data = payload

    try:
        return model.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError primarily
        raise ContractViolation(f"role={role}: contract validation failed: {exc}") from exc
