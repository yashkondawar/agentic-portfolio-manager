"""FII/DII daily provisional flows pipeline — Phase 8 macro KPI sourcing.

Source: the raw NSE JSON endpoint api/fiidiiTradeReact (see
config/sources.yaml macro.nse_fii_dii) — no dedicated method exists for
this report in the `nse` PyPI library (checked live: no fii/dii-named
method on the NSE class), so this pipeline hits the endpoint directly via
afund.data.http.bootstrap_nse_session(make_session()), the same
cookie-bootstrap pattern index_valuation.py uses for nse_all_indices.

Confirmed live response shape: a short JSON list, one row per
{"category": "DII"|"FII/FPI", "date": "DD-Mon-YYYY", "buyValue": "...",
"sellValue": "...", "netValue": "..."} — always just the latest 1-2
trading days (this is NSE's "provisional" daily report, not a historical
archive).

IMPORTANT LIMITATION (documented per plan instruction): there is no free
bulk historical FII/DII endpoint found within budget. This pipeline is
therefore forward-accumulating only — each daily run adds whatever
new day(s) NSE is currently serving to macro_series FII_NET / DII_NET,
via idempotent upsert so re-running the same day is a no-op change.
Deep history (multi-year backfill) is NOT available from this source;
knowledge/data/kpis/fii_dii_flows.yaml's rolling 3/6/12m stats will only
become meaningful after months of forward accumulation.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from afund.data.base import Pipeline
from afund.data.http import bootstrap_nse_session, get, make_session
from afund.sources import get_source

NSE_HOST_KEY = "nseindia.com"


def _parse_nse_date(date_str: str) -> str:
    """'03-Jul-2026' -> '2026-07-03'."""
    return dt.datetime.strptime(date_str, "%d-%b-%Y").date().isoformat()


def parse_fii_dii_rows(rows: list[dict]) -> list[tuple[str, str, float]]:
    """Normalize the raw fiidiiTradeReact JSON rows into
    [(series_code, date, net_value)], series_code in {"FII_NET", "DII_NET"}.
    Skips rows with an unrecognized category or unparseable fields rather
    than fabricating."""
    parsed: list[tuple[str, str, float]] = []
    for row in rows:
        category = (row.get("category") or "").strip().upper()
        if category == "DII":
            series_code = "DII_NET"
        elif category in ("FII/FPI", "FII", "FPI"):
            series_code = "FII_NET"
        else:
            continue

        date_raw = row.get("date")
        net_raw = row.get("netValue")
        if date_raw is None or net_raw is None:
            continue
        try:
            date = _parse_nse_date(date_raw)
            value = float(str(net_raw).replace(",", ""))
        except (ValueError, TypeError):
            continue
        parsed.append((series_code, date, value))
    return parsed


class FiiDiiPipeline(Pipeline):
    """Fetch the latest FII/DII provisional flows + upsert."""

    job_name = "fii_dii"

    def fetch(self) -> list[dict]:
        source = get_source("macro", "nse_fii_dii")
        session = bootstrap_nse_session(make_session())
        resp = get(
            session,
            source["url"],
            host_key=NSE_HOST_KEY,
            min_interval=1.0,
            headers={"Referer": "https://www.nseindia.com/reports/fii-dii"},
            timeout=20.0,
        )
        resp.raise_for_status()
        return resp.json()

    def parse(self, raw: list[dict]) -> list[tuple[str, str, float]]:
        return parse_fii_dii_rows(raw)

    def upsert(self, parsed: list[tuple[str, str, float]]) -> int:
        written = 0
        for series_code, date, value in parsed:
            cur = self.conn.execute(
                """
                INSERT INTO macro_series (series_code, source, date, value, unit, freq)
                VALUES (?, 'NSE', ?, ?, 'INR_cr', 'D')
                ON CONFLICT(series_code, date) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source
                """,
                (series_code, date, value),
            )
            written += cur.rowcount
        self.conn.commit()
        return written


if __name__ == "__main__":
    result = FiiDiiPipeline().run()
    print(result)
