"""Corporate actions + announcements pipeline via the `nse` PyPI library
(BennyThadikaran/NseIndiaApi), watchlist-scoped like financials.py.

`pip install nse` succeeded and its NSE.actions()/NSE.announcements() calls
were smoke-tested live against INFY during Phase 1 authoring (see
config/sources.yaml -> nse_corporate) — both work cleanly, so this module
wraps the library directly rather than falling back to hand-rolled
requests calls against the raw JSON endpoints.

Storage: corporate_actions (ex_date, action_type, details, record_date,
raw_json holding the full action dict). Announcements are stored inside
corporate_actions.raw_json too (action_type='ANNOUNCEMENT') rather than a
dedicated table, since the schema only defines corporate_actions for this
data — see schema.sql.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from afund.config import load_settings
from afund.data.base import Pipeline

try:
    from nse import NSE

    NSE_LIB_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only if `nse` fails to install
    NSE_LIB_AVAILABLE = False


def fetch_actions_for_symbol(symbol: str, download_folder: str = ".") -> list[dict]:
    """Fetch forthcoming/recent corporate actions for one symbol via the nse library."""
    if not NSE_LIB_AVAILABLE:
        raise RuntimeError("`nse` package not installed — pip install nse")
    client = NSE(download_folder=download_folder)
    try:
        return client.actions(symbol=symbol) or []
    finally:
        client.exit()


def fetch_announcements_for_symbol(symbol: str, download_folder: str = ".") -> list[dict]:
    """Fetch recent corporate announcements for one symbol via the nse library."""
    if not NSE_LIB_AVAILABLE:
        raise RuntimeError("`nse` package not installed — pip install nse")
    client = NSE(download_folder=download_folder)
    try:
        return client.announcements(symbol=symbol) or []
    finally:
        client.exit()


def _parse_action_date(raw: str | None) -> str | None:
    if not raw or raw == "-":
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _row_exists(conn: sqlite3.Connection, instrument_id: int, ex_date, action_type: str, details) -> bool:
    """corporate_actions has no UNIQUE constraint in the Phase 0 schema, so
    idempotency is enforced here at the application layer: skip insert if an
    identical (instrument_id, ex_date, action_type, details) row already
    exists."""
    row = conn.execute(
        """
        SELECT 1 FROM corporate_actions
         WHERE instrument_id = ? AND action_type = ?
           AND ex_date IS ? AND details IS ?
         LIMIT 1
        """,
        (instrument_id, action_type, ex_date, details),
    ).fetchone()
    return row is not None


class CorpActionsPipeline(Pipeline):
    """Watchlist-scoped NSE corporate actions + announcements fetch."""

    job_name = "corp_actions"

    def __init__(self, conn: sqlite3.Connection | None = None, symbols: list[str] | None = None):
        super().__init__(conn)
        settings = load_settings()
        self.symbols = symbols if symbols is not None else settings.get("universe", {}).get("watchlist", [])
        self.symbol_errors: dict[str, str] = {}

    def fetch(self) -> dict[str, dict]:
        if not NSE_LIB_AVAILABLE:
            raise RuntimeError("`nse` package not installed — cannot fetch corporate actions")

        results: dict[str, dict] = {}
        for symbol in self.symbols:
            entry: dict = {"actions": [], "announcements": []}
            try:
                entry["actions"] = fetch_actions_for_symbol(symbol)
            except Exception as exc:  # noqa: BLE001
                self.symbol_errors[f"{symbol}:actions"] = f"{type(exc).__name__}: {exc}"
            try:
                entry["announcements"] = fetch_announcements_for_symbol(symbol)
            except Exception as exc:  # noqa: BLE001
                self.symbol_errors[f"{symbol}:announcements"] = f"{type(exc).__name__}: {exc}"
            results[symbol] = entry
        return results

    def parse(self, raw: dict[str, dict]) -> dict[str, dict]:
        return raw  # already in a directly-storable shape

    def upsert(self, parsed: dict[str, dict]) -> int:
        rows_written = 0
        for symbol, entry in parsed.items():
            instrument = self.conn.execute(
                "SELECT id FROM instruments WHERE symbol = ? AND instrument_type = 'STOCK'",
                (symbol,),
            ).fetchone()
            if instrument is None:
                self.symbol_errors[symbol] = "symbol not found in instruments (run universe pipeline first)"
                continue
            instrument_id = instrument["id"]

            for action in entry.get("actions", []):
                ex_date = _parse_action_date(action.get("exDate"))
                record_date = _parse_action_date(action.get("recDate"))
                details = action.get("subject")
                if _row_exists(self.conn, instrument_id, ex_date, "CORPORATE_ACTION", details):
                    continue
                self.conn.execute(
                    """
                    INSERT INTO corporate_actions
                        (instrument_id, ex_date, action_type, details, record_date, raw_json)
                    VALUES (?, ?, 'CORPORATE_ACTION', ?, ?, ?)
                    """,
                    (instrument_id, ex_date, details, record_date, json.dumps(action)),
                )
                rows_written += 1

            for ann in entry.get("announcements", []):
                ex_date = _parse_action_date((ann.get("an_dt") or "").split(" ")[0]) if ann.get("an_dt") else None
                details = ann.get("desc")
                if _row_exists(self.conn, instrument_id, ex_date, "ANNOUNCEMENT", details):
                    continue
                self.conn.execute(
                    """
                    INSERT INTO corporate_actions
                        (instrument_id, ex_date, action_type, details, record_date, raw_json)
                    VALUES (?, ?, 'ANNOUNCEMENT', ?, NULL, ?)
                    """,
                    (instrument_id, ex_date, details, json.dumps(ann)),
                )
                rows_written += 1

        self.conn.commit()
        return rows_written
