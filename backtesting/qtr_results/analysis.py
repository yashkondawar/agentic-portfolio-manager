"""
analysis.py
===========

Point-in-time verification of a single quarterly result — the backtest's
leak-free re-implementation of ``qtr_results.analysis.analyze_symbol``.

The live strategy scrapes screener.in and analyses the *latest* quarter. Here we
have the whole scraped quarterly table (many quarters of as-reported history) and
analyse a *chosen* quarter index as if it had just been declared: only quarter
columns dated ``<= q_idx`` are consulted, so no future quarter ever leaks in.
Every growth/strength/target number is computed with the exact same helpers the
live code uses (``_index_quarterly``, ``_strength_score``, ``build_target_plan``),
guaranteeing the backtest reasons with the same playbook.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

# Reuse the live analysis internals verbatim so the maths is identical.
from qtr_results.analysis import (
    AnalysisResult,
    _build_rationale,
    _index_quarterly,
    _series,
    _strength_score,
    _val,
)
from qtr_results.util import pct_change

logger = logging.getLogger("backtest.qtr.analysis")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class ResultEvent:
    """One quarterly result declaration to (potentially) trade."""
    symbol: str
    company: str
    q_idx: int              # index into the quarter-column list
    quarter_label: str      # e.g. "Jun 2025"
    quarter_end: date
    decl_date: date         # quarter_end + reporting lag (assumed filing date)


def _quarter_end(label: str) -> Optional[date]:
    """Parse a screener quarter column label like 'Jun 2025' → month-end date."""
    parts = (label or "").strip().split()
    if len(parts) != 2:
        return None
    mon = _MONTHS.get(parts[0][:3].lower())
    try:
        year = int(parts[1])
    except ValueError:
        return None
    if mon is None:
        return None
    # Last day of the quarter-end month.
    if mon == 12:
        return date(year, 12, 31)
    nxt = date(year, mon + 1, 1)
    from datetime import timedelta

    return nxt - timedelta(days=1)


def parse_quarters(raw: dict):
    """Return ``(quarters, metrics)`` from a scraped screener fundamentals dict."""
    return _index_quarterly(raw.get("quarterly_results", []) or [])


def enumerate_events(
    symbol: str,
    raw: dict,
    quarters: List[str],
    *,
    reporting_lag_days: int,
) -> List[ResultEvent]:
    """All declarable result events for a symbol (one per parseable quarter col).

    A quarter needs at least 4 prior quarters (index >= 4) so year-on-year and a
    trailing-EPS baseline can be computed — mirroring the live selection gate.
    """
    from datetime import timedelta

    company = raw.get("company_name", symbol)
    events: List[ResultEvent] = []
    for i, label in enumerate(quarters):
        if i < 4:
            continue  # need YoY base + prior TTM window
        qend = _quarter_end(label)
        if qend is None:
            continue
        events.append(
            ResultEvent(
                symbol=symbol,
                company=company,
                q_idx=i,
                quarter_label=label,
                quarter_end=qend,
                decl_date=qend + timedelta(days=reporting_lag_days),
            )
        )
    return events


def _ttm_eps_window(
    eps: Dict[str, Optional[float]], quarters: List[str], end_idx: int
) -> Optional[float]:
    """Sum EPS over the 4 quarters ending at ``end_idx`` (inclusive)."""
    if end_idx < 3:
        return None
    vals = [eps.get(quarters[j]) for j in range(end_idx - 3, end_idx + 1)]
    if any(v is None for v in vals):
        return None
    return sum(v for v in vals if v is not None)


def analyze_event(
    raw: dict,
    quarters: List[str],
    metrics: Dict[str, Dict[str, Optional[float]]],
    q_idx: int,
    entry_price: float,
    *,
    cfg,
) -> AnalysisResult:
    """Compute the as-of AnalysisResult for the quarter at ``q_idx``.

    Mirrors ``qtr_results.analysis.analyze_symbol`` but (a) pins the "latest"
    quarter to ``q_idx`` (point-in-time) and (b) derives the P/E from the
    *historical* entry price and the pre-result trailing EPS — never screener's
    live "Current Price"/"Stock P/E" — so the PE-rerating target is leak-free.
    """
    latest = quarters[q_idx]
    qoq_base = quarters[q_idx - 1]
    yoy_base = quarters[q_idx - 4]

    net_profit = _series(metrics, "net_profit")
    sales = _series(metrics, "sales")
    eps = _series(metrics, "eps")
    opm = _series(metrics, "opm")

    yoy_profit = pct_change(_val(net_profit, latest), _val(net_profit, yoy_base))
    qoq_profit = pct_change(_val(net_profit, latest), _val(net_profit, qoq_base))
    yoy_sales = pct_change(_val(sales, latest), _val(sales, yoy_base))
    qoq_sales = pct_change(_val(sales, latest), _val(sales, qoq_base))
    yoy_eps = pct_change(_val(eps, latest), _val(eps, yoy_base))

    margin_latest = _val(opm, latest)
    margin_yoy = _val(opm, yoy_base)
    margin_delta = (
        margin_latest - margin_yoy
        if margin_latest is not None and margin_yoy is not None
        else None
    )

    score = _strength_score(yoy_profit, qoq_profit, yoy_eps, yoy_sales, margin_delta)

    is_strong = (
        yoy_profit is not None
        and yoy_profit >= cfg.min_yoy_profit_growth
        and (yoy_eps is None or yoy_eps >= cfg.min_yoy_eps_growth)
        and (qoq_profit is None or qoq_profit >= cfg.min_qoq_profit_growth)
    )

    # PE re-rating inputs (point-in-time): hold the pre-result market multiple
    # constant against the freshly-grown TTM EPS.
    ttm_eps_new = _ttm_eps_window(eps, quarters, q_idx)
    ttm_eps_old = _ttm_eps_window(eps, quarters, q_idx - 1)
    pre_pe = (
        entry_price / ttm_eps_old
        if entry_price and ttm_eps_old and ttm_eps_old > 0
        else None
    )

    result = AnalysisResult(
        symbol=raw.get("symbol", ""),
        company_name=raw.get("company_name", ""),
        latest_quarter=latest,
        current_price=entry_price,
        current_pe=pre_pe,
        ttm_eps=ttm_eps_new,
        yoy_profit_growth=yoy_profit,
        qoq_profit_growth=qoq_profit,
        yoy_sales_growth=yoy_sales,
        qoq_sales_growth=qoq_sales,
        yoy_eps_growth=yoy_eps,
        margin_delta_pp=margin_delta,
        strength_score=score,
        is_strong=bool(is_strong),
        raw_top_ratios={},
    )
    result.rationale = _build_rationale(result)
    return result
