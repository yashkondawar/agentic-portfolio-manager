"""Index valuation pipeline: daily PE/PB/div-yield (+ close) for NIFTY 50,
NIFTY 500, NIFTY BANK, NIFTY TOTAL MARKET (TARGET_INDICES, the original
benchmark set) plus the 8 sector indices mapping the KPI-registry sectors —
NIFTY BANK, NIFTY FINANCIAL SERVICES, NIFTY IT, NIFTY PHARMA, NIFTY AUTO,
NIFTY FMCG, NIFTY METAL, NIFTY INFRASTRUCTURE, NIFTY ENERGY (SECTOR_INDICES)
— into `index_data`. See config/settings.yaml -> sector_index_map for the
KPI-sector-slug -> index-name mapping consumed by the (Phase 7) cycle
engine's sector-cycle gate.

Three sources are used (see config/sources.yaml -> equity_index for the
full investigation notes):

1. nse_all_indices (www.nseindia.com/api/allIndices) — CURRENT-DAY snapshot
   for every index in one call, INCLUDING pe/pb/dy. This is the primary
   daily-cadence source.

2. nse_indices_history (.../api/historicalOR/indicesHistory) — historical
   OHLC (close only, no PE/PB) for a single named index over a date range.
   Empirically the endpoint returns unreliable/empty results for ranges
   much beyond ~150-180 days per call (likely an internal NSE pagination
   cap), so multi-year backfills must chunk into <=150-day windows. This
   pipeline's `fetch_index_history()` does that chunking; historical rows
   are stored with pe/pb/div_yield left NULL (only close is known) — this
   is a genuine, documented data gap for this endpoint specifically, not a
   bug.

3. niftyindices_daily_snapshot_archive
   (www.niftyindices.com/Daily_Snapshot/ind_close_all_{DDMMYYYY}.csv) —
   a STATIC per-calendar-day CSV archive (not the dead Backpage.aspx JSON
   API — see below) containing every NSE index's OHLC + P/E + P/B + Div
   Yield for that one date. This IS a genuine historical PE/PB/DY source,
   confirmed reliably available back to 2013 (older files use the
   pre-rebrand "S&P CNX Nifty" name and lack some indices; not used here).
   `backfill_index_valuation()` walks this archive day-by-day and is the
   function that gives regime.py's pe_percentile_5y real history to work
   with. See its docstring for the quirks (weekends/holidays return a
   disguised HTTP-200 HTML shell, not a 404 or empty file).

The original niftyindices.com "historical-data" POST endpoints
(Backpage.aspx/getHistoricaldatatabletoString and the alternate
.../getpepbHistoricaldataDBtoString used by some scraper libraries) are
confirmed DEAD — both return HTTP 200 but with the site's generic
Sitefinity HTML shell instead of JSON (the legacy ASP.NET backend behind
niftyindices.com has been fully decommissioned). See sources.yaml.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import time
import urllib.parse

from afund.data.base import Pipeline
from afund.data.http import bootstrap_nse_session, make_session
from afund.sources import get_source

TARGET_INDICES = ["NIFTY 50", "NIFTY 500", "NIFTY BANK", "NIFTY TOTAL MARKET"]

# Sector indices mapping the 8 KPI-registry sectors (see
# config/settings.yaml -> sector_index_map). Confirmed present under these
# exact names in BOTH live sources as of 2026-07-04: nse_all_indices (all
# caps, e.g. "NIFTY IT") and the niftyindices.com Daily_Snapshot archive
# (title case, e.g. "Nifty IT") — see _SNAPSHOT_NAME_MAP below. "NIFTY
# INFRASTRUCTURE" (not "NIFTY INFRA") is the archive/live-API's actual name.
SECTOR_INDICES = [
    "NIFTY BANK",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY IT",
    "NIFTY PHARMA",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY METAL",
    "NIFTY INFRASTRUCTURE",
    "NIFTY ENERGY",
]

# All indices this pipeline knows how to fetch/backfill (benchmark + sector).
# NIFTY BANK appears in both TARGET_INDICES and SECTOR_INDICES; ALL_INDICES
# dedupes while preserving TARGET_INDICES' original ordering first.
ALL_INDICES = TARGET_INDICES + [n for n in SECTOR_INDICES if n not in TARGET_INDICES]

# niftyindices.com Daily_Snapshot rows use title case ("Nifty 50", "Nifty
# Total Market") rather than the all-caps names used elsewhere in this
# module/DB (nse_all_indices uses "NIFTY 50" etc). This maps the archive's
# row label to our canonical (all-caps) index_name.
_SNAPSHOT_NAME_MAP = {
    "Nifty 50": "NIFTY 50",
    "Nifty 500": "NIFTY 500",
    "Nifty Bank": "NIFTY BANK",
    "Nifty Total Market": "NIFTY TOTAL MARKET",
    "Nifty Financial Services": "NIFTY FINANCIAL SERVICES",
    "Nifty IT": "NIFTY IT",
    "Nifty Pharma": "NIFTY PHARMA",
    "Nifty Auto": "NIFTY AUTO",
    "Nifty FMCG": "NIFTY FMCG",
    "Nifty Metal": "NIFTY METAL",
    "Nifty Infrastructure": "NIFTY INFRASTRUCTURE",
    "Nifty Energy": "NIFTY ENERGY",
}

HISTORY_REFERER = "https://www.nseindia.com/reports-indices-historical-index-data"
ALLINDICES_REFERER = "https://www.nseindia.com/market-data/live-equity-market"

# Empirically safe window for historicalOR/indicesHistory before NSE starts
# returning empty/erroring responses.
HISTORY_CHUNK_DAYS = 150


def _float_or_none(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_current_snapshot(timeout: float = 20.0) -> list[dict]:
    """Fetch today's PE/PB/DY/close for every index in ALL_INDICES (the 4
    benchmark indices + 8 sector indices) via the allIndices API. This is
    the daily-cadence path (afund.data.run_daily / IndexValuationPipeline)
    that keeps the sector-index P/E series growing going forward, on top of
    the one-off historical backfill_index_valuation() below."""
    source = get_source("equity_index", "nse_all_indices")
    session = bootstrap_nse_session(make_session())
    resp = session.get(source["url"], timeout=timeout, headers={"Referer": ALLINDICES_REFERER})
    resp.raise_for_status()
    data = resp.json().get("data", [])

    rows = []
    for entry in data:
        if entry.get("index") in ALL_INDICES:
            rows.append(
                {
                    "index_name": entry["index"],
                    "close": _float_or_none(entry.get("last")),
                    "pe": _float_or_none(entry.get("pe")),
                    "pb": _float_or_none(entry.get("pb")),
                    "div_yield": _float_or_none(entry.get("dy")),
                }
            )
    return rows


def fetch_index_history(
    index_name: str,
    from_date: dt.date,
    to_date: dt.date,
    session=None,
    chunk_days: int = HISTORY_CHUNK_DAYS,
    sleep_between_chunks: float = 1.0,
) -> list[dict]:
    """Fetch historical OHLC close for one index, chunked into
    <=chunk_days windows (pe/pb/div_yield are not available from this
    endpoint and are omitted from the returned rows)."""
    session = session or bootstrap_nse_session(make_session())
    source = get_source("equity_index", "nse_indices_history")
    base_url = source["url"].split("?")[0]

    rows: list[dict] = []
    cursor = from_date
    while cursor <= to_date:
        chunk_end = min(cursor + dt.timedelta(days=chunk_days), to_date)
        params = {
            "indexType": index_name,
            "from": cursor.strftime("%d-%m-%Y"),
            "to": chunk_end.strftime("%d-%m-%Y"),
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        try:
            resp = session.get(url, timeout=20, headers={"Referer": HISTORY_REFERER})
            resp.raise_for_status()
            payload = resp.json().get("data", [])
            for entry in payload:
                date_raw = entry.get("EOD_TIMESTAMP")  # "02-JUL-2026"
                close = _float_or_none(entry.get("EOD_CLOSE_INDEX_VAL"))
                if not date_raw or close is None:
                    continue
                try:
                    date_iso = dt.datetime.strptime(date_raw, "%d-%b-%Y").date().isoformat()
                except ValueError:
                    continue
                rows.append({"index_name": index_name, "date": date_iso, "close": close})
        except Exception:
            pass  # one chunk failing must not abort the whole history fetch
        cursor = chunk_end + dt.timedelta(days=1)
        if cursor <= to_date:
            time.sleep(sleep_between_chunks)
    return rows


# ---------------------------------------------------------------------------
# Historical PE/PB/div-yield backfill via niftyindices.com's static
# Daily_Snapshot CSV archive.
# ---------------------------------------------------------------------------

DAILY_SNAPSHOT_SOURCE_GROUP = "equity_index"
DAILY_SNAPSHOT_SOURCE_NAME = "niftyindices_daily_snapshot_archive"

# Value used for index_data.source on rows written by this backfill, so
# regime.py (or a future migration) can scope percentile math to this
# provenance if the pre/post-Apr-2021 PE methodology shift (standalone ->
# consolidated earnings) ever needs to be excluded from a percentile window.
# See parse_daily_snapshot_csv()'s docstring for the full caveat.
BACKFILL_SOURCE_TAG = "backfill_niftyindices_daily_snapshot"


def _daily_snapshot_url(date: dt.date) -> str:
    source = get_source(DAILY_SNAPSHOT_SOURCE_GROUP, DAILY_SNAPSHOT_SOURCE_NAME)
    template = source["url"]
    return template.format(DDMMYYYY=date.strftime("%d%m%Y"))


def parse_daily_snapshot_csv(text: str, date: dt.date) -> list[dict]:
    """Parse one day's niftyindices.com Daily_Snapshot CSV into rows for
    every index name this module knows about (_SNAPSHOT_NAME_MAP — the
    union of TARGET_INDICES and SECTOR_INDICES). Callers (e.g.
    backfill_index_valuation) further filter to the specific index_names
    they want written.

    IMPORTANT quirk: a date with no snapshot (weekend, market holiday, or a
    date outside the archive's coverage) does NOT 404 — niftyindices.com
    (a Sitefinity CMS) serves its generic site shell HTML with HTTP 200 for
    any unmatched Daily_Snapshot path. The only reliable way to detect "no
    data for this date" is that the response body does not start with the
    expected CSV header ("Index Name,..."). Returns [] in that case (and
    for any other parse failure) rather than raising, so a single bad/
    missing date can't abort a multi-year backfill loop.

    METHODOLOGY CAVEAT (see BACKFILL_SOURCE_TAG): NSE switched the NIFTY PE
    calculation from standalone to consolidated company earnings around
    April 2021, which is documented elsewhere (e.g. freefincal, ValuePickr)
    to cause a level shift in the published PE series across that boundary.
    This archive's rows are stored as-is with source=BACKFILL_SOURCE_TAG
    specifically so that later analysis (e.g. a stricter regime.py
    percentile window) can exclude or separately treat pre-Apr-2021 history
    if the shift turns out to matter for a given index's series in practice.
    """
    lines = text.splitlines()
    if not lines or not lines[0].startswith("Index Name"):
        return []

    date_iso = date.isoformat()
    rows: list[dict] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split(",")
        if len(fields) < 12:
            continue
        raw_name = fields[0].strip()
        index_name = _SNAPSHOT_NAME_MAP.get(raw_name)
        if index_name is None:
            continue
        rows.append(
            {
                "index_name": index_name,
                "date": date_iso,
                "close": _float_or_none(fields[5]),
                "pe": _float_or_none(fields[10]),
                "pb": _float_or_none(fields[11]),
                "div_yield": _float_or_none(fields[12]) if len(fields) > 12 else None,
            }
        )
    return rows


def fetch_daily_snapshot(date: dt.date, session=None, timeout: float = 20.0) -> list[dict]:
    """Fetch + parse one day's Daily_Snapshot CSV. Returns [] on any HTTP
    error or if the date has no snapshot (see parse_daily_snapshot_csv)."""
    session = session or make_session()
    url = _daily_snapshot_url(date)
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return []
    return parse_daily_snapshot_csv(resp.text, date)


def backfill_index_valuation(
    conn: sqlite3.Connection,
    index_names: list[str] | None = None,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    years: float = 10.0,
    session=None,
    sleep_between_requests: float = 0.15,
    progress_every: int = 250,
) -> dict[str, int]:
    """Backfill historical PE/PB/div_yield (+close) for `index_names` into
    index_data from the niftyindices.com Daily_Snapshot CSV archive, walking
    one calendar day at a time from `from_date` to `to_date`.

    Idempotent / non-destructive by construction:
      - UNIQUE(index_name, date) is upserted via ON CONFLICT.
      - Existing rows that already have a non-NULL `pe` (i.e. today's live
        nse_all_indices snapshot, or a prior backfill run) are NEVER
        overwritten — the SQL only fills columns that are currently NULL,
        via COALESCE(existing, excluded). A row with no existing pe/pb/
        div_yield/close gets the archive's values; a row that already has
        real pe from the live snapshot keeps it untouched.
      - Weekends/holidays/missing dates contribute 0 rows for that day
        (fetch_daily_snapshot returns [] for them) and do not raise.

    Returns a dict of {index_name: rows_written} plus a "_days_fetched" /
    "_days_with_data" pair of counters under those literal keys for the
    caller's own reporting.
    """
    index_names = index_names or TARGET_INDICES
    to_date = to_date or dt.date.today()
    from_date = from_date or (to_date - dt.timedelta(days=round(years * 365.25)))
    session = session or make_session()

    written = {name: 0 for name in index_names}
    days_fetched = 0
    days_with_data = 0

    cursor = from_date
    while cursor <= to_date:
        days_fetched += 1
        day_rows = fetch_daily_snapshot(cursor, session=session)
        if day_rows:
            days_with_data += 1
        for row in day_rows:
            if row["index_name"] not in index_names:
                continue

            existing = conn.execute(
                "SELECT pe FROM index_data WHERE index_name = ? AND date = ?",
                (row["index_name"], row["date"]),
            ).fetchone()
            # SQLite's ON CONFLICT ... DO UPDATE always registers as a
            # "change" (via total_changes) even when COALESCE makes it a
            # pure no-op, so we determine "did this row actually gain new
            # data" ourselves: it's a fresh fill whenever there was no row
            # yet, or the existing row's pe was still NULL (i.e. an
            # OHLC-only row from fetch_index_history / _backfill_history).
            is_fresh_fill = existing is None or existing["pe"] is None

            conn.execute(
                """
                INSERT INTO index_data (index_name, date, close, pe, pb, div_yield, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_name, date) DO UPDATE SET
                    close     = COALESCE(index_data.close, excluded.close),
                    pe        = COALESCE(index_data.pe, excluded.pe),
                    pb        = COALESCE(index_data.pb, excluded.pb),
                    div_yield = COALESCE(index_data.div_yield, excluded.div_yield),
                    -- Only stamp `source` if this row didn't already have a
                    -- real pe (i.e. it wasn't already filled by the live
                    -- nse_all_indices snapshot) — never relabel the
                    -- provenance of a value we didn't actually write.
                    source    = CASE WHEN index_data.pe IS NULL THEN excluded.source ELSE index_data.source END
                """,
                (
                    row["index_name"],
                    row["date"],
                    row["close"],
                    row["pe"],
                    row["pb"],
                    row["div_yield"],
                    BACKFILL_SOURCE_TAG,
                ),
            )
            if is_fresh_fill and row["pe"] is not None:
                written[row["index_name"]] += 1

        if progress_every and days_fetched % progress_every == 0:
            conn.commit()

        cursor += dt.timedelta(days=1)
        if cursor <= to_date and sleep_between_requests:
            time.sleep(sleep_between_requests)

    conn.commit()
    written["_days_fetched"] = days_fetched
    written["_days_with_data"] = days_with_data
    return written


class IndexValuationPipeline(Pipeline):
    """Current-day PE/PB/DY snapshot for ALL_INDICES (4 benchmark + 8 sector
    indices — see module docstring). Historical backfill (OHLC only, via
    nse_indices_history, confirmed to cover only NIFTY 50/500/BANK per
    sources.yaml) is a separate opt-in method (`_backfill_history`) since
    it's multi-request and slower — the base `run()` stays fast and safe for
    a daily cadence. The genuine historical PE/PB/DY backfill for sector
    indices is `backfill_index_valuation()` (Daily_Snapshot archive path),
    run as a one-off/periodic script, not part of this daily pipeline."""

    job_name = "index_valuation"

    def __init__(self, conn: sqlite3.Connection | None = None, backfill_years: float = 0):
        super().__init__(conn)
        self.backfill_years = backfill_years  # 0 = current-day snapshot only

    def fetch(self) -> list[dict]:
        return fetch_current_snapshot()

    def parse(self, raw: list[dict]) -> list[dict]:
        today = dt.date.today().isoformat()
        for row in raw:
            row["date"] = today
        return raw

    def upsert(self, parsed: list[dict]) -> int:
        rows_written = 0
        for row in parsed:
            before = self.conn.total_changes
            self.conn.execute(
                """
                INSERT INTO index_data (index_name, date, close, pe, pb, div_yield)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_name, date) DO UPDATE SET
                    close = excluded.close,
                    pe = excluded.pe,
                    pb = excluded.pb,
                    div_yield = excluded.div_yield
                """,
                (row["index_name"], row["date"], row["close"], row["pe"], row["pb"], row["div_yield"]),
            )
            rows_written += max(self.conn.total_changes - before, 1)

        if self.backfill_years > 0:
            rows_written += self._backfill_history()

        self.conn.commit()
        return rows_written

    def _backfill_history(self) -> int:
        """Best-effort OHLC-only history backfill (pe/pb/div_yield left NULL
        for these rows unless a row for that date already has values from
        the current-day snapshot)."""
        session = bootstrap_nse_session(make_session())
        to_date = dt.date.today()
        from_date = to_date - dt.timedelta(days=int(self.backfill_years * 365))
        rows_written = 0
        for index_name in TARGET_INDICES:
            history_rows = fetch_index_history(index_name, from_date, to_date, session=session)
            for row in history_rows:
                before = self.conn.total_changes
                self.conn.execute(
                    """
                    INSERT INTO index_data (index_name, date, close, pe, pb, div_yield)
                    VALUES (?, ?, ?, NULL, NULL, NULL)
                    ON CONFLICT(index_name, date) DO UPDATE SET
                        close = excluded.close
                    """,
                    (row["index_name"], row["date"], row["close"]),
                )
                rows_written += max(self.conn.total_changes - before, 0)
            self.conn.commit()
        return rows_written
