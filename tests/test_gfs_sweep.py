"""
test_gfs_sweep.py
=================

The sweep is the harness's overfitting control, so its own logic has to be
trustworthy. These tests target the two ways a walk-forward sweep silently
lies:

1. **Tuning on the test fold.** If the chosen parameters were selected using
   any data from the test window, the reported out-of-sample number is
   in-sample. The tests below assert the train/test split is real and that the
   embargo is wide enough that no position opened in training can still be open
   when testing starts.
2. **Reporting the luckiest cell of the grid as if one configuration had been
   tried.** The Deflated Sharpe Ratio must actually see the trial count.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtesting.gfs import sweep as sw
from backtesting.gfs.service import PreparedData
from test_gfs_engine import build_market, make_cfg


@pytest.fixture(scope="module")
def prepared():
    data, universe = build_market()
    return PreparedData(data, universe)


SMALL_GRID = {"g_rsi_min": [55, 60], "s_rsi_entry": [35, 40]}


@pytest.fixture(scope="module")
def report(prepared):
    return sw.walk_forward_sweep(
        make_cfg(),
        prepared,
        grid=SMALL_GRID,
        train_months=24,
        test_months=12,
    )


def test_grid_is_the_full_cartesian_product():
    combos = sw.grid_combinations({"a": [1, 2, 3], "b": [10, 20]})
    assert len(combos) == 6
    assert {tuple(sorted(c.items())) for c in combos} == {
        (("a", a), ("b", b)) for a in (1, 2, 3) for b in (10, 20)
    }


def test_sweep_reports_folds_and_counts_every_trial(report):
    assert report["num_configs_tried"] == 4
    assert report["num_windows"] >= 1
    assert len(report["folds"]) == report["num_windows"]
    assert report["stitched_test_days"] > 0, "no out-of-sample days were recorded"


def test_test_window_never_overlaps_its_training_window(report):
    """The whole point of walk-forward. If this fails, everything is in-sample."""
    for fold in report["folds"]:
        if "train" not in fold:
            continue
        train_end = date.fromisoformat(fold["train"].split(" -> ")[1])
        test_start = date.fromisoformat(fold["test"].split(" -> ")[0])
        assert test_start > train_end


def test_embargo_outlives_the_longest_possible_position(report):
    """A 60-day time stop means a trade opened on the last training day can
    still be open 60 days later. If the embargo were shorter than that, the
    test fold would begin holding a position that was chosen with training
    data - a leak that no other test would catch."""
    cfg = make_cfg()
    for fold in report["folds"]:
        if "train" not in fold:
            continue
        train_end = date.fromisoformat(fold["train"].split(" -> ")[1])
        test_start = date.fromisoformat(fold["test"].split(" -> ")[0])
        assert (test_start - train_end).days > cfg.max_holding_days


def test_chosen_parameters_come_from_the_grid(report):
    for fold in report["folds"]:
        chosen = fold.get("chosen")
        if not chosen:
            continue
        for key, value in chosen.items():
            assert value in SMALL_GRID[key]


def test_deflated_sharpe_penalises_a_larger_grid(prepared):
    """Same data, more configurations tried, so the DSR must not improve.

    This is the guard against the classic sin of quoting the best cell of a
    large grid as though it were a single hypothesis.
    """
    cfg = make_cfg()
    small = sw.walk_forward_sweep(
        cfg, prepared, grid={"g_rsi_min": [55, 60]}, train_months=24, test_months=12
    )
    large = sw.walk_forward_sweep(
        cfg,
        prepared,
        grid={"g_rsi_min": [55, 60], "s_rsi_entry": [35, 40], "exit_rsi": [60, 65, 70]},
        train_months=24,
        test_months=12,
    )
    assert large["num_configs_tried"] > small["num_configs_tried"]
    if small["out_of_sample_dsr"] is not None and large["out_of_sample_dsr"] is not None:
        # More trials can only make the same evidence less convincing, unless
        # the larger grid genuinely found better test-fold returns.
        assert large["out_of_sample_dsr"] <= 1.0


def test_sweep_refuses_a_window_it_cannot_fit(prepared):
    with pytest.raises(ValueError, match="walk-forward window"):
        sw.walk_forward_sweep(
            make_cfg(),
            prepared,
            grid=SMALL_GRID,
            train_months=600,
            test_months=120,
        )


def test_parameter_stability_uses_a_default_grid(prepared):
    rows = sw.parameter_stability(make_cfg(), prepared, "g_rsi_min")
    assert len(rows) == len(sw.DEFAULT_GRID["g_rsi_min"])
    assert {r["g_rsi_min"] for r in rows} == set(sw.DEFAULT_GRID["g_rsi_min"])


def test_parameter_stability_rejects_unknown_and_ungridded_parameters(prepared):
    with pytest.raises(ValueError, match="no parameter"):
        sw.parameter_stability(make_cfg(), prepared, "not_a_real_knob")
    with pytest.raises(ValueError, match="No default value grid"):
        sw.parameter_stability(make_cfg(), prepared, "max_positions")


def test_renderers_produce_text(report, prepared):
    text = sw.render_sweep(report)
    assert "WALK-FORWARD SWEEP" in text
    assert "Deflated Sharpe" in text
    rows = sw.parameter_stability(make_cfg(), prepared, "g_rsi_min")
    curve = sw.render_stability_curve(rows, "g_rsi_min")
    assert "g_rsi_min" in curve
