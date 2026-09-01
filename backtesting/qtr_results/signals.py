"""
signals.py
==========

Earnings-*surprise* signals for the quarterly-results (PEAD) strategy.

The legacy playbook gates on ABSOLUTE growth (``yoy_profit >= 20%``). That is the
wrong economic object: +20% YoY when the market expected +40% is a *negative*
surprise and the stock falls. Post-earnings-announcement drift (PEAD; Ball & Brown
1968, Bernard & Thomas 1989, Sehgal & Bijoy 2015 for India) is driven by the
earnings *surprise vs expectation*, not the level of growth.

This module computes surprise from data the backtest already has — no analyst
consensus vendor required:

* :func:`compute_sue` — **Standardized Unexpected Earnings** (Foster-Olsen-Shevlin).
  A seasonal-random-walk-with-drift model forecasts this quarter's EPS from the
  same quarter a year ago plus the trailing drift; the surprise is standardized by
  the trailing volatility of those seasonal changes. This is the primary signal.
* :func:`announcement_reaction` — the **declaration-day abnormal return** (stock
  return minus benchmark return): the market's own read on the surprise, used as a
  confirming second leg (strong SUE *confirmed* by price is the high-quality decile;
  strong SUE *rejected* by price is a trap).
* :func:`zscores` — cross-sectional standardization used by :mod:`ranking` to blend
  the two legs plus a quality tilt into one comparable score.

All functions are **pure** and **point-in-time**: SUE consults only quarter columns
``<= q_idx``; the reaction consults only price rows ``<=`` the signal day (the caller
slices them that way). Missing / insufficient inputs return ``None`` so a data gap
never fabricates a signal (mirrors the debt-gate's data-gap-safe convention).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import pandas as pd

# Minimum trailing seasonal-change observations needed to standardize a surprise.
_MIN_SUE_OBS = 4


def _seasonal_deltas(
    eps: Dict[str, Optional[float]], quarters: List[str], up_to_idx: int
) -> List[float]:
    """Year-on-year EPS changes ``eps[i] - eps[i-4]`` for every quarter ``i`` in
    ``[4, up_to_idx]`` whose value and its seasonal base are both known.

    Point-in-time: the caller passes ``up_to_idx`` so no future quarter leaks in.
    """
    out: List[float] = []
    for i in range(4, up_to_idx + 1):
        cur = eps.get(quarters[i]) if 0 <= i < len(quarters) else None
        base = eps.get(quarters[i - 4]) if 0 <= i - 4 < len(quarters) else None
        if cur is None or base is None:
            continue
        out.append(float(cur) - float(base))
    return out


def compute_sue(
    eps: Dict[str, Optional[float]],
    quarters: List[str],
    q_idx: int,
    *,
    window: int = 8,
) -> Optional[float]:
    """Standardized Unexpected Earnings for the quarter at ``q_idx`` (point-in-time).

    Model (seasonal random walk with drift):

        deltaₜ      = EPSₜ − EPS₍ₜ₋₄₎                     # this quarter's YoY change
        driftₜ      = mean(delta over the trailing ``window`` quarters BEFORE t)
        surpriseₜ   = deltaₜ − driftₜ                     # unexpected earnings
        SUEₜ        = surpriseₜ / stdev(trailing deltas)  # standardized

    A positive SUE means EPS grew *more than* its own recent trend — the genuine
    positive surprise PEAD trades on. Standardizing by the company's own earnings
    volatility makes SUE comparable **across names** (a ₹2 beat in a steady utility
    is a bigger surprise than in a swingy commodity name), which is what a
    cross-sectional rank needs.

    Returns ``None`` when there are fewer than ``_MIN_SUE_OBS`` trailing seasonal
    changes or their dispersion is zero (can't standardize) — never fabricates a
    value on thin history.
    """
    if q_idx < 4 or q_idx >= len(quarters):
        return None
    cur = eps.get(quarters[q_idx])
    base = eps.get(quarters[q_idx - 4])
    if cur is None or base is None:
        return None
    delta_now = float(cur) - float(base)

    # Trailing seasonal changes STRICTLY BEFORE the current quarter.
    trailing = _seasonal_deltas(eps, quarters, q_idx - 1)
    if window > 0:
        trailing = trailing[-window:]
    if len(trailing) < _MIN_SUE_OBS:
        return None

    mean = sum(trailing) / len(trailing)
    var = sum((d - mean) ** 2 for d in trailing) / (len(trailing) - 1)
    std = math.sqrt(var)
    if std <= 0:
        return None
    return (delta_now - mean) / std


def announcement_reaction(
    stock_bars: Optional[pd.DataFrame],
    bench_bars: Optional[pd.DataFrame],
    *,
    lookback: int = 1,
) -> Optional[float]:
    """Declaration-day abnormal return: stock return minus benchmark return over
    the trailing ``lookback`` sessions, measured as-of the last row of each frame.

    Both frames must be sliced to rows ``<=`` the signal day (the first session
    on/after the real announcement), so the value is knowable at ranking time —
    entries only fill the NEXT open. A positive value means the market itself
    reacted well to the print, confirming the fundamental surprise.

    Returns ``None`` when either series is too short.
    """
    if stock_bars is None or len(stock_bars) < lookback + 1:
        return None
    if bench_bars is None or len(bench_bars) < lookback + 1:
        return None
    s = stock_bars["Close"].astype(float)
    b = bench_bars["Close"].astype(float)
    s0, s1 = float(s.iloc[-1 - lookback]), float(s.iloc[-1])
    b0, b1 = float(b.iloc[-1 - lookback]), float(b.iloc[-1])
    if s0 <= 0 or b0 <= 0:
        return None
    return (s1 / s0 - 1.0) - (b1 / b0 - 1.0)


def zscores(values: Sequence[Optional[float]]) -> List[Optional[float]]:
    """Cross-sectional z-scores of ``values``, preserving ``None`` in place.

    Standardizes over the non-missing entries: ``z = (v - mean) / std`` (sample
    std). Used to blend heterogeneous signal legs (SUE, reaction, quality) onto a
    common scale before they are summed into a composite rank. If fewer than two
    real values exist, or dispersion is zero, every real entry maps to ``0.0``
    (no information to rank on) and missing entries stay ``None``.
    """
    present = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(present) < 2:
        return [None if v is None else 0.0 for v in values]
    mean = sum(present) / len(present)
    var = sum((v - mean) ** 2 for v in present) / (len(present) - 1)
    std = math.sqrt(var)
    if std <= 0:
        return [None if v is None else 0.0 for v in values]
    out: List[Optional[float]] = []
    for v in values:
        if v is None or not math.isfinite(float(v)):
            out.append(None)
        else:
            out.append((float(v) - mean) / std)
    return out
