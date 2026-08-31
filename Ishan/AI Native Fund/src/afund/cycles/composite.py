"""Multi-cycle synthesis: EVI (partial-aware), functional-group rollup,
regime cluster classification, regime-weighted composite score, alignment
score, and reconciliation-quadrant application.

(cycle_framework.yaml `evi` / `functional_groups` / `regime_clusters` /
`group_weights_by_cluster` / `regime_classification_rules` / `alignment` /
`reconciliation`; source doc sections 3-4 + 2.6.)

Pure functions operating on already-classified per-cycle readings
(CyclePhaseReading) — no DB/I/O here; assess.py is the orchestration layer
that gathers readings via anchors.py + classify.py and calls into this
module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from afund.cycles.framework import CycleFramework


@dataclass
class CyclePhaseReading:
    """One cycle's classified reading, ready for composite synthesis."""
    cycle_id: str            # catalog cycle_id (e.g. "valuation_cycle")
    scope: str
    phase_id: str | None     # None when data_pending
    directional_lean: int | None   # -1/0/+1, None when data_pending
    percentile: float | None
    data_pending: bool = False
    missing_kpis: list[str] = field(default_factory=list)


@dataclass
class EviResult:
    value: float | None
    components_used: list[str]
    components_missing: list[str]
    data_pending: bool


def compute_evi(
    framework: CycleFramework,
    component_values: dict[str, float | None],
) -> EviResult:
    """Equity Valuation Index: equal-weighted average of whichever of the
    4 components (index_pe, index_pb, gsec_yield_x_pe, mcap_gdp) are
    available, weights re-normalized among the available set. Discloses
    components_missing explicitly rather than silently zero-filling or
    treating a partial EVI as full-confidence (DRAFT judgment call
    documented in cycle_framework.yaml's evi.partial_evi_disclosure)."""
    evi_cfg = framework.evi
    available = {k: v for k, v in component_values.items() if v is not None and k in evi_cfg.components}
    missing = [c for c in evi_cfg.components if c not in available]

    if not available:
        return EviResult(value=None, components_used=[], components_missing=missing, data_pending=True)

    total_weight = sum(evi_cfg.weights.get(k, 0.0) for k in available)
    if total_weight == 0:
        return EviResult(value=None, components_used=[], components_missing=missing, data_pending=True)

    weighted_sum = sum(evi_cfg.weights.get(k, 0.0) * v for k, v in available.items())
    value = weighted_sum / total_weight
    return EviResult(
        value=value,
        components_used=sorted(available.keys()),
        components_missing=missing,
        data_pending=bool(missing),
    )


def select_allocation_band(
    framework: CycleFramework,
    yield_gap_value: float,
    valuation_phase_id: str | None = None,
):
    """Select the allocation_bands row for a computed Yield Gap value
    (source doc section 5.1 table; cycle_framework.yaml allocation_bands).

    The framework's own yield_gap_thresholds only pin the two EXTREME
    bands (<1.40 -> Deep Value, >1.70 -> Distribution/Euphoria); the two
    middle bands are described by valuation-cycle phase ranges ("Value /
    Phase 4-6", "Neutral / Phase 6-7"). Deterministic encoding (DRAFT
    judgment call, documented here):

      - yield_gap < deep_value_below (1.40)  -> bands[0] (Deep Value)
      - yield_gap > euphoria_above  (1.70)   -> bands[3] (Distribution)
      - otherwise, disambiguate the middle zone by the valuation cycle's
        phase: value/deep_value/attractive_growth (wheel phases 4-6)
        -> bands[1] "Value / Early Recovery"; momentum (phase 7)
        -> bands[2] "Momentum / Fair Value". attractive_growth sits in
        both bands' stated ranges — it goes to bands[1] because that
        band's own regime_label ("Value / Early Recovery") names it.
        Any other phase (euphoria/distribution/denial/optimism) or a
        missing phase falls back to bands[2] (Neutral) — the extreme
        bands are only ever triggered by the yield_gap thresholds
        themselves, never by phase alone (conservative: the composite_
        reading strings pair those bands with "high alignment", which
        this function does not evaluate).

    Returns (band, basis_note)."""
    bands = framework.allocation_bands.bands
    thresholds = framework.allocation_bands.yield_gap_thresholds

    if yield_gap_value < thresholds.deep_value_below:
        return bands[0], (
            f"yield_gap {yield_gap_value:.3f} < deep_value_below {thresholds.deep_value_below}"
        )
    if yield_gap_value > thresholds.euphoria_above:
        return bands[3], (
            f"yield_gap {yield_gap_value:.3f} > euphoria_above {thresholds.euphoria_above}"
        )

    if valuation_phase_id in ("value", "deep_value", "attractive_growth"):
        return bands[1], (
            f"yield_gap {yield_gap_value:.3f} in neutral zone; valuation phase "
            f"{valuation_phase_id!r} in wheel range 4-6 -> Value band"
        )
    if valuation_phase_id == "momentum":
        return bands[2], (
            f"yield_gap {yield_gap_value:.3f} in neutral zone; valuation phase "
            f"'momentum' -> Neutral/Momentum band"
        )
    return bands[2], (
        f"yield_gap {yield_gap_value:.3f} in neutral zone; valuation phase "
        f"{valuation_phase_id!r} outside the 4-7 disambiguation range (or unavailable) "
        f"-> Neutral band default"
    )


@dataclass
class RegimeClusterResult:
    cluster: str | None   # one of framework.regime_clusters, or None if UNKNOWN
    unknown: bool
    basis_cycle_ids: list[str]
    note: str


def classify_regime_cluster(
    framework: CycleFramework,
    macro_regime_readings: list[CyclePhaseReading],
) -> RegimeClusterResult:
    """Classify the prevailing regime cluster from the Macro-Regime
    functional group's own constituent cycles ONLY (source doc section
    4.2; cycle_framework.yaml regime_classification_rules). UNKNOWN when
    every macro_regime cycle is data_pending — never guessed."""
    available = [r for r in macro_regime_readings if not r.data_pending and r.phase_id is not None]

    if not available:
        return RegimeClusterResult(
            cluster=None,
            unknown=True,
            basis_cycle_ids=[],
            note="all macro_regime cycles are data_pending; regime cluster is UNKNOWN per "
                 "regime_classification_rules.unknown_when_data_pending",
        )

    phase_map = framework.regime_classification_rules.phase_to_cluster_map
    macro_group_cycle_order = framework.functional_groups["macro_regime"].cycles

    counts: dict[str, int] = {}
    for r in available:
        cluster = phase_map.get(r.phase_id)
        if cluster:
            counts[cluster] = counts.get(cluster, 0) + 1

    if not counts:
        return RegimeClusterResult(
            cluster=None,
            unknown=True,
            basis_cycle_ids=[r.cycle_id for r in available],
            note="available macro_regime phases did not map to any cluster",
        )

    max_count = max(counts.values())
    tied_clusters = [c for c, n in counts.items() if n == max_count]

    if len(tied_clusters) == 1:
        winner = tied_clusters[0]
    else:
        # Tie-break: cluster favored by the cycle earliest in
        # functional_groups.macro_regime.cycles (DRAFT judgment call, per
        # cycle_framework.yaml regime_classification_rules.resolution).
        winner = tied_clusters[0]
        for cycle_id in macro_group_cycle_order:
            match = next((r for r in available if r.cycle_id == cycle_id), None)
            if match and phase_map.get(match.phase_id) in tied_clusters:
                winner = phase_map[match.phase_id]
                break

    return RegimeClusterResult(
        cluster=winner,
        unknown=False,
        basis_cycle_ids=[r.cycle_id for r in available],
        note=f"plurality cluster from {len(available)} available macro_regime cycle(s): {counts}",
    )


@dataclass
class CompositeResult:
    composite_score: float | None   # -100..+100
    regime_cluster: RegimeClusterResult
    group_scores: dict[str, float | None]
    group_weights_used: dict[str, float]
    data_pending_groups: list[str]
    note: str


def _group_score(readings: list[CyclePhaseReading]) -> float | None:
    """Average directional_lean (-1/0/+1) across a functional group's
    available (non-data_pending) cycles, scaled to -100..+100. None if the
    entire group is data_pending."""
    available = [r for r in readings if not r.data_pending and r.directional_lean is not None]
    if not available:
        return None
    avg_lean = sum(r.directional_lean for r in available) / len(available)
    return avg_lean * 100.0


def compute_composite(
    framework: CycleFramework,
    readings_by_group: dict[str, list[CyclePhaseReading]],
) -> CompositeResult:
    """Regime-weighted composite score (-100..+100) across the 4 functional
    groups (source doc section 4.3). Regime cluster is classified from the
    macro_regime group's own readings first; its weight table then
    combines the (possibly partial) group scores. Any group with zero
    available cycles is excluded and its weight re-normalized among the
    remaining groups (DRAFT judgment call — the doc's weight table assumes
    all 4 groups have data; re-normalizing rather than zero-filling avoids
    silently dragging the composite toward a false neutral read)."""
    macro_readings = readings_by_group.get("macro_regime", [])
    regime_result = classify_regime_cluster(framework, macro_readings)

    group_scores: dict[str, float | None] = {
        group_id: _group_score(readings) for group_id, readings in readings_by_group.items()
    }

    if regime_result.unknown:
        return CompositeResult(
            composite_score=None,
            regime_cluster=regime_result,
            group_scores=group_scores,
            group_weights_used={},
            data_pending_groups=[g for g, s in group_scores.items() if s is None],
            note="composite score withheld: regime cluster UNKNOWN (macro_regime group fully data_pending)",
        )

    weights = framework.group_weights_by_cluster[regime_result.cluster]
    weight_map = {
        "macro_regime": weights.macro_regime,
        "market_structure": weights.market_structure,
        "external": weights.external,
    }
    # idiosyncratic has no weight in the doc's 4.3 table (only 3 groups are
    # weighted there) — DRAFT judgment call: idiosyncratic is informational
    # context for security selection (source doc 4.1's own framing, "within
    # the favored macro backdrop, what looks attractive"), not a composite
    # allocation input, so it is intentionally excluded from the weighted
    # composite score here.
    available_weighted = {
        g: (weight_map[g], group_scores.get(g))
        for g in weight_map
        if group_scores.get(g) is not None
    }

    data_pending_groups = [g for g in weight_map if group_scores.get(g) is None]

    if not available_weighted:
        return CompositeResult(
            composite_score=None,
            regime_cluster=regime_result,
            group_scores=group_scores,
            group_weights_used={},
            data_pending_groups=data_pending_groups,
            note="composite score withheld: no weighted group has any available cycle",
        )

    total_weight = sum(w for w, _ in available_weighted.values())
    weighted_sum = sum(w * s for w, s in available_weighted.values())
    composite_score = weighted_sum / total_weight

    return CompositeResult(
        composite_score=composite_score,
        regime_cluster=regime_result,
        group_scores=group_scores,
        group_weights_used={g: w for g, (w, _) in available_weighted.items()},
        data_pending_groups=data_pending_groups,
        note=f"regime={regime_result.cluster}, weights re-normalized over {list(available_weighted.keys())}"
             + (f"; data_pending groups excluded: {data_pending_groups}" if data_pending_groups else ""),
    )


@dataclass
class AlignmentResult:
    alignment_score: float | None  # 0-100
    n_cycles: int
    n_aligned: int
    majority_lean: int | None
    note: str


def compute_alignment(readings: list[CyclePhaseReading]) -> AlignmentResult:
    """Alignment Score (source doc section 4.4): the proportion of
    independently-scored (non-data_pending) cycles whose directional_lean
    matches the majority sign, expressed 0-100. data_pending cycles are
    excluded from the denominator entirely (never counted as neutral)."""
    available = [r for r in readings if not r.data_pending and r.directional_lean is not None]
    if not available:
        return AlignmentResult(
            alignment_score=None, n_cycles=0, n_aligned=0, majority_lean=None,
            note="no available (non-data_pending) cycles to score alignment over",
        )

    counts = {-1: 0, 0: 0, 1: 0}
    for r in available:
        counts[r.directional_lean] += 1

    majority_lean = max(counts, key=lambda k: counts[k])
    n_aligned = counts[majority_lean]
    score = 100.0 * n_aligned / len(available)

    return AlignmentResult(
        alignment_score=score,
        n_cycles=len(available),
        n_aligned=n_aligned,
        majority_lean=majority_lean,
        note=f"{n_aligned}/{len(available)} cycles share majority lean {majority_lean}",
    )


@dataclass
class ReconciliationResult:
    quadrant: str | None  # framework.reconciliation quadrant outcome key, or None
    interpretation: str
    outcome: str
    flags: dict[str, bool]
    note: str


def _narrative_bucket(framework: CycleFramework, narrative_intensity_score: float) -> str:
    for name, band in framework.reconciliation.narrative_bucket_bands.items():
        if band.min <= narrative_intensity_score <= band.max:
            return name
    return "neutral"


def apply_reconciliation(
    framework: CycleFramework,
    quant_directional_lean: int,
    narrative_intensity_score: float | None,
) -> ReconciliationResult:
    """Apply the reconciliation quadrant table (source doc section 2.6):
    quant phase (via its directional_lean) x qualitative Narrative
    Intensity Score bucket -> outcome + flags. Returns a "no narrative yet"
    result when narrative_intensity_score is None (honest, since the
    narrative_intensity agent runs on a separate weekly cadence and may not
    have ingested yet for this scope)."""
    if narrative_intensity_score is None:
        return ReconciliationResult(
            quadrant=None,
            interpretation="Narrative Intensity Score not yet available for this scope "
                           "(narrative_intensity agent has not ingested) — quant-only reading.",
            outcome="quant_only_pending_narrative",
            flags={},
            note="reconciliation withheld until narrative_intensity_score is ingested",
        )

    narrative_bucket = _narrative_bucket(framework, narrative_intensity_score)

    if quant_directional_lean > 0:
        quant_bucket = "cheap"
    elif quant_directional_lean < 0:
        quant_bucket = "expensive"
    else:
        quant_bucket = "ambiguous_or_conflicting"

    for q in framework.reconciliation.quadrants:
        if q.quant_phase_bucket == quant_bucket and (
            q.narrative_bucket == narrative_bucket or q.narrative_bucket in ("any", "any_matching")
        ):
            # aligned_favorable ("any_matching") only applies when the
            # narrative bucket's own sign agrees with the quant lean sign;
            # otherwise fall through to the ambiguous row.
            if q.narrative_bucket == "any_matching":
                sign_matches = (
                    (quant_directional_lean > 0 and narrative_bucket == "dismissive")
                    or (quant_directional_lean < 0 and narrative_bucket == "euphoric")
                    or (quant_directional_lean == 0 and narrative_bucket == "neutral")
                )
                if not sign_matches:
                    continue
            return ReconciliationResult(
                quadrant=q.quant_phase_bucket,
                interpretation=q.interpretation,
                outcome=q.outcome,
                flags=q.flags,
                note=f"quant_bucket={quant_bucket}, narrative_bucket={narrative_bucket}",
            )

    # Fall through to the ambiguous quadrant if nothing else matched.
    ambiguous = next((q for q in framework.reconciliation.quadrants if q.quant_phase_bucket == "ambiguous_or_conflicting"), None)
    if ambiguous:
        return ReconciliationResult(
            quadrant=ambiguous.quant_phase_bucket,
            interpretation=ambiguous.interpretation,
            outcome=ambiguous.outcome,
            flags=ambiguous.flags,
            note=f"quant_bucket={quant_bucket}, narrative_bucket={narrative_bucket} (fallback to ambiguous)",
        )
    return ReconciliationResult(
        quadrant=None, interpretation="no matching quadrant", outcome="unresolved", flags={},
        note=f"quant_bucket={quant_bucket}, narrative_bucket={narrative_bucket}",
    )
