"""Universe pipeline: NIFTY TOTAL MARKET constituents, liquid ETFs, and
benchmark INDEX rows.

Populates `instruments` + `universe_membership`:
  - STOCK rows for every NIFTY TOTAL MARKET constituent (from the CSV in
    config/sources.yaml -> equity_index.niftyindices_constituents), with
    yf_ticker = symbol + ".NS" and sector/industry from the CSV.
  - ETF rows seeded from config/settings.yaml -> universe.etfs.
  - INDEX rows for NIFTY 50 / NIFTY 500 / NIFTY BANK (with yfinance
    tickers) and NIFTY TOTAL MARKET (yf_ticker NULL — its levels/PE come
    from the index_valuation pipeline instead).
  - INDEX rows for the 8 sector indices (Phase 6, SECTOR_BENCHMARK_INDICES)
    mapping the KPI-registry sectors — see config/settings.yaml ->
    sector_index_map.

Reconstitution handling: any symbol previously flagged as a member of
NIFTY_TOTAL_MARKET (open membership row, effective_to IS NULL) that is no
longer present in the freshly downloaded CSV gets its membership row closed
(effective_to = today). The instrument itself is left active=1 — it may
still trade, just outside this index.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import sqlite3

from afund.config import load_settings
from afund.data.base import Pipeline
from afund.data.http import make_session
from afund.sources import get_source

INDEX_NAME = "NIFTY TOTAL MARKET"

# Benchmark INDEX instruments seeded unconditionally (not sourced from a CSV).
BENCHMARK_INDICES = [
    # symbol, name, yf_ticker
    ("NIFTY 50", "Nifty 50", "^NSEI"),
    ("NIFTY 500", "Nifty 500", "^CRSLDX"),
    ("NIFTY BANK", "Nifty Bank", "^NSEBANK"),
    ("NIFTY TOTAL MARKET", "Nifty Total Market", None),
]

# Sector INDEX instruments (Phase 6) mapping the 8 KPI-registry sectors —
# see config/settings.yaml -> sector_index_map and
# afund.data.index_valuation.SECTOR_INDICES for the P/E backfill target
# list. NIFTY BANK is already seeded above (shared with BENCHMARK_INDICES);
# not repeated here. yf_ticker=None where no working yfinance symbol was
# found (checked live 2026-07-04): NIFTY FINANCIAL SERVICES has no known
# public yfinance ticker (^CNXFINANCE returns no data).
SECTOR_BENCHMARK_INDICES = [
    # symbol, name, yf_ticker
    ("NIFTY FINANCIAL SERVICES", "Nifty Financial Services", None),
    ("NIFTY IT", "Nifty IT", "^CNXIT"),
    ("NIFTY PHARMA", "Nifty Pharma", "^CNXPHARMA"),
    ("NIFTY AUTO", "Nifty Auto", "^CNXAUTO"),
    ("NIFTY FMCG", "Nifty FMCG", "^CNXFMCG"),
    ("NIFTY METAL", "Nifty Metal", "^CNXMETAL"),
    ("NIFTY INFRASTRUCTURE", "Nifty Infrastructure", "^CNXINFRA"),
    ("NIFTY ENERGY", "Nifty Energy", "^CNXENERGY"),
]


def _today() -> str:
    return dt.date.today().isoformat()


def fetch_constituents_csv(timeout: float = 30.0) -> str:
    """Download the NIFTY TOTAL MARKET constituents CSV as raw text."""
    source = get_source("equity_index", "niftyindices_constituents")
    session = make_session()
    resp = session.get(source["url"], timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_constituents_csv(raw_csv: str) -> list[dict]:
    """Parse the constituents CSV text into normalized row dicts.

    Expected columns: Company Name, Industry, Symbol, Series, ISIN Code.
    """
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows: list[dict] = []
    for row in reader:
        symbol = (row.get("Symbol") or "").strip()
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": (row.get("Company Name") or "").strip() or None,
                "sector": (row.get("Industry") or "").strip() or None,
                "industry": (row.get("Industry") or "").strip() or None,
                "isin": (row.get("ISIN Code") or "").strip() or None,
            }
        )
    return rows


def _get_or_create_instrument(
    conn: sqlite3.Connection,
    symbol: str,
    instrument_type: str,
    name: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    isin: str | None = None,
    yf_ticker: str | None = None,
) -> int:
    today = _today()
    existing = conn.execute(
        "SELECT id FROM instruments WHERE symbol = ? AND instrument_type = ?",
        (symbol, instrument_type),
    ).fetchone()
    if existing:
        instrument_id = existing["id"]
        conn.execute(
            """
            UPDATE instruments
               SET name = COALESCE(?, name),
                   sector = COALESCE(?, sector),
                   industry = COALESCE(?, industry),
                   isin = COALESCE(?, isin),
                   yf_ticker = COALESCE(?, yf_ticker),
                   active = 1,
                   last_seen = ?
             WHERE id = ?
            """,
            (name, sector, industry, isin, yf_ticker, today, instrument_id),
        )
        return instrument_id

    cur = conn.execute(
        """
        INSERT INTO instruments
            (symbol, isin, name, instrument_type, sector, industry, yf_ticker,
             active, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (symbol, isin, name, instrument_type, sector, industry, yf_ticker, today, today),
    )
    return cur.lastrowid


def _ensure_membership_open(conn: sqlite3.Connection, instrument_id: int, index_name: str) -> None:
    today = _today()
    open_row = conn.execute(
        """
        SELECT id FROM universe_membership
         WHERE instrument_id = ? AND index_name = ? AND effective_to IS NULL
        """,
        (instrument_id, index_name),
    ).fetchone()
    if open_row:
        return  # already an open membership row, nothing to do (idempotent)
    conn.execute(
        """
        INSERT INTO universe_membership (instrument_id, index_name, effective_from, effective_to)
        VALUES (?, ?, ?, NULL)
        """,
        (instrument_id, index_name, today),
    )


def _close_membership(conn: sqlite3.Connection, instrument_id: int, index_name: str) -> None:
    today = _today()
    conn.execute(
        """
        UPDATE universe_membership
           SET effective_to = ?
         WHERE instrument_id = ? AND index_name = ? AND effective_to IS NULL
        """,
        (today, instrument_id, index_name),
    )


class UniversePipeline(Pipeline):
    """Downloads NIFTY TOTAL MARKET constituents, seeds ETFs + benchmark
    indices, and reconciles universe_membership for reconstitution."""

    job_name = "universe"

    def fetch(self) -> str:
        return fetch_constituents_csv()

    def parse(self, raw: str) -> list[dict]:
        return parse_constituents_csv(raw)

    def upsert(self, parsed: list[dict]) -> int:
        settings = load_settings()
        etf_symbols: list[str] = settings.get("universe", {}).get("etfs", [])

        rows_written = 0
        current_symbols: set[str] = set()

        for row in parsed:
            symbol = row["symbol"]
            current_symbols.add(symbol)
            instrument_id = _get_or_create_instrument(
                self.conn,
                symbol=symbol,
                instrument_type="STOCK",
                name=row["name"],
                sector=row["sector"],
                industry=row["industry"],
                isin=row["isin"],
                yf_ticker=f"{symbol}.NS",
            )
            _ensure_membership_open(self.conn, instrument_id, INDEX_NAME)
            rows_written += 1

        # Reconstitution: close membership for symbols with an open
        # membership row that are no longer in the freshly downloaded CSV.
        previously_open = self.conn.execute(
            """
            SELECT i.id AS instrument_id, i.symbol AS symbol
              FROM universe_membership um
              JOIN instruments i ON i.id = um.instrument_id
             WHERE um.index_name = ? AND um.effective_to IS NULL
            """,
            (INDEX_NAME,),
        ).fetchall()
        for prev in previously_open:
            if prev["symbol"] not in current_symbols:
                _close_membership(self.conn, prev["instrument_id"], INDEX_NAME)

        # Seed liquid ETFs.
        for symbol in etf_symbols:
            _get_or_create_instrument(
                self.conn,
                symbol=symbol,
                instrument_type="ETF",
                yf_ticker=f"{symbol}.NS",
            )
            rows_written += 1

        # Seed benchmark INDEX rows.
        for symbol, name, yf_ticker in BENCHMARK_INDICES:
            _get_or_create_instrument(
                self.conn,
                symbol=symbol,
                instrument_type="INDEX",
                name=name,
                yf_ticker=yf_ticker,
            )
            rows_written += 1

        # Seed sector benchmark INDEX rows (Phase 6).
        for symbol, name, yf_ticker in SECTOR_BENCHMARK_INDICES:
            _get_or_create_instrument(
                self.conn,
                symbol=symbol,
                instrument_type="INDEX",
                name=name,
                yf_ticker=yf_ticker,
            )
            rows_written += 1

        self.conn.commit()
        return rows_written
