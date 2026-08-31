"""Percentile rank, direction (3/6/12m RoC), momentum-of-momentum, and
deterministic 8-phase classification (cycle_framework.yaml `phases` +
`classification_rules`; source doc sections 2.3/2.4).

Pure functions throughout — golden-testable, no I/O. `classify_phase()` is
the single entry point assess.py calls once a cycle's anchor series has been
reduced to (percentile, direction, momentum_state).
"""
from __future__ import annotations

from dataclasses import dataclass

from afund.cycles.framework import CycleFramework, Phase

DIRECTIONS = ("rising", "falling", "flat")
MOMENTUM_STATES = ("accelerating", "decelerating", "stable")


def percentile_rank(current: float, history: list[float]) -> float | None:
    """Percentile rank of `current` within `history` (0-100), inclusive
    counting: percentile = (# of historical points <= current) / n * 100.
    Mirrors derive/regime.py's pe_percentile_5y() convention exactly.
    Returns None if history is empty."""
    if not history:
        return None
    n = len(history)
    count_le = sum(1 for h in history if h <= current)
    return count_le / n * 100.0


def roc_pct(current: float, past: float) -> float | None:
    """Simple (non-annualized) rate of change from `past` to `current`, as
    a percentage. None if past is 0 (undefined) or None."""
    if past is None or past == 0:
        return None
    return (current - past) / abs(past) * 100.0


def classify_direction(
    roc_3m: float | None,
    roc_6m: float | None,
    roc_12m: float | None,
    flat_threshold_pct: float,
) -> str:
    """Classify direction from trailing RoC windows. Uses the shortest
    available window preferentially (3m most responsive), falling back to
    6m then 12m when shorter windows are unavailable — this priority order
    is a DRAFT judgment call (the doc names all three windows but doesn't
    specify a priority when they disagree or when some are missing;
    documented here rather than in the YAML because it's pure mechanical
    plumbing, not a strategy threshold)."""
    roc = roc_3m if roc_3m is not None else (roc_6m if roc_6m is not None else roc_12m)
    if roc is None:
        return "flat"
    if abs(roc) < flat_threshold_pct:
        return "flat"
    return "rising" if roc > 0 else "falling"


def classify_momentum_of_momentum(
    roc_recent: float | None,
    roc_prior: float | None,
    stable_threshold_pct: float,
) -> str:
    """RoC-of-RoC: compare the most recent trailing-window RoC against the
    trailing RoC measured one window earlier. accelerating if the trend is
    speeding up in its own direction, decelerating if slowing, stable if
    the change is within stable_threshold_pct."""
    if roc_recent is None or roc_prior is None:
        return "stable"
    delta = roc_recent - roc_prior
    if abs(delta) < stable_threshold_pct:
        return "stable"
    # Accelerating means the magnitude of change is growing in the same
    # direction as the trend itself (both positive = speeding up rally;
    # both negative = speeding up decline). Decelerating = trend slowing,
    # including a sign flip (turning).
    if (roc_recent > 0 and delta > 0) or (roc_recent < 0 and delta < 0):
        return "accelerating"
    return "decelerating"


@dataclass
class DirectionReading:
    roc_3m: float | None
    roc_6m: float | None
    roc_12m: float | None
    direction: str          # "rising" | "falling" | "flat"
    momentum_state: str     # "accelerating" | "decelerating" | "stable"


def _direction_compatible(direction_rule: str, direction: str, momentum_state: str,
                           compatibility: dict[str, list[str]]) -> bool:
    """A phase's direction_rule is compatible with an observed
    (direction, momentum_state) reading if:
      - the plain compatibility map (framework.classification_rules.
        direction_compatibility) lists `direction` as accepted, AND
      - if the direction_rule itself encodes a momentum qualifier
        (falling_decelerating, rising_decelerating), momentum_state must
        match that qualifier too.
    """
    accepted_directions = compatibility.get(direction_rule, [])
    if direction not in accepted_directions:
        return False
    if direction_rule.endswith("_decelerating"):
        return momentum_state == "decelerating"
    if direction_rule == "turning_up":
        # turning_up accepts direction=rising outright, OR direction=falling
        # with momentum_state=accelerating-toward-zero i.e. decelerating
        # decline (DRAFT judgment call already documented in the YAML gap
        # note for the 15-20 band; kept lenient here to catch the early
        # inflection the doc describes ("price stops making new lows")).
        return direction == "rising" or (direction == "falling" and momentum_state == "decelerating")
    return True


def classify_phase(
    framework: CycleFramework,
    percentile: float,
    reading: DirectionReading,
) -> Phase:
    """Deterministically classify (percentile, direction) into one of the
    8 phases using cycle_framework.yaml's phases + classification_rules
    (see that file's extensive commentary on the two band-gap DRAFT
    judgment calls this implements: 45-55 and 15-20)."""
    phases = framework.phases
    compatibility = framework.classification_rules.direction_compatibility

    # Step 1: exact-band matches (percentile falls inside the phase's own
    # band) that are ALSO direction-compatible.
    exact_matches = [
        p for p in phases
        if p.percentile_band.min <= percentile <= p.percentile_band.max
        and _direction_compatible(p.direction_rule, reading.direction, reading.momentum_state, compatibility)
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        # Overlapping bands with multiple direction-compatible matches:
        # prefer the tightest (smallest band width) match — DRAFT judgment
        # call, no doc basis, included only so the function is total.
        return min(exact_matches, key=lambda p: p.percentile_band.max - p.percentile_band.min)

    # Step 1b: percentile is inside a band, but the ONLY matching band(s)
    # are direction-incompatible. Fall through to nearest-band resolution
    # below rather than returning a direction-incompatible phase.
    in_band = [
        p for p in phases
        if p.percentile_band.min <= percentile <= p.percentile_band.max
    ]

    # Step 2: nearest-band resolution (gap or direction-incompatible band).
    max_dist = framework.classification_rules.nearest_band_tiebreak_max_distance

    def _distance(p: Phase) -> float:
        if p.percentile_band.min <= percentile <= p.percentile_band.max:
            return 0.0
        if percentile < p.percentile_band.min:
            return p.percentile_band.min - percentile
        return percentile - p.percentile_band.max

    candidates = [p for p in phases if _distance(p) <= max_dist]
    if not candidates:
        candidates = in_band or phases  # last resort: whatever's in-band, else all phases

    direction_compatible_candidates = [
        p for p in candidates
        if _direction_compatible(p.direction_rule, reading.direction, reading.momentum_state, compatibility)
    ]
    pool = direction_compatible_candidates or candidates

    # Step 3: among the pool, pick nearest by distance; ties broken by
    # earlier phase_id ordinal (wheel order) — DRAFT judgment call per the
    # YAML's classification_rules commentary.
    phase_order = framework.phase_order()
    pool_sorted = sorted(pool, key=lambda p: (_distance(p), phase_order.index(p.phase_id)))
    return pool_sorted[0]
