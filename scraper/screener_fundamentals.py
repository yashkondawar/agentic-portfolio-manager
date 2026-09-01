"""Import screener.in quarterly results into the shared fundamentals store.

NSE's as-filed archive is the better source — it is point-in-time and reaches
back to 2011 — but it stops carrying regular filings after ~Mar 2025, on every
endpoint (the dated archive, the per-symbol feed and the event calendar all
agree). Screener covers the recent tail including the current quarter.

Rather than teaching the backtest to read two stores and stitch them, this
module normalises screener's scraped tables into the same
:class:`QuarterlyResult` records the NSE parser emits and writes them to the
same table. The store's :data:`~scraper.fundamentals_store.SOURCE_RANK` keeps
as-filed rows winning wherever the two overlap, so importing screener can only
ever *extend* history forward, never rewrite it.

Two caveats travel with these rows, both flagged by ``source='screener'``:

* The figures are **restated**, not as-filed. A company that later revised a
  quarter shows the revised number on the day it originally reported.
* Screener publishes no declaration date. We attach NSE's board-meeting date
  from :mod:`scraper.nse_events` where available, which covers the recent
  quarters that matter here; rows without one fall back to the engine's
  estimated reporting lag.
"""
from __future__ import annotations

import calendar
import logging
import pickle
import re
import sqlite3
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence

from core.storage import get_cache
from scraper.nse_fundamentals import QuarterlyResult

logger = logging.getLogger("scraper.screener_fundamentals")

SOURCE = "screener"

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

#: Screener's row labels -> QuarterlyResult fields. Screener serves two
#: schedules: the ordinary one and a bank one ("Revenue"/"Financing Profit"),
#: which the downstream analysis keys on to skip the debt gate.
_LABEL_MAP = {
    "sales": "sales",
    "revenue": "sales",
    "expenses": "expenses",
    "operating profit": "operating_profit",
    "financing profit": "bank_operating_profit",
    "other income": "other_income",
    "interest": "finance_costs",
    "depreciation": "depreciation",
    "profit before tax": "profit_before_tax",
    "net profit": "net_profit",
    "eps in rs": "eps",
    "eps": "eps",
}


def _clean_label(raw: str) -> str:
    """Strip screener's decorations: trailing '+', footnote marks, whitespace."""
    return re.sub(r"[^a-z ]", "", str(raw or "").lower()).strip()


def _parse_quarter(label: str) -> Optional[date]:
    """'Mar 2025' -> date(2025, 3, 31). Screener columns are month-ends."""
    parts = str(label or "").strip().split()
    if len(parts) != 2:
        return None
    month = _MONTHS.get(parts[0][:3].lower())
    if month is None:
        return None
    try:
        year = int(parts[1])
    except ValueError:
        return None
    return date(year, month, calendar.monthrange(year, month)[1])


def _parse_number(raw) -> Optional[float]:
    """Screener numbers are strings: '60,583', '-96', '25%', ''."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", "").replace("%", "").replace("\u20b9", "")
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def rows_for_symbol(
    symbol: str,
    payload: dict,
    *,
    declaration_dates: Optional[Dict[date, date]] = None,
    since: Optional[date] = None,
) -> List[QuarterlyResult]:
    """Convert one symbol's screener payload into store records."""
    table = payload.get("quarterly_results") or []
    if not isinstance(table, list) or not table:
        return []

    # Screener gives row-per-metric with quarter columns; pivot to quarter-major.
    by_quarter: Dict[date, Dict[str, float]] = {}
    for row in table:
        if not isinstance(row, dict):
            continue
        field = _LABEL_MAP.get(_clean_label(row.get("", "")))
        if field is None:
            continue
        for column, value in row.items():
            if not column:
                continue
            period_end = _parse_quarter(column)
            if period_end is None or (since and period_end < since):
                continue
            number = _parse_number(value)
            if number is None:
                continue
            # First label wins, mirroring the screener parser's own precedence
            # so a "Profit before tax" row can never claim the net-profit slot.
            by_quarter.setdefault(period_end, {}).setdefault(field, number)

    out: List[QuarterlyResult] = []
    for period_end, metrics in sorted(by_quarter.items()):
        declared = (declaration_dates or {}).get(period_end)
        out.append(
            QuarterlyResult(
                symbol=symbol,
                company=str(payload.get("company_name") or symbol),
                period_end=period_end,
                period_start=_quarter_start(period_end),
                # Screener serves the consolidated statement when a company
                # files one, which is the same preference the NSE path applies.
                consolidated=True,
                broadcast_at=(
                    datetime(declared.year, declared.month, declared.day)
                    if declared
                    else None
                ),
                source=SOURCE,
                url=str(payload.get("source") or ""),
                **{k: metrics.get(k) for k in _VALUE_FIELDS},
            )
        )
    return out


_VALUE_FIELDS = (
    "sales",
    "expenses",
    "operating_profit",
    "bank_operating_profit",
    "other_income",
    "finance_costs",
    "depreciation",
    "profit_before_tax",
    "net_profit",
    "eps",
)


def _quarter_start(period_end: date) -> date:
    month = period_end.month - 2
    year = period_end.year
    if month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def load_screener_cache(tag: str = "500sym") -> Dict[str, dict]:
    """Read the cached screener snapshot the backtest already maintains."""
    entry = get_cache("qtr_backtest_fundamentals", tag)
    if entry is None:
        return {}
    return pickle.loads(entry.payload)


def import_screener(
    connection: sqlite3.Connection,
    raw: Optional[Dict[str, dict]] = None,
    *,
    since: Optional[date] = None,
    declaration_dates: Optional[Dict[str, Dict[date, date]]] = None,
    symbols: Optional[Sequence[str]] = None,
) -> int:
    """Normalise a screener snapshot into the store. Returns rows offered.

    Existing as-filed rows are protected by the store's source ranking, so this
    is safe to re-run and safe to run in any order relative to the NSE backfill.
    """
    from scraper import fundamentals_store

    raw = raw if raw is not None else load_screener_cache()
    if not raw:
        logger.warning("No screener snapshot available to import.")
        return 0

    wanted = {s.strip().upper() for s in symbols} if symbols else None
    records: List[QuarterlyResult] = []
    for symbol, payload in raw.items():
        sym = str(symbol).strip().upper()
        if wanted and sym not in wanted:
            continue
        if not isinstance(payload, dict):
            continue
        records.extend(
            rows_for_symbol(
                sym,
                payload,
                declaration_dates=(declaration_dates or {}).get(sym),
                since=since,
            )
        )

    written = fundamentals_store.store_results(connection, records)
    dated = sum(1 for r in records if r.broadcast_at is not None)
    logger.info(
        "Screener import: %d rows for %d symbols (%d with a real declaration "
        "date); as-filed rows were left untouched.",
        written,
        len({r.symbol for r in records}),
        dated,
    )
    return written


def collect_declaration_dates(
    start: date, end: date
) -> Dict[str, Dict[date, date]]:
    """Real board-meeting dates for the window, for the screener-only tail.

    NSE's event calendar is one request per month for the whole market and
    still serves the current quarter, unlike the financial-results archive.
    """
    from scraper import nse_events

    try:
        return nse_events.results_event_calendar(start, end)
    except Exception as exc:  # noqa: BLE001 - dates are an upgrade, not a requirement
        logger.warning("Event calendar unavailable (%s); falling back to lag.", exc)
        return {}





def main(argv=None) -> int:
    """Refresh the recent tail of the store from the screener snapshot.

    Safe and cheap to re-run: as-filed rows are protected by the store's source
    ranking, so this only ever touches the quarters NSE does not serve.
    """
    import argparse

    from scraper import fundamentals_store

    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument("--tag", default="500sym",
                   help="Screener cache tag to import (default: 500sym)")
    p.add_argument("--since", default=None,
                   help="Ignore quarters before YYYY-MM-DD")
    p.add_argument("--no-dates", action="store_true",
                   help="Skip the NSE board-meeting lookup for declaration dates")
    p.add_argument("--status", action="store_true",
                   help="Report store coverage and exit")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )

    connection = fundamentals_store.open_store()
    try:
        if args.status:
            _print_status(fundamentals_store.coverage(connection))
            return 0

        raw = load_screener_cache(args.tag)
        if not raw:
            logger.error("No screener cache under tag %r.", args.tag)
            return 1

        since = date.fromisoformat(args.since) if args.since else None
        dates: Dict[str, Dict[date, date]] = {}
        if not args.no_dates:
            # One request per month for the whole market, so a wide window is
            # cheap and covers every quarter the snapshot might carry.
            dates = collect_declaration_dates(
                since or date.today().replace(year=date.today().year - 4),
                date.today(),
            )

        import_screener(connection, raw, since=since, declaration_dates=dates)
        _print_status(fundamentals_store.coverage(connection))
        return 0
    finally:
        connection.close()


def _print_status(cov: Dict[str, object]) -> None:
    print(
        f"Store holds {cov.get('rows', 0):,} quarters for "
        f"{cov.get('symbols', 0):,} symbols."
    )
    print(f"  range   : {cov.get('first_quarter')} -> {cov.get('last_quarter')}")
    print(f"  dated   : {cov.get('dated', 0):,} with a real declaration date")
    for src, n in (cov.get("by_source") or {}).items():
        print(f"  {src:8}: {n:,}")


if __name__ == "__main__":
    raise SystemExit(main())
