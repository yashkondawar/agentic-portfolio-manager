"""Phase 10 — match ETF instruments to AMFI scheme codes.

The 10 seeded ETF instruments (config/settings.yaml -> universe.etfs) are
registered with amfi_scheme_code = NULL (they're sourced from yfinance for
prices, not AMFI). ETF premium/discount analysis
(src/afund/derive/fund_analytics.py::etf_premium_discount) needs each ETF's
AMFI scheme code to look up its official NAV in mf_navs.

This script:
  1. Fetches NAVAll.txt once (afund.data.amfi_nav helpers — no new fetch path).
  2. Normalizes every AMFI scheme_name into tokens and tries to match each
     ETF's instruments.symbol / name against candidate AMFI rows whose scheme
     category text looks like an ETF ("EXCHANGE TRADED FUND" AMC groupings —
     NAVAll.txt has no explicit category column reaching this parser, so we
     match on name tokens only).
  3. Auto-matches confident hits (all significant symbol tokens present in
     the candidate scheme name) and writes instruments.amfi_scheme_code.
  4. Falls back to config/settings.yaml -> etf_scheme_code_pins for any ETF
     that doesn't auto-match, or that has a pin explicitly set (pins win).
  5. Prints a per-ETF report: MATCHED (auto) / MATCHED (pin) / UNMATCHED.

Idempotent: re-running just re-confirms/re-writes the same scheme codes
(UPDATE, not INSERT), never clobbers a non-NULL amfi_scheme_code with NULL.
"""
from __future__ import annotations

import re
import sqlite3
import sys

from afund.config import load_settings
from afund.data.amfi_nav import fetch_navall_text, parse_navall
from afund.db.connection import get_conn

# Hand-curated token hints per ETF symbol: words that should appear in the
# matching AMFI scheme name, beyond the obvious symbol-derived tokens. AMFI
# scheme names for ETFs are typically like "Nippon India ETF Nifty BeES" or
# "SBI - ETF Nifty 50" — free-form, no fixed template — so a pure
# token-overlap heuristic needs a bit of domain steering per symbol.
_SYMBOL_HINTS: dict[str, list[str]] = {
    "NIFTYBEES": ["nifty", "bees"],
    "JUNIORBEES": ["junior", "bees"],
    "GOLDBEES": ["gold", "bees"],
    # Nippon dropped the "BeES" brand suffix for these three when it renamed
    # its ETF range (~2023) — the live AMFI names are plain
    # "Nippon India ETF <Silver|Nifty IT|Nifty Pharma>", no "bees" token.
    "SILVERBEES": ["nippon", "silver"],
    "BANKBEES": ["bank", "bees"],
    "ITBEES": ["nippon", "nifty", "it"],
    "PHARMABEES": ["nippon", "nifty", "pharma"],
    "MON100": ["nasdaq", "100"],  # Motilal Oswal NASDAQ 100 ETF
    "MAFANG": ["nyse", "fang"],  # Motilal Oswal NYSE FANG+ ETF
    "CPSEETF": ["cpse"],
}

_STOPWORDS = {"the", "a", "an", "of", "and", "&", "-", "etf", "fund", "scheme"}


def _tokenize(name: str) -> set[str]:
    name = name.lower().replace("-", " ")
    tokens = re.findall(r"[a-z0-9]+", name)
    return {t for t in tokens if t not in _STOPWORDS}


def _best_match(hints: list[str], candidates: list[dict]) -> dict | None:
    """Return the AMFI row whose scheme_name contains ALL hint tokens, with
    the shortest scheme_name among ties (more specific / less padded)."""
    hint_set = {h.lower() for h in hints}
    hits = []
    for row in candidates:
        tokens = _tokenize(row["scheme_name"])
        if hint_set.issubset(tokens):
            hits.append(row)
    if not hits:
        return None
    hits.sort(key=lambda r: len(r["scheme_name"]))
    return hits[0]


def build_matches(navall_rows: list[dict]) -> dict[str, dict | None]:
    """Return {etf_symbol: best-matching AMFI row (or None)}."""
    # De-dup by scheme_code (NAVAll.txt has one row per code per day; a
    # single fetch will already be de-duped across the batch, but be safe).
    by_code: dict[str, dict] = {}
    for row in navall_rows:
        by_code[row["scheme_code"]] = row
    candidates = list(by_code.values())

    matches: dict[str, dict | None] = {}
    for symbol, hints in _SYMBOL_HINTS.items():
        matches[symbol] = _best_match(hints, candidates)
    return matches


def apply_matches(conn: sqlite3.Connection, matches: dict[str, dict | None], pins: dict[str, str]) -> list[dict]:
    """Write instruments.amfi_scheme_code; pins override auto-matches.
    Returns a per-ETF report list of dicts for printing."""
    report = []
    for symbol in _SYMBOL_HINTS:
        row = conn.execute(
            "SELECT id, amfi_scheme_code FROM instruments WHERE symbol = ? AND instrument_type = 'ETF'",
            (symbol,),
        ).fetchone()
        if row is None:
            report.append({"symbol": symbol, "status": "NO_INSTRUMENT_ROW", "scheme_code": None, "scheme_name": None})
            continue

        pin = pins.get(symbol)
        auto = matches.get(symbol)

        if pin:
            scheme_code = str(pin)
            scheme_name = None
            status = "MATCHED (pin)"
        elif auto:
            scheme_code = auto["scheme_code"]
            scheme_name = auto["scheme_name"]
            status = "MATCHED (auto)"
        else:
            report.append({"symbol": symbol, "status": "UNMATCHED", "scheme_code": None, "scheme_name": None})
            continue

        conn.execute(
            "UPDATE instruments SET amfi_scheme_code = ? WHERE id = ?",
            (scheme_code, row["id"]),
        )
        report.append({"symbol": symbol, "status": status, "scheme_code": scheme_code, "scheme_name": scheme_name})

    conn.commit()
    return report


def main() -> int:
    settings = load_settings()
    pins = settings.get("etf_scheme_code_pins") or {}

    print("Fetching AMFI NAVAll.txt ...")
    raw = fetch_navall_text()
    navall_rows = parse_navall(raw)
    print(f"Parsed {len(navall_rows)} NAV rows.")

    matches = build_matches(navall_rows)

    conn = get_conn()
    try:
        report = apply_matches(conn, matches, pins)
    finally:
        conn.close()

    print()
    print(f"{'SYMBOL':<12}{'STATUS':<18}{'SCHEME_CODE':<14}SCHEME_NAME")
    for r in report:
        print(f"{r['symbol']:<12}{r['status']:<18}{str(r['scheme_code'] or ''):<14}{r['scheme_name'] or ''}")

    unmatched = [r for r in report if r["status"] == "UNMATCHED"]
    if unmatched:
        print()
        print(f"{len(unmatched)} ETF(s) unmatched — add a pin to config/settings.yaml -> etf_scheme_code_pins:")
        for r in unmatched:
            print(f"  {r['symbol']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
