"""Durable store for point-in-time quarterly results, whatever the source.

The screener.in cache is a single pickle of *current* fundamentals, which is
fine for a two-year window but wrong for a twelve-year backtest: it is
restated, and re-fetching it is cheap. This store is the opposite on both
counts. As-filed filings are immutable once published, and collecting a decade
of them is an hours-long scrape, so the data lands in the same durable SQLite
database the rest of the app uses (outside the repo, in the per-user data
directory) as ordinary rows rather than a blob.

Every source writes the *same* :class:`QuarterlyResult` shape into the *same*
table and is distinguished only by the ``source`` column. That is what makes
history appendable: NSE's as-filed archive covers Dec-2011 to Dec-2024 but
stops there, screener covers the last ~3 years including the current quarter,
and the two simply union into one continuous series with no bridging code.

Because the sources overlap and disagree, writes are ranked (:data:`SOURCE_RANK`).
As-filed always wins over restated, so re-importing screener can never quietly
overwrite a filing we scraped from the exchange, regardless of import order.

Two further consequences worth stating, because they are the whole point:

* **Resumable.** Every fetch attempt is recorded, successes and 404s alike, so
  an interrupted backfill restarts where it stopped instead of re-walking the
  archive. Re-running a completed window costs one index request.
* **Queryable.** Point-in-time lookups ("what had this symbol filed as of this
  date?") are an indexed query, not a full deserialise.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import fields as dataclass_fields
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from core.storage import connect
from scraper.nse_fundamentals import QuarterlyResult

logger = logging.getLogger("scraper.fundamentals_store")

#: Write precedence when two sources carry the same (symbol, quarter, basis).
#: As-filed exchange filings outrank screener, which serves restated figures —
#: a later restatement must never overwrite what the market actually saw. Any
#: source not listed here is treated as as-filed.
SOURCE_RANK = {"screener": 1}
_DEFAULT_RANK = 3


def _rank_sql(operand: str) -> str:
    """CASE expression ranking a source column, built from SOURCE_RANK."""
    whens = " ".join(
        f"WHEN {src!r} THEN {rank}" for src, rank in sorted(SOURCE_RANK.items())
    )
    return f"(CASE {operand} {whens} ELSE {_DEFAULT_RANK} END)"


# Numeric columns mirrored straight off QuarterlyResult.
_VALUE_COLUMNS = (
    "sales",
    "other_income",
    "expenses",
    "depreciation",
    "finance_costs",
    "operating_profit",
    "bank_operating_profit",
    "profit_before_tax",
    "tax_expense",
    "net_profit",
    "eps",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS quarterly_results (
    symbol                 TEXT    NOT NULL,
    period_end             TEXT    NOT NULL,
    consolidated           INTEGER NOT NULL,
    isin                   TEXT    NOT NULL DEFAULT '',
    company                TEXT    NOT NULL DEFAULT '',
    period_start           TEXT,
    quarter_label          TEXT,
    relating_to            TEXT    NOT NULL DEFAULT '',
    audited                TEXT    NOT NULL DEFAULT '',
    broadcast_at           TEXT,
    sales                  REAL,
    other_income           REAL,
    expenses               REAL,
    depreciation           REAL,
    finance_costs          REAL,
    operating_profit       REAL,
    bank_operating_profit  REAL,
    profit_before_tax      REAL,
    tax_expense            REAL,
    net_profit             REAL,
    eps                    REAL,
    source                 TEXT    NOT NULL DEFAULT '',
    url                    TEXT    NOT NULL DEFAULT '',
    fetched_at             TEXT    NOT NULL,
    PRIMARY KEY (symbol, period_end, consolidated)
);

-- Point-in-time lookups filter on when the market learned the number, so the
-- broadcast timestamp is the useful index, not the period.
CREATE INDEX IF NOT EXISTS idx_qr_symbol_broadcast
    ON quarterly_results (symbol, broadcast_at);
CREATE INDEX IF NOT EXISTS idx_qr_quarter
    ON quarterly_results (quarter_label);
CREATE INDEX IF NOT EXISTS idx_qr_source
    ON quarterly_results (source);

-- Fetch ledger, so a resumed backfill skips work it already did. 404s are
-- recorded too: roughly 15% of pre-2019 archive links belong to renamed or
-- delisted issuers and will never resolve, and retrying them every run would
-- dominate the scrape. This is NSE scrape bookkeeping, not history, so it
-- stays source-specific.
CREATE TABLE IF NOT EXISTS nse_filing_attempts (
    url         TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL DEFAULT '',
    ok          INTEGER NOT NULL,
    attempted_at TEXT NOT NULL
);

-- Windows that were walked to completion, so a re-run is a no-op.
CREATE TABLE IF NOT EXISTS nse_backfill_windows (
    from_date   TEXT NOT NULL,
    to_date     TEXT NOT NULL,
    filings     INTEGER NOT NULL DEFAULT 0,
    stored      INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (from_date, to_date)
);
"""


def _migrate(connection: sqlite3.Connection) -> None:
    """Adopt the pre-rename NSE-only table, which held the original backfill.

    The table was called ``nse_quarterly_results`` when NSE was the only
    source. Renaming it in place keeps the 17k-filing backfill rather than
    forcing a re-scrape.
    """
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "nse_quarterly_results" in names and "quarterly_results" not in names:
        logger.info("Migrating nse_quarterly_results -> quarterly_results.")
        connection.execute(
            "ALTER TABLE nse_quarterly_results RENAME TO quarterly_results"
        )
        connection.commit()


def open_store(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open the shared database and make sure this module's tables exist."""
    connection = connect(db_path)
    _migrate(connection)
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def store_results(
    connection: sqlite3.Connection, results: Iterable[QuarterlyResult]
) -> int:
    """Upsert filings, respecting :data:`SOURCE_RANK`.

    A row is only overwritten by a source of equal or higher rank, so importing
    screener's restated figures can never clobber an as-filed exchange filing
    for the same quarter, no matter which import runs last. Returns the number
    of rows offered (not all of which necessarily win their conflict).
    """
    rows = []
    now = _now()
    for result in results:
        if result.period_end is None:
            continue
        rows.append(
            (
                result.symbol,
                _iso(result.period_end),
                1 if result.consolidated else 0,
                result.isin,
                result.company,
                _iso(result.period_start),
                result.quarter_label,
                result.relating_to,
                result.audited,
                _iso(result.broadcast_at),
                *(getattr(result, c) for c in _VALUE_COLUMNS),
                result.source,
                result.url,
                now,
            )
        )
    if not rows:
        return 0
    placeholders = ", ".join("?" * (10 + len(_VALUE_COLUMNS) + 3))
    connection.executemany(
        f"""
        INSERT INTO quarterly_results (
            symbol, period_end, consolidated, isin, company, period_start,
            quarter_label, relating_to, audited, broadcast_at,
            {", ".join(_VALUE_COLUMNS)},
            source, url, fetched_at
        ) VALUES ({placeholders})
        ON CONFLICT(symbol, period_end, consolidated) DO UPDATE SET
            isin=excluded.isin,
            company=excluded.company,
            period_start=excluded.period_start,
            quarter_label=excluded.quarter_label,
            relating_to=excluded.relating_to,
            audited=excluded.audited,
            broadcast_at=COALESCE(
                excluded.broadcast_at, quarterly_results.broadcast_at),
            {", ".join(f"{c}=excluded.{c}" for c in _VALUE_COLUMNS)},
            source=excluded.source,
            url=excluded.url,
            fetched_at=excluded.fetched_at
        WHERE {_rank_sql("excluded.source")}
              >= {_rank_sql("quarterly_results.source")}
        """,
        rows,
    )
    connection.commit()
    return len(rows)


def record_attempt(
    connection: sqlite3.Connection, url: str, symbol: str, ok: bool
) -> None:
    connection.execute(
        """
        INSERT INTO nse_filing_attempts (url, symbol, ok, attempted_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            ok=excluded.ok, attempted_at=excluded.attempted_at
        """,
        (url, symbol, 1 if ok else 0, _now()),
    )


def attempted_urls(connection: sqlite3.Connection) -> set:
    """Every URL already tried, successfully or not."""
    return {
        row["url"]
        for row in connection.execute("SELECT url FROM nse_filing_attempts")
    }


def mark_window(
    connection: sqlite3.Connection,
    from_date: date,
    to_date: date,
    filings: int,
    stored: int,
) -> None:
    connection.execute(
        """
        INSERT INTO nse_backfill_windows
            (from_date, to_date, filings, stored, completed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(from_date, to_date) DO UPDATE SET
            filings=excluded.filings,
            stored=excluded.stored,
            completed_at=excluded.completed_at
        """,
        (
            from_date.isoformat(),
            to_date.isoformat(),
            filings,
            stored,
            _now(),
        ),
    )
    connection.commit()


def completed_windows(connection: sqlite3.Connection) -> set:
    return {
        (row["from_date"], row["to_date"])
        for row in connection.execute(
            "SELECT from_date, to_date FROM nse_backfill_windows"
        )
    }


def _row_to_result(row: sqlite3.Row) -> QuarterlyResult:
    known = {f.name for f in dataclass_fields(QuarterlyResult)}
    kwargs = {k: row[k] for k in row.keys() if k in known}
    kwargs["consolidated"] = bool(row["consolidated"])
    for key in ("period_start", "period_end"):
        raw = kwargs.get(key)
        kwargs[key] = date.fromisoformat(raw) if raw else None
    raw = kwargs.get("broadcast_at")
    kwargs["broadcast_at"] = datetime.fromisoformat(raw) if raw else None
    return QuarterlyResult(**kwargs)


def load_results(
    connection: sqlite3.Connection,
    symbols: Optional[Sequence[str]] = None,
    sources: Optional[Sequence[str]] = None,
) -> List[QuarterlyResult]:
    """Read filings back, preferring the consolidated version of each quarter.

    ``sources`` restricts the read to specific ``source`` values, which is how
    a caller asks for "as-filed only" and refuses the restated tail.
    """
    query = "SELECT * FROM quarterly_results"
    params: List = []
    clauses: List[str] = []
    if symbols:
        wanted = [s.strip().upper() for s in symbols]
        clauses.append(f"symbol IN ({', '.join('?' * len(wanted))})")
        params.extend(wanted)
    if sources:
        clauses.append(f"source IN ({', '.join('?' * len(sources))})")
        params.extend(sources)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    # Consolidated last so it overwrites standalone in the dedupe below.
    query += " ORDER BY symbol, period_end, consolidated"
    return [_row_to_result(row) for row in connection.execute(query, params)]


def coverage(connection: sqlite3.Connection) -> Dict[str, object]:
    """Summary used to report backfill progress."""
    row = connection.execute(
        """
        SELECT COUNT(*) AS rows,
               COUNT(DISTINCT symbol) AS symbols,
               MIN(period_end) AS first_quarter,
               MAX(period_end) AS last_quarter,
               SUM(CASE WHEN broadcast_at IS NOT NULL THEN 1 ELSE 0 END) AS dated
        FROM quarterly_results
        """
    ).fetchone()
    out = dict(row) if row else {}
    out["by_source"] = {
        r["source"]: r["n"]
        for r in connection.execute(
            "SELECT source, COUNT(*) AS n FROM quarterly_results"
            " GROUP BY source ORDER BY n DESC"
        )
    }
    return out


