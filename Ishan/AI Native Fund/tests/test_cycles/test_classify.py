"""Golden tests for the deterministic 8-phase classifier
(src/afund/cycles/classify.py against registry/strategies/
cycle_framework.yaml). Every golden below is hand-computed from the
framework's phases + classification_rules — see the inline comments for the
step-by-step resolution each case exercises."""
from __future__ import annotations

import pytest

from afund.cycles import classify
from afund.cycles.classify import DirectionReading
from afund.cycles.framework import load as load_framework


@pytest.fixture(scope="module")
def fw():
    return load_framework()


def _reading(direction: str, momentum: str = "stable") -> DirectionReading:
    return DirectionReading(roc_3m=None, roc_6m=None, roc_12m=None,
                            direction=direction, momentum_state=momentum)


# ---------------------------------------------------------------------------
# percentile_rank / roc_pct / classify_direction / momentum-of-momentum
# ---------------------------------------------------------------------------

def test_percentile_rank_inclusive_counting():
    # count_le / n * 100: 5 of 10 values <= 5 -> 50.0 (inclusive convention,
    # mirrors derive/regime.py's pe_percentile_5y exactly).
    history = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert classify.percentile_rank(5, history) == 50.0
    # current == max -> all 10 <= current -> 100.0
    assert classify.percentile_rank(10, history) == 100.0
    # current below min -> 0 <= current -> 0.0
    assert classify.percentile_rank(0.5, history) == 0.0


def test_percentile_rank_empty_history_is_none():
    assert classify.percentile_rank(5.0, []) is None


def test_roc_pct():
    assert classify.roc_pct(110.0, 100.0) == pytest.approx(10.0)
    assert classify.roc_pct(90.0, 100.0) == pytest.approx(-10.0)
    assert classify.roc_pct(100.0, 0.0) is None  # undefined base


def test_classify_direction_uses_shortest_available_window():
    # 3m preferred: +5% -> rising even if 12m is negative.
    assert classify.classify_direction(5.0, -3.0, -8.0, flat_threshold_pct=2.0) == "rising"
    # 3m missing -> falls back to 6m.
    assert classify.classify_direction(None, -4.0, 8.0, flat_threshold_pct=2.0) == "falling"
    # |RoC| below flat threshold -> flat.
    assert classify.classify_direction(1.0, None, None, flat_threshold_pct=2.0) == "flat"
    # everything missing -> flat (honest neutral, never fabricated).
    assert classify.classify_direction(None, None, None, flat_threshold_pct=2.0) == "flat"


def test_momentum_of_momentum():
    # recent +10 vs prior +5: delta +5 > 1pp, trend positive & speeding up.
    assert classify.classify_momentum_of_momentum(10.0, 5.0, 1.0) == "accelerating"
    # recent +5 vs prior +10: positive trend slowing -> decelerating.
    assert classify.classify_momentum_of_momentum(5.0, 10.0, 1.0) == "decelerating"
    # recent -10 vs prior -5: decline speeding up in its own direction.
    assert classify.classify_momentum_of_momentum(-10.0, -5.0, 1.0) == "accelerating"
    # recent -5 vs prior -10: decline slowing -> decelerating (bottoming).
    assert classify.classify_momentum_of_momentum(-5.0, -10.0, 1.0) == "decelerating"
    # |delta| under stable threshold -> stable.
    assert classify.classify_momentum_of_momentum(5.0, 4.5, 1.0) == "stable"
    # missing either window -> stable (honest neutral).
    assert classify.classify_momentum_of_momentum(None, 5.0, 1.0) == "stable"


# ---------------------------------------------------------------------------
# classify_phase goldens — >= 10 hand-computed (percentile, direction,
# momentum) -> phase combos, including the task-spec examples and every
# band-gap DRAFT judgment call in cycle_framework.yaml.
# ---------------------------------------------------------------------------

GOLDENS = [
    # (percentile, direction, momentum, expected_phase, why)
    (95.0, "rising", "accelerating", "euphoria",
     "in-band 90-100, rising_or_flat_at_highs accepts rising -> exact match"),
    (92.0, "flat", "stable", "euphoria",
     "in-band 90-100, rising_or_flat_at_highs accepts flat -> exact match"),
    (80.0, "flat", "stable", "distribution",
     "in-band 75-90 stalling accepts flat; optimism (65-85) needs rising -> distribution only"),
    (85.0, "falling", "accelerating", "distribution",
     "in-band 75-90 stalling accepts falling; optimism needs rising -> distribution only"),
    (12.0, "falling", "decelerating", "deep_value",
     "in-band 0-15, falling_decelerating requires falling+decelerating -> exact match (task-spec golden)"),
    (25.0, "rising", "accelerating", "attractive_growth",
     "in-band 15-30 turning_up accepts rising; value (20-45) needs falling -> attractive_growth only (task-spec golden)"),
    (50.0, "rising", "stable", "momentum",
     "in-band 45-65 rising -> exact match (task-spec golden)"),
    (50.0, "falling", "stable", "denial",
     "gap (a): 45-55 falling; momentum in-band but needs rising; nearest compatible are denial (dist 5) "
     "and value (dist 5); tie broken by wheel order -> denial (YAML gap note: falling -> denial)"),
    (48.0, "flat", "stable", "momentum",
     "gap (a): 45-55 flat; no nearby band accepts flat, pool falls back to all candidates; "
     "nearest by distance is momentum (dist 0, in-band) per YAML gap note 'flat -> momentum wins ties'"),
    (17.0, "falling", "decelerating", "deep_value",
     "gap (b): 15-20 falling+decelerating; attractive_growth in-band but turning_up rejects falling; "
     "nearest compatible: deep_value (dist 2) beats value (dist 3) -> deep_value (YAML gap note)"),
    (17.0, "rising", "accelerating", "attractive_growth",
     "gap (b): 15-20 turning_up -> attractive_growth (in-band 15-30, accepts rising) per YAML gap note"),
    (17.0, "falling", "accelerating", "value",
     "gap (b): 15-20 plain falling (not decelerating); deep_value needs decelerating -> "
     "value is the only direction-compatible nearby band (YAML gap note: falling -> value)"),
    (70.0, "rising", "decelerating", "optimism",
     "in-band 65-85, rising_decelerating requires rising+decelerating -> exact match"),
    (70.0, "rising", "accelerating", "momentum",
     "70 in denial (needs falling) and optimism (needs decelerating) bands, both incompatible; "
     "nearest compatible within 10: momentum (45-65, dist 5, accepts rising)"),
    (5.0, "falling", "accelerating", "deep_value",
     "in-band 0-15 but falling_decelerating needs decelerating; no nearby band accepts "
     "falling+accelerating, pool falls back to candidates; nearest is deep_value (dist 0)"),
]


@pytest.mark.parametrize("percentile,direction,momentum,expected,why", GOLDENS,
                         ids=[f"{g[0]:g}_{g[1]}_{g[2]}" for g in GOLDENS])
def test_classify_phase_goldens(fw, percentile, direction, momentum, expected, why):
    phase = classify.classify_phase(fw, percentile, _reading(direction, momentum))
    assert phase.phase_id == expected, why


def test_classified_phase_carries_directional_lean(fw):
    # euphoria leans -1, deep_value leans +1, value leans 0 (doc 4.4 map).
    assert classify.classify_phase(fw, 95.0, _reading("rising")).directional_lean == -1
    assert classify.classify_phase(fw, 12.0, _reading("falling", "decelerating")).directional_lean == 1
    assert classify.classify_phase(fw, 30.0, _reading("falling")).directional_lean == 0


def test_direction_compatibility_yaml_uses_known_direction_enum(fw):
    """The YAML's direction_compatibility lists must only reference the
    direction strings classify.py can actually emit (the golden cross-check
    promised in cycle_framework.yaml's classification_rules comment)."""
    for rule, accepted in fw.classification_rules.direction_compatibility.items():
        for d in accepted:
            assert d in classify.DIRECTIONS, f"{rule} accepts unknown direction {d!r}"


def test_every_phase_direction_rule_has_compatibility_entry(fw):
    rules = set(fw.classification_rules.direction_compatibility)
    for phase in fw.phases:
        assert phase.direction_rule in rules, (
            f"phase {phase.phase_id} direction_rule {phase.direction_rule!r} "
            f"missing from direction_compatibility map"
        )


def test_classify_phase_is_total_over_grid(fw):
    """classify_phase must always return exactly one phase for ANY
    (percentile, direction, momentum) combination — no gap may crash or
    return None."""
    for pct in range(0, 101, 5):
        for direction in classify.DIRECTIONS:
            for momentum in classify.MOMENTUM_STATES:
                phase = classify.classify_phase(fw, float(pct), _reading(direction, momentum))
                assert phase is not None
                assert phase.phase_id in fw.phase_order()
