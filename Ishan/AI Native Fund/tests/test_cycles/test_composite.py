"""Composite-synthesis tests (src/afund/cycles/composite.py): EVI partial
disclosure, alignment score, regime-cluster UNKNOWN honesty, regime-weighted
composite, and the reconciliation quadrant table (incl. requires_premortem)."""
from __future__ import annotations

import pytest

from afund.cycles import composite
from afund.cycles.composite import CyclePhaseReading
from afund.cycles.framework import load as load_framework


@pytest.fixture(scope="module")
def fw():
    return load_framework()


def _reading(cycle_id: str, lean: int | None, phase_id: str | None = None,
             pending: bool = False, percentile: float | None = None) -> CyclePhaseReading:
    return CyclePhaseReading(
        cycle_id=cycle_id, scope="NIFTY 50", phase_id=phase_id,
        directional_lean=lean, percentile=percentile, data_pending=pending,
    )


# ---------------------------------------------------------------------------
# EVI — partial disclosure
# ---------------------------------------------------------------------------

def test_evi_all_components_available(fw):
    result = composite.compute_evi(fw, {
        "index_pe": 40.0, "index_pb": 60.0, "gsec_yield_x_pe": 50.0, "mcap_gdp": 50.0,
    })
    assert result.value == pytest.approx(50.0)  # equal weights, plain average
    assert result.components_missing == []
    assert not result.data_pending


def test_evi_partial_renormalizes_and_discloses(fw):
    # Only index_pe available (today's live reality): EVI = 40, and the
    # other 3 components MUST be disclosed as missing, never zero-filled.
    result = composite.compute_evi(fw, {
        "index_pe": 40.0, "index_pb": None, "gsec_yield_x_pe": None, "mcap_gdp": None,
    })
    assert result.value == pytest.approx(40.0)
    assert set(result.components_missing) == {"index_pb", "gsec_yield_x_pe", "mcap_gdp"}
    assert result.components_used == ["index_pe"]
    assert result.data_pending  # partial EVI is flagged, not full-confidence


def test_evi_two_of_four_weights_renormalized(fw):
    # (0.25*40 + 0.25*60) / 0.5 = 50 — re-normalized among available, not
    # diluted toward zero by the missing half.
    result = composite.compute_evi(fw, {
        "index_pe": 40.0, "index_pb": 60.0, "gsec_yield_x_pe": None, "mcap_gdp": None,
    })
    assert result.value == pytest.approx(50.0)
    assert set(result.components_missing) == {"gsec_yield_x_pe", "mcap_gdp"}


def test_evi_nothing_available_is_none(fw):
    result = composite.compute_evi(fw, {c: None for c in fw.evi.components})
    assert result.value is None
    assert result.data_pending
    assert set(result.components_missing) == set(fw.evi.components)


# ---------------------------------------------------------------------------
# Alignment score
# ---------------------------------------------------------------------------

def test_alignment_majority_proportion(fw):
    readings = [
        _reading("a", 1), _reading("b", 1), _reading("c", 1),
        _reading("d", -1), _reading("e", -1),
    ]
    result = composite.compute_alignment(readings)
    # 3 of 5 share the majority lean (+1) -> 60.0
    assert result.alignment_score == pytest.approx(60.0)
    assert result.majority_lean == 1
    assert result.n_cycles == 5
    assert result.n_aligned == 3


def test_alignment_excludes_data_pending_from_denominator(fw):
    readings = [
        _reading("a", 1), _reading("b", 1),
        _reading("c", None, pending=True), _reading("d", None, pending=True),
        _reading("e", None, pending=True),
    ]
    result = composite.compute_alignment(readings)
    # data_pending cycles are NOT counted as neutral: 2/2 aligned -> 100.
    assert result.alignment_score == pytest.approx(100.0)
    assert result.n_cycles == 2


def test_alignment_none_when_nothing_available(fw):
    readings = [_reading("a", None, pending=True)]
    result = composite.compute_alignment(readings)
    assert result.alignment_score is None
    assert result.n_cycles == 0


# ---------------------------------------------------------------------------
# Regime cluster — UNKNOWN honesty + plurality vote
# ---------------------------------------------------------------------------

def test_regime_unknown_when_all_macro_pending(fw):
    # Today's live reality: gdp/inflation/rate/credit cycles all
    # data_pending -> UNKNOWN, never guessed.
    readings = [
        _reading("gdp_business_cycle", None, pending=True),
        _reading("inflation_cycle", None, pending=True),
        _reading("interest_rate_liquidity_cycle", None, pending=True),
        _reading("credit_debt_cycle", None, pending=True),
    ]
    result = composite.classify_regime_cluster(fw, readings)
    assert result.unknown
    assert result.cluster is None
    assert result.basis_cycle_ids == []


def test_regime_plurality_vote(fw):
    # momentum -> Expansion (x2), attractive_growth -> Recovery (x1):
    # plurality is Expansion.
    readings = [
        _reading("gdp_business_cycle", 1, phase_id="momentum"),
        _reading("inflation_cycle", 1, phase_id="momentum"),
        _reading("interest_rate_liquidity_cycle", 1, phase_id="attractive_growth"),
        _reading("credit_debt_cycle", None, pending=True),
    ]
    result = composite.classify_regime_cluster(fw, readings)
    assert not result.unknown
    assert result.cluster == "Expansion"


def test_regime_tie_broken_by_group_cycle_order(fw):
    # 1 vote Recovery (gdp, listed FIRST in macro_regime.cycles) vs 1 vote
    # Expansion (inflation): tie -> earliest-listed cycle's cluster wins.
    readings = [
        _reading("gdp_business_cycle", 1, phase_id="attractive_growth"),   # Recovery
        _reading("inflation_cycle", 1, phase_id="momentum"),               # Expansion
    ]
    result = composite.classify_regime_cluster(fw, readings)
    assert result.cluster == "Recovery"


# ---------------------------------------------------------------------------
# Composite score — withheld on UNKNOWN, regime-weighted otherwise
# ---------------------------------------------------------------------------

def test_composite_withheld_when_regime_unknown(fw):
    readings_by_group = {
        "macro_regime": [_reading("gdp_business_cycle", None, pending=True)],
        "market_structure": [_reading("valuation_cycle", 1, phase_id="attractive_growth")],
        "external": [],
        "idiosyncratic": [],
    }
    result = composite.compute_composite(fw, readings_by_group)
    assert result.regime_cluster.unknown
    assert result.composite_score is None


def test_composite_regime_weighted_with_renormalization(fw):
    # macro: single momentum (+1) -> group score +100, regime Expansion.
    # market_structure: +1 and -1 -> group score 0.
    # external: fully pending -> excluded, weights re-normalized.
    # Expansion weights: macro 35, market_structure 40 -> composite =
    # (35*100 + 40*0) / 75 = 46.666...
    readings_by_group = {
        "macro_regime": [_reading("gdp_business_cycle", 1, phase_id="momentum")],
        "market_structure": [
            _reading("valuation_cycle", 1, phase_id="momentum"),
            _reading("earnings_margin_cycle", -1, phase_id="distribution"),
        ],
        "external": [_reading("currency_external_balance_cycle", None, pending=True)],
        "idiosyncratic": [_reading("commodity_cycle", -1, phase_id="distribution")],
    }
    result = composite.compute_composite(fw, readings_by_group)
    assert result.regime_cluster.cluster == "Expansion"
    assert result.composite_score == pytest.approx(35 * 100 / 75)
    assert "external" in result.data_pending_groups
    # idiosyncratic is deliberately NOT a weighted composite input (doc 4.3
    # weights only 3 groups; DRAFT judgment call documented in composite.py).
    assert "idiosyncratic" not in result.group_weights_used


# ---------------------------------------------------------------------------
# Reconciliation quadrants (source doc 2.6, cycle_framework.yaml verbatim)
# ---------------------------------------------------------------------------

def test_reconciliation_contrarian_sweet_spot_requires_premortem(fw):
    # Quant cheap (+1) x narrative dismissive (-50): the contrarian sweet
    # spot — highest conviction, but a Pre-Mortem is MANDATORY (governance
    # premortem_trigger references this flag explicitly).
    result = composite.apply_reconciliation(fw, quant_directional_lean=1,
                                            narrative_intensity_score=-50.0)
    assert result.outcome == "highest_conviction_opportunity"
    assert result.flags.get("contrarian_sweet_spot") is True
    assert result.flags.get("requires_premortem") is True


def test_reconciliation_late_cycle_top(fw):
    # Quant expensive (-1) x narrative euphoric (+60): textbook top.
    result = composite.apply_reconciliation(fw, quant_directional_lean=-1,
                                            narrative_intensity_score=60.0)
    assert result.outcome == "reduce_do_not_wait_for_narrative_confirmation"
    assert result.flags.get("late_cycle_top") is True
    assert result.flags.get("reduce_signal") is True


def test_reconciliation_ambiguous_quadrant(fw):
    # Quant lean 0 -> ambiguous_or_conflicting bucket regardless of narrative.
    result = composite.apply_reconciliation(fw, quant_directional_lean=0,
                                            narrative_intensity_score=10.0)
    assert result.outcome == "lower_confidence_smaller_size_flag_for_review"
    assert result.flags.get("route_to_critique") is True


def test_reconciliation_unmatched_combo_falls_back_to_ambiguous(fw):
    # Quant cheap (+1) x narrative euphoric (+80): no verbatim quadrant row
    # covers cheap+euphoric -> deterministic fallback to ambiguous.
    result = composite.apply_reconciliation(fw, quant_directional_lean=1,
                                            narrative_intensity_score=80.0)
    assert result.outcome == "lower_confidence_smaller_size_flag_for_review"
    assert "fallback to ambiguous" in result.note


def test_reconciliation_none_score_is_quant_only(fw):
    # Narrative agent hasn't ingested for this scope yet: honest
    # quant-only outcome, never a guessed narrative bucket.
    result = composite.apply_reconciliation(fw, quant_directional_lean=1,
                                            narrative_intensity_score=None)
    assert result.outcome == "quant_only_pending_narrative"
    assert result.quadrant is None
    assert result.flags == {}


def test_narrative_bucket_bands(fw):
    assert composite._narrative_bucket(fw, -50.0) == "dismissive"
    assert composite._narrative_bucket(fw, 0.0) == "neutral"
    assert composite._narrative_bucket(fw, 50.0) == "euphoric"
    # band edges (verbatim from cycle_framework.yaml)
    assert composite._narrative_bucket(fw, -34.0) == "dismissive"
    assert composite._narrative_bucket(fw, -33.0) == "neutral"
    assert composite._narrative_bucket(fw, 33.0) == "neutral"
    assert composite._narrative_bucket(fw, 34.0) == "euphoric"
