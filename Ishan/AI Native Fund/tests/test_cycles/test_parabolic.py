"""Parabolic Return Compression Rule tests (src/afund/cycles/parabolic.py;
cycle_framework.yaml parabolic_rule, source doc section 3)."""
from __future__ import annotations

import pytest

from afund.cycles import parabolic
from afund.cycles.framework import load as load_framework


@pytest.fixture(scope="module")
def fw():
    return load_framework()


def test_secondary_flat_trigger_fires_at_100pct(fw):
    # min_abs_return_pct = 100 (DRAFT): a 120% trailing 24m return fires
    # even with no long-run mean supplied.
    check = parabolic.check_parabolic(fw, trailing_window_return_pct=120.0)
    assert check.triggered
    assert check.action == "auto_trim_flag"
    assert "secondary trigger" in check.reason


def test_compression_trigger_fires_below_100pct(fw):
    # long-run mean 3%/yr x factor 20 = 60% threshold; 70% fires the
    # compression trigger even though it's under the flat 100% floor.
    check = parabolic.check_parabolic(
        fw, trailing_window_return_pct=70.0,
        long_run_annual_mean_return_pct=3.0, compression_factor=20.0,
    )
    assert check.triggered
    assert "compression trigger" in check.reason
    assert "secondary trigger" not in check.reason


def test_no_trigger_below_both_thresholds(fw):
    check = parabolic.check_parabolic(
        fw, trailing_window_return_pct=50.0,
        long_run_annual_mean_return_pct=3.0, compression_factor=20.0,
    )
    assert not check.triggered
    assert check.action is None
    assert "no trigger" in check.reason


def test_compression_not_evaluated_without_long_run_mean(fw):
    # 90% with no long-run mean: compression can't be evaluated (never
    # fabricated), and 90 < 100 so the secondary trigger stays quiet too.
    check = parabolic.check_parabolic(fw, trailing_window_return_pct=90.0)
    assert not check.triggered


def test_both_triggers_can_fire_together(fw):
    check = parabolic.check_parabolic(
        fw, trailing_window_return_pct=250.0,
        long_run_annual_mean_return_pct=8.0, compression_factor=20.0,
    )
    assert check.triggered
    assert "compression trigger" in check.reason
    assert "secondary trigger" in check.reason


def test_window_months_comes_from_framework(fw):
    check = parabolic.check_parabolic(fw, trailing_window_return_pct=10.0)
    assert check.window_months == fw.parabolic_rule.window_months == 24
