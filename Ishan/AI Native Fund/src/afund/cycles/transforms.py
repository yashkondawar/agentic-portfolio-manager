"""Orientation transforms (cycle_framework.yaml `orientations` section;
source doc section 2.2).

Pure functions — no I/O, no DB, no registry/knowledge reads. Callers pass in
already-fetched raw values plus whatever band/config the transform needs.
"""
from __future__ import annotations


def value_type_score(percentile: float) -> float:
    """High reading = expensive/late-cycle. Use the percentile as-is."""
    return percentile


def fear_type_invert(percentile: float) -> float:
    """High reading = distressed = early-cycle opportunity. Invert so a
    high raw fear percentile maps to a LOW transformed percentile (reads
    like "cheap"/early-cycle) once run through the same 8-phase wheel as
    value-type metrics. p -> 100 - p."""
    return 100.0 - percentile


def goldilocks_distance_score(value: float, band_min: float, band_max: float) -> float:
    """Score a goldilocks-type metric by its distance outside a target
    band. 0 if inside the band; positive distance (in the metric's native
    units) if outside on either side, since both extremes are equally
    late-cycle stress (source doc section 2.2). This is NOT a percentile —
    callers combine it with the metric's own percentile-of-distance
    computed over the historical distance series, exactly like any other
    anchor (see classify.percentile_rank applied to a distance series)."""
    if value < band_min:
        return band_min - value
    if value > band_max:
        return value - band_max
    return 0.0


def apply_orientation(raw_percentile: float, orientation: str) -> float:
    """Dispatch to the correct transform given an orientation string
    ("value_type" | "fear_type"). goldilocks_type is handled separately
    (goldilocks_distance_score) because it needs the raw value + band, not
    a raw percentile — callers must percentile-rank the *distance* series,
    not the raw metric, for goldilocks-type KPIs."""
    if orientation == "value_type":
        return value_type_score(raw_percentile)
    if orientation == "fear_type":
        return fear_type_invert(raw_percentile)
    raise ValueError(
        f"apply_orientation only accepts value_type|fear_type, got {orientation!r}; "
        f"goldilocks_type must use goldilocks_distance_score + percentile_rank of the distance series"
    )
