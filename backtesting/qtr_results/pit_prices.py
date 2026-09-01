"""Point-in-time prices for the backtest, served from the whole-market tape.

Why this exists
---------------
The default :class:`PointInTimeData` downloads per-symbol history from
yfinance. That is fine for a live watchlist but it quietly ruins a long
backtest in two ways:

* **It cannot see the dead.** yfinance serves today's listed companies. Jet
  Airways, DHFL, Reliance Communications and every other name that failed are
  either missing or truncated, so the backtest silently skips exactly the
  positions that would have lost money. That is survivorship bias, and it is
  the single largest distortion in a long-horizon equity backtest.
* **Its history is not stable.** ``auto_adjust=True`` restates the whole series
  whenever a new corporate action lands, so the close for a past date changes
  depending on when it was fetched.

This module serves the same interface from the local NSE bhavcopy store, which
is a record of *every* symbol that traded on a given day, including the ones
that no longer exist. Raw exchange closes are never restated, so the series is
reproducible; the split and bonus adjustment is applied here, from filings we
parsed ourselves, and is therefore auditable.

One adjustment basis for every name
-----------------------------------
It is tempting to keep yfinance for the living and use the tape only for the
dead. Resist it: yfinance's adjusted closes fold dividends back into the price
while ours deliberately do not (the benchmark is a price index). Mixing them
would leave some holdings total-return and others price-return, so a strategy
could look good purely from which data source its picks happened to land in.
Every symbol is served from the same basis here, even where yfinance would
have worked.

Renames are stitched through ISIN
---------------------------------
The tape records the ticker of the day, so a renamed company arrives as two
disjoint stubs -- ``CROMPGREAV`` until 2016 and ``CGPOWER`` after it. Both
carry the same ISIN, so they are concatenated into one continuous series filed
under the name the company uses today, which is the name the fundamentals are
keyed by.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

from backtesting.swing_trading.data import PointInTimeData, _plain_symbol
from core import bars as bar_store
from scraper import conn_cache
from scraper.corporate_actions import adjustment_series, load_factors

logger = logging.getLogger(__name__)

#: A symbol needs at least this many sessions to be worth trading in a
#: backtest; below it the indicators cannot even warm up.
MIN_USABLE_ROWS = 60

_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _canonical_groups(
    connection: sqlite3.Connection,
) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    """Map each present-day ticker to every ticker its ISIN ever used.

    The name a company trades under today is the one the fundamentals use, so
    that is the key. Symbols with a blank ISIN (a handful of very old rows)
    stand alone rather than being pooled into one meaningless group.

    Memoised on the connection: the underlying scan costs ~100s on a 6M-row
    tape, and the answer only changes when new bars are imported.
    """
    cached = conn_cache.cached(
        connection,
        "pit_canonical_groups",
        lambda: _build_canonical_groups(connection),
    )
    return cached


def _build_canonical_groups(
    connection: sqlite3.Connection,
) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    last_seen: Dict[str, str] = {}
    by_isin: Dict[str, Set[str]] = {}
    isin_of: Dict[str, str] = {}
    for symbol, isin, last in connection.execute(
        "SELECT symbol, isin, MAX(trade_date) FROM market_bars GROUP BY symbol"
    ):
        last_seen[symbol] = last
        if isin:
            by_isin.setdefault(isin, set()).add(symbol)
            isin_of[symbol] = isin

    groups: Dict[str, Set[str]] = {}
    canonical_of: Dict[str, str] = {}
    for symbol in last_seen:
        peers = by_isin.get(isin_of.get(symbol, ""), {symbol})
        # The ticker still printing prices most recently is the live one.
        canonical = max(peers, key=lambda s: (last_seen[s], s))
        groups.setdefault(canonical, set()).update(peers)
        canonical_of[symbol] = canonical
    return groups, canonical_of


class MarketBarsPrices(PointInTimeData):
    """``PointInTimeData`` backed by the local bhavcopy tape.

    Drop-in for the engine: only loading is overridden, so ``as_of``,
    ``bar_on``, ``next_session`` and the rest keep their leak-free semantics.
    """

    def __init__(self, cache_dir, connection: sqlite3.Connection):
        super().__init__(cache_dir)
        self.connection = connection
        self.adjusted_symbols = 0
        self.renamed_symbols = 0

    def load_or_download(
        self,
        symbols: List[str],
        benchmark: str,
        start: date,
        end: date,
        warmup_days: int,
        use_cache: bool = True,
        chunk_size: int = 40,
    ) -> None:
        """Build adjusted frames from the tape; benchmark still comes from yf.

        ``symbols`` is treated as a *filter*, not a shopping list: a name is
        served if the exchange printed prices for it, and nothing is fetched
        over the network for equities.
        """
        dl_start = start - timedelta(days=warmup_days)
        dl_end = end + timedelta(days=2)
        wanted = {_plain_symbol(s).upper() for s in symbols}

        groups, canonical_of = _canonical_groups(self.connection)
        # Accept a request under a former name too, so the caller does not have
        # to know which era of the ticker it is asking about.
        targets = {
            canonical for symbol, canonical in canonical_of.items()
            if symbol in wanted or canonical in wanted
        }
        tickers: Set[str] = set()
        for canonical in targets:
            tickers.update(groups.get(canonical, {canonical}))

        rows = self._read_rows(tickers, dl_start, dl_end)
        factors = load_factors(self.connection, resolve_renames=True)

        self.frames = {}
        for canonical in sorted(targets):
            frame = self._build_frame(
                canonical, groups.get(canonical, {canonical}), rows, factors
            )
            if frame is not None:
                self.frames[canonical] = frame

        self.benchmark = bar_store.read_symbol(benchmark, dl_start, dl_end)
        self._trading_days = None
        logger.info(
            "Tape: %d / %d symbols usable, %d split/bonus adjusted, "
            "%d stitched across a rename.",
            len(self.frames), len(targets), self.adjusted_symbols,
            self.renamed_symbols,
        )

    def _read_rows(
        self, tickers: Iterable[str], start: date, end: date
    ) -> Dict[str, List[tuple]]:
        """Bars per ticker in the window.

        Queried per chunk of symbols rather than by scanning the window and
        filtering in Python: ``market_bars`` is keyed on ``(symbol,
        trade_date)``, so this rides the primary key instead of reading every
        row of a 6M-bar tape.
        """
        out: Dict[str, List[tuple]] = {}
        wanted = sorted(set(tickers))
        if not wanted:
            return out
        chunk = 400
        for index in range(0, len(wanted), chunk):
            batch = wanted[index:index + chunk]
            placeholders = ",".join("?" * len(batch))
            cursor = self.connection.execute(
                "SELECT symbol, trade_date, open, high, low, close, volume"
                f" FROM market_bars WHERE symbol IN ({placeholders})"
                " AND trade_date BETWEEN ? AND ?",
                (*batch, start.isoformat(), end.isoformat()),
            )
            for row in cursor:
                out.setdefault(row[0], []).append(tuple(row[1:]))
        return out

    def _build_frame(
        self,
        canonical: str,
        peers: Set[str],
        rows: Dict[str, List[tuple]],
        factors: Dict[str, List[Tuple[date, float]]],
    ) -> Optional[pd.DataFrame]:
        collected: List[tuple] = []
        for peer in peers:
            collected.extend(rows.get(peer, []))
        if len(collected) < MIN_USABLE_ROWS:
            return None
        collected.sort(key=lambda r: r[0])

        # A rename overlaps by a session or two while the tape switches over.
        deduped: Dict[str, tuple] = {}
        for row in collected:
            deduped[row[0]] = row
        ordered = [deduped[key] for key in sorted(deduped)]
        if len(ordered) < MIN_USABLE_ROWS:
            return None
        if len(peers) > 1 and any(rows.get(p) for p in peers - {canonical}):
            self.renamed_symbols += 1

        sessions = [date.fromisoformat(row[0]) for row in ordered]
        events = factors.get(canonical, [])
        series = adjustment_series(events, sessions)
        if any(value != 1.0 for value in series):
            self.adjusted_symbols += 1

        data = []
        for row, factor in zip(ordered, series):
            _, open_, high, low, close, volume = row
            # Prices scale down going back through a split; share counts scale
            # up by the same amount, which keeps Close * Volume -- the
            # liquidity filter the strategy actually uses -- invariant.
            inverse = (1.0 / factor) if factor else 1.0
            data.append((
                _scale(open_, factor), _scale(high, factor),
                _scale(low, factor), _scale(close, factor),
                _scale(volume, inverse),
            ))
        frame = pd.DataFrame(
            data,
            columns=_COLUMNS,
            index=pd.DatetimeIndex([pd.Timestamp(d) for d in sessions]),
        )
        return frame.dropna(subset=["Close"])


def _scale(value, factor: float):
    if value is None:
        return None
    return float(value) * factor


def available_symbols(
    connection: sqlite3.Connection, symbols: Sequence[str]
) -> List[str]:
    """Present-day names for whichever of ``symbols`` the tape can serve."""
    _, canonical_of = _canonical_groups(connection)
    wanted = {_plain_symbol(s).upper() for s in symbols}
    return sorted({
        canonical for symbol, canonical in canonical_of.items()
        if symbol in wanted or canonical in wanted
    })
