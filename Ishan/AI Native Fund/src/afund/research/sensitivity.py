"""Pure EPS x PE sensitivity grid math for the buy_side agent.

The buy_side agent supplies 5 EPS scenarios and 5 PE scenarios (with
reasoning) but never does the multiplication itself — Python computes the
5x5 target-price grid deterministically here, and (optionally) percentage
upside/downside against the current price. No DB access, no I/O: these are
pure functions so they're trivially unit-testable and reusable from both
``src/afund/research/er_adapter.py``-style callers and ad hoc scripts.
"""
from __future__ import annotations


def grid(eps_scenarios: list[float], pe_scenarios: list[float]) -> list[list[float]]:
    """5x5 (or NxM) target-price grid: grid[i][j] = eps_scenarios[i] * pe_scenarios[j].

    Row index tracks eps_scenarios (ascending, worst-to-best EPS by
    convention), column index tracks pe_scenarios (ascending, de-rate to
    re-rate by convention) — callers decide the ordering; this function only
    multiplies.
    """
    return [[eps * pe for pe in pe_scenarios] for eps in eps_scenarios]


def pct_upside(grid_values: list[list[float]], current_price: float) -> list[list[float]]:
    """Elementwise % upside/downside of each grid cell vs current_price.

    Returns fractions (e.g. 0.25 for +25%), not percentages, matching the
    convention used elsewhere in this codebase (derive/returns.py etc).
    Raises ValueError if current_price is not strictly positive — a
    zero/negative price makes "% upside" meaningless rather than merely
    imprecise.
    """
    if current_price <= 0:
        raise ValueError(f"current_price must be > 0, got {current_price!r}")
    return [[(cell - current_price) / current_price for cell in row] for row in grid_values]
