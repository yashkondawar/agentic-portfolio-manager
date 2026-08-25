"""
core/bars.py
============

Per-symbol daily OHLCV store, shared by every strategy and backtest.

Why this exists
---------------
The original price cache keyed a single pickled blob by a hash of *the exact
symbol set plus the exact date range*::

    f"{len(symbols)}sym_{identity_hash}_{download_start}_{download_end}"

That is correct but almost never reusable. Shifting ``--start`` by one day,
adding one ticker, or extending the window to today produced a fresh key and
re-downloaded the entire universe. A Nifty 500 run costs ~10 minutes of network
time under that scheme and ``nse_all`` closer to 15, which is what made the
parameter sweep painful.

This module stores **one row per (symbol, day)** instead. Any universe and any
date range is then a SQL slice of data already on disk, and only genuinely-new
bars are fetched. A second run over a different window is effectively free.

What is stored, and what is deliberately NOT
--------------------------------------------
Only **raw daily OHLCV**. Weekly and monthly candles are resampled from these
bars, and every RSI/ATR/SMA is computed from those. Derived indicators are never
persisted, for two reasons:

1. *Leak safety.* A stored ``monthly_rsi`` value carries no record of whether it
   came from a closed candle or an in-progress one. That distinction is worth
   about 6 percentage points of CAGR in the GFS study, and it would be invisible
   in a database column. Recomputing from raw bars keeps the leak-free logic in
   exactly one place (``indicators.htf_rsi_daily``).
2. *Invalidation.* Every indicator has parameters. Persisting outputs means
   every parameter change is a cache-invalidation problem, which is precisely
   the bug class this module is meant to remove.

Deriving indicators from cached bars takes seconds. Persisting them would buy
very little and risk a great deal.

The split/dividend hazard
-------------------------
``yfinance`` is asked for ``auto_adjust=True`` prices, so a new corporate action
silently **rewrites history**: the close for a date fetched last month may not
equal the close for that same date fetched today. Appending to a store of
adjusted prices would therefore quietly mix two different adjustment bases
inside one series - a subtle error that a naive incremental cache would never
notice, and one that is worse than the slowness it set out to fix.

So every top-up re-fetches a short ``overlap_sessions`` window that is already
on disk and compares it. If any overlapping close has moved by more than
``DRIFT_TOLERANCE``, the symbol is treated as re-based: its rows are dropped and
the full range is fetched again. The store is self-healing rather than merely
fast.

Coverage vs. data
-----------------
``daily_bars`` records what we *have*; ``bar_coverage`` records what we have
*asked for*. The two differ legitimately - a stock listed in 2021 has no bars in
2018 no matter how often it is requested. Without tracking the requested range
separately, every run would re-request that permanently empty window forever.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from core.storage import connect

logger = logging.getLogger("core.bars")

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

#: Relative close difference above which a symbol is considered re-based by a
#: corporate action. Comfortably larger than float noise, far smaller than any
#: real split.
DRIFT_TOLERANCE = 0.005

STATUS_OK = "ok"
STATUS_EMPTY = "empty"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_bars (
    symbol TEXT NOT NULL,
    day    TEXT NOT NULL,
    open   REAL,
    high   REAL,
    low    REAL,
    close  REAL NOT NULL,
    volume REAL,
    PRIMARY KEY (symbol, day)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_daily_bars_day ON daily_bars(day);

CREATE TABLE IF NOT EXISTS bar_coverage (
    symbol          TEXT PRIMARY KEY,
    first_day       TEXT,
    last_day        TEXT,
    requested_start TEXT NOT NULL,
    requested_end   TEXT NOT NULL,
    row_count       INTEGER NOT NULL,
    status          TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


# ── Symbol normalisation ─────────────────────────────────────────────────────


def plain_symbol(symbol: str) -> str:
    """Storage key: uppercase, no exchange suffix. Index tickers keep their ^."""
    return symbol.strip().upper().replace(".NS", "").replace(".BO", "")


def yf_symbol(symbol: str) -> str:
    """Download key: NSE suffix added unless it is an index or already suffixed."""
    s = symbol.strip().upper()
    if s.startswith("^") or s.endswith((".NS", ".BO")):
        return s
    return f"{s}.NS"


# ── Schema / connection helpers ──────────────────────────────────────────────


def _ensure_schema(conn) -> None:
    conn.executescript(_SCHEMA)


def _open():
    conn = connect()
    _ensure_schema(conn)
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


# ── Coverage ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Coverage:
    """What the store holds for one symbol, and what has been asked for."""

    symbol: str
    first_day: Optional[date]
    last_day: Optional[date]
    requested_start: date
    requested_end: date
    row_count: int
    status: str

    @property
    def is_empty(self) -> bool:
        return self.status == STATUS_EMPTY or self.row_count == 0


def coverage(symbols: Sequence[str], conn=None) -> Dict[str, Coverage]:
    """Coverage rows for `symbols`, keyed by plain symbol. Missing = absent."""
    owned = conn is None
    conn = conn or _open()
    try:
        wanted = {plain_symbol(s) for s in symbols}
        if not wanted:
            return {}
        out: Dict[str, Coverage] = {}
        keys = list(wanted)
        for i in range(0, len(keys), 500):
            batch = keys[i : i + 500]
            placeholders = ",".join("?" * len(batch))
            rows = conn.execute(
                f"SELECT * FROM bar_coverage WHERE symbol IN ({placeholders})", batch
            ).fetchall()
            for row in rows:
                out[row["symbol"]] = Coverage(
                    symbol=row["symbol"],
                    first_day=_as_date(row["first_day"]) if row["first_day"] else None,
                    last_day=_as_date(row["last_day"]) if row["last_day"] else None,
                    requested_start=_as_date(row["requested_start"]),
                    requested_end=_as_date(row["requested_end"]),
                    row_count=int(row["row_count"]),
                    status=row["status"],
                )
        return out
    finally:
        if owned:
            conn.close()


# ── Read ─────────────────────────────────────────────────────────────────────


def read_bars(
    symbols: Sequence[str],
    start: Optional[date] = None,
    end: Optional[date] = None,
    *,
    min_rows: int = 0,
    conn=None,
) -> Dict[str, pd.DataFrame]:
    """Daily OHLCV per symbol, keyed by plain symbol.

    Symbols with fewer than `min_rows` sessions in the window are omitted, which
    mirrors the old loader's "usable history" rule. The returned index is
    tz-naive and normalised to midnight.
    """
    owned = conn is None
    conn = conn or _open()
    try:
        wanted = sorted({plain_symbol(s) for s in symbols})
        if not wanted:
            return {}

        clauses = []
        params: List[object] = []
        if start is not None:
            clauses.append("day >= ?")
            params.append(_as_date(start).isoformat())
        if end is not None:
            clauses.append("day <= ?")
            params.append(_as_date(end).isoformat())
        window_sql = (" AND " + " AND ".join(clauses)) if clauses else ""

        frames: Dict[str, pd.DataFrame] = {}
        for i in range(0, len(wanted), 500):
            batch = wanted[i : i + 500]
            placeholders = ",".join("?" * len(batch))
            sql = (
                "SELECT symbol, day, open, high, low, close, volume FROM daily_bars "
                f"WHERE symbol IN ({placeholders}){window_sql} ORDER BY symbol, day"
            )
            rows = conn.execute(sql, [*batch, *params]).fetchall()
            if not rows:
                continue
            frame = pd.DataFrame(
                rows,
                columns=["symbol", "day", "Open", "High", "Low", "Close", "Volume"],
            )
            frame["day"] = pd.to_datetime(frame["day"])
            for sym, group in frame.groupby("symbol", sort=False):
                df = group.drop(columns=["symbol"]).set_index("day")
                df.index.name = None
                df = df[OHLCV_COLUMNS].astype("float64")
                if len(df) >= min_rows:
                    frames[str(sym)] = df
        return frames
    finally:
        if owned:
            conn.close()


def read_symbol(
    symbol: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    *,
    conn=None,
) -> Optional[pd.DataFrame]:
    """Convenience single-symbol read."""
    frames = read_bars([symbol], start, end, conn=conn)
    return frames.get(plain_symbol(symbol))


# ── Write ────────────────────────────────────────────────────────────────────


def write_bars(
    symbol: str,
    frame: Optional[pd.DataFrame],
    requested_start: date,
    requested_end: date,
    *,
    conn=None,
    replace: bool = False,
) -> int:
    """Upsert `frame` for `symbol` and widen its recorded requested range.

    `replace=True` drops the symbol's existing rows first; use it when a
    corporate action has re-based the series.
    """
    owned = conn is None
    conn = conn or _open()
    try:
        key = plain_symbol(symbol)
        req_start = _as_date(requested_start)
        req_end = _as_date(requested_end)

        if replace:
            conn.execute("DELETE FROM daily_bars WHERE symbol = ?", (key,))

        written = 0
        if frame is not None and not frame.empty:
            payload = _to_rows(key, frame)
            conn.executemany(
                "INSERT INTO daily_bars(symbol, day, open, high, low, close, volume) "
                "VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(symbol, day) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume",
                payload,
            )
            written = len(payload)

        row = conn.execute(
            "SELECT MIN(day) AS lo, MAX(day) AS hi, COUNT(*) AS n "
            "FROM daily_bars WHERE symbol = ?",
            (key,),
        ).fetchone()
        first_day, last_day, count = row["lo"], row["hi"], int(row["n"])

        existing = conn.execute(
            "SELECT requested_start, requested_end FROM bar_coverage WHERE symbol = ?",
            (key,),
        ).fetchone()
        if existing and not replace:
            req_start = min(req_start, _as_date(existing["requested_start"]))
            req_end = max(req_end, _as_date(existing["requested_end"]))

        # Coverage of the future cannot exist. Callers routinely pad the end
        # date past today, and recording that pad made `plan_fetches` treat the
        # symbol as covered until the calendar caught up - so a symbol could
        # silently stop topping up for days. Clamped after the merge so an
        # already-poisoned row heals on its next write.
        req_end = max(req_start, min(req_end, date.today()))

        conn.execute(
            "INSERT INTO bar_coverage(symbol, first_day, last_day, requested_start, "
            "requested_end, row_count, status, updated_at) VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET first_day=excluded.first_day, "
            "last_day=excluded.last_day, requested_start=excluded.requested_start, "
            "requested_end=excluded.requested_end, row_count=excluded.row_count, "
            "status=excluded.status, updated_at=excluded.updated_at",
            (
                key,
                first_day,
                last_day,
                req_start.isoformat(),
                req_end.isoformat(),
                count,
                STATUS_OK if count else STATUS_EMPTY,
                _utc_now(),
            ),
        )
        conn.commit()
        return written
    finally:
        if owned:
            conn.close()


def _to_rows(key: str, frame: pd.DataFrame) -> List[Tuple]:
    df = normalise_frame(frame)
    if df is None or df.empty:
        return []
    rows: List[Tuple] = []
    for ts, row in df.iterrows():
        rows.append(
            (
                key,
                ts.date().isoformat(),
                _f(row.get("Open")),
                _f(row.get("High")),
                _f(row.get("Low")),
                _f(row.get("Close")),
                _f(row.get("Volume")),
            )
        )
    return rows


def _f(value) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def drop_symbols(symbols: Iterable[str], *, conn=None) -> int:
    """Forget everything about `symbols` so the next sync refetches them."""
    owned = conn is None
    conn = conn or _open()
    try:
        keys = [plain_symbol(s) for s in symbols]
        if not keys:
            return 0
        conn.executemany("DELETE FROM daily_bars WHERE symbol = ?", [(k,) for k in keys])
        conn.executemany("DELETE FROM bar_coverage WHERE symbol = ?", [(k,) for k in keys])
        conn.commit()
        return len(keys)
    finally:
        if owned:
            conn.close()


def normalise_frame(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Flatten yfinance output to tz-naive daily OHLCV with a unique index."""
    if df is None or df.empty:
        return None
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance puts the field names on level 0 under group_by="column" but
        # on level 1 under group_by="ticker" - and it returns a MultiIndex even
        # for a single ticker. Assuming level 0 silently produced a frame whose
        # columns were all the ticker name, so "Close" went missing and the
        # symbol was recorded as having no data. Pick the level that actually
        # carries the field names.
        levels = [df.columns.get_level_values(i) for i in range(df.columns.nlevels)]
        df.columns = next(
            (lv for lv in levels if any(c in OHLCV_COLUMNS for c in lv)), levels[0]
        )
    keep = [c for c in OHLCV_COLUMNS if c in df.columns]
    if "Close" not in keep:
        return None
    df = df[keep].dropna(subset=["Close"])
    if df.empty:
        return None
    idx = pd.to_datetime(df.index)
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


# ── Fetch planning ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FetchJob:
    symbol: str
    start: date
    end: date
    #: True when the symbol already has rows, so the overlap must be drift-checked.
    is_topup: bool


def plan_fetches(
    symbols: Sequence[str],
    start: date,
    end: date,
    *,
    overlap_sessions: int = 10,
    force: bool = False,
    conn=None,
) -> List[FetchJob]:
    """Work out the minimum set of downloads needed to cover [start, end].

    A symbol already covering the window produces no job. One needing only newer
    bars produces a short forward job that deliberately overlaps existing rows so
    the adjustment basis can be verified. Backfill and forward extension are
    separate jobs, so extending a window in both directions never degenerates
    into a full re-download.
    """
    start, end = _as_date(start), _as_date(end)
    cov = coverage(symbols, conn=conn)
    # Calendar days per session, with slack for holidays.
    overlap_days = max(overlap_sessions, 0) * 2 + 5
    today = date.today()

    jobs: List[FetchJob] = []
    for raw in symbols:
        key = plain_symbol(raw)
        info = cov.get(key)
        if force or info is None:
            jobs.append(FetchJob(key, start, end, is_topup=False))
            continue

        # A window recorded past today cannot have been verified, so trust it
        # only as far as today. This also heals rows written before the clamp
        # in write_bars existed, which would otherwise never top up again.
        covered_to = min(info.requested_end, today)
        needs_backfill = start < info.requested_start
        needs_forward = end > covered_to
        if not (needs_backfill or needs_forward):
            continue

        if info.is_empty:
            # Nothing on disk to overlap against; just widen the request.
            jobs.append(
                FetchJob(
                    key,
                    min(start, info.requested_start),
                    max(end, covered_to),
                    is_topup=False,
                )
            )
            continue

        if needs_forward and info.last_day is not None:
            jobs.append(
                FetchJob(
                    key,
                    info.last_day - timedelta(days=overlap_days),
                    end,
                    is_topup=True,
                )
            )
        if needs_backfill and info.first_day is not None:
            jobs.append(
                FetchJob(
                    key,
                    start,
                    info.first_day + timedelta(days=overlap_days),
                    is_topup=True,
                )
            )
    return jobs


def detect_drift(
    stored: pd.DataFrame,
    fetched: pd.DataFrame,
    tolerance: float = DRIFT_TOLERANCE,
) -> bool:
    """True when overlapping closes disagree, i.e. a corporate action re-based
    the series and the stored rows use a stale adjustment basis."""
    if stored is None or fetched is None or stored.empty or fetched.empty:
        return False
    shared = stored.index.intersection(fetched.index)
    if len(shared) == 0:
        return False
    a = stored.loc[shared, "Close"].astype("float64")
    b = fetched.loc[shared, "Close"].astype("float64")
    denom = a.abs().where(a.abs() > 0)
    rel = ((a - b).abs() / denom).dropna()
    if rel.empty:
        return False
    return bool(rel.max() > tolerance)


# ── Sync ─────────────────────────────────────────────────────────────────────


@dataclass
class SyncReport:
    requested: int = 0
    up_to_date: int = 0
    fetched: int = 0
    rebased: List[str] = field(default_factory=list)
    empty: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    rows_written: int = 0

    def summary(self) -> str:
        parts = [
            f"{self.requested} requested",
            f"{self.up_to_date} already covered",
            f"{self.fetched} fetched",
            f"{self.rows_written:,} rows written",
        ]
        if self.rebased:
            parts.append(f"{len(self.rebased)} re-based (refetched)")
        if self.empty:
            parts.append(f"{len(self.empty)} with no data")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts)


def _download(tickers: List[str], start: date, end: date):
    import yfinance as yf

    return yf.download(
        tickers if len(tickers) > 1 else tickers[0],
        start=start,
        end=end + timedelta(days=1),
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )


def sync(
    symbols: Sequence[str],
    start: date,
    end: date,
    *,
    chunk_size: int = 40,
    overlap_sessions: int = 10,
    force: bool = False,
    downloader=None,
) -> SyncReport:
    """Bring the store up to date for `symbols` over [start, end].

    Only missing ranges are downloaded. Symbols whose overlap fails the drift
    check are dropped and refetched in full, so a split can never leave two
    adjustment bases spliced together inside one series.

    `downloader` is injectable for tests: it takes (tickers, start, end) and
    returns a yfinance-shaped frame.
    """
    start, end = _as_date(start), _as_date(end)
    fetch = downloader or _download
    report = SyncReport(requested=len({plain_symbol(s) for s in symbols}))

    conn = _open()
    try:
        jobs = plan_fetches(
            symbols, start, end, overlap_sessions=overlap_sessions,
            force=force, conn=conn,
        )
        report.up_to_date = report.requested - len({j.symbol for j in jobs})
        if not jobs:
            logger.info("Bar store already covers %d symbols.", report.requested)
            return report

        rebase: List[str] = []
        # Group by identical window so one download serves many symbols.
        by_window: Dict[Tuple[date, date], List[FetchJob]] = {}
        for job in jobs:
            by_window.setdefault((job.start, job.end), []).append(job)

        for (lo, hi), group in by_window.items():
            done = _run_jobs(conn, group, lo, hi, chunk_size, fetch, report)
            rebase.extend(done)

        if rebase:
            logger.warning(
                "%d symbol(s) re-based by a corporate action; refetching in full.",
                len(rebase),
            )
            report.rebased = sorted(set(rebase))
            drop_symbols(report.rebased, conn=conn)
            full = [FetchJob(s, start, end, is_topup=False) for s in report.rebased]
            _run_jobs(conn, full, start, end, chunk_size, fetch, report)

        logger.info("Bar sync: %s", report.summary())
        return report
    finally:
        conn.close()


def _run_jobs(
    conn,
    jobs: List[FetchJob],
    lo: date,
    hi: date,
    chunk_size: int,
    fetch,
    report: SyncReport,
) -> List[str]:
    """Download one window for a set of symbols; return those needing a rebase."""
    rebase: List[str] = []
    plain = [j.symbol for j in jobs]
    topups = {j.symbol for j in jobs if j.is_topup}
    yf_map = {yf_symbol(s): s for s in plain}
    tickers = list(yf_map.keys())

    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        logger.info(
            "Fetching bars %d-%d of %d for %s -> %s",
            i + 1, min(i + chunk_size, len(tickers)), len(tickers), lo, hi,
        )
        try:
            data = fetch(chunk, lo, hi)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fetch failed for %d symbols (%s); skipping.", len(chunk), exc)
            report.failed.extend(yf_map[t] for t in chunk)
            continue

        for ticker in chunk:
            key = yf_map[ticker]
            # Select by frame shape rather than by chunk size: yfinance returns
            # a per-ticker MultiIndex even when one ticker was requested, so a
            # chunk of one must still be indexed into.
            sub = data
            try:
                cols = getattr(data, "columns", None)
                if isinstance(cols, pd.MultiIndex):
                    # yfinance returns a per-ticker MultiIndex even for a chunk
                    # of one, so a lone ticker must still be indexed into.
                    # Falling back to the whole frame here would splice another
                    # ticker's prices into this symbol.
                    present = cols.get_level_values(0)
                    sub = data[ticker] if ticker in present else None
            except (KeyError, TypeError):
                sub = None
            frame = normalise_frame(sub)

            if frame is None or frame.empty:
                # Record the attempt so this window is not requested forever.
                write_bars(key, None, lo, hi, conn=conn)
                report.empty.append(key)
                continue

            if key in topups:
                stored = read_symbol(
                    key, frame.index.min().date(), frame.index.max().date(), conn=conn
                )
                if detect_drift(stored, frame):
                    rebase.append(key)
                    continue

            report.rows_written += write_bars(key, frame, lo, hi, conn=conn)
            report.fetched += 1

    return rebase


# ── Maintenance ──────────────────────────────────────────────────────────────


def store_stats() -> Dict[str, object]:
    """Row counts and date span, for the CLI and for sanity checks."""
    conn = _open()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS bars, COUNT(DISTINCT symbol) AS symbols, "
            "MIN(day) AS lo, MAX(day) AS hi FROM daily_bars"
        ).fetchone()
        empties = conn.execute(
            "SELECT COUNT(*) AS n FROM bar_coverage WHERE status = ?", (STATUS_EMPTY,)
        ).fetchone()
        return {
            "bars": int(row["bars"] or 0),
            "symbols": int(row["symbols"] or 0),
            "first_day": row["lo"],
            "last_day": row["hi"],
            "symbols_without_data": int(empties["n"] or 0),
        }
    finally:
        conn.close()


