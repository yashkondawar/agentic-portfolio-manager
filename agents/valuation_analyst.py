"""
Valuation Analyst Agent — Multi-Model DCF adapted for India.

Models:
1. DCF (40% weight) — 3-stage FCFF model with India risk parameters
2. Owner Earnings (30% weight) — Buffett-style, margin of safety built in
3. EV/EBITDA relative (30% weight) — Median historical multiple

India-specific parameters:
- Risk-free rate: 7.1% (10-year G-Sec yield)
- Equity Risk Premium: 7.5% (Damodaran India ERP)
- Terminal growth: 5% (higher than US due to India GDP growth)
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

from agents.models import AnalystSignal, ValuationResult

logger = logging.getLogger(__name__)

# India-specific parameters
RISK_FREE_RATE = 0.071  # 10-year G-Sec
EQUITY_RISK_PREMIUM = 0.075  # India ERP
TERMINAL_GROWTH = 0.05  # India nominal GDP growth proxy
DEFAULT_BETA = 1.0


def _get_valuation_data(symbol: str) -> Dict[str, Any]:
    """Fetch valuation data from yfinance."""
    import yfinance as yf

    ticker_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info or {}

    # Get financial statements for FCF calculation
    cashflow = None
    try:
        cf = ticker.cashflow
        if cf is not None and not cf.empty:
            cashflow = cf
    except Exception:
        pass

    return {"info": info, "cashflow": cashflow}


def _dcf_valuation(info: Dict, cashflow) -> Optional[float]:
    """
    3-stage DCF model:
    Stage 1 (years 1-3): High growth
    Stage 2 (years 4-7): Transition
    Stage 3 (terminal): Perpetuity at terminal growth
    """
    # Get FCF
    fcf = info.get("freeCashflow")
    if not fcf or fcf <= 0:
        return None

    # Cost of equity (CAPM with India parameters)
    beta = info.get("beta", DEFAULT_BETA) or DEFAULT_BETA
    cost_of_equity = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM

    # Growth estimation
    earnings_growth = info.get("earningsGrowth", 0.10) or 0.10
    revenue_growth = info.get("revenueGrowth", 0.10) or 0.10
    base_growth = min((earnings_growth + revenue_growth) / 2, 0.25)  # Cap at 25%

    # WACC (simplified — assume 70% equity, 30% debt for India companies)
    de_ratio = (info.get("debtToEquity", 50) or 50) / 100
    weight_debt = de_ratio / (1 + de_ratio)
    weight_equity = 1 - weight_debt
    cost_of_debt = RISK_FREE_RATE + 0.02  # Spread over risk-free
    tax_rate = 0.25  # India corporate tax
    wacc = weight_equity * cost_of_equity + weight_debt * cost_of_debt * (1 - tax_rate)
    wacc = max(min(wacc, 0.20), 0.08)  # Clamp between 8-20%

    # Stage 1: High growth (years 1-3)
    pv = 0
    current_fcf = fcf
    for year in range(1, 4):
        current_fcf *= (1 + base_growth)
        pv += current_fcf / (1 + wacc) ** year

    # Stage 2: Transition (years 4-7), linear fade to terminal
    transition_growth = base_growth
    growth_step = (base_growth - TERMINAL_GROWTH) / 4
    for year in range(4, 8):
        transition_growth -= growth_step
        current_fcf *= (1 + transition_growth)
        pv += current_fcf / (1 + wacc) ** year

    # Stage 3: Terminal value
    terminal_fcf = current_fcf * (1 + TERMINAL_GROWTH)
    terminal_value = terminal_fcf / (wacc - TERMINAL_GROWTH)
    pv_terminal = terminal_value / (1 + wacc) ** 7

    intrinsic_value = pv + pv_terminal
    return intrinsic_value


def _owner_earnings_valuation(info: Dict) -> Optional[float]:
    """Buffett-style owner earnings valuation with built-in margin of safety."""
    net_income = info.get("netIncomeToCommon")
    if not net_income or net_income <= 0:
        return None

    # Approximate owner earnings
    # Owner earnings ≈ Net Income (yfinance doesn't break out depreciation easily)
    # Apply conservative multiplier based on growth
    earnings_growth = info.get("earningsGrowth", 0.08) or 0.08
    earnings_growth = min(earnings_growth, 0.20)  # Cap

    required_return = 0.15  # 15% for India
    terminal_growth = min(earnings_growth * 0.4, TERMINAL_GROWTH)

    # 5-year projection
    pv = 0
    current_earnings = net_income
    for year in range(1, 6):
        current_earnings *= (1 + earnings_growth)
        pv += current_earnings / (1 + required_return) ** year

    # Terminal value
    terminal_earnings = current_earnings * (1 + terminal_growth)
    terminal_value = terminal_earnings / (required_return - terminal_growth)
    pv_terminal = terminal_value / (1 + required_return) ** 5

    intrinsic = (pv + pv_terminal) * 0.75  # 25% margin of safety built in
    return intrinsic


def _ev_ebitda_valuation(info: Dict) -> Optional[float]:
    """Relative valuation using EV/EBITDA."""
    ev = info.get("enterpriseValue")
    ev_ebitda = info.get("enterpriseToEbitda")
    market_cap = info.get("marketCap")

    if not ev or not ev_ebitda or ev_ebitda <= 0:
        return None

    current_ebitda = ev / ev_ebitda

    # Use sector median for India (approximate)
    # Large-cap India median EV/EBITDA ~ 15-18x
    fair_multiple = 15.0
    if ev_ebitda < 10:
        fair_multiple = 12.0
    elif ev_ebitda > 25:
        fair_multiple = 20.0

    fair_ev = current_ebitda * fair_multiple
    net_debt = ev - market_cap if market_cap else 0
    fair_equity = fair_ev - net_debt

    return fair_equity


def analyze_valuation(symbol: str) -> Dict[str, Any]:
    """
    Run multi-model valuation for a ticker.
    Returns structured signal + metrics.
    """
    logger.info(f"[VALUATION] {symbol}: Fetching valuation data...")

    try:
        data = _get_valuation_data(symbol)
        info = data["info"]

        if not info or not info.get("marketCap"):
            logger.warning(f"[VALUATION] {symbol}: No market cap data available")
            return {
                "signal": AnalystSignal(
                    signal="neutral", confidence=0,
                    reasoning=f"No valuation data available for {symbol}"
                ),
                "metrics": None,
            }

        logger.info(
            f"[VALUATION] {symbol}: Data fetched - "
            f"MarketCap=₹{info['marketCap']/1e7:,.0f}Cr, "
            f"FCF=₹{(info.get('freeCashflow') or 0)/1e7:,.0f}Cr, "
            f"EV/EBITDA={info.get('enterpriseToEbitda', 'N/A')}, "
            f"Beta={info.get('beta', 'N/A')}, "
            f"EarningsGrowth={info.get('earningsGrowth', 'N/A')}"
        )

        market_cap = info["marketCap"]

        # Run all valuation models
        dcf_val = _dcf_valuation(info, data["cashflow"])
        owner_val = _owner_earnings_valuation(info)
        ev_ebitda_val = _ev_ebitda_valuation(info)

        # Weighted average of available models
        models = {
            "dcf": (dcf_val, 0.40),
            "owner_earnings": (owner_val, 0.30),
            "ev_ebitda": (ev_ebitda_val, 0.30),
        }

        dcf_str = f"₹{dcf_val/1e7:,.0f}Cr" if dcf_val else "N/A"
        owner_str = f"₹{owner_val/1e7:,.0f}Cr" if owner_val else "N/A"
        ev_str = f"₹{ev_ebitda_val/1e7:,.0f}Cr" if ev_ebitda_val else "N/A"
        logger.info(
            f"[VALUATION] {symbol}: Model outputs - "
            f"DCF={dcf_str}, OwnerEarnings={owner_str}, EV/EBITDA={ev_str}"
        )

        weighted_value = 0
        total_weight = 0
        method_used = []

        for name, (value, weight) in models.items():
            if value is not None and value > 0:
                weighted_value += value * weight
                total_weight += weight
                method_used.append(name)

        if total_weight == 0:
            return {
                "signal": AnalystSignal(
                    signal="neutral", confidence=20,
                    reasoning=f"Could not compute intrinsic value for {symbol}"
                ),
                "metrics": None,
            }

        intrinsic_value = weighted_value / total_weight
        margin_of_safety = (intrinsic_value - market_cap) / market_cap

        # Determine signal
        if margin_of_safety > 0.20:
            signal = "bullish"
        elif margin_of_safety < -0.20:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(abs(margin_of_safety) / 0.40 * 100, 95)

        reasoning = (
            f"Intrinsic: ₹{intrinsic_value/1e7:.0f}Cr vs Market: ₹{market_cap/1e7:.0f}Cr. "
            f"MoS={margin_of_safety*100:.1f}%. Methods: {'+'.join(method_used)}"
        )

        metrics = ValuationResult(
            intrinsic_value=intrinsic_value,
            market_cap=market_cap,
            margin_of_safety_pct=margin_of_safety * 100,
            dcf_value=dcf_val,
            ev_ebitda_value=ev_ebitda_val,
            method_used="+".join(method_used),
        )

        return {
            "signal": AnalystSignal(
                signal=signal, confidence=confidence, reasoning=reasoning
            ),
            "metrics": metrics,
        }

    except Exception as e:
        logger.error(f"Valuation analysis failed for {symbol}: {e}")
        return {
            "signal": AnalystSignal(
                signal="neutral", confidence=0,
                reasoning=f"Valuation error: {str(e)[:80]}"
            ),
            "metrics": None,
        }
