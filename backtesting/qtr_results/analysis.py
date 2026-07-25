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

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

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
    decl_date: date         # real NSE announcement date, else quarter_end + lag
    decl_date_real: bool = False  # True if decl_date came from the real NSE feed


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


# ── Point-in-time balance-sheet / ratio quality metrics ──────────────────────
#
# The scraper already captures balance_sheet, cash_flow and financial_ratios with
# full annual history — these are as-reported historicals that never change, so
# consulting only the annual column whose period-end is on/before the declared
# quarter keeps them point-in-time (identical guarantee to the quarterly logic).

from qtr_results.util import parse_number as _parse_number  # noqa: E402


def _index_section(rows: List[dict]) -> Tuple[Dict[str, Dict[str, Optional[float]]], List[str]]:
    """Generic screener section → ``({row_label: {col: value}}, ordered_cols)``."""
    out: Dict[str, Dict[str, Optional[float]]] = {}
    cols: List[str] = []
    for row in rows or []:
        if "data" in row and len(row) == 1:
            continue
        label = row.get("", "")
        if not label:
            first_key = next(iter(row), None)
            label = row.get(first_key, "") if first_key else ""
        if not label:
            continue
        vals: Dict[str, Optional[float]] = {}
        for k, v in row.items():
            if k in ("", None):
                continue
            vals[k] = _parse_number(v)
        out.setdefault(label, vals)
        if not cols:
            cols = [k for k in row.keys() if k not in ("", None)]
    return out, cols


def _latest_col_leq(cols: List[str], qend: date) -> Optional[str]:
    """Most recent annual/quarter column whose period-end is on/before ``qend``."""
    best: Optional[str] = None
    best_end: Optional[date] = None
    for c in cols:
        ce = _quarter_end(c)
        if ce is not None and ce <= qend:
            if best_end is None or ce > best_end:
                best, best_end = c, ce
    return best


@dataclass
class QualityMetrics:
    """Point-in-time balance-sheet / ratio quality snapshot for a result event."""
    debt_to_equity: Optional[float] = None
    roce: Optional[float] = None
    is_financial: bool = False


def quality_metrics(raw: dict, quarter_label: str) -> QualityMetrics:
    """Compute leverage + ROCE as-of ``quarter_label`` (point-in-time, leak-free).

    * ``debt_to_equity`` = Borrowings ÷ (Equity Capital + Reserves) from the
      latest annual balance sheet on/before the quarter-end.
    * ``roce`` = ROCE % from the latest annual financial-ratios column.
    * ``is_financial`` flags banks/NBFCs (they report Financing Profit and carry
      structurally high leverage, so a debt filter is not meaningful for them).

    Missing inputs yield ``None`` (callers treat that as "don't reject").
    """
    qend = _quarter_end(quarter_label)
    if qend is None:
        return QualityMetrics()

    qsec, _ = _index_section(raw.get("quarterly_results", []) or [])
    is_financial = "Financing Profit" in qsec or (
        "OPM %" not in qsec and "Financing Margin %" in qsec
    )

    de: Optional[float] = None
    bs, bsc = _index_section(raw.get("balance_sheet", []) or [])
    bcol = _latest_col_leq(bsc, qend)
    if bcol:
        borrow = bs.get("Borrowings+", {}).get(bcol)
        eq_cap = bs.get("Equity Capital", {}).get(bcol) or 0.0
        reserves = bs.get("Reserves", {}).get(bcol) or 0.0
        equity = eq_cap + reserves
        if borrow is not None and equity:
            de = borrow / equity

    roce: Optional[float] = None
    fr, frc = _index_section(raw.get("financial_ratios", []) or [])
    fcol = _latest_col_leq(frc, qend)
    if fcol:
        roce = fr.get("ROCE %", {}).get(fcol)

    return QualityMetrics(debt_to_equity=de, roce=roce, is_financial=is_financial)


def _symbol_reporting_lag(symbol: str, lag_min: int, lag_max: int) -> int:
    """Deterministic per-symbol reporting lag in ``[lag_min, lag_max]`` days.

    Indian companies do NOT all declare quarterly results on the same day —
    large caps report ~15-25 days after quarter-end, mid/small caps ~30-45 days.
    A fixed lag collapses this month-long distribution onto a single Monday, so
    every quarter's 100+ ideas fire simultaneously and the strategy's discovery
    engine is never really tested.

    We spread the declaration dates by hashing the symbol name into a stable
    day within the ``[lag_min, lag_max]`` window. Deterministic (md5-based, not
    Python's randomised ``hash``) so reruns are reproducible.
    """
    if lag_max < lag_min:
        lag_min, lag_max = lag_max, lag_min
    span = lag_max - lag_min + 1
    if span <= 1:
        return lag_min
    h = int(hashlib.md5(symbol.encode("utf-8")).hexdigest()[:8], 16)
    return lag_min + (h % span)


def enumerate_events(
    symbol: str,
    raw: dict,
    quarters: List[str],
    *,
    reporting_lag_min: int,
    reporting_lag_max: int,
    real_decl_dates: Optional[Dict[date, date]] = None,
) -> List[ResultEvent]:
    """All declarable result events for a symbol (one per parseable quarter col).

    A quarter needs at least 4 prior quarters (index >= 4) so year-on-year and a
    trailing-EPS baseline can be computed — mirroring the live selection gate.

    The declaration date is the REAL NSE announcement date when ``real_decl_dates``
    (a ``{quarter_end -> declaration date}`` map) contains this quarter; otherwise
    it falls back to ``quarter_end + per-symbol lag`` — a deterministic value in
    ``[reporting_lag_min, reporting_lag_max]`` — so the tape stays staggered and
    the backtest never breaks on a missing real date.
    """
    from datetime import timedelta

    company = raw.get("company_name", symbol)
    lag = _symbol_reporting_lag(symbol, reporting_lag_min, reporting_lag_max)
    real = real_decl_dates or {}
    events: List[ResultEvent] = []
    for i, label in enumerate(quarters):
        if i < 4:
            continue  # need YoY base + prior TTM window
        qend = _quarter_end(label)
        if qend is None:
            continue
        real_date = real.get(qend)
        decl_date = real_date if real_date is not None else qend + timedelta(days=lag)
        events.append(
            ResultEvent(
                symbol=symbol,
                company=company,
                q_idx=i,
                quarter_label=label,
                quarter_end=qend,
                decl_date=decl_date,
                decl_date_real=real_date is not None,
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


# ── PE-percentile guard (B3) ──────────────────────────────────────────────────

def _quarter_ttm_series(
    quarters: List[str],
    eps: Dict[str, Optional[float]],
    reporting_lag_days: int,
) -> List[Tuple[date, float]]:
    """Return (known_from_date, ttm_eps) pairs for every quarter with a full
    trailing-four-quarter EPS window.

    Each pair says: "from ``known_from_date`` onwards, the market knew this
    trailing EPS." Sorted chronologically. Only closed windows are included.
    """
    series: List[Tuple[date, float]] = []
    for j, label in enumerate(quarters):
        if j < 3:
            continue
        ttm = _ttm_eps_window(eps, quarters, j)
        if ttm is None or ttm <= 0:
            continue
        qend = _quarter_end(label)
        if qend is None:
            continue
        series.append((qend + timedelta(days=reporting_lag_days), ttm))
    series.sort(key=lambda p: p[0])
    return series


def pe_percentile(
    price_frame: Optional[pd.DataFrame],
    quarters: List[str],
    metrics: Dict[str, Dict[str, Optional[float]]],
    q_idx: int,
    as_of_day: date,
    reporting_lag_days: int,
    history_years: int,
) -> Optional[float]:
    """Point-in-time percentile rank of the entry PE within its ``history_years``
    trailing daily-PE distribution.

    Returns ``None`` when there is insufficient history or the PE cannot be
    formed. Otherwise returns a value in ``[0, 100]``: 0 = cheapest ever,
    100 = most expensive ever.

    Point-in-time integrity: only quarters with ``j < q_idx`` are used (their
    TTM windows are fully known *before* the current declaration), and prices
    are restricted to ``as_of_day`` and earlier.
    """
    if price_frame is None or price_frame.empty:
        return None

    eps = _series(metrics, "eps")
    # Truncate quarters used to only those known BEFORE the current declaration.
    ttm_series = _quarter_ttm_series(quarters[:q_idx], eps, reporting_lag_days)
    if not ttm_series:
        return None

    # Build a daily TTM-EPS lookup by stepping the piecewise-constant series
    # across the trading days in [as_of_day - history_years, as_of_day].
    cutoff_start = date(as_of_day.year - history_years, as_of_day.month, min(as_of_day.day, 28))
    df = price_frame.loc[: pd.Timestamp(as_of_day).normalize()]
    df = df.loc[df.index >= pd.Timestamp(cutoff_start).normalize()]
    if df.empty:
        return None

    # For each row, pick the latest ttm_series entry whose known_from <= row date.
    import numpy as np

    known_dates = np.array(
        [pd.Timestamp(kd).to_datetime64() for kd, _ in ttm_series],
        dtype="datetime64[ns]",
    )
    known_eps = np.array([e for _, e in ttm_series], dtype=float)
    row_dates = df.index.values.astype("datetime64[ns]")

    idx = np.searchsorted(known_dates, row_dates, side="right") - 1
    valid = idx >= 0
    if not valid.any():
        return None
    prices = df["Close"].to_numpy()[valid]
    eps_lookup = known_eps[idx[valid]]
    pe_series = prices / eps_lookup
    pe_series = pe_series[(pe_series > 0) & np.isfinite(pe_series)]
    if pe_series.size < 30:
        return None

    # Current PE = latest close available / most recent known TTM.
    current_pe = pe_series[-1]
    rank = float((pe_series <= current_pe).sum()) / pe_series.size * 100.0
    return rank
