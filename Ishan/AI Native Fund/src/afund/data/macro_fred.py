"""FRED CSV-gateway pipeline — Phase 8 macro KPI sourcing.

FRED (Federal Reserve Bank of St. Louis) publishes a no-API-key CSV
gateway at https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}
that returns the full history of a series as a two-column CSV
(observation_date,{SERIES_ID}). No key, no rate limit documented; still
routed through afund.data.http.make_session + a polite host rate limit.

Configured series (see config/sources.yaml `macro` group for the
per-series verify_status/notes):
    INDIRLTLT01STM -> GSEC_10Y   (India 10Y G-Sec yield, monthly, %)
    RBINBIS        -> REER       (India real effective exchange rate, monthly, index)
    INDCPIALLMINMEI-> CPI_INDEX  (India CPI all-items, monthly, index)
                       + derives CPI_YOY (12m %-change) as a second write
    DGS10          -> US_10Y     (US 10Y Treasury yield, daily, %)

Full history is re-fetched every run (each file is a few hundred KB at
most) and idempotently upserted: unlike afund.data.macro_rbi's
`INSERT OR IGNORE` (used for a static manual CSV import where existing
rows never need to change), this pipeline uses
`ON CONFLICT(series_code, date) DO UPDATE` because FRED occasionally
revises published values and re-running should refresh them, not just
skip.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import sqlite3
from typing import Any

import requests

from afund.data.base import Pipeline
from afund.data.http import get, make_session
from afund.sources import get_source

FRED_HOST_KEY = "fred.stlouisfed.org"
FRED_MIN_INTERVAL = 1.0

# FRED's edge (WAF/Akamai) silently hangs/resets connections that present a
# spoofed browser User-Agent (confirmed live: afund.data.http.make_session's
# default Chrome-style UA causes a hard read-timeout/connection-reset on
# every request, while a plain `requests` default UA — "python-requests/x.y"
# — succeeds in ~1s). This is the opposite of most sites this project talks
# to (which usually want a browser UA to avoid basic bot-blocking), so
# macro_fred deliberately overrides the session's User-Agent back to
# requests' own default rather than reusing the shared browser-UA session
# as-is.
_FRED_UA_OVERRIDE = requests.utils.default_user_agent()

# (fred_series_id, series_code, unit, freq)
FRED_SERIES: list[tuple[str, str, str, str]] = [
    ("INDIRLTLT01STM", "GSEC_10Y", "%", "M"),
    ("RBINBIS", "REER", "index", "M"),
    ("INDCPIALLMINMEI", "CPI_INDEX", "index", "M"),
    ("DGS10", "US_10Y", "%", "D"),
]

# sources.yaml key per fred_series_id, for URL templating.
_SOURCES_KEY = {
    "INDIRLTLT01STM": "fred_gsec_10y",
    "RBINBIS": "fred_reer",
    "INDCPIALLMINMEI": "fred_cpi_india",
    "DGS10": "fred_us_10y",
}


def _fetch_series_csv(session, fred_series_id: str) -> str:
    source = get_source("macro", _SOURCES_KEY[fred_series_id])
    resp = get(
        session,
        source["url"],
        host_key=FRED_HOST_KEY,
        min_interval=FRED_MIN_INTERVAL,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.text


def parse_fred_csv(text: str, series_id: str) -> list[tuple[str, float]]:
    """Parse a FRED gateway CSV (`observation_date,{series_id}` header)
    into a sorted [(date, value)] list. FRED marks missing observations
    with the literal string "." — those rows are skipped (never coerced
    to 0 or fabricated)."""
    rows: list[tuple[str, float]] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2:
        return rows
    for row in reader:
        if len(row) < 2:
            continue
        date_str, raw_value = row[0].strip(), row[1].strip()
        if not date_str or raw_value in ("", "."):
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        rows.append((date_str, value))
    rows.sort(key=lambda r: r[0])
    return rows


def compute_cpi_yoy(cpi_index_rows: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """12-month %-change of a monthly CPI index series -> CPI_YOY points.
    Matches on the observation exactly 12 rows earlier (monthly cadence,
    so this is a true YoY comparison as long as the source series has no
    gaps — FRED's INDCPIALLMINMEI is a complete monthly series)."""
    yoy: list[tuple[str, float]] = []
    for i in range(12, len(cpi_index_rows)):
        date, value = cpi_index_rows[i]
        _, base_value = cpi_index_rows[i - 12]
        if base_value == 0:
            continue
        yoy.append((date, (value - base_value) / base_value * 100.0))
    return yoy


def _upsert_series(conn: sqlite3.Connection, series_code: str, source: str,
                    rows: list[tuple[str, float]], unit: str, freq: str) -> int:
    written = 0
    for date, value in rows:
        cur = conn.execute(
            """
            INSERT INTO macro_series (series_code, source, date, value, unit, freq)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_code, date) DO UPDATE SET
                value = excluded.value,
                source = excluded.source,
                unit = COALESCE(excluded.unit, macro_series.unit),
                freq = COALESCE(excluded.freq, macro_series.freq)
            """,
            (series_code, source, date, value, unit, freq),
        )
        written += cur.rowcount
    return written


class MacroFredPipeline(Pipeline):
    """Fetch + upsert all FRED-sourced macro series, including the derived
    CPI_YOY write."""

    job_name = "macro_fred"

    def fetch(self) -> dict[str, str]:
        session = make_session()
        session.headers["User-Agent"] = _FRED_UA_OVERRIDE
        raw: dict[str, str] = {}
        for fred_series_id, _series_code, _unit, _freq in FRED_SERIES:
            raw[fred_series_id] = _fetch_series_csv(session, fred_series_id)
        return raw

    def parse(self, raw: dict[str, str]) -> dict[str, list[tuple[str, float]]]:
        parsed: dict[str, list[tuple[str, float]]] = {}
        for fred_series_id, series_code, _unit, _freq in FRED_SERIES:
            parsed[series_code] = parse_fred_csv(raw[fred_series_id], fred_series_id)

        cpi_rows = parsed.get("CPI_INDEX", [])
        if cpi_rows:
            parsed["CPI_YOY"] = compute_cpi_yoy(cpi_rows)
        return parsed

    def upsert(self, parsed: dict[str, list[tuple[str, float]]]) -> int:
        unit_freq = {series_code: (unit, freq) for _id, series_code, unit, freq in FRED_SERIES}
        unit_freq["CPI_YOY"] = ("%", "M")

        total = 0
        for series_code, rows in parsed.items():
            unit, freq = unit_freq.get(series_code, (None, None))
            total += _upsert_series(self.conn, series_code, "FRED", rows, unit, freq)
        self.conn.commit()
        return total


if __name__ == "__main__":
    result = MacroFredPipeline().run()
    print(result)
