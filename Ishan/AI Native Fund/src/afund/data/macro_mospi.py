"""MOSPI (Ministry of Statistics) macro series ingestion.

PHASE 1 FINDING: mospi.gov.in publishes CPI/IIP/GDP releases as dated
press-note PDF bundles (e.g. under "Press Release" / "Publications"), not as
a single stable machine-readable index CSV/XLSX URL. Within the ~20 minute
Phase 1 budget, no scriptable fetch could be found (see
config/sources.yaml -> macro.mospi, marked broken with investigation
notes). eSankhyiki (https://esankhyiki.mospi.gov.in/) hosts a newer data
portal with an API, but it requires registration/exploration beyond the
time budget for this phase.

Supported path: `import_macro_csv()` (delegates to the same implementation
as macro_rbi.import_macro_csv — the two modules share format and behavior,
kept separate only so each has its own module docstring documenting where
to get ITS series specifically).

Manual download instructions (CPI combined index, the series most useful to
the regime overlay):
  1. Go to https://www.mospi.gov.in/ -> "Statistics" / "Press Releases" ->
     find the latest "Consumer Price Index" press release for the target
     month (published monthly, typically ~12th of the following month).
  2. The release PDF contains the All-India CPI (Combined) index table;
     transcribe (or use eSankhyiki's CPI dataset export once explored) into
     a CSV of the form:
         date,value
         2026-01-01,187.4
         2026-02-01,188.1
     `date` = first of the reference month, ISO-8601; `value` = the index
     level (base 2012=100).
  3. Run: `import_macro_csv(path, series_code="CPI_COMBINED", source="MOSPI")`
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from afund.data.macro_rbi import import_macro_csv as _import_macro_csv

MANUAL_IMPORT_DIR = Path(__file__).resolve().parents[3] / "data" / "manual"


def import_macro_csv(
    path: str | Path,
    series_code: str,
    source: str = "MOSPI",
    freq: str = "M",
    unit: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Import a two-column (date,value) CSV into macro_series. See module
    docstring for the documented CSV format and where to source MOSPI data."""
    return _import_macro_csv(path, series_code=series_code, source=source, freq=freq, unit=unit, conn=conn)
