"""Manual-import definitions for macro KPI series that have no free,
stable, machine-readable source within this project's scripting budget —
Phase 8 macro KPI sourcing.

Thin wrapper around afund.data.macro_rbi.import_macro_csv (the same
idempotent `INSERT OR IGNORE`-on-(series_code,date) pattern already used
by macro_rbi.py / macro_mospi.py). This module adds no new import
mechanics — it exists to document, in one place, exactly which series are
manual-only and the CSV shape + source page each expects, so a human can
periodically drop a 2-column `date,value` CSV into data/manual/ and run
the corresponding import_*() helper.

Series covered (all quarterly or lower cadence, all released as
PDF/press-note bundles or dashboard-only with no stable CSV/XLSX download
URL discoverable within budget — see config/sources.yaml `macro` group
rbi_dbie/mospi entries for the underlying site investigation notes):

  GDP_NOMINAL   — India nominal GDP, quarterly (INR crore or % YoY, pick
                  one unit and stay consistent — MOSPI's quarterly GDP
                  press release: https://www.mospi.gov.in/press-release
                  ("Provisional Estimates of Annual National Income" /
                  quarterly GDP estimates PDF bundle). No stable direct
                  file URL; copy the headline nominal GDP figure per
                  quarter by hand.
  PMI_MFG       — S&P Global India Manufacturing PMI, monthly (index,
                  50=neutral). Published via S&P Global press release
                  (https://www.pmi.spglobal.com/Public/Home/PressRelease
                  — search "India Manufacturing PMI"); the headline index
                  value is in the press release's opening paragraph/table.
                  No free bulk history API; S&P's own site gates the full
                  time series behind a paid subscription.
  PMI_SERVICES  — S&P Global India Services PMI, monthly (index,
                  50=neutral). Same source/caveats as PMI_MFG.
  REPO_RATE     — RBI policy repo rate, event-driven (changes only at MPC
                  meetings, not a fixed cadence). RBI DBIE
                  (https://data.rbi.org.in/DBIE/) or the RBI Monetary
                  Policy press release page. See macro_rbi.py's own
                  docstring for the DBIE export steps already documented
                  there.

CSV format (identical to macro_rbi.import_macro_csv's existing
convention, documented again here for discoverability):
    date,value
    2026-01-01,7.5
    2026-04-01,7.8

  - `date`: ISO 8601 (YYYY-MM-DD). For quarterly/monthly series, use the
    first day of the period.
  - `value`: a plain float. No units/commas/currency symbols.
  - Malformed rows (bad date or non-numeric value) are skipped, not
    fabricated — see macro_rbi.import_macro_csv's malformed-row handling.

PHASE 8 CLEANUP NOTE: the live macro_series table previously carried 11
REPO_RATE_EXAMPLE rows (source='RBI', 2025-08 through 2026-06) that were
placeholder/illustrative data seeded during Phase 0-1 authoring, never a
real RBI import. These were deleted as part of Phase 8 (see the Phase 8
commit) since REPO_RATE_EXAMPLE was never a real series_code any pipeline
or KPI references — data/manual/example_repo_rate.csv remains on disk
purely as the offline test fixture for
tests/test_pipelines/test_macro_import.py's import_macro_csv tests,
unrelated to this cleanup.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from afund.data.macro_rbi import import_macro_csv

MANUAL_IMPORT_DIR = Path(__file__).resolve().parents[3] / "data" / "manual"


def import_gdp_nominal(path: Path, conn: sqlite3.Connection | None = None) -> int:
    """Import a manually-prepared GDP_NOMINAL CSV (MOSPI quarterly GDP
    press release figures)."""
    return import_macro_csv(path, series_code="GDP_NOMINAL", source="MOSPI", freq="Q", conn=conn)


def import_pmi_mfg(path: Path, conn: sqlite3.Connection | None = None) -> int:
    """Import a manually-prepared PMI_MFG CSV (S&P Global India
    Manufacturing PMI press release headline figures)."""
    return import_macro_csv(path, series_code="PMI_MFG", source="S&P_GLOBAL", freq="M", conn=conn)


def import_pmi_services(path: Path, conn: sqlite3.Connection | None = None) -> int:
    """Import a manually-prepared PMI_SERVICES CSV (S&P Global India
    Services PMI press release headline figures)."""
    return import_macro_csv(path, series_code="PMI_SERVICES", source="S&P_GLOBAL", freq="M", conn=conn)


def import_repo_rate(path: Path, conn: sqlite3.Connection | None = None) -> int:
    """Import a manually-prepared REPO_RATE CSV (RBI policy repo rate,
    one row per MPC decision/change)."""
    return import_macro_csv(path, series_code="REPO_RATE", source="RBI", freq="M", conn=conn)
