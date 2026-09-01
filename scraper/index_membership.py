"""Point-in-time index membership — who was actually in the index, and when.

The backtest's universe was, until now, *today's* NIFTY 500 projected
backwards. That is survivorship bias in its purest form: 500 companies that
made it, with the ones that were dropped, delisted or wound up quietly deleted
from history. Over 2014-2026 the NIFTY 500 actually contained **951** distinct
names, so nearly half the real universe was invisible — and the missing half is
systematically the losing half.

Membership intervals come from ``aditya-jha/nse-historical-membership`` (CC BY
4.0), which reconstructs them by walking NSE Indices' reconstitution press
releases backwards from the current published list. Measured against NSE's own
current constituent CSV it agrees on 497 of 500 names (99.4%). Events from 2017
are press-release backed; 2014-2016 intervals are anchored to a 2014-01-01
floor and are approximate, which is why the backtest should not start before
2014.

**Symbols are canonicalised to their present-day name.** The dataset says
ADANIENSOL was a member from 2014, but in 2015 that company traded as
ADANITRANS — so a naive symbol join silently loses every renamed company.
:func:`members_on` therefore resolves through **ISIN**, which is stable across
renames and is carried by both :mod:`scraper.bhavcopy` and the fundamentals
store, and returns the ticker as it traded on the day in question.

    uv run python -m scraper.index_membership --import   # load/refresh
    uv run python -m scraper.index_membership --status
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import requests

from core.storage import connect
from scraper import conn_cache

logger = logging.getLogger("scraper.index_membership")

MEMBERSHIP_URL = (
    "https://raw.githubusercontent.com/aditya-jha/nse-historical-membership/"
    "HEAD/index_history/data/index_membership_history.csv"
)

#: The index the qtr_results strategy screens.
DEFAULT_INDEX = "Nifty 500"

#: Intervals before this are anchored to a synthetic floor rather than to a
#: real reconstitution event, so treat membership as unreliable before it.
RELIABLE_FROM = date(2014, 1, 1)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_membership (
    index_name  TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    valid_from  TEXT NOT NULL,
    valid_to    TEXT,
    source      TEXT NOT NULL DEFAULT '',
    source_url  TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL,
    PRIMARY KEY (index_name, symbol, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_member_index ON index_membership (index_name);
CREATE INDEX IF NOT EXISTS idx_member_dates
    ON index_membership (index_name, valid_from, valid_to);
"""


def open_store(db_path: Optional[Path] = None) -> sqlite3.Connection:
    connection = connect(db_path)
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_date(raw) -> Optional[date]:
    token = (str(raw) if raw is not None else "").strip()
    if not token or token.lower() in {"nan", "none", "null"}:
        return None
    try:
        return date.fromisoformat(token[:10])
    except ValueError:
        return None


# ── import ───────────────────────────────────────────────────────────────────
def fetch_membership_csv(url: str = MEMBERSHIP_URL) -> List[dict]:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    text = resp.content.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def import_membership(
    connection: sqlite3.Connection,
    rows: Sequence[dict],
    *,
    indices: Optional[Sequence[str]] = None,
) -> int:
    """Replace stored intervals for the given indices with these rows."""
    wanted = {i.strip().lower() for i in indices} if indices else None
    payload = []
    now = _now()
    seen_indices: Set[str] = set()
    for row in rows:
        index_name = (row.get("index_name") or "").strip()
        if not index_name:
            continue
        if wanted is not None and index_name.lower() not in wanted:
            continue
        symbol = (row.get("symbol") or "").strip().upper()
        valid_from = _parse_date(row.get("valid_from"))
        if not symbol or valid_from is None:
            continue
        valid_to = _parse_date(row.get("valid_to"))
        seen_indices.add(index_name)
        payload.append((
            index_name, symbol, valid_from.isoformat(),
            valid_to.isoformat() if valid_to else None,
            (row.get("source") or "").strip(),
            (row.get("source_url") or "").strip(),
            now,
        ))
    if not payload:
        return 0
    for index_name in seen_indices:
        connection.execute(
            "DELETE FROM index_membership WHERE index_name = ?", (index_name,)
        )
    connection.executemany(
        "INSERT INTO index_membership (index_name, symbol, valid_from, "
        "valid_to, source, source_url, imported_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(index_name, symbol, valid_from) DO UPDATE SET "
        "valid_to = excluded.valid_to, source = excluded.source, "
        "source_url = excluded.source_url, imported_at = excluded.imported_at",
        payload,
    )
    connection.commit()
    return len(payload)


# ── identity: ISIN bridges renames ───────────────────────────────────────────
class _AliasIndex:
    """Symbol/ISIN cross-reference, built once per connection.

    Scanning ``market_bars`` for this costs seconds, and ``members_on`` is
    called once per rebalance date, so the maps are built lazily and cached on
    the connection rather than rebuilt per call.
    """

    __slots__ = ("by_symbol", "by_isin")

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.by_symbol: Dict[str, str] = {}
        self.by_isin: Dict[str, Set[str]] = {}
        for symbol, isin in connection.execute(
            "SELECT DISTINCT symbol, isin FROM market_bars WHERE isin <> ''"
        ):
            self.by_symbol.setdefault(symbol, isin)
            self.by_isin.setdefault(isin, set()).add(symbol)


def _aliases(connection: sqlite3.Connection) -> _AliasIndex:
    return conn_cache.cached(
        connection, "membership_aliases", lambda: _AliasIndex(connection)
    )


def isin_map(connection: sqlite3.Connection) -> Dict[str, str]:
    """``symbol -> ISIN``."""
    return _aliases(connection).by_symbol


def symbols_by_isin(connection: sqlite3.Connection) -> Dict[str, Set[str]]:
    """``ISIN -> every ticker it has ever traded under``."""
    return _aliases(connection).by_isin


def clear_alias_cache(connection: sqlite3.Connection = None) -> None:
    """Drop the cached cross-reference after new bars are written."""
    conn_cache.clear(connection, "membership_aliases")


def traded_on(connection: sqlite3.Connection, day: date) -> Set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT symbol FROM market_bars WHERE trade_date = ?",
            (day.isoformat(),),
        )
    }


# ── queries ──────────────────────────────────────────────────────────────────
def canonical_members_on(
    connection: sqlite3.Connection,
    day: date,
    *,
    index_name: str = DEFAULT_INDEX,
) -> Set[str]:
    """Members on a date, under the dataset's present-day symbol names."""
    iso = day.isoformat()
    return {
        row[0]
        for row in connection.execute(
            "SELECT symbol FROM index_membership WHERE index_name = ? "
            "AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)",
            (index_name, iso, iso),
        )
    }


def members_on(
    connection: sqlite3.Connection,
    day: date,
    *,
    index_name: str = DEFAULT_INDEX,
    resolve_renames: bool = True,
) -> Set[str]:
    """Members on a date, as the tickers they actually traded under that day.

    Without ``resolve_renames`` this returns present-day names, which will fail
    to match historical price and filing rows for any company that has since
    been renamed.
    """
    canonical = canonical_members_on(connection, day, index_name=index_name)
    if not resolve_renames or not canonical:
        return canonical
    live = traded_on(connection, day)
    if not live:
        return canonical
    aliases = _aliases(connection)
    by_symbol = aliases.by_symbol
    by_isin = aliases.by_isin
    out: Set[str] = set()
    for symbol in canonical:
        if symbol in live:
            out.add(symbol)
            continue
        isin = by_symbol.get(symbol)
        alias = (by_isin.get(isin, set()) & live) if isin else set()
        # A single ISIN trading under two tickers on one day does not happen in
        # the cash market, but pick deterministically if it ever does.
        out.add(sorted(alias)[0] if alias else symbol)
    return out


def membership_intervals(
    connection: sqlite3.Connection, *, index_name: str = DEFAULT_INDEX
) -> List[sqlite3.Row]:
    return list(
        connection.execute(
            "SELECT * FROM index_membership WHERE index_name = ? "
            "ORDER BY symbol, valid_from",
            (index_name,),
        )
    )


def coverage(connection: sqlite3.Connection) -> List[dict]:
    return [
        {
            "index": row[0],
            "intervals": row[1],
            "symbols": row[2],
            "first": row[3],
            "last": row[4],
            "current": row[5],
        }
        for row in connection.execute(
            "SELECT index_name, COUNT(*), COUNT(DISTINCT symbol), "
            "MIN(valid_from), MAX(valid_from), SUM(valid_to IS NULL) "
            "FROM index_membership GROUP BY index_name ORDER BY index_name"
        )
    ]


def print_status(connection: sqlite3.Connection) -> None:
    rows = coverage(connection)
    if not rows:
        print("\nNo membership imported yet. Run with --import.")
        return
    print(f"\nIndex membership: {len(rows)} indices.")
    for row in rows:
        print(
            f"  {row['index']:<28} {row['intervals']:>5} intervals, "
            f"{row['symbols']:>4} distinct symbols, "
            f"{row['current']:>4} current, from {row['first']}"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--import", dest="do_import", action="store_true",
        help="Download and load membership intervals.",
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--index", action="append", default=None,
        help="Limit the import to an index (repeatable). Default: all.",
    )
    parser.add_argument("--url", default=MEMBERSHIP_URL)
    parser.add_argument(
        "--on", default=None,
        help="Show membership on an ISO date, resolved to traded tickers.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    connection = open_store()
    try:
        if args.do_import:
            rows = fetch_membership_csv(args.url)
            logger.info("Fetched %d interval rows.", len(rows))
            stored = import_membership(connection, rows, indices=args.index)
            logger.info("Stored %d intervals.", stored)
        if args.on:
            day = date.fromisoformat(args.on)
            canonical = canonical_members_on(connection, day)
            resolved = members_on(connection, day)
            renamed = len(resolved - canonical)
            print(
                f"\n{DEFAULT_INDEX} on {day}: {len(canonical)} members "
                f"({renamed} resolved to a different historical ticker)"
            )
        print_status(connection)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
