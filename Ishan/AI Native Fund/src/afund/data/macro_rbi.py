"""RBI macro series ingestion.

PHASE 1 FINDING: data.rbi.org.in/DBIE (RBI's "Database on Indian Economy")
is a form-driven Angular dashboard — every series export requires
JavaScript-driven UI interaction (select series -> select date range ->
click export) with no stable, discoverable direct CSV/XLSX URL. The same is
true of rbi.org.in's "current rates" pages, which are HTML tables refreshed
by hand rather than a stable feed. Within the ~20 minute Phase 1 budget, no
scriptable fetch could be found (see config/sources.yaml -> macro.rbi_dbie,
marked broken with the investigation notes).

Supported path: `import_macro_csv()` — a manual-import function the user
runs after downloading a CSV export themselves.

Manual download instructions (repo rate + CPI, the two series most useful
to the regime overlay):
  1. Repo rate: https://www.rbi.org.in/en/web/rbi -> "Rates" widget (top of
     homepage) shows the current policy repo rate; for history, RBI's
     Monetary Policy Report / Database on Indian Economy (DBIE) at
     https://data.rbi.org.in/DBIE/ -> Statistics -> "Bank Rate, Repo Rate...”
     -> export to CSV.
  2. CPI (combined, base 2012=100): DBIE -> Statistics -> "CPI" section ->
     export to CSV, or the monthly CPI press release PDF at mospi.gov.in
     (see macro_mospi.py) if DBIE access is inconvenient.

CSV format expected by import_macro_csv() (documented so the user's export
just needs re-saving into this shape, or the user hand-builds a CSV):
    date,value
    2026-01-01,6.50
    2026-02-01,6.50
    ...
`date` must be ISO-8601 (YYYY-MM-DD); `value` a plain float. One CSV per
series (series_code and source are passed as arguments, not read from the
file, since RBI's own exports don't consistently include them). No comment
lines — csv.DictReader treats the first line as the header, so a leading
`#...` line would corrupt parsing.

data/manual/example_repo_rate.csv demonstrates the expected shape (ILLUSTRATIVE
placeholder values only, not a real RBI export — replace before importing
for real use).
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from afund.db.connection import get_conn

MANUAL_IMPORT_DIR = Path(__file__).resolve().parents[3] / "data" / "manual"


def import_macro_csv(
    path: str | Path,
    series_code: str,
    source: str = "RBI",
    freq: str = "M",
    unit: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Import a two-column (date,value) CSV into macro_series.

    Idempotent via INSERT OR IGNORE on the (series_code, date) UNIQUE key.
    Returns the number of new rows written.
    """
    owns_conn = conn is None
    conn = conn or get_conn()
    try:
        rows_written = 0
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = (row.get("date") or "").strip()
                value_raw = (row.get("value") or "").strip()
                if not date or not value_raw:
                    continue
                try:
                    value = float(value_raw)
                except ValueError:
                    continue
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO macro_series (series_code, source, date, value, unit, freq)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (series_code, source, date, value, unit, freq),
                )
                rows_written += conn.total_changes - before
        conn.commit()
        return rows_written
    finally:
        if owns_conn:
            conn.close()
