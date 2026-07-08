"""Mechanical verification of quarterly results via screener.in.

For a given NSE symbol this scrapes screener.in (reusing
``scraper.screener.scrape_fundamentals``) and computes QoQ / YoY growth for
sales, net profit and EPS, margin trend, a TTM-EPS estimate and a composite
"result strength" score used for selection and static target tiering.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from scraper.screener import scrape_fundamentals

from qtr_results import config
from qtr_results.util import parse_number, pct_change

logger = logging.getLogger("qtr_results.analysis")


@dataclass
class AnalysisResult:
    symbol: str
    company_name: str = ""
    latest_quarter: str = ""
    current_price: Optional[float] = None
    current_pe: Optional[float] = None
    ttm_eps: Optional[float] = None
    yoy_profit_growth: Optional[float] = None
    qoq_profit_growth: Optional[float] = None
    yoy_sales_growth: Optional[float] = None
    qoq_sales_growth: Optional[float] = None
    yoy_eps_growth: Optional[float] = None
    margin_delta_pp: Optional[float] = None
    strength_score: float = 0.0
    is_strong: bool = False
    rationale: str = ""
    error: Optional[str] = None
    raw_top_ratios: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d.pop("raw_top_ratios", None)
        return d


# ── screener label normalization ───────────────────────────────────────────
def _norm_label(label: str) -> str:
    s = re.sub(r"[^a-z% ]", "", (label or "").lower()).strip()
    if "sales" in s or "revenue" in s or "income" in s and "other" not in s:
        return "sales"
    if "net profit" in s or (s.startswith("profit") and "operating" not in s):
        return "net_profit"
    if "operating profit" in s:
        return "operating_profit"
    if "opm" in s:
        return "opm"
    if s.startswith("eps"):
        return "eps"
    return s


def _index_quarterly(rows: List[Dict[str, str]]) -> Tuple[List[str], Dict[str, Dict[str, Optional[float]]]]:
    """Turn screener's quarterly table rows into {metric: {quarter: value}}."""
    quarters: List[str] = []
    metrics: Dict[str, Dict[str, Optional[float]]] = {}
    for row in rows:
        if "data" in row and len(row) == 1:
            continue
        label = row.get("", "")
        if not label:
            # Fall back to the first value if the row-label column isn't empty-keyed.
            first_key = next(iter(row), None)
            label = row.get(first_key, "") if first_key else ""
        canon = _norm_label(label)
        if not canon:
            continue
        qvals: Dict[str, Optional[float]] = {}
        for k, v in row.items():
            if k == "" or k is None:
                continue
            qvals[k] = parse_number(v)
        metrics.setdefault(canon, qvals)
        if not quarters:
            quarters = [k for k in row.keys() if k not in ("", None)]
    return quarters, metrics


def _series(metrics: Dict[str, Dict[str, Optional[float]]], name: str) -> Dict[str, Optional[float]]:
    return metrics.get(name, {})


def _val(series: Dict[str, Optional[float]], quarter: Optional[str]) -> Optional[float]:
    return series.get(quarter) if quarter else None


def _ttm_eps(eps_series: Dict[str, Optional[float]], quarters: List[str]) -> Optional[float]:
    last4 = [eps_series.get(q) for q in quarters[-4:]]
    if len(last4) < 4 or any(v is None for v in last4):
        return None
    return sum(v for v in last4 if v is not None)


def _strength_score(
    yoy_profit: Optional[float],
    qoq_profit: Optional[float],
    yoy_eps: Optional[float],
    yoy_sales: Optional[float],
    margin_delta: Optional[float],
) -> float:
    def contrib(value: Optional[float], cap: float, weight: float, floor: float = 0.0) -> float:
        if value is None:
            return 0.0
        v = max(floor, min(value, cap))
        return (v - floor) / (cap - floor) * weight if cap > floor else 0.0

    score = (
        contrib(yoy_profit, 100.0, 35.0)
        + contrib(qoq_profit, 50.0, 20.0)
        + contrib(yoy_eps, 100.0, 25.0)
        + contrib(yoy_sales, 50.0, 15.0)
        + contrib(margin_delta, 10.0, 5.0)
    )
    return round(max(0.0, min(100.0, score)), 1)


def analyze_symbol(symbol: str) -> AnalysisResult:
    """Scrape screener.in and compute the result-strength profile for a symbol."""
    symbol = symbol.strip().upper()
    logger.info("Analyzing quarterly results for %s", symbol)

    data = scrape_fundamentals(symbol)
    if not data or "error" in data:
        return AnalysisResult(symbol=symbol, error=(data or {}).get("error", "no data"))

    top = data.get("top_ratios", {}) or {}
    quarterly_rows = data.get("quarterly_results", []) or []
    quarters, metrics = _index_quarterly(quarterly_rows)

    if len(quarters) < 2:
        return AnalysisResult(
            symbol=symbol,
            company_name=data.get("company_name", ""),
            raw_top_ratios=top,
            error="insufficient quarterly history",
        )

    latest = quarters[-1]
    qoq_base = quarters[-2] if len(quarters) >= 2 else None
    yoy_base = quarters[-5] if len(quarters) >= 5 else None

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
        and yoy_profit >= config.MIN_YOY_PROFIT_GROWTH
        and (yoy_eps is None or yoy_eps >= config.MIN_YOY_EPS_GROWTH)
        and (qoq_profit is None or qoq_profit >= config.MIN_QOQ_PROFIT_GROWTH)
    )

    result = AnalysisResult(
        symbol=symbol,
        company_name=data.get("company_name", ""),
        latest_quarter=latest,
        current_price=parse_number(top.get("Current Price")),
        current_pe=parse_number(top.get("Stock P/E") or top.get("P/E")),
        ttm_eps=_ttm_eps(eps, quarters),
        yoy_profit_growth=yoy_profit,
        qoq_profit_growth=qoq_profit,
        yoy_sales_growth=yoy_sales,
        qoq_sales_growth=qoq_sales,
        yoy_eps_growth=yoy_eps,
        margin_delta_pp=margin_delta,
        strength_score=score,
        is_strong=bool(is_strong),
        raw_top_ratios=top,
    )
    result.rationale = _build_rationale(result)
    return result


def _build_rationale(r: AnalysisResult) -> str:
    from qtr_results.util import fmt_pct

    parts = [
        f"Net profit YoY {fmt_pct(r.yoy_profit_growth)}",
        f"QoQ {fmt_pct(r.qoq_profit_growth)}",
        f"EPS YoY {fmt_pct(r.yoy_eps_growth)}",
        f"Sales YoY {fmt_pct(r.yoy_sales_growth)}",
    ]
    if r.margin_delta_pp is not None:
        parts.append(f"OPM d {r.margin_delta_pp:+.1f}pp")
    return "; ".join(parts)
