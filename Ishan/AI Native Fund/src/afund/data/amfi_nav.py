"""AMFI mutual fund NAV pipeline.

Parses NAVAll.txt (semicolon-delimited; one line per scheme, interspersed
with blank lines and AMC/category header lines that have no semicolons) and
upserts every scheme's NAV into `mf_navs`. Also auto-registers `instruments`
rows (instrument_type MUTUAL_FUND) for schemes listed in
config/settings.yaml -> universe.mf_watchlist (NOT for every scheme — that
list is empty by default; the user fills it in later).

Also provides fetch_scheme_history(), a helper for later single-scheme
NAV backfills. See its docstring for the important caveat about AMFI's
history endpoint not actually supporting server-side single-scheme
filtering (see config/sources.yaml -> mutual_funds.amfi_nav_history notes).
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from afund.config import load_settings
from afund.data.base import Pipeline
from afund.data.http import make_session
from afund.sources import get_source


def fetch_navall_text(timeout: float = 60.0) -> str:
    source = get_source("mutual_funds", "amfi_daily_nav")
    session = make_session()
    resp = session.get(source["url"], timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _parse_date(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return dt.datetime.strptime(raw, "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def parse_navall(raw_text: str) -> list[dict]:
    """Parse NAVAll.txt into a list of {scheme_code, scheme_name, nav, date, isin_growth, isin_div}.

    Lines are semicolon-delimited with 6 fields:
      Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
    AMC/category header lines (no semicolons) and blank lines are skipped.
    The literal header row (starts with "Scheme Code;") is also skipped.
    """
    rows: list[dict] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Scheme Code;"):
            continue
        if ";" not in line:
            continue  # AMC name or category header line
        parts = line.split(";")
        if len(parts) < 6:
            continue
        scheme_code, isin_growth, isin_div, scheme_name, nav_raw, date_raw = parts[:6]
        scheme_code = scheme_code.strip()
        if not scheme_code or not scheme_code.isdigit():
            continue
        try:
            nav = float(nav_raw.strip())
        except ValueError:
            continue
        date_iso = _parse_date(date_raw)
        if date_iso is None:
            continue
        rows.append(
            {
                "scheme_code": scheme_code,
                "scheme_name": scheme_name.strip(),
                "isin_growth": isin_growth.strip() if isin_growth.strip() != "-" else None,
                "isin_div": isin_div.strip() if isin_div.strip() != "-" else None,
                "nav": nav,
                "date": date_iso,
            }
        )
    return rows


def fetch_scheme_history(scheme_code: str, from_date: dt.date, to_date: dt.date, timeout: float = 60.0) -> list[dict]:
    """Fetch NAV history for ONE scheme code over a date range (<=90 days).

    IMPORTANT: AMFI's DownloadNAVHistoryReport_Po.aspx endpoint does not
    actually support server-side filtering by scheme code (confirmed live
    during Phase 1 — see config/sources.yaml notes on amfi_nav_history); it
    always returns the full bulk file for the `tp` bucket. This helper
    fetches the bulk open-ended-schemes file (tp=1) for the requested date
    range and filters to `scheme_code` client-side. For longer backfills,
    callers must chunk the date range into <=90-day windows themselves.
    """
    if (to_date - from_date).days > 90:
        raise ValueError("AMFI history requests are capped at ~90 days per call; chunk the range.")

    source = get_source("mutual_funds", "amfi_nav_history")
    base_url = source["url"].split("&frmdt=")[0]  # "...aspx?tp=1"
    url = (
        f"{base_url}&frmdt={from_date.strftime('%d-%b-%Y')}"
        f"&todt={to_date.strftime('%d-%b-%Y')}"
    )
    session = make_session()
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()

    rows: list[dict] = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line or line.startswith("Scheme Code;") or ";" not in line:
            continue
        parts = line.split(";")
        if len(parts) < 8:
            continue
        code = parts[0].strip()
        if code != scheme_code:
            continue
        nav_raw = parts[4].strip()
        date_raw = parts[7].strip()
        try:
            nav = float(nav_raw)
        except ValueError:
            continue
        date_iso = _parse_date(date_raw)
        if date_iso is None:
            continue
        rows.append({"scheme_code": code, "nav": nav, "date": date_iso})
    return rows


def _get_or_create_mf_instrument(conn: sqlite3.Connection, scheme_code: str, scheme_name: str) -> int:
    today = dt.date.today().isoformat()
    existing = conn.execute(
        "SELECT id FROM instruments WHERE amfi_scheme_code = ? AND instrument_type = 'MUTUAL_FUND'",
        (scheme_code,),
    ).fetchone()
    if existing:
        return existing["id"]
    cur = conn.execute(
        """
        INSERT INTO instruments
            (symbol, name, instrument_type, amfi_scheme_code, active, first_seen, last_seen)
        VALUES (?, ?, 'MUTUAL_FUND', ?, 1, ?, ?)
        """,
        (scheme_code, scheme_name, scheme_code, today, today),
    )
    return cur.lastrowid


class AmfiNavPipeline(Pipeline):
    """Daily AMFI NAV fetch: stores NAVs for ALL schemes, registers
    instruments only for schemes in universe.mf_watchlist."""

    job_name = "amfi_nav"

    def fetch(self) -> str:
        return fetch_navall_text()

    def parse(self, raw: str) -> list[dict]:
        return parse_navall(raw)

    def upsert(self, parsed: list[dict]) -> int:
        settings = load_settings()
        watchlist = set(settings.get("universe", {}).get("mf_watchlist", []) or [])

        rows_written = 0
        for row in parsed:
            before = self.conn.total_changes
            self.conn.execute(
                """
                INSERT OR IGNORE INTO mf_navs (scheme_code, date, nav, source)
                VALUES (?, ?, ?, 'AMFI')
                """,
                (row["scheme_code"], row["date"], row["nav"]),
            )
            rows_written += self.conn.total_changes - before

            if row["scheme_code"] in watchlist:
                _get_or_create_mf_instrument(self.conn, row["scheme_code"], row["scheme_name"])

        self.conn.commit()
        return rows_written
