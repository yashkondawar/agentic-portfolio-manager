"""Earnings-season capital staggering.

An Indian quarter's entire opportunity set lands in a ~6-week burst: SEBI gives
listed companies 45 days from quarter end to declare, and in practice almost
nobody files before day 15. With a flat slot/cash cap the book therefore fills
on whoever declares FIRST, and every later declarer -- however much stronger --
is turned away with no slot and no cash. That is a calendar artefact, not a
selection decision.

The fix is to ration slots and capital across the window instead of spending
them in its first three days. Both ramp linearly from ``deploy_floor`` at the
START of the declaration window (quarter_end + ``lag_min``) to 1.0 at its END
(quarter_end + ``lag_max``).

The schedule depends only on the quarter-end date and the statutory lags, so it
is fully knowable on the day -- it never consults a future declaration and so
introduces no look-ahead into the backtest.

This module is the single source of truth for that maths. The live engine and
the backtest engine BOTH call it, so the two cannot drift apart: a change here
is a change to both. It deliberately lives in the live package because the
dependency direction is backtest -> live (the backtest already reads its growth
gates from ``qtr_results.config``), never the reverse.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Iterable, Optional

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def quarter_end_from_label(label: str) -> Optional[date]:
    """Parse a screener quarter column label like ``'Jun 2025'`` to a month end.

    Returns ``None`` for anything unparseable, so callers can fall back rather
    than crash on an unexpected label.
    """
    parts = (label or "").strip().split()
    if len(parts) != 2:
        return None
    mon = _MONTHS.get(parts[0][:3].lower())
    if mon is None:
        return None
    try:
        year = int(parts[1])
    except ValueError:
        return None
    if mon == 12:
        return date(year, 12, 31)
    return date(year, mon + 1, 1) - timedelta(days=1)


def season_progress(
    quarter_end: date, today: date, lag_min: int, lag_max: int
) -> float:
    """How far through its declaration window this quarter is, in ``[0, 1]``."""
    start = quarter_end + timedelta(days=lag_min)
    end = quarter_end + timedelta(days=lag_max)
    span = (end - start).days
    if span <= 0:
        return 1.0
    return min(max((today - start).days / span, 0.0), 1.0)


def deploy_factor(
    quarter_ends: Iterable[date],
    today: date,
    deploy_floor: float,
    lag_min: int,
    lag_max: int,
) -> float:
    """Fraction of slots/corpus usable today, given the quarters in play.

    Uses the MOST advanced quarter on the day, so a straggler still filing for
    an older quarter is never throttled by a fresher quarter's clock.

    A ``deploy_floor`` of 1.0 disables staggering entirely and restores the
    "deploy everything on the first declarers" behaviour.
    """
    floor = min(max(deploy_floor, 0.0), 1.0)
    if floor >= 1.0:
        return 1.0
    ends = [q for q in quarter_ends if q is not None]
    if not ends:
        return 1.0
    best = max(season_progress(q, today, lag_min, lag_max) for q in ends)
    return floor + (1.0 - floor) * best


def slot_cap(max_positions: int, factor: float) -> int:
    """Concurrent-position ceiling for today.

    Rounds UP and never returns 0: a partial slot is still a tradable slot, and
    stranding the whole book on a rounding error would be worse than the
    problem being solved.
    """
    if factor >= 1.0:
        return max_positions
    return max(1, math.ceil(max_positions * factor))
