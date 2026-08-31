"""screener.in financials scraper.

Approach adapted from the community screener.py scraper referenced in the
Phase 1 spec (yashkondawar/agentic-portfolio-manager), reimplemented in our
own style rather than vendored: slug resolution via the search API, a
2.0s minimum interval + exponential backoff on 429/503, and parsing of the
top-ratios / quarterly-results / P&L / balance-sheet / cash-flow /
shareholding sections from the company page.

Scope guard: `run_for_symbols()` takes an explicit symbol list; the smoke
CLI and run_daily orchestrator wire it to config/settings.yaml's
universe.watchlist (a single symbol by default).

Phase 12 — `scrape_universe()` / `--universe` CLI (this module's batch
sibling to `run_for_symbols()`): a deliberate, human-invoked, resumable
crawl of the FULL active-STOCK universe (~750 instruments), run explicitly
by the user per the Phase 12 task spec rather than on any automated
schedule. Distinct politeness posture from the watchlist path above (2.5s
minimum interval + 0-1s random jitter, vs. the watchlist path's flat 2.0s)
and disk-cached raw HTML (data/raw/screener/<SYMBOL>.html) with a 30-day
freshness check so a rerun after a partial/interrupted crawl only refetches
what's actually stale — see scrape_universe()'s docstring for the full
resumability contract.


Storage:
  - Quarterly results -> financials_quarterly (revenue/operating_profit/
    net_profit/eps mapped from the "Sales"/"Operating Profit"/"Net Profit"/
    "EPS in Rs" rows; the full parsed table for every statement section
    goes into raw_json so nothing is lost even where our mapping is partial).
  - Top ratios -> derived_ratios (as_of_date=today, metric_name normalized
    to snake_case, sector_kpi=0).
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import sqlite3
import time
from pathlib import Path

from bs4 import BeautifulSoup

from afund.config import REPO_ROOT, load_settings
from afund.data.base import Pipeline, log_job_run
from afund.data.http import make_session
from afund.sources import get_source

RATE_LIMIT_SECONDS = 2.0
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 3.0

_last_request_at: float = 0.0


def _rate_limited_get(session, url: str, **kwargs):
    """GET with a hard 2s minimum interval between screener.in requests and
    exponential backoff retries on 429/503."""
    global _last_request_at
    for attempt in range(MAX_RETRIES + 1):
        elapsed = time.monotonic() - _last_request_at
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)
        resp = session.get(url, timeout=20, **kwargs)
        _last_request_at = time.monotonic()

        if resp.status_code in (429, 503) and attempt < MAX_RETRIES:
            time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
            continue
        return resp
    return resp


# ---------------------------------------------------------------------------
# Phase 12 — batch universe scrape
# ---------------------------------------------------------------------------

UNIVERSE_RATE_LIMIT_SECONDS = 2.5
UNIVERSE_JITTER_MAX_SECONDS = 1.0
UNIVERSE_MAX_RETRIES = 3
UNIVERSE_BACKOFF_BASE_SECONDS = 5.0
UNIVERSE_FRESHNESS_DAYS = 30

RAW_DIR = REPO_ROOT / "data" / "raw" / "screener"

_universe_last_request_at: float = 0.0


def _universe_rate_limited_get(session, url: str, **kwargs):
    """GET with the batch-scrape politeness posture: 2.5s minimum interval
    plus 0-1s random jitter (distinct from, and more conservative than, the
    watchlist path's flat 2.0s), exponential backoff on 429/503."""
    global _universe_last_request_at
    for attempt in range(UNIVERSE_MAX_RETRIES + 1):
        elapsed = time.monotonic() - _universe_last_request_at
        min_wait = UNIVERSE_RATE_LIMIT_SECONDS + random.uniform(0, UNIVERSE_JITTER_MAX_SECONDS)
        if elapsed < min_wait:
            time.sleep(min_wait - elapsed)
        resp = session.get(url, timeout=20, **kwargs)
        _universe_last_request_at = time.monotonic()

        if resp.status_code in (429, 503) and attempt < UNIVERSE_MAX_RETRIES:
            time.sleep(UNIVERSE_BACKOFF_BASE_SECONDS * (2**attempt))
            continue
        return resp
    return resp


def _raw_html_path(symbol: str) -> Path:
    return RAW_DIR / f"{symbol}.html"


def _is_cache_fresh(path: Path, *, max_age_days: int = UNIVERSE_FRESHNESS_DAYS) -> bool:
    """True if `path` exists and its mtime is within max_age_days of now."""
    if not path.exists():
        return False
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    return age_days < max_age_days


def _derived_ratios_fresh(conn: sqlite3.Connection, instrument_id: int, *, max_age_days: int = UNIVERSE_FRESHNESS_DAYS) -> bool:
    """True if this instrument already has a derived_ratios row newer than
    max_age_days — the second half of the resumability contract (a symbol
    can be skipped if EITHER the cached HTML OR the derived data is fresh,
    since a fresh DB row with no cached HTML still means there's nothing
    useful left to do for this symbol today)."""
    row = conn.execute(
        "SELECT MAX(as_of_date) AS latest FROM derived_ratios WHERE instrument_id = ?",
        (instrument_id,),
    ).fetchone()
    if row is None or not row["latest"]:
        return False
    try:
        latest_date = dt.date.fromisoformat(row["latest"][:10])
    except ValueError:
        return False
    age_days = (dt.date.today() - latest_date).days
    return age_days < max_age_days


def _active_stock_symbols(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id AS instrument_id, symbol FROM instruments
         WHERE active = 1 AND instrument_type = 'STOCK'
         ORDER BY symbol ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def scrape_universe(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    session=None,
    freshness_days: int = UNIVERSE_FRESHNESS_DAYS,
) -> dict:
    """Batch screener.in scrape across ALL active STOCK instruments.

    Resumable / idempotent by design:
      - Every fetched page is cached to data/raw/screener/<SYMBOL>.html.
      - A symbol is SKIPPED (no network request at all) if its cached HTML
        is younger than `freshness_days` OR its derived_ratios already has
        an as_of_date within `freshness_days` — so a rerun after a partial
        crawl (interrupted, killed, or deliberately re-invoked) only
        refetches symbols that are actually stale or were never reached.
      - Every parse/upsert failure for one symbol is logged as its own
        `job_runs` row (job_name='financials_universe', status='FAILED',
        error naming the symbol) WITHOUT raising — one bad symbol never
        aborts the batch.

    Politeness: UNIVERSE_RATE_LIMIT_SECONDS (2.5s) minimum interval + up to
    UNIVERSE_JITTER_MAX_SECONDS (1.0s) random jitter between requests,
    exponential backoff on 429/503, one shared `requests.Session` reused
    across the whole run.

    Returns a summary dict:
        {
          "attempted": int,       # symbols that actually triggered a network fetch
          "skipped_fresh": int,   # symbols skipped via the freshness check
          "parsed_ok": int,       # symbols successfully parsed AND upserted
          "failed": int,          # symbols that errored (see failures)
          "failures": [{"symbol": str, "reason": str}, ...],
          "total_universe": int,
        }
    """
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    session = session or make_session()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    stocks = _active_stock_symbols(conn)
    total_universe = len(stocks)
    if limit is not None:
        stocks = stocks[:limit]

    today = dt.date.today().isoformat()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    attempted = 0
    parsed_ok = 0
    skipped_fresh = 0
    failures: list[dict] = []

    for stock in stocks:
        instrument_id = stock["instrument_id"]
        symbol = stock["symbol"]
        html_path = _raw_html_path(symbol)

        if _is_cache_fresh(html_path, max_age_days=freshness_days) or _derived_ratios_fresh(
            conn, instrument_id, max_age_days=freshness_days
        ):
            skipped_fresh += 1
            continue

        attempted += 1
        try:
            slug = resolve_screener_slug(symbol, session=session)
            if slug is None:
                raise ValueError("no screener.in match found")

            source = get_source("company_research", "screener_company")
            consolidated_url = source["url"].format(slug=slug)
            resp = _universe_rate_limited_get(session, consolidated_url)
            if resp.status_code == 200:
                html, statement_type = resp.text, "consolidated"
            else:
                standalone_url = f"https://www.screener.in/company/{slug}/"
                resp = _universe_rate_limited_get(session, standalone_url)
                resp.raise_for_status()
                html, statement_type = resp.text, "standalone"

            html_path.write_text(html, encoding="utf-8")

            top_ratios = parse_top_ratios(html)
            quarters = parse_statement_section(html, "quarters")
            quarterly_financials = quarterly_rows_to_financials(quarters) if quarters else []

            if not top_ratios and not quarterly_financials:
                raise ValueError("page fetched but no parseable ratios/financials found")

            for record in quarterly_financials:
                conn.execute(
                    """
                    INSERT INTO financials_quarterly
                        (instrument_id, period_end, statement_type, revenue, ebitda,
                         operating_profit, net_profit, eps, raw_json, source, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'screener.in', ?)
                    ON CONFLICT(instrument_id, period_end, statement_type) DO UPDATE SET
                        revenue = excluded.revenue,
                        ebitda = excluded.ebitda,
                        operating_profit = excluded.operating_profit,
                        net_profit = excluded.net_profit,
                        eps = excluded.eps,
                        raw_json = excluded.raw_json,
                        ingested_at = excluded.ingested_at
                    """,
                    (
                        instrument_id, record["period_end"], statement_type, record["revenue"],
                        record["ebitda"], record["operating_profit"], record["net_profit"],
                        record["eps"], record["raw_json"], now_iso,
                    ),
                )

            for metric_name, value in top_ratios.items():
                conn.execute(
                    """
                    INSERT INTO derived_ratios
                        (instrument_id, as_of_date, cadence, metric_name, metric_value, sector_kpi)
                    VALUES (?, ?, 'daily', ?, ?, 0)
                    ON CONFLICT(instrument_id, as_of_date, metric_name) DO UPDATE SET
                        metric_value = excluded.metric_value
                    """,
                    (instrument_id, today, metric_name, value),
                )
            conn.commit()
            parsed_ok += 1

        except Exception as exc:  # noqa: BLE001 - one bad symbol must not abort the batch
            reason = f"{type(exc).__name__}: {exc}"
            failures.append({"symbol": symbol, "reason": reason})
            log_job_run(
                conn, "financials_universe", "FAILED", 0,
                dt.datetime.now(dt.timezone.utc).isoformat(),
                dt.datetime.now(dt.timezone.utc).isoformat(),
                f"{symbol}: {reason}",
            )

    finished_at = dt.datetime.now(dt.timezone.utc).isoformat()
    summary = {
        "attempted": attempted,
        "skipped_fresh": skipped_fresh,
        "parsed_ok": parsed_ok,
        "failed": len(failures),
        "failures": failures,
        "total_universe": total_universe,
    }
    log_job_run(
        conn, "financials_universe",
        "SUCCESS" if not failures else "PARTIAL",
        parsed_ok, started_at, finished_at,
        None if not failures else f"{len(failures)} symbol(s) failed; see failures list",
    )
    return summary


# Staged universe coverage: ~100 stale names per invocation instead of one
# bulk run — the politeness posture chosen for filling the company_fit table
# (user decision 2026-07-08; keeps single-session footprint on screener.in
# modest while the 30-day freshness skip makes repeated runs converge on
# full coverage in ~7-8 invocations).
STAGE_BATCH_SIZE = 100


def scrape_universe_staged(conn: sqlite3.Connection) -> dict:
    """One polite stage of universe coverage (router py-step callable)."""
    return scrape_universe(conn, limit=STAGE_BATCH_SIZE)


def resolve_screener_slug(symbol: str, session=None) -> str | None:
    """Resolve a stock symbol to its screener.in company slug via the search API."""
    source = get_source("company_research", "screener_search")
    url = source["url"].format(symbol=symbol)
    session = session or make_session()
    resp = _rate_limited_get(session, url, headers={"Referer": "https://www.screener.in/"})
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    # results[i]['url'] looks like "/company/INFY/consolidated/"
    match = results[0]["url"].strip("/").split("/")
    return match[1] if len(match) >= 2 else None


def fetch_company_page(slug: str, session=None) -> tuple[str, str]:
    """Fetch the company page HTML, preferring consolidated, falling back to
    standalone. Returns (html, statement_type)."""
    session = session or make_session()
    source = get_source("company_research", "screener_company")
    consolidated_url = source["url"].format(slug=slug)
    resp = _rate_limited_get(session, consolidated_url)
    if resp.status_code == 200:
        return resp.text, "consolidated"

    standalone_url = f"https://www.screener.in/company/{slug}/"
    resp = _rate_limited_get(session, standalone_url)
    resp.raise_for_status()
    return resp.text, "standalone"


def _snake_case(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def parse_top_ratios(html: str) -> dict[str, float]:
    """Parse the ul#top-ratios list into {metric_name_snake_case: value}."""
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("ul", id="top-ratios")
    if container is None:
        return {}

    ratios: dict[str, float] = {}
    for li in container.find_all("li", recursive=False):
        name_el = li.find("span", class_="name")
        if name_el is None:
            continue
        name = name_el.get_text(strip=True)
        number_els = li.find_all("span", class_="number")
        if not number_els:
            continue
        # "High / Low" has two numbers; store as high/low, everything else
        # as a single value.
        if name.lower() == "high / low" and len(number_els) >= 2:
            try:
                ratios[_snake_case("52w_high")] = float(number_els[0].get_text(strip=True).replace(",", ""))
                ratios[_snake_case("52w_low")] = float(number_els[1].get_text(strip=True).replace(",", ""))
            except ValueError:
                pass
            continue
        try:
            value = float(number_els[0].get_text(strip=True).replace(",", ""))
        except ValueError:
            continue
        ratios[_snake_case(name)] = value
    return ratios


def _parse_data_table(table) -> dict:
    """Parse a screener.in table.data-table into
    {"periods": [...], "rows": {row_label: [values...]}}."""
    thead = table.find("thead")
    periods: list[str] = []
    if thead:
        header_row = thead.find("tr")
        if header_row:
            for th in header_row.find_all("th")[1:]:
                date_key = th.get("data-date-key")
                periods.append(date_key or th.get_text(strip=True))

    rows: dict[str, list[str]] = {}
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True).replace("+", "").strip()
            label = re.sub(r"\s+", " ", label)
            values = [c.get_text(strip=True) for c in cells[1:]]
            if label:
                rows[label] = values
    return {"periods": periods, "rows": rows}


def parse_statement_section(html: str, section_id: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    section = soup.find("section", id=section_id)
    if section is None:
        return None
    table = section.find("table", class_="data-table")
    if table is None:
        return None
    return _parse_data_table(table)


def _to_number(raw: str) -> float | None:
    raw = raw.replace(",", "").replace("%", "").strip()
    if raw in ("", "-"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


ROW_LABEL_MAP = {
    "revenue": ["Sales", "Revenue"],
    "operating_profit": ["Operating Profit"],
    "net_profit": ["Net Profit", "Net Profit +"],
    "eps": ["EPS in Rs"],
}


def quarterly_rows_to_financials(quarters_table: dict) -> list[dict]:
    """Turn the parsed 'quarters' table into per-period financials_quarterly
    row dicts with revenue/operating_profit/net_profit/eps mapped, and the
    full table stashed as raw_json on every row."""
    periods = quarters_table.get("periods", [])
    rows = quarters_table.get("rows", {})
    raw_json = json.dumps(quarters_table)

    results = []
    for i, period in enumerate(periods):
        record = {"period_end": period, "raw_json": raw_json}
        for field, candidate_labels in ROW_LABEL_MAP.items():
            value = None
            for label in candidate_labels:
                if label in rows and i < len(rows[label]):
                    value = _to_number(rows[label][i])
                    if value is not None:
                        break
            record[field] = value
        record["ebitda"] = None  # not directly exposed as a row label; left for a later derivation pass
        results.append(record)
    return results


class FinancialsPipeline(Pipeline):
    """Watchlist-scoped screener.in financials fetch for an explicit symbol list."""

    job_name = "financials"

    def __init__(self, conn: sqlite3.Connection | None = None, symbols: list[str] | None = None):
        super().__init__(conn)
        settings = load_settings()
        self.symbols = symbols if symbols is not None else settings.get("universe", {}).get("watchlist", [])
        self.session = make_session()
        self.symbol_errors: dict[str, str] = {}

    def fetch(self) -> dict[str, tuple[str, str]]:
        pages: dict[str, tuple[str, str]] = {}
        for symbol in self.symbols:
            try:
                slug = resolve_screener_slug(symbol, session=self.session)
                if slug is None:
                    self.symbol_errors[symbol] = "no screener.in match found"
                    continue
                html, statement_type = fetch_company_page(slug, session=self.session)
                pages[symbol] = (html, statement_type)
            except Exception as exc:  # noqa: BLE001 - one bad symbol must not kill the batch
                self.symbol_errors[symbol] = f"{type(exc).__name__}: {exc}"
        return pages

    def parse(self, raw: dict[str, tuple[str, str]]) -> dict[str, dict]:
        parsed: dict[str, dict] = {}
        for symbol, (html, statement_type) in raw.items():
            try:
                top_ratios = parse_top_ratios(html)
                quarters = parse_statement_section(html, "quarters")
                parsed[symbol] = {
                    "statement_type": statement_type,
                    "top_ratios": top_ratios,
                    "quarterly_financials": quarterly_rows_to_financials(quarters) if quarters else [],
                }
            except Exception as exc:  # noqa: BLE001
                self.symbol_errors[symbol] = f"parse {type(exc).__name__}: {exc}"
        return parsed

    def upsert(self, parsed: dict[str, dict]) -> int:
        today = dt.date.today().isoformat()
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        rows_written = 0

        for symbol, data in parsed.items():
            instrument = self.conn.execute(
                "SELECT id FROM instruments WHERE symbol = ? AND instrument_type = 'STOCK'",
                (symbol,),
            ).fetchone()
            if instrument is None:
                self.symbol_errors[symbol] = "symbol not found in instruments (run universe pipeline first)"
                continue
            instrument_id = instrument["id"]

            for record in data["quarterly_financials"]:
                before = self.conn.total_changes
                self.conn.execute(
                    """
                    INSERT INTO financials_quarterly
                        (instrument_id, period_end, statement_type, revenue, ebitda,
                         operating_profit, net_profit, eps, raw_json, source, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'screener.in', ?)
                    ON CONFLICT(instrument_id, period_end, statement_type) DO UPDATE SET
                        revenue = excluded.revenue,
                        ebitda = excluded.ebitda,
                        operating_profit = excluded.operating_profit,
                        net_profit = excluded.net_profit,
                        eps = excluded.eps,
                        raw_json = excluded.raw_json,
                        ingested_at = excluded.ingested_at
                    """,
                    (
                        instrument_id,
                        record["period_end"],
                        data["statement_type"],
                        record["revenue"],
                        record["ebitda"],
                        record["operating_profit"],
                        record["net_profit"],
                        record["eps"],
                        record["raw_json"],
                        now_iso,
                    ),
                )
                rows_written += max(self.conn.total_changes - before, 1)

            for metric_name, value in data["top_ratios"].items():
                before = self.conn.total_changes
                self.conn.execute(
                    """
                    INSERT INTO derived_ratios
                        (instrument_id, as_of_date, cadence, metric_name, metric_value, sector_kpi)
                    VALUES (?, ?, 'daily', ?, ?, 0)
                    ON CONFLICT(instrument_id, as_of_date, metric_name) DO UPDATE SET
                        metric_value = excluded.metric_value
                    """,
                    (instrument_id, today, metric_name, value),
                )
                rows_written += max(self.conn.total_changes - before, 1)

        self.conn.commit()
        return rows_written


def _print_universe_summary(summary: dict) -> None:
    print(
        f"screener.in universe scrape — total_universe={summary['total_universe']} "
        f"attempted={summary['attempted']} skipped_fresh={summary['skipped_fresh']} "
        f"parsed_ok={summary['parsed_ok']} failed={summary['failed']}"
    )
    if summary["failures"]:
        print("\nFailures:")
        for f in summary["failures"]:
            print(f"  {f['symbol']:<15} {f['reason']}")


def main() -> None:
    import argparse

    from afund.db.connection import get_conn

    parser = argparse.ArgumentParser(description="screener.in financials pipeline")
    parser.add_argument(
        "--universe", action="store_true",
        help="Batch scrape ALL active STOCK instruments (Phase 12), resumable/cached.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="With --universe, cap the run to the first N symbols (alphabetical) — for smoke-testing.",
    )
    args = parser.parse_args()

    conn = get_conn()
    try:
        if args.universe:
            summary = scrape_universe(conn, limit=args.limit)
            _print_universe_summary(summary)
        else:
            result = FinancialsPipeline(conn=conn).run()
            print(f"financials (watchlist) — status={result.status} rows_written={result.rows_written}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
