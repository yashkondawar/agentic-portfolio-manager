"""BIS (Bank for International Settlements) bulk credit-gap pipeline —
Phase 8 macro KPI sourcing.

Source: https://data.bis.org/static/bulk/WS_CREDIT_GAP_csv_col.zip — a
"wide" (one column per quarter) CSV bundled in a zip, covering every BIS
member country's credit-to-GDP ratio/trend/gap series. See
config/sources.yaml macro.bis_credit_gap for the full column-layout notes
and a documented correction: the series key of interest for India is
`Q:IN:P:A:C` (CG_DTYPE=C, "Credit-to-GDP gaps (actual-trend)") — NOT
`Q.IN.P.A.A` as an earlier plan draft assumed (that key, dot- vs
colon-delimited and CG_DTYPE=A, is actually the raw ratio, not the gap;
confirmed by direct inspection of the unzipped CSV).

The zip is small (~130KB) but re-downloading on every run is wasteful
since BIS only republishes quarterly. Cached under data/raw/bis/; a fresh
download only happens when:
  - no cached copy exists, or
  - the cached copy is >30 days old, or
  - the remote Content-Length differs from the cached file's size
    (a lightweight HEAD-based staleness check; BIS does not reliably
    expose ETag on this static file host, so size is the fallback
    change-detection signal).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import sqlite3
import zipfile
from pathlib import Path

from afund.data.base import Pipeline
from afund.data.http import get, make_session
from afund.sources import get_source

BIS_HOST_KEY = "data.bis.org"
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "bis"
CACHE_FILE = RAW_DIR / "WS_CREDIT_GAP_csv_col.zip"
MAX_CACHE_AGE_DAYS = 30

# Series key for India's credit-to-GDP GAP (actual minus HP-filter trend).
# NOTE (live finding): although the header names column 12 "TITLE_TS" and
# column 13 "Series", in the actual data rows the Q:IN:P:A:C key sits in
# column 13 while column 12 is empty — so matching on header.index("TITLE_TS")
# silently selects nothing. The parser therefore matches on the structured
# metadata columns (BORROWERS_CTY == "IN", CG_DTYPE == "C") instead, which is
# robust to that column quirk.
INDIA_CREDIT_GAP_KEY = "Q:IN:P:A:C"
BORROWERS_CTY_COLUMN = "BORROWERS_CTY"
CG_DTYPE_COLUMN = "CG_DTYPE"
INDIA_COUNTRY_CODE = "IN"
GAP_DTYPE_CODE = "C"  # A=ratio (actual), B=HP trend, C=gap (actual-trend)
N_METADATA_COLUMNS = 14  # FREQ..Series pairs; quarter columns start after this


def _cache_is_stale(session) -> bool:
    if not CACHE_FILE.exists():
        return True
    age_days = (dt.datetime.now() - dt.datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)).days
    if age_days > MAX_CACHE_AGE_DAYS:
        return True
    try:
        source = get_source("macro", "bis_credit_gap")
        head = session.head(source["url"], timeout=20.0)
        remote_len = head.headers.get("Content-Length")
        if remote_len is not None and int(remote_len) != CACHE_FILE.stat().st_size:
            return True
    except Exception:
        # HEAD failing is not itself a reason to force a re-download if we
        # already have a reasonably fresh cache — fall through to "not stale".
        pass
    return False


def _download(session) -> bytes:
    source = get_source("macro", "bis_credit_gap")
    resp = get(session, source["url"], host_key=BIS_HOST_KEY, min_interval=1.0, timeout=60.0)
    resp.raise_for_status()
    return resp.content


class MacroBisPipeline(Pipeline):
    """Fetch (cache-aware) + upsert the India credit-to-GDP gap series."""

    job_name = "macro_bis"

    def fetch(self) -> bytes:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        session = make_session()
        if _cache_is_stale(session):
            content = _download(session)
            CACHE_FILE.write_bytes(content)
            return content
        return CACHE_FILE.read_bytes()

    def parse(self, raw: bytes) -> list[tuple[str, float]]:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                return []
            text = zf.read(csv_names[0]).decode("utf-8-sig")
        return parse_bis_credit_gap_csv(text)

    def upsert(self, parsed: list[tuple[str, float]]) -> int:
        written = 0
        for date, value in parsed:
            cur = self.conn.execute(
                """
                INSERT INTO macro_series (series_code, source, date, value, unit, freq)
                VALUES ('CREDIT_GDP_GAP', 'BIS', ?, ?, 'pct_pts', 'Q')
                ON CONFLICT(series_code, date) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source
                """,
                (date, value),
            )
            written += cur.rowcount
        self.conn.commit()
        return written


def _quarter_to_date(quarter_label: str) -> str | None:
    """'1947-Q4' -> '1947-10-01' (first day of the quarter's first month,
    matching macro_series' date-as-text convention used elsewhere)."""
    try:
        year_str, q_str = quarter_label.split("-Q")
        year = int(year_str)
        quarter = int(q_str)
    except (ValueError, AttributeError):
        return None
    if quarter not in (1, 2, 3, 4):
        return None
    month = (quarter - 1) * 3 + 1
    return dt.date(year, month, 1).isoformat()


def parse_bis_credit_gap_csv(text: str) -> list[tuple[str, float]]:
    """Parse the wide BIS credit-gap CSV, extracting only the India
    actual-minus-trend gap row (BORROWERS_CTY == "IN" and CG_DTYPE == "C",
    i.e. series Q:IN:P:A:C — see the column-quirk note above), and
    returning [(date, value)] for every non-blank quarter column."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        return []

    try:
        cty_idx = header.index(BORROWERS_CTY_COLUMN)
        dtype_idx = header.index(CG_DTYPE_COLUMN)
    except ValueError:
        return []

    quarter_columns = header[N_METADATA_COLUMNS:]

    for row in reader:
        if len(row) <= max(cty_idx, dtype_idx):
            continue
        if row[cty_idx].strip() != INDIA_COUNTRY_CODE:
            continue
        if row[dtype_idx].strip() != GAP_DTYPE_CODE:
            continue

        values = row[N_METADATA_COLUMNS:]
        rows: list[tuple[str, float]] = []
        for quarter_label, raw_value in zip(quarter_columns, values):
            raw_value = raw_value.strip()
            if not raw_value:
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            date = _quarter_to_date(quarter_label.strip())
            if date is None:
                continue
            rows.append((date, value))
        return rows

    return []


if __name__ == "__main__":
    result = MacroBisPipeline().run()
    print(result)
