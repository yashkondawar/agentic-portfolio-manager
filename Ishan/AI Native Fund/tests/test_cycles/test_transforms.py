"""Orientation transform tests (src/afund/cycles/transforms.py; source doc
section 2.2 / cycle_framework.yaml orientations)."""
from __future__ import annotations

import pytest

from afund.cycles import transforms


def test_value_type_is_identity():
    assert transforms.value_type_score(70.0) == 70.0
    assert transforms.value_type_score(0.0) == 0.0


def test_fear_type_inverts():
    # High raw fear percentile (distress spike) must read as LOW/cheap.
    assert transforms.fear_type_invert(80.0) == 20.0
    assert transforms.fear_type_invert(0.0) == 100.0
    assert transforms.fear_type_invert(100.0) == 0.0


def test_goldilocks_inside_band_is_zero():
    # CPI 4.5% inside RBI's 2-6 band -> no stress.
    assert transforms.goldilocks_distance_score(4.5, 2.0, 6.0) == 0.0
    # boundary values count as inside (inclusive).
    assert transforms.goldilocks_distance_score(2.0, 2.0, 6.0) == 0.0
    assert transforms.goldilocks_distance_score(6.0, 2.0, 6.0) == 0.0


def test_goldilocks_both_extremes_positive_distance():
    # Both extremes are late-cycle stress of equal severity (doc 2.2):
    # 1pp below the floor and 1pp above the ceiling score identically.
    below = transforms.goldilocks_distance_score(1.0, 2.0, 6.0)
    above = transforms.goldilocks_distance_score(7.0, 2.0, 6.0)
    assert below == 1.0
    assert above == 1.0
    assert below == above


def test_apply_orientation_dispatch():
    assert transforms.apply_orientation(70.0, "value_type") == 70.0
    assert transforms.apply_orientation(70.0, "fear_type") == 30.0


def test_apply_orientation_rejects_goldilocks():
    # goldilocks_type needs the raw value + band (distance series), not a
    # percentile — dispatching it through apply_orientation is a caller bug.
    with pytest.raises(ValueError):
        transforms.apply_orientation(50.0, "goldilocks_type")
