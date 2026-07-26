"""
ranking.py
==========

Cross-sectional selection for the quarterly-results (PEAD) strategy.

The legacy engine buys **every** name that clears fixed absolute thresholds, up to
capacity caps. That makes the basket size and quality drift with the tape: a strong
earnings season fires 100 near-identical buys, a weak one fires three, and the bar
for "good" never adapts. A hedge-fund desk instead **ranks all of the day's
declarers against each other** and holds the top slice — self-normalizing to how
strong the season actually is.

This module turns a day's candidate result events into a ranked shortlist:

* :func:`composite_scores` — blends the surprise legs (SUE, declaration-day
  reaction) and a quality tilt into one comparable z-score per candidate. Leverage
  is demoted from a knife-edge *hard gate* (``debt/equity <= 0.05``) to a graded
  *tilt*, so it shapes weight instead of binary-rejecting on one fitted threshold.
* :func:`select_top` — picks the top-quantile (or top-N) by composite score,
  subject to the per-day cap.

Pure functions over plain dataclasses so they are trivially unit-testable and carry
no engine/portfolio state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from .signals import zscores


@dataclass
class Candidate:
    """One rankable result event with its raw signal legs (any may be ``None``)."""
    symbol: str
    sue: Optional[float] = None                 # standardized unexpected earnings
    reaction: Optional[float] = None            # declaration-day abnormal return
    strength_score: Optional[float] = None      # legacy composite (fallback signal)
    debt_to_equity: Optional[float] = None      # quality tilt input (lower = better)
    is_financial: bool = False                  # banks/NBFCs: skip the leverage tilt
    payload: object = None                      # opaque carry-through (the event, etc.)


@dataclass
class ScoredCandidate:
    symbol: str
    score: float
    sue_z: Optional[float]
    reaction_z: Optional[float]
    quality_z: Optional[float]
    payload: object = None


# Composite weights. SUE (the fundamental surprise) leads; the declaration-day
# reaction confirms it; the quality tilt is a light shaping term, NOT a gate.
DEFAULT_W_SUE = 0.5
DEFAULT_W_REACTION = 0.3
DEFAULT_W_QUALITY = 0.2


def _quality_raw(c: Candidate) -> Optional[float]:
    """Higher is better. Uses ``-log1p(debt/equity)`` so lower leverage scores
    higher with diminishing sensitivity; banks/NBFCs (structurally levered) and
    missing values contribute no tilt (``None``)."""
    if c.is_financial or c.debt_to_equity is None:
        return None
    de = max(float(c.debt_to_equity), 0.0)
    return -math.log1p(de)


def composite_scores(
    candidates: List[Candidate],
    *,
    w_sue: float = DEFAULT_W_SUE,
    w_reaction: float = DEFAULT_W_REACTION,
    w_quality: float = DEFAULT_W_QUALITY,
) -> List[ScoredCandidate]:
    """Blend each candidate's legs into one cross-sectional composite score.

    Every leg is z-scored **across the day's candidates** (via :func:`signals.zscores`)
    so heterogeneous units (a unitless SUE, a % reaction, a log-leverage tilt) become
    comparable, then summed with the given weights. A missing leg contributes ``0``
    (neutral) to that name rather than dropping it — a name with a strong SUE but no
    computable reaction is still rankable.

    Fallback: when SUE is unavailable for a name, the legacy ``strength_score`` is
    z-scored into the SUE slot so the ranker degrades gracefully to the old signal
    instead of discarding the candidate.
    """
    if not candidates:
        return []

    # SUE with legacy-strength fallback per name.
    sue_raw = [
        c.sue if c.sue is not None else c.strength_score for c in candidates
    ]
    sue_z = zscores(sue_raw)
    reaction_z = zscores([c.reaction for c in candidates])
    quality_z = zscores([_quality_raw(c) for c in candidates])

    scored: List[ScoredCandidate] = []
    for i, c in enumerate(candidates):
        sz = sue_z[i] or 0.0
        rz = reaction_z[i] or 0.0
        qz = quality_z[i] or 0.0
        score = w_sue * sz + w_reaction * rz + w_quality * qz
        scored.append(
            ScoredCandidate(
                symbol=c.symbol,
                score=score,
                sue_z=sue_z[i],
                reaction_z=reaction_z[i],
                quality_z=quality_z[i],
                payload=c.payload,
            )
        )
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def select_top(
    scored: List[ScoredCandidate],
    *,
    top_quantile: Optional[float] = None,
    top_n: Optional[int] = None,
    cap: Optional[int] = None,
    min_score: Optional[float] = None,
) -> List[ScoredCandidate]:
    """Take the best candidates by composite score.

    * ``top_quantile`` — keep the top fraction (e.g. ``0.2`` = top quintile). Rounded
      up so a tiny candidate set still yields at least one pick.
    * ``top_n`` — keep at most this many (applied after the quantile if both given).
    * ``cap`` — hard ceiling from the engine's remaining capacity / per-day limit.
    * ``min_score`` — optional floor; drop names below it even if they rank high in a
      uniformly weak field (lets a bad season deploy *less*, the whole point of a
      cross-sectional bar).

    ``scored`` is assumed already sorted (``composite_scores`` returns it sorted).
    """
    picks = list(scored)
    if min_score is not None:
        picks = [s for s in picks if s.score >= min_score]
    if top_quantile is not None and 0 < top_quantile < 1:
        k = max(1, math.ceil(len(picks) * top_quantile))
        picks = picks[:k]
    if top_n is not None:
        picks = picks[: max(top_n, 0)]
    if cap is not None:
        picks = picks[: max(cap, 0)]
    return picks
