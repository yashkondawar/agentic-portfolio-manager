"""
Fundamentals Analyst Agent — 4-Dimension Rule-Based Scoring.

Scores stocks on:
1. Profitability (0-3): ROE, net margin, operating margin
2. Growth (0-3): Revenue growth, earnings growth, book value growth
3. Financial Health (0-3): Current ratio, debt-to-equity, FCF quality
4. Valuation (0-3): P/E, P/B, EV/EBITDA (inverted — high = expensive)

No LLM needed — pure quantitative scoring.
"""

import logging
from typing import Dict, Any

from agents.models import AnalystSignal, FundamentalMetrics

logger = logging.getLogger(__name__)


def _get_fundamentals_data(symbol: str) -> Dict[str, Any]:
    """Fetch fundamental data via the unified data provider (yfinance + screener.in)."""
    from scraper.data_provider import get_stock_data

    data = get_stock_data(symbol)

    # Build a dict compatible with the scoring functions (same keys as yfinance .info)
    info = {
        "returnOnEquity": data.roe or None,
        "profitMargins": data.profit_margins or None,
        "operatingMargins": data.operating_margins or None,
        "revenueGrowth": data.revenue_growth or None,
        "earningsGrowth": data.earnings_growth or None,
        "trailingPE": data.pe_ratio or None,
        "priceToBook": data.price_to_book or None,
        "enterpriseToEbitda": data.ev_to_ebitda or None,
        "debtToEquity": data.debt_to_equity or None,
        "currentRatio": data.current_ratio or None,
        "freeCashflow": data.free_cashflow or None,
        "totalRevenue": data.total_revenue or None,
        "regularMarketPrice": data.current_price or None,
        # Screener.in extras (ROCE, sales growth trend, etc.)
        "_screener_ratios": data.screener_ratios,
        "_quarterly_results": data.quarterly_results,
    }

    # Enrich from screener.in ratios if yfinance missing data
    sr = data.screener_ratios
    if sr:
        if not info["returnOnEquity"]:
            try:
                roe_str = sr.get("Return on Equity", sr.get("ROE", ""))
                if roe_str:
                    info["returnOnEquity"] = float(roe_str.replace("%", "").replace(",", "")) / 100
            except (ValueError, TypeError):
                pass

    return info


def _score_profitability(info: Dict) -> int:
    """Score profitability 0-3. Each metric above threshold = +1."""
    score = 0
    roe = info.get("returnOnEquity")
    net_margin = info.get("profitMargins")
    op_margin = info.get("operatingMargins")

    if roe is not None and roe > 0.15:
        score += 1
    if net_margin is not None and net_margin > 0.10:
        score += 1
    if op_margin is not None and op_margin > 0.15:
        score += 1

    return score


def _score_growth(info: Dict) -> int:
    """Score growth 0-3."""
    score = 0
    rev_growth = info.get("revenueGrowth")
    earn_growth = info.get("earningsGrowth")
    # Book value growth approximated via earnings retention
    payout = info.get("payoutRatio", 0) or 0
    roe = info.get("returnOnEquity", 0) or 0
    bv_growth = roe * (1 - payout) if roe > 0 else 0

    if rev_growth is not None and rev_growth > 0.10:
        score += 1
    if earn_growth is not None and earn_growth > 0.10:
        score += 1
    if bv_growth > 0.08:
        score += 1

    return score


def _score_health(info: Dict) -> int:
    """Score financial health 0-3."""
    score = 0
    current_ratio = info.get("currentRatio")
    de_ratio = info.get("debtToEquity")
    fcf = info.get("freeCashflow", 0) or 0
    net_income = info.get("netIncomeToCommon", 0) or 0

    if current_ratio is not None and current_ratio > 1.5:
        score += 1
    if de_ratio is not None and de_ratio < 80:  # yfinance reports as percentage
        score += 1
    if fcf > 0 and net_income > 0 and fcf > net_income * 0.6:
        score += 1

    return score


def _score_valuation(info: Dict) -> int:
    """Score valuation 0-3 (inverted: cheap = higher score)."""
    score = 0
    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    ev_ebitda = info.get("enterpriseToEbitda")

    # Indian market thresholds (slightly higher than US due to growth premium)
    if pe is not None and pe < 25:
        score += 1
    if pb is not None and pb < 4:
        score += 1
    if ev_ebitda is not None and ev_ebitda < 18:
        score += 1

    return score


def analyze_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    Run 4-dimension fundamental scoring for a ticker.
    Returns structured signal + metrics.
    """
    logger.info(f"[FUNDAMENTALS] {symbol}: Fetching data from yfinance...")

    try:
        info = _get_fundamentals_data(symbol)

        if not info or info.get("regularMarketPrice") is None:
            logger.warning(f"[FUNDAMENTALS] {symbol}: No data returned from yfinance")
            return {
                "signal": AnalystSignal(
                    signal="neutral", confidence=0,
                    reasoning=f"No fundamental data available for {symbol}"
                ),
                "metrics": None,
            }

        # Log fetched data
        logger.info(
            f"[FUNDAMENTALS] {symbol}: Data fetched - "
            f"ROE={info.get('returnOnEquity', 'N/A')}, "
            f"P/E={info.get('trailingPE', 'N/A')}, "
            f"P/B={info.get('priceToBook', 'N/A')}, "
            f"D/E={info.get('debtToEquity', 'N/A')}, "
            f"RevenueGrowth={info.get('revenueGrowth', 'N/A')}, "
            f"EarningsGrowth={info.get('earningsGrowth', 'N/A')}, "
            f"OpMargin={info.get('operatingMargins', 'N/A')}, "
            f"CurrentRatio={info.get('currentRatio', 'N/A')}"
        )

        # Score all 4 dimensions
        prof_score = _score_profitability(info)
        growth_score = _score_growth(info)
        health_score = _score_health(info)
        val_score = _score_valuation(info)
        total = prof_score + growth_score + health_score + val_score

        # Determine signal based on total score (max 12)
        if total >= 8:
            signal = "bullish"
        elif total <= 4:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = (total / 12) * 100

        # Build reasoning
        reasoning = (
            f"Score {total}/12: Profitability={prof_score}/3, "
            f"Growth={growth_score}/3, Health={health_score}/3, "
            f"Valuation={val_score}/3. "
            f"ROE={info.get('returnOnEquity', 'N/A')}, "
            f"P/E={info.get('trailingPE', 'N/A')}, "
            f"D/E={info.get('debtToEquity', 'N/A')}"
        )

        metrics = FundamentalMetrics(
            profitability_score=prof_score,
            growth_score=growth_score,
            health_score=health_score,
            valuation_score=val_score,
            total_score=total,
        )

        return {
            "signal": AnalystSignal(
                signal=signal, confidence=confidence, reasoning=reasoning
            ),
            "metrics": metrics,
        }

    except Exception as e:
        logger.error(f"Fundamentals analysis failed for {symbol}: {e}")
        return {
            "signal": AnalystSignal(
                signal="neutral", confidence=0,
                reasoning=f"Analysis error: {str(e)[:80]}"
            ),
            "metrics": None,
        }
