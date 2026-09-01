"""Point-in-time universe construction — who was investable on a given day.

Removing survivorship bias needs three things to be true at once, and getting
only two of them right leaves the result just as wrong:

1. the index must contain the companies that were dropped, not just the ones
   that survived — :mod:`scraper.index_membership` supplies that;
2. those companies must have prices, including after they stopped existing —
   :mod:`scraper.bhavcopy` supplies that;
3. companies must not appear *before* they belonged there.

Point 3 is the one that bites. The membership dataset reconstructs history by
walking reconstitution press releases backwards from today's list, so it knows
exits precisely but has to guess entries: any member whose joining event
predates its press-release coverage is stamped ``snapshot_floor`` and
back-dated to 2014-01-01. On 2014-03-31 that is 505 of 516 names. ALKEM (listed
December 2015), ANGELONE (2021) and 360ONE (2019) all claim to be 2014
constituents.

Left alone that swaps survivorship bias for look-ahead bias, which flatters
returns just as badly: every back-dated name is by definition one that grew
enough to enter the index later, so the 2014 portfolio gets pre-selected
winners.

The fix is to trust the dataset only where it is an observation (exits) and to
re-derive entries from the market tape, which cannot look ahead:

    universe(t) = members(t) ∩ traded_on(t) ∩ top-N of the whole market by
                  trailing turnover as at t

The traded gate removes companies that were not listed yet. The turnover gate
removes companies that were listed but far too small to have been in a top-500
index — using only bars dated on or before ``t``. NSE ranks constituents by
full market capitalisation, which needs shares outstanding that this project
does not store; turnover is the closest honest proxy and is what an investor
could actually have observed.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from scraper.index_membership import DEFAULT_INDEX, members_on

#: Trading days of turnover history used to rank liquidity. ~6 months.
DEFAULT_LOOKBACK_DAYS = 182

#: How many names of the whole market are treated as index-eligible.
#:
#: Calibrated, not guessed. Turnover is only a proxy for the free-float market
#: cap the index actually ranks on, so the cutoff was chosen on the years where
#: membership is press-release accurate (2022-2025) and the answer is therefore
#: already known: whatever value is picked must leave that period essentially
#: untouched, otherwise the gate is inventing a different distortion instead of
#: removing one. Measured retention of a known-correct 500-name list:
#:
#:     top_n     2022    2024    2025
#:       500      390     400     415
#:       600      436     437     457
#:       900      497     495     496
#:      1200      500     499     498
#:
#: 600 discards ~12% of names that provably belonged to the index, so it is
#: wrong. 1200 is a no-op and cannot restrain the back-dated early years. 900
#: keeps >=99% of a verified list while still excluding the genuinely illiquid
#: tail, so it is the loosest cutoff that does real work.
DEFAULT_MARKET_RANK = 900

#: A name needs this many sessions in the window to be ranked at all, which
#: keeps freshly listed tickers from topping the table on IPO-day turnover.
DEFAULT_MIN_SESSIONS = 30


def market_liquidity_rank(
    connection: sqlite3.Connection,
    as_of: date,
    *,
    top_n: int = DEFAULT_MARKET_RANK,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_sessions: int = DEFAULT_MIN_SESSIONS,
) -> List[str]:
    """Most-traded symbols in the whole cash market as at ``as_of``.

    Ranked by average daily turnover over the trailing window. Uses only bars
    dated on or before ``as_of``, so it is safe to call inside a backtest loop.
    """
    start = (as_of - timedelta(days=lookback_days)).isoformat()
    rows = connection.execute(
        "SELECT symbol, AVG(turnover) AS adt, COUNT(*) AS n "
        "FROM market_bars WHERE trade_date > ? AND trade_date <= ? "
        "AND turnover > 0 GROUP BY symbol HAVING n >= ? "
        "ORDER BY adt DESC LIMIT ?",
        (start, as_of.isoformat(), min_sessions, top_n),
    ).fetchall()
    return [row[0] for row in rows]


def last_traded_on_or_before(
    connection: sqlite3.Connection, as_of: date, *, within_days: int = 10
) -> Set[str]:
    """Symbols with a bar in the days up to ``as_of``.

    A window rather than an exact date, so that a symbol that simply did not
    trade on one illiquid session is not mistaken for a delisting.
    """
    start = (as_of - timedelta(days=within_days)).isoformat()
    return {
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT symbol FROM market_bars "
            "WHERE trade_date > ? AND trade_date <= ?",
            (start, as_of.isoformat()),
        )
    }


def pit_universe(
    connection: sqlite3.Connection,
    as_of: date,
    *,
    index_name: str = DEFAULT_INDEX,
    top_n: int = DEFAULT_MARKET_RANK,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_sessions: int = DEFAULT_MIN_SESSIONS,
    apply_liquidity_gate: bool = True,
) -> Set[str]:
    """The investable universe on ``as_of``, free of both bias directions."""
    members = members_on(connection, as_of, index_name=index_name)
    if not members:
        return set()
    listed = last_traded_on_or_before(connection, as_of)
    universe = members & listed
    if not apply_liquidity_gate:
        return universe
    eligible = set(
        market_liquidity_rank(
            connection,
            as_of,
            top_n=top_n,
            lookback_days=lookback_days,
            min_sessions=min_sessions,
        )
    )
    return universe & eligible


def universe_diagnostics(
    connection: sqlite3.Connection,
    as_of: date,
    *,
    index_name: str = DEFAULT_INDEX,
    top_n: int = DEFAULT_MARKET_RANK,
) -> Dict[str, int]:
    """Where names are lost between the raw dataset and the final universe."""
    members = members_on(connection, as_of, index_name=index_name)
    listed = last_traded_on_or_before(connection, as_of)
    tradable = members & listed
    eligible = set(market_liquidity_rank(connection, as_of, top_n=top_n))
    return {
        "members": len(members),
        "not_listed": len(members - listed),
        "tradable": len(tradable),
        "below_liquidity": len(tradable - eligible),
        "universe": len(tradable & eligible),
    }


class PitUniverse:
    """Caching wrapper — a backtest asks for the universe on many dates."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        index_name: str = DEFAULT_INDEX,
        top_n: int = DEFAULT_MARKET_RANK,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        apply_liquidity_gate: bool = True,
    ) -> None:
        self.connection = connection
        self.index_name = index_name
        self.top_n = top_n
        self.lookback_days = lookback_days
        self.apply_liquidity_gate = apply_liquidity_gate
        self._cache: Dict[date, Set[str]] = {}

    def on(self, as_of: date) -> Set[str]:
        # Resolved to the start of the month: NIFTY 500 reconstitutes twice a
        # year and liquidity ranks drift slowly, so a monthly refresh loses no
        # real resolution while keeping the number of scans small.
        #
        # The universe is computed *at* the month start rather than at the
        # requested date, so the answer does not depend on which date in the
        # month happened to be asked first. Using the older date also means the
        # gate can only ever be stale, never forward-looking.
        key = as_of.replace(day=1)
        cached = self._cache.get(key)
        if cached is None:
            cached = pit_universe(
                self.connection,
                key,
                index_name=self.index_name,
                top_n=self.top_n,
                lookback_days=self.lookback_days,
                apply_liquidity_gate=self.apply_liquidity_gate,
            )
            self._cache[key] = cached
        return cached

    def contains(self, symbol: str, as_of: Optional[date]) -> bool:
        if as_of is None:
            return True
        return symbol in self.on(as_of)
