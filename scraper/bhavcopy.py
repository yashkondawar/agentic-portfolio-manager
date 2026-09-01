"""Point-in-time daily bars for the entire NSE cash market.

Every other price path in this project asks "give me prices for these symbols",
which quietly bakes in survivorship bias: the symbol list can only ever be
*today's* list, so companies that were listed and investable in 2015 but have
since merged or been delisted are invisible. A backtest built that way never
buys DHFL at 609 and rides it to 17, never holds JETAIRWAYS to zero, and so
reports a return no one could have earned.

NSE's daily *bhavcopy* is the fix. It is a per-session dump of every instrument
that traded that day, published since 2000, so it answers the opposite and much
more useful question: "what was listed, and at what price, on this date?" Dead
companies are in it, at the prices they actually traded at, right up to their
last session.

Two formats, transparently handled:

* **Legacy** (2000 → mid-2024) ``cm<DDMONYYYY>bhav.csv.zip`` under
  ``/content/historical/EQUITIES/<YYYY>/<MON>/``.
* **UDiFF** (2024 →) ``BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip``.

Both are normalised onto one row shape, so the seam is invisible to callers —
the same principle the fundamentals store uses for NSE vs screener.

Caveat worth stating loudly: **these prices are not adjusted for corporate
actions.** ``PREVCLOSE`` is the raw prior close, so a 1:2 split shows up as a
-50% day. See :mod:`scraper.corporate_actions`, which derives the adjustment
factors this data needs before it can be used for returns.

This lands in ``market_bars``, deliberately separate from the app's existing
``daily_bars``. The two are not interchangeable: ``daily_bars`` is a per-symbol
cache of *adjusted* yfinance series for names someone asked about, whereas this
is the *raw, unadjusted, whole-market* session record. Merging them would mix
adjusted and unadjusted prices in one column, which is precisely the kind of
silent error this work exists to remove.

    uv run python -m scraper.bhavcopy --from 2013-01-01   # backfill/resume
    uv run python -m scraper.bhavcopy --status            # coverage report
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sqlite3
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from core.storage import connect
from scraper import conn_cache

logger = logging.getLogger("scraper.bhavcopy")

_BASE = "https://www.nseindia.com"
_LEGACY_HOST = "https://archives.nseindia.com"
_UDIFF_HOST = "https://nsearchives.nseindia.com"
_REPORTS_PAGE = f"{_BASE}/all-reports"

#: Cash-market series we keep. ``EQ`` is the normal rolling segment; ``BE`` is
#: trade-to-trade (delivery-only), where surveillance-flagged names land — a
#: stock sliding toward delisting often spends its final months in ``BE``, so
#: dropping it would reintroduce exactly the bias this module exists to remove.
EQUITY_SERIES = ("EQ", "BE")

#: NSE tolerates a brisk pace; this leaves headroom. One request per
#: session-day.
MIN_REQUEST_INTERVAL = 0.25

_MONTHS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)

#: First session available in the UDiFF feed. Before this, only legacy exists.
UDIFF_FROM = date(2024, 1, 1)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _REPORTS_PAGE,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_bars (
    symbol      TEXT NOT NULL,
    trade_date  TEXT NOT NULL,
    series      TEXT NOT NULL DEFAULT '',
    isin        TEXT NOT NULL DEFAULT '',
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    prev_close  REAL,
    volume      REAL,
    turnover    REAL,
    trades      REAL,
    source      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (symbol, trade_date)
);

-- "What was listed on this date?" is the whole point, so date leads.
CREATE INDEX IF NOT EXISTS idx_bars_date   ON market_bars (trade_date);
CREATE INDEX IF NOT EXISTS idx_bars_isin   ON market_bars (isin);

-- Symbol/ISIN cross-references drive the rename bridge, and every one of them
-- reads (symbol, isin) for the whole tape. Without an index that pulls the
-- ISIN off the row itself, which is a full scan of ~6M rows and costs ~100s.
-- trade_date is the third column so "latest ISIN per symbol" -- the question
-- the rename bridge actually asks -- is answered from the index alone (~2s)
-- instead of falling back to the table for every group.
CREATE INDEX IF NOT EXISTS idx_bars_symbol_isin_date
    ON market_bars (symbol, isin, trade_date);

-- Session ledger, so a resumed backfill skips days it already has. Market
-- holidays are recorded with rows = 0 rather than left absent; otherwise every
-- re-run would re-request ~250 known-empty days per decade.
CREATE TABLE IF NOT EXISTS bhavcopy_days (
    trade_date  TEXT PRIMARY KEY,
    rows        INTEGER NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT '',
    fetched_at  TEXT NOT NULL
);
"""


def open_store(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open the shared database and ensure this module's tables exist."""
    connection = connect(db_path)
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── HTTP ─────────────────────────────────────────────────────────────────────
_session: Optional[requests.Session] = None
_bootstrapped_at = 0.0
_BOOTSTRAP_TTL = 600.0
_last_request = 0.0


def get_session() -> requests.Session:
    """Cookie-bootstrapped session.

    NSE serves 403 to cookieless archive hits.
    """
    global _session, _bootstrapped_at
    now = time.time()
    if _session is not None and (now - _bootstrapped_at) < _BOOTSTRAP_TTL:
        return _session
    sess = _session or requests.Session()
    sess.headers.update(_HEADERS)
    try:
        sess.get(f"{_BASE}/", timeout=20)
        sess.get(_REPORTS_PAGE, timeout=20)
        _bootstrapped_at = now
    except requests.RequestException as exc:
        logger.warning("NSE cookie bootstrap failed: %s", exc)
    _session = sess
    return sess


def _throttled_get(url: str, *, timeout: int = 40):
    global _last_request
    wait = MIN_REQUEST_INTERVAL - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()
    return get_session().get(url, timeout=timeout)


def legacy_url(day: date) -> str:
    mon = _MONTHS[day.month - 1]
    return (
        f"{_LEGACY_HOST}/content/historical/EQUITIES/{day.year}/{mon}/"
        f"cm{day:%d}{mon}{day.year}bhav.csv.zip"
    )


def udiff_url(day: date) -> str:
    return (
        f"{_UDIFF_HOST}/content/cm/"
        f"BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    )


def _unzip_csv(payload: bytes) -> Optional[List[dict]]:
    if payload[:2] != b"PK":
        return None
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
        name = archive.namelist()[0]
        text = archive.read(name).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, IndexError, OSError) as exc:
        logger.warning("bhavcopy unzip failed: %s", exc)
        return None
    return list(csv.DictReader(io.StringIO(text)))


def _num(raw) -> Optional[float]:
    if raw is None:
        return None
    token = str(raw).strip().replace(",", "")
    if not token or token in {"-", "NA", "null"}:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _clean(raw) -> str:
    return (str(raw) if raw is not None else "").strip()


def parse_legacy(rows: Sequence[dict], day: date) -> List[tuple]:
    """Normalise the pre-2024 layout onto the common row shape."""
    keep = set(EQUITY_SERIES)
    out = []
    for row in rows:
        series = _clean(row.get("SERIES")).upper()
        if series not in keep:
            continue
        symbol = _clean(row.get("SYMBOL")).upper()
        if not symbol:
            continue
        out.append((
            symbol, day.isoformat(), series, _clean(row.get("ISIN")).upper(),
            _num(row.get("OPEN")), _num(row.get("HIGH")), _num(row.get("LOW")),
            _num(row.get("CLOSE")), _num(row.get("PREVCLOSE")),
            _num(row.get("TOTTRDQTY")), _num(row.get("TOTTRDVAL")),
            _num(row.get("TOTALTRADES")), "legacy",
        ))
    return out


def parse_udiff(rows: Sequence[dict], day: date) -> List[tuple]:
    """Normalise the 2024+ UDiFF layout onto the common row shape."""
    keep = set(EQUITY_SERIES)
    out = []
    for row in rows:
        # UDiFF carries derivatives too; equities are the STK instrument type.
        if _clean(row.get("FinInstrmTp")).upper() not in {"STK", ""}:
            continue
        series = _clean(row.get("SctySrs")).upper()
        if series not in keep:
            continue
        symbol = _clean(row.get("TckrSymb")).upper()
        if not symbol:
            continue
        out.append((
            symbol, day.isoformat(), series, _clean(row.get("ISIN")).upper(),
            _num(row.get("OpnPric")), _num(row.get("HghPric")),
            _num(row.get("LwPric")), _num(row.get("ClsPric")),
            _num(row.get("PrvsClsgPric")), _num(row.get("TtlTradgVol")),
            _num(row.get("TtlTrfVal")), _num(row.get("TtlNbOfTxsExctd")),
            "udiff",
        ))
    return out


def fetch_day(day: date) -> Tuple[List[tuple], str]:
    """Fetch one session, trying the format most likely to exist first.

    Returns ``(rows, source)``. An empty list with source ``"holiday"`` means
    both formats returned 404 — almost always a market holiday, occasionally a
    genuine archive gap. Either way there is nothing to retry.
    """
    orders = (
        (
            ("udiff", udiff_url, parse_udiff),
            ("legacy", legacy_url, parse_legacy),
        )
        if day >= UDIFF_FROM
        else (
            ("legacy", legacy_url, parse_legacy),
            ("udiff", udiff_url, parse_udiff),
        )
    )
    for name, build_url, parse in orders:
        url = build_url(day)
        try:
            resp = _throttled_get(url)
        except requests.RequestException as exc:
            logger.warning("%s %s failed: %s", name, day, exc)
            continue
        if resp.status_code != 200:
            continue
        rows = _unzip_csv(resp.content)
        if rows is None:
            continue
        parsed = parse(rows, day)
        if parsed:
            return parsed, name
    return [], "holiday"


# ── storage ──────────────────────────────────────────────────────────────────
_INSERT = """
INSERT INTO market_bars (
    symbol, trade_date, series, isin, open, high, low, close,
    prev_close, volume, turnover, trades, source
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(symbol, trade_date) DO UPDATE SET
    series     = excluded.series,
    isin       = CASE WHEN excluded.isin <> '' THEN excluded.isin
                      ELSE market_bars.isin END,
    open       = excluded.open,
    high       = excluded.high,
    low        = excluded.low,
    close      = excluded.close,
    prev_close = excluded.prev_close,
    volume     = excluded.volume,
    turnover   = excluded.turnover,
    trades     = excluded.trades,
    source     = excluded.source
"""


def store_bars(connection: sqlite3.Connection, rows: Sequence[tuple]) -> int:
    if not rows:
        return 0
    connection.executemany(_INSERT, rows)
    # Symbol/ISIN lookups derived from the tape are memoised per connection;
    # a new session can introduce a ticker or a rename, so drop them.
    conn_cache.clear(connection)
    return len(rows)


def mark_day(
    connection: sqlite3.Connection, day: date, rows: int, source: str
) -> None:
    connection.execute(
        "INSERT INTO bhavcopy_days (trade_date, rows, source, fetched_at) "
        "VALUES (?,?,?,?) ON CONFLICT(trade_date) DO UPDATE SET "
        "rows = excluded.rows, source = excluded.source, "
        "fetched_at = excluded.fetched_at",
        (day.isoformat(), rows, source, _now()),
    )


def fetched_days(connection: sqlite3.Connection) -> Dict[str, int]:
    return {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT trade_date, rows FROM bhavcopy_days"
        )
    }


def sessions(
    connection: sqlite3.Connection, start: date, end: date
) -> List[date]:
    """Trading days that actually produced rows, in order."""
    return [
        date.fromisoformat(row[0])
        for row in connection.execute(
            "SELECT trade_date FROM bhavcopy_days WHERE rows > 0 "
            "AND trade_date BETWEEN ? AND ? ORDER BY trade_date",
            (start.isoformat(), end.isoformat()),
        )
    ]


def listed_on(connection: sqlite3.Connection, day: date) -> List[str]:
    """Symbols that traded on a given session."""
    return [
        row[0]
        for row in connection.execute(
            "SELECT symbol FROM market_bars WHERE trade_date = ? "
            "ORDER BY symbol",
            (day.isoformat(),),
        )
    ]


def load_bars(
    connection: sqlite3.Connection,
    symbols: Optional[Sequence[str]] = None,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Dict[str, List[sqlite3.Row]]:
    """Bars grouped by symbol, ascending by date."""
    clauses, params = [], []
    if start is not None:
        clauses.append("trade_date >= ?")
        params.append(start.isoformat())
    if end is not None:
        clauses.append("trade_date <= ?")
        params.append(end.isoformat())
    if symbols:
        wanted = sorted({s.strip().upper() for s in symbols if s})
        clauses.append(f"symbol IN ({','.join('?' * len(wanted))})")
        params.extend(wanted)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"SELECT * FROM market_bars {where} ORDER BY symbol, trade_date",
        params,
    )
    out: Dict[str, List[sqlite3.Row]] = {}
    for row in cursor:
        out.setdefault(row["symbol"], []).append(row)
    return out


def coverage(connection: sqlite3.Connection) -> dict:
    row = connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(trade_date), "
        "MAX(trade_date) FROM market_bars"
    ).fetchone()
    days = connection.execute(
        "SELECT COUNT(*), SUM(rows > 0) FROM bhavcopy_days"
    ).fetchone()
    return {
        "bars": row[0] or 0,
        "symbols": row[1] or 0,
        "first": row[2],
        "last": row[3],
        "days_known": days[0] or 0,
        "days_traded": days[1] or 0,
    }


# ── backfill ─────────────────────────────────────────────────────────────────
def weekdays(start: date, end: date) -> Iterable[date]:
    day = start
    step = timedelta(days=1)
    while day <= end:
        if day.weekday() < 5:  # NSE trades Mon-Fri
            yield day
        day += step


def run(
    start: date,
    end: date,
    *,
    connection: Optional[sqlite3.Connection] = None,
    resume: bool = True,
    progress_every: int = 100,
) -> dict:
    """Download every session in the window, skipping days already recorded."""
    own = connection is None
    connection = connection or open_store()
    try:
        known = fetched_days(connection) if resume else {}
        pending = [
            d for d in weekdays(start, end) if d.isoformat() not in known
        ]
        logger.info(
            "bhavcopy: %d weekdays in window, %d recorded, %d to fetch.",
            sum(1 for _ in weekdays(start, end)), len(known), len(pending),
        )
        stored = holidays = 0
        for index, day in enumerate(pending, 1):
            rows, source = fetch_day(day)
            store_bars(connection, rows)
            mark_day(connection, day, len(rows), source)
            connection.commit()
            if rows:
                stored += len(rows)
            else:
                holidays += 1
            if index % progress_every == 0 or index == len(pending):
                logger.info(
                    "  %d/%d sessions — %s (%d rows, %s). %d bars stored.",
                    index, len(pending), day, len(rows), source, stored,
                )
        return {"sessions": len(pending), "bars": stored, "empty": holidays}
    finally:
        if own:
            connection.close()


def print_status(connection: sqlite3.Connection) -> None:
    stats = coverage(connection)
    print(
        f"\nDaily bars: {stats['bars']:,} rows for "
        f"{stats['symbols']:,} symbols.\n"
        f"  range    : {stats['first']} -> {stats['last']}\n"
        f"  sessions : {stats['days_traded']:,} traded "
        f"({stats['days_known']:,} days checked)"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    global MIN_REQUEST_INTERVAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", default="2013-01-01")
    parser.add_argument("--to", dest="end", default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--rate", type=float, default=MIN_REQUEST_INTERVAL,
        help="Minimum seconds between requests.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    MIN_REQUEST_INTERVAL = args.rate

    connection = open_store()
    try:
        if args.status:
            print_status(connection)
            return 0
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today()
        result = run(
            start, end, connection=connection, resume=not args.no_resume
        )
        logger.info(
            "Done: %d sessions fetched, %d bars stored, %d empty days.",
            result["sessions"], result["bars"], result["empty"],
        )
        print_status(connection)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
