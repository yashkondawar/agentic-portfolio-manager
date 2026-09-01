"""Serve the qtr_results backtest from as-filed NSE filings instead of screener.

The engine reads screener-shaped dicts (``quarterly_results`` and friends as
lists of row dicts). This module renders the NSE store into exactly that shape,
so ``analysis.py`` and the portfolio engine work unchanged — but over a ~14-year
window of *as-filed* numbers rather than screener's ~3-year, retro-restated one.

Two corrections are applied on the way through:

**EPS is rebased onto a constant share count.** As-filed EPS is divided by
whatever the share count was on the filing date, so a 1:10 split makes EPS
"fall" 90% with no change in earnings, and it no longer lines up with the
split-adjusted prices the backtest uses. We recover the implied share count from
each filing (``net_profit / eps`` — both from the same document, so mutually
consistent), pick one reference count per symbol, and restate the whole EPS
series on it. Growth then reflects earnings rather than corporate actions, and
``price / EPS`` is on a single basis. This is also what makes "EPS growth" and
"net profit growth" the same number, which is the intent.

**Declaration dates are real.** Every row carries NSE's broadcast timestamp, so
the engine can drop its hashed reporting-lag estimate and use the minute the
result actually hit the tape.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from scraper import fundamentals_store
from scraper.nse_fundamentals import QuarterlyResult, select_best

logger = logging.getLogger("backtest.qtr.nse_source")

# Annual sections the NSE quarterly feed cannot supply; borrowed from screener.
_ANNUAL_SECTIONS = ("balance_sheet", "financial_ratios", "profit_loss", "cash_flow")

_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

#: Minimum |EPS| for a filing to be trusted as a share-count observation. Tiny
#: EPS values make ``net_profit / eps`` explode.
_MIN_EPS_FOR_SHARES = 0.5


def _label(period_end: date) -> str:
    return f"{_MONTH_ABBR[period_end.month]} {period_end.year}"


def _implied_shares(row: QuarterlyResult) -> Optional[float]:
    """Share count implied by this filing's own net profit and EPS, in crores."""
    if row.net_profit is None or row.eps is None:
        return None
    if abs(row.eps) < _MIN_EPS_FOR_SHARES:
        return None
    if row.net_profit == 0:
        return None
    shares = row.net_profit / row.eps
    # A quarterly EPS against an annual-scale share count is nonsense either way;
    # reject implausible counts rather than letting them poison the median.
    if not (0.01 < shares < 100000):
        return None
    return shares


def reference_share_count(rows: Sequence[QuarterlyResult]) -> Optional[float]:
    """One share count per symbol, used to restate the whole EPS series.

    Uses the median of the most recent observations: recent filings are the most
    likely to reflect the share base the split-adjusted price series is quoted
    on, and the median shrugs off one-off EPS oddities (exceptional items,
    near-zero denominators).
    """
    observations = [
        s for s in (_implied_shares(r) for r in rows[-12:]) if s is not None
    ]
    if len(observations) < 2:
        observations = [s for s in (_implied_shares(r) for r in rows) if s is not None]
    if not observations:
        return None
    return statistics.median(observations)


def _opm(row: QuarterlyResult) -> Optional[float]:
    top = row.sales
    op = row.bank_operating_profit if row.is_bank else row.operating_profit
    if top is None or op is None or top == 0:
        return None
    return round(100.0 * op / top, 2)


def _section(rows: List[Tuple[str, Dict[str, Optional[float]]]]) -> List[dict]:
    """Assemble screener-style section rows: ``{"": label, "Mar 2024": value}``."""
    out = []
    for label, values in rows:
        row: dict = {"": label}
        row.update({k: v for k, v in values.items()})
        out.append(row)
    return out


def build_quarterly_section(
    rows: Sequence[QuarterlyResult],
    *,
    shares: Optional[float],
) -> List[dict]:
    """Render one symbol's filings as a screener ``quarterly_results`` section."""
    banky = sum(1 for r in rows if r.is_bank) > len(rows) / 2

    sales: Dict[str, Optional[float]] = {}
    expenses: Dict[str, Optional[float]] = {}
    op: Dict[str, Optional[float]] = {}
    opm: Dict[str, Optional[float]] = {}
    depreciation: Dict[str, Optional[float]] = {}
    interest: Dict[str, Optional[float]] = {}
    other_income: Dict[str, Optional[float]] = {}
    pbt: Dict[str, Optional[float]] = {}
    net_profit: Dict[str, Optional[float]] = {}
    eps: Dict[str, Optional[float]] = {}

    for row in rows:
        if row.period_end is None:
            continue
        col = _label(row.period_end)
        sales[col] = row.sales
        expenses[col] = row.expenses
        op[col] = row.bank_operating_profit if row.is_bank else row.operating_profit
        opm[col] = _opm(row)
        depreciation[col] = row.depreciation
        interest[col] = row.finance_costs
        other_income[col] = row.other_income
        pbt[col] = row.profit_before_tax
        net_profit[col] = row.net_profit
        # Restated EPS keeps growth and P/E on one share basis (see module docs).
        if shares and row.net_profit is not None:
            eps[col] = round(row.net_profit / shares, 4)
        else:
            eps[col] = row.eps

    if banky:
        # Bank schedule: the engine detects financials by these row labels and
        # skips the debt filter, which is meaningless for a lender.
        return _section([
            ("Revenue", sales),
            ("Interest", interest),
            ("Financing Profit", op),
            ("Financing Margin %", opm),
            ("Other Income+", other_income),
            ("Profit before tax", pbt),
            ("Net Profit+", net_profit),
            ("EPS in Rs", eps),
        ])

    return _section([
        ("Sales+", sales),
        ("Expenses+", expenses),
        ("Operating Profit", op),
        ("OPM %", opm),
        ("Other Income+", other_income),
        ("Interest", interest),
        ("Depreciation", depreciation),
        ("Profit before tax", pbt),
        ("Net Profit+", net_profit),
        ("EPS in Rs", eps),
    ])


def _dedupe(rows: Iterable[QuarterlyResult]) -> List[QuarterlyResult]:
    """One filing per quarter — consolidated preferred, richest wins ties."""
    picked = select_best(rows).values()
    return sorted(
        (r for r in picked if r.period_end is not None),
        key=lambda r: r.period_end,
    )


def build(
    symbols: Optional[Sequence[str]] = None,
    *,
    screener_raw: Optional[Dict[str, dict]] = None,
    min_quarters: int = 8,
    connection=None,
) -> Tuple[Dict[str, dict], Dict[str, Dict[date, date]]]:
    """Build ``(raw_by_symbol, declaration_calendar)`` from the NSE store.

    ``screener_raw`` supplies the annual sections (balance sheet, ROCE) that
    quarterly filings don't carry. Symbols missing from it still work — the
    engine treats an absent debt/ROCE reading as "don't reject".

    Pass ``connection`` to reuse an open store; otherwise one is opened and
    closed here.
    """
    owned = connection is None
    connection = connection or fundamentals_store.open_store()
    try:
        stored = fundamentals_store.load_results(connection, symbols=symbols)
    finally:
        if owned:
            connection.close()

    grouped: Dict[str, List[QuarterlyResult]] = {}
    for row in stored:
        grouped.setdefault(row.symbol, []).append(row)

    raw: Dict[str, dict] = {}
    calendar: Dict[str, Dict[date, date]] = {}
    thin = 0
    for symbol, rows in grouped.items():
        series = _dedupe(rows)
        if len(series) < min_quarters:
            thin += 1
            continue

        shares = reference_share_count(series)
        entry: dict = {
            "symbol": symbol,
            "company_name": next((r.company for r in reversed(series) if r.company), symbol),
            "source": "nse",
            "top_ratios": [],
            "quarterly_results": build_quarterly_section(series, shares=shares),
            "shareholding": [],
        }
        borrowed = (screener_raw or {}).get(symbol) or {}
        for section in _ANNUAL_SECTIONS:
            entry[section] = borrowed.get(section, []) or []
        raw[symbol] = entry

        dates: Dict[date, date] = {}
        for row in series:
            if row.period_end is not None and row.broadcast_at is not None:
                stamp = row.broadcast_at
                dates[row.period_end] = (
                    stamp.date() if isinstance(stamp, datetime) else stamp
                )
        calendar[symbol] = dates

    logger.info(
        "NSE source: %d symbols usable (%d dropped for <%d quarters), "
        "%d real declaration dates.",
        len(raw), thin, min_quarters, sum(len(d) for d in calendar.values()),
    )
    return raw, calendar
