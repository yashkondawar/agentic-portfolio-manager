"""Offline tests for afund.research.sensitivity — pure EPS x PE grid math
used by the buy_side agent's output. No DB, no filesystem, no LLM."""
from __future__ import annotations

import pytest

from afund.research.sensitivity import grid, pct_upside

EPS_SCENARIOS = [8.0, 9.0, 10.0, 11.0, 12.0]
PE_SCENARIOS = [15.0, 18.0, 20.0, 22.0, 25.0]


def test_grid_shape_is_5x5():
    g = grid(EPS_SCENARIOS, PE_SCENARIOS)
    assert len(g) == 5
    assert all(len(row) == 5 for row in g)


def test_grid_center_cell_matches_golden_value():
    # Center cell: eps[2]=10 * pe[2]=20 == 200 (the spec's golden test case).
    g = grid(EPS_SCENARIOS, PE_SCENARIOS)
    assert g[2][2] == 200


def test_grid_corner_cells():
    g = grid(EPS_SCENARIOS, PE_SCENARIOS)
    assert g[0][0] == pytest.approx(8.0 * 15.0)
    assert g[4][4] == pytest.approx(12.0 * 25.0)


def test_grid_is_pure_multiplication_row_major():
    g = grid(EPS_SCENARIOS, PE_SCENARIOS)
    for i, eps in enumerate(EPS_SCENARIOS):
        for j, pe in enumerate(PE_SCENARIOS):
            assert g[i][j] == pytest.approx(eps * pe)


def test_grid_handles_non_square_inputs():
    g = grid([10.0, 20.0], [1.0, 2.0, 3.0])
    assert len(g) == 2
    assert len(g[0]) == 3
    assert g[1][2] == pytest.approx(60.0)


def test_pct_upside_fractions_not_percentages():
    g = grid(EPS_SCENARIOS, PE_SCENARIOS)
    upside = pct_upside(g, current_price=200.0)
    # center cell (200) vs current_price (200) -> exactly 0.0 (no upside/downside)
    assert upside[2][2] == pytest.approx(0.0)
    # corner cell (8*15=120) vs 200 -> -0.4 (a fraction, not -40)
    assert upside[0][0] == pytest.approx((120.0 - 200.0) / 200.0)
    assert upside[0][0] == pytest.approx(-0.4)


def test_pct_upside_rejects_zero_price():
    g = grid(EPS_SCENARIOS, PE_SCENARIOS)
    with pytest.raises(ValueError):
        pct_upside(g, current_price=0.0)


def test_pct_upside_rejects_negative_price():
    g = grid(EPS_SCENARIOS, PE_SCENARIOS)
    with pytest.raises(ValueError):
        pct_upside(g, current_price=-10.0)
