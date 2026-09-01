"""Signal construction for the ATH breakout sleeve.

Everything here is a pure function of a wide ``date x ticker`` close matrix, so
the rules can be unit-tested on a handful of hand-written prices without
touching the price store.

Two rules define an entry:

``breakout``
    Today's close is strictly above every close in the preceding ``lookback``
    sessions — a genuinely new one-year closing high, not merely a touch of it.

``near_lifetime_high``
    Today's close is at least ``floor`` of the highest close the stock has
    *ever* printed, today included. This is what keeps the sleeve out of names
    that are breaking a one-year high while still deep under an old peak, where
    the overhead supply the strategy is trying to avoid is exactly what is
    waiting above.

The lifetime high is expanding and therefore depends on how much history the
price store actually holds: truncating history raises the ratio and lets
through names the rule is meant to reject. Feed these functions the deepest
history available, not just the backtest window.
"""

from __future__ import annotations

import pandas as pd


def rolling_prior_high(closes: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Highest close over the ``lookback`` sessions *before* each row."""
    return closes.shift(1).rolling(lookback, min_periods=lookback).max()


def lifetime_high(closes: pd.DataFrame) -> pd.DataFrame:
    """Highest close up to and including each row."""
    return closes.cummax()


def breakout_matrix(closes: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """True where the close sets a new ``lookback``-session closing high."""
    return closes > rolling_prior_high(closes, lookback)


def lifetime_ratio(closes: pd.DataFrame) -> pd.DataFrame:
    """Close divided by the lifetime closing high; capped at 1.0 by design."""
    return closes / lifetime_high(closes)


def momentum(closes: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Simple price momentum over ``lookback`` sessions."""
    return closes / closes.shift(lookback) - 1.0


def entry_matrix(closes: pd.DataFrame, *, lookback: int, floor: float) -> pd.DataFrame:
    """True where a name is eligible to be bought at today's close."""
    eligible = breakout_matrix(closes, lookback) & (lifetime_ratio(closes) >= floor)
    return eligible.fillna(False)


_RANKERS = {
    "mom_3m": 63,
    "mom_6m": 126,
    "mom_12m": 252,
}


def ranking_matrix(closes: pd.DataFrame, rule: str, mom_lookback: int) -> pd.DataFrame:
    """The score candidates are sorted by, highest first.

    ``proximity`` prefers names closest to their lifetime high, which for a
    fresh breakout is a near-tie at 1.0; the momentum rules break the tie on
    trailing return instead, which is what the dossier used.
    """
    if rule == "proximity":
        return lifetime_ratio(closes)
    return momentum(closes, _RANKERS.get(rule, mom_lookback))
