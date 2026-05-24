"""
Investor Persona Agents — LLM-powered analysis with quantitative pre-scoring.

Inspired by virattt/ai-hedge-fund architecture:
1. Pre-compute quantitative facts (no LLM)
2. Pass facts to LLM with persona system prompt
3. LLM returns structured {signal, confidence, reasoning}

Two personas adapted for Indian markets:
1. Warren Buffett — Moat + owner earnings + margin of safety
2. Rakesh Jhunjhunwala — India growth compounder style
"""

import json
import logging
from typing import Dict, Any

from agents.models import AnalystSignal

logger = logging.getLogger(__name__)


def _get_stock_data(symbol: str) -> Dict[str, Any]:
    """Fetch comprehensive stock data via the unified data provider."""
    from scraper.data_provider import get_stock_data

    data = get_stock_data(symbol)

    # Build info dict compatible with persona fact computation
    info = {
        "returnOnEquity": data.roe or 0,
        "operatingMargins": data.operating_margins or 0,
        "profitMargins": data.profit_margins or 0,
        "debtToEquity": data.debt_to_equity or 0,
        "currentRatio": data.current_ratio or 0,
        "freeCashflow": data.free_cashflow or 0,
        "trailingPE": data.pe_ratio or 0,
        "priceToBook": data.price_to_book or 0,
        "marketCap": data.market_cap or 0,
        "netIncomeToCommon": 0,  # Not directly available, not critical
        "revenueGrowth": data.revenue_growth or 0,
        "earningsGrowth": data.earnings_growth or 0,
        "currentPrice": data.current_price or 0,
        "sector": data.sector or "",
        "industry": data.industry or "",
        "bookValue": data.book_value or 0,
        # Screener.in extras
        "_screener_ratios": data.screener_ratios,
        "_quarterly_results": data.quarterly_results,
        "_shareholding": data.shareholding,
    }

    # Enrich from screener.in if available
    sr = data.screener_ratios
    if sr:
        try:
            roce_str = sr.get("ROCE", "")
            if roce_str and not info.get("_roce"):
                info["_roce"] = float(roce_str.replace("%", "").replace(",", "")) / 100
        except (ValueError, TypeError):
            pass

    return info


def _compute_buffett_facts(info: Dict) -> Dict[str, Any]:
    """
    Pre-compute Warren Buffett's quantitative checklist into a facts bundle.
    This is what gets passed to the LLM — pure numbers, no opinion.
    """
    roe = info.get("returnOnEquity", 0) or 0
    op_margin = info.get("operatingMargins", 0) or 0
    net_margin = info.get("profitMargins", 0) or 0
    de = info.get("debtToEquity", 0) or 0
    current_ratio = info.get("currentRatio", 0) or 0
    fcf = info.get("freeCashflow", 0) or 0
    pe = info.get("trailingPE", 0) or 0
    pb = info.get("priceToBook", 0) or 0
    market_cap = info.get("marketCap", 0) or 0
    net_income = info.get("netIncomeToCommon", 0) or 0
    revenue_growth = info.get("revenueGrowth", 0) or 0
    earnings_growth = info.get("earningsGrowth", 0) or 0

    # Moat indicators
    moat_strong = roe > 0.15 and op_margin > 0.15
    moat_reasoning = []
    if roe > 0.15:
        moat_reasoning.append(f"ROE of {roe:.1%} exceeds 15% threshold")
    else:
        moat_reasoning.append(f"ROE of {roe:.1%} below 15% (weak moat signal)")
    if op_margin > 0.15:
        moat_reasoning.append(f"Operating margin {op_margin:.1%} suggests pricing power")
    else:
        moat_reasoning.append(f"Operating margin {op_margin:.1%} is thin")

    # Financial strength
    strength_reasoning = []
    if de < 80:
        strength_reasoning.append(f"D/E ratio of {de:.0f}% is conservative")
    else:
        strength_reasoning.append(f"D/E ratio of {de:.0f}% indicates heavy debt")
    if current_ratio > 1.5:
        strength_reasoning.append(f"Current ratio {current_ratio:.1f} shows adequate liquidity")
    else:
        strength_reasoning.append(f"Current ratio {current_ratio:.1f} is tight")
    if fcf > 0:
        strength_reasoning.append(f"Positive FCF of ₹{fcf/1e7:,.0f}Cr")
    else:
        strength_reasoning.append("Negative free cash flow (cash burn)")

    # Valuation
    reasonably_priced = pe > 0 and pe < 25
    val_reasoning = []
    if pe > 0:
        val_reasoning.append(f"P/E of {pe:.1f}" + (" (reasonable)" if pe < 25 else " (expensive)"))
    if pb > 0:
        val_reasoning.append(f"P/B of {pb:.1f}" + (" (fair)" if pb < 4 else " (premium)"))

    # Intrinsic value estimate (simple owner earnings model)
    if net_income > 0:
        # Buffett: owner earnings × multiple
        owner_earnings = net_income * 0.85  # Conservative
        fair_multiple = min(15, max(8, 10 + (earnings_growth or 0) * 20))
        intrinsic_value = owner_earnings * fair_multiple
        margin_of_safety = (intrinsic_value - market_cap) / market_cap if market_cap > 0 else 0
    else:
        intrinsic_value = 0
        margin_of_safety = -1

    # Aggregate score (for fallback)
    score = 0
    if roe > 0.15: score += 1
    if op_margin > 0.15: score += 1
    if de < 80: score += 1
    if current_ratio > 1.5: score += 1
    if fcf > 0: score += 1
    if reasonably_priced: score += 1

    return {
        "ticker": info.get("symbol", ""),
        "company_name": info.get("shortName", ""),
        "sector": info.get("sector", "Unknown"),
        "market_cap_cr": round(market_cap / 1e7, 0) if market_cap else 0,
        "moat": {
            "roe": round(roe * 100, 1),
            "operating_margin": round(op_margin * 100, 1),
            "net_margin": round(net_margin * 100, 1),
            "is_strong": moat_strong,
            "details": "; ".join(moat_reasoning),
        },
        "financial_strength": {
            "debt_to_equity": round(de, 1),
            "current_ratio": round(current_ratio, 2),
            "free_cash_flow_cr": round(fcf / 1e7, 0) if fcf else 0,
            "details": "; ".join(strength_reasoning),
        },
        "growth": {
            "revenue_growth": round((revenue_growth or 0) * 100, 1),
            "earnings_growth": round((earnings_growth or 0) * 100, 1),
        },
        "valuation": {
            "pe_ratio": round(pe, 1) if pe else None,
            "pb_ratio": round(pb, 1) if pb else None,
            "reasonably_priced": reasonably_priced,
            "intrinsic_value_cr": round(intrinsic_value / 1e7, 0) if intrinsic_value else 0,
            "market_cap_cr": round(market_cap / 1e7, 0) if market_cap else 0,
            "margin_of_safety_pct": round(margin_of_safety * 100, 1),
            "details": "; ".join(val_reasoning),
        },
        "score": score,
        "max_score": 6,
    }


def _compute_jhunjhunwala_facts(info: Dict) -> Dict[str, Any]:
    """
    Pre-compute Jhunjhunwala-style growth scoring into a facts bundle.
    Focus: Growth quality, ROE, low debt, India themes.
    """
    rev_growth = info.get("revenueGrowth", 0) or 0
    earn_growth = info.get("earningsGrowth", 0) or 0
    roe = info.get("returnOnEquity", 0) or 0
    net_margin = info.get("profitMargins", 0) or 0
    de = info.get("debtToEquity", 0) or 0
    pe = info.get("trailingPE", 0) or 0
    market_cap = info.get("marketCap", 0) or 0
    sector = info.get("sector", "Unknown")
    industry = info.get("industry", "Unknown")

    # Growth quality
    growth_details = []
    if rev_growth > 0.15:
        growth_details.append(f"Revenue growing at {rev_growth:.0%} (excellent)")
    elif rev_growth > 0:
        growth_details.append(f"Revenue growing at {rev_growth:.0%} (moderate)")
    else:
        growth_details.append(f"Revenue declining at {rev_growth:.0%}")

    if earn_growth > 0.15:
        growth_details.append(f"Earnings growing at {earn_growth:.0%} (strong)")
    elif earn_growth > 0:
        growth_details.append(f"Earnings growing at {earn_growth:.0%}")
    else:
        growth_details.append(f"Earnings declining at {earn_growth:.0%}")

    # Profitability
    profit_details = []
    if roe > 0.20:
        profit_details.append(f"Excellent ROE of {roe:.0%} (>20% — compounder)")
    elif roe > 0.12:
        profit_details.append(f"Good ROE of {roe:.0%}")
    else:
        profit_details.append(f"Weak ROE of {roe:.0%}")
    profit_details.append(f"Net margin: {net_margin:.0%}")

    # Balance sheet
    bs_details = []
    if de < 30:
        bs_details.append(f"Very low debt (D/E={de:.0f}%) — Jhunjhunwala preferred")
    elif de < 80:
        bs_details.append(f"Moderate debt (D/E={de:.0f}%)")
    else:
        bs_details.append(f"High debt (D/E={de:.0f}%) — risky")

    # India themes
    india_themes = []
    bullish_sectors = ["Financial Services", "Consumer Cyclical", "Industrials", "Technology", "Healthcare"]
    if sector in bullish_sectors:
        india_themes.append(f"Sector '{sector}' aligns with India growth themes")
    india_themes.append(f"Industry: {industry}")
    if market_cap > 200000000000:
        india_themes.append("Large-cap (>₹20,000 Cr)")
    elif market_cap > 50000000000:
        india_themes.append("Mid-cap (₹5,000-20,000 Cr) — Jhunjhunwala's sweet spot")
    else:
        india_themes.append("Small-cap (<₹5,000 Cr)")

    # Score
    score = 0
    if rev_growth > 0.15: score += 1
    if earn_growth > 0.15: score += 1
    if rev_growth > 0 and earn_growth > 0: score += 1
    if roe > 0.20: score += 2
    elif roe > 0.12: score += 1
    if net_margin > 0.10: score += 1
    if de < 30: score += 2
    elif de < 80: score += 1

    return {
        "ticker": info.get("symbol", ""),
        "company_name": info.get("shortName", ""),
        "sector": sector,
        "industry": industry,
        "market_cap_cr": round(market_cap / 1e7, 0) if market_cap else 0,
        "growth": {
            "revenue_growth_pct": round(rev_growth * 100, 1),
            "earnings_growth_pct": round(earn_growth * 100, 1),
            "details": "; ".join(growth_details),
        },
        "profitability": {
            "roe_pct": round(roe * 100, 1),
            "net_margin_pct": round(net_margin * 100, 1),
            "details": "; ".join(profit_details),
        },
        "balance_sheet": {
            "debt_to_equity": round(de, 1),
            "details": "; ".join(bs_details),
        },
        "india_themes": "; ".join(india_themes),
        "valuation": {
            "pe_ratio": round(pe, 1) if pe else None,
        },
        "score": score,
        "max_score": 8,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS — Inspired by virattt/ai-hedge-fund, adapted for Indian markets
# ══════════════════════════════════════════════════════════════════════════════

BUFFETT_SYSTEM_PROMPT = """You are Warren Buffett analyzing an Indian NSE-listed stock.
Decide bullish, bearish, or neutral using ONLY the provided quantitative facts.

Your investment checklist:
1. Circle of competence — Is this a business you understand?
2. Competitive moat — High ROE (>15%), strong margins, pricing power
3. Financial strength — Low debt, positive free cash flow, adequate liquidity
4. Valuation vs intrinsic value — Margin of safety > 0 means undervalued
5. Management quality — Evidenced by capital allocation (ROE, low dilution)

Signal rules:
- Bullish: Strong moat AND positive margin of safety AND low debt
- Bearish: No moat (weak ROE/margins) OR clearly overvalued (negative MoS > 20%) OR deteriorating financials
- Neutral: Good business but expensive, or mixed signals

Confidence scale:
- 80-100%: Exceptional business with clear margin of safety
- 60-79%: Good business with decent moat, fair valuation
- 40-59%: Mixed signals, would need better price
- 20-39%: Concerning fundamentals or outside circle of competence
- 0-19%: Poor business or significantly overvalued

Keep reasoning under 150 characters. Do not invent data. Return ONLY valid JSON."""

BUFFETT_HUMAN_TEMPLATE = """Ticker: {ticker}

Quantitative Facts:
{facts}

Return exactly this JSON format:
{{"signal": "bullish" or "bearish" or "neutral", "confidence": 0-100, "reasoning": "concise justification"}}"""


JHUNJHUNWALA_SYSTEM_PROMPT = """You are Rakesh Jhunjhunwala analyzing an Indian NSE-listed stock.
Decide bullish, bearish, or neutral using ONLY the provided quantitative facts.

Your investment philosophy ("Buy right and hold tight"):
1. Growth is king — Revenue and earnings must be growing >15% for excitement
2. ROE excellence — Only back compounders with ROE > 20%
3. Low debt — Prefer companies that can self-fund growth (D/E < 50%)
4. India themes — Favor consumption, banking, infra, pharma, and digital India
5. Promoter quality — Large-cap or reputed mid-cap with skin in the game
6. Valuation is secondary to growth — Willing to pay up for genuine compounders

Signal rules:
- Bullish: High growth (>15%) + High ROE (>20%) + Low debt + India-aligned sector
- Bearish: Stagnant/negative growth + Deteriorating ROE + High leverage
- Neutral: Moderate growth but fully valued, or turnaround story too early to call

Confidence scale:
- 80-100%: Multi-year compounder with all boxes ticked
- 60-79%: Good growth story, most metrics positive
- 40-59%: Some growth but concerns remain
- 20-39%: Weak growth or fundamental issues
- 0-19%: Avoid — no growth, high debt, or poor sector dynamics

Keep reasoning under 150 characters. Do not invent data. Return ONLY valid JSON."""

JHUNJHUNWALA_HUMAN_TEMPLATE = """Ticker: {ticker}

Quantitative Facts:
{facts}

Return exactly this JSON format:
{{"signal": "bullish" or "bearish" or "neutral", "confidence": 0-100, "reasoning": "concise justification"}}"""


def _call_llm_for_signal(llm, system_prompt: str, human_message: str, agent_name: str) -> Dict[str, Any]:
    """Call LLM with system + human prompt and parse JSON response."""
    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_message),
    ]

    response = llm.invoke(messages)
    content = response.content if hasattr(response, "content") else str(response)

    logger.info(f"[{agent_name}] LLM raw response: {content[:200]}")

    # Parse JSON from response
    json_str = content.strip()
    if "```" in json_str:
        json_str = json_str.split("```")[1].strip()
        if json_str.startswith("json"):
            json_str = json_str[4:].strip()

    # Handle cases where LLM wraps in extra text
    if not json_str.startswith("{"):
        import re
        match = re.search(r'\{[^{}]*"signal"[^{}]*\}', json_str)
        if match:
            json_str = match.group(0)

    result = json.loads(json_str)
    signal = result.get("signal", "neutral")
    if signal not in ("bullish", "bearish", "neutral"):
        signal = "neutral"

    return {
        "signal": signal,
        "confidence": min(max(result.get("confidence", 50), 0), 100),
        "reasoning": str(result.get("reasoning", ""))[:150],
    }


def analyze_buffett(symbol: str, llm=None) -> Dict[str, Any]:
    """
    Run Warren Buffett analysis.
    With LLM: pre-compute facts → pass to LLM with Buffett persona prompt.
    Without LLM: pure quantitative scoring fallback.
    """
    logger.info(f"[BUFFETT] {symbol}: Fetching stock data...")

    try:
        info = _get_stock_data(symbol)
        if not info or not info.get("marketCap"):
            logger.warning(f"[BUFFETT] {symbol}: No data available")
            return {
                "signal": AnalystSignal(
                    signal="neutral", confidence=0,
                    reasoning=f"No data for {symbol}"
                )
            }

        facts = _compute_buffett_facts(info)
        logger.info(
            f"[BUFFETT] {symbol}: Facts computed - "
            f"Moat={'Strong' if facts['moat']['is_strong'] else 'Weak'} (ROE={facts['moat']['roe']}%, OpMargin={facts['moat']['operating_margin']}%), "
            f"D/E={facts['financial_strength']['debt_to_equity']}%, "
            f"MoS={facts['valuation']['margin_of_safety_pct']}%, "
            f"Score={facts['score']}/{facts['max_score']}"
        )

        # With LLM: use persona prompt
        if llm is not None:
            try:
                human_msg = BUFFETT_HUMAN_TEMPLATE.format(
                    ticker=symbol,
                    facts=json.dumps(facts, indent=2),
                )
                result = _call_llm_for_signal(llm, BUFFETT_SYSTEM_PROMPT, human_msg, "BUFFETT")
                logger.info(
                    f"[BUFFETT] {symbol}: LLM verdict - "
                    f"signal={result['signal']}, confidence={result['confidence']}%, "
                    f"reasoning={result['reasoning']}"
                )
                return {"signal": AnalystSignal(**result)}
            except Exception as e:
                logger.warning(f"[BUFFETT] {symbol}: LLM call failed ({e}), using quantitative fallback")

        # Quantitative fallback (no LLM)
        total = facts["score"]
        if total >= 5:
            signal = "bullish"
        elif total <= 2:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = (total / facts["max_score"]) * 100
        reasoning = (
            f"Buffett score {total}/{facts['max_score']}: "
            f"Moat={'Y' if facts['moat']['is_strong'] else 'N'}, "
            f"MoS={facts['valuation']['margin_of_safety_pct']}%"
        )
        return {"signal": AnalystSignal(signal=signal, confidence=confidence, reasoning=reasoning)}

    except Exception as e:
        logger.error(f"[BUFFETT] {symbol}: EXCEPTION - {e}")
        return {
            "signal": AnalystSignal(
                signal="neutral", confidence=0,
                reasoning=f"Error: {str(e)[:80]}"
            )
        }


def analyze_jhunjhunwala(symbol: str, llm=None) -> Dict[str, Any]:
    """
    Run Rakesh Jhunjhunwala analysis.
    With LLM: pre-compute facts → pass to LLM with Jhunjhunwala persona prompt.
    Without LLM: pure quantitative scoring fallback.
    """
    logger.info(f"[JHUNJHUNWALA] {symbol}: Fetching stock data...")

    try:
        info = _get_stock_data(symbol)
        if not info or not info.get("marketCap"):
            logger.warning(f"[JHUNJHUNWALA] {symbol}: No data available")
            return {
                "signal": AnalystSignal(
                    signal="neutral", confidence=0,
                    reasoning=f"No data for {symbol}"
                )
            }

        facts = _compute_jhunjhunwala_facts(info)
        logger.info(
            f"[JHUNJHUNWALA] {symbol}: Facts computed - "
            f"Growth(Rev={facts['growth']['revenue_growth_pct']}%, Earn={facts['growth']['earnings_growth_pct']}%), "
            f"ROE={facts['profitability']['roe_pct']}%, "
            f"D/E={facts['balance_sheet']['debt_to_equity']}%, "
            f"Score={facts['score']}/{facts['max_score']}"
        )

        # With LLM: use persona prompt
        if llm is not None:
            try:
                human_msg = JHUNJHUNWALA_HUMAN_TEMPLATE.format(
                    ticker=symbol,
                    facts=json.dumps(facts, indent=2),
                )
                result = _call_llm_for_signal(llm, JHUNJHUNWALA_SYSTEM_PROMPT, human_msg, "JHUNJHUNWALA")
                logger.info(
                    f"[JHUNJHUNWALA] {symbol}: LLM verdict - "
                    f"signal={result['signal']}, confidence={result['confidence']}%, "
                    f"reasoning={result['reasoning']}"
                )
                return {"signal": AnalystSignal(**result)}
            except Exception as e:
                logger.warning(f"[JHUNJHUNWALA] {symbol}: LLM call failed ({e}), using quantitative fallback")

        # Quantitative fallback (no LLM)
        total = facts["score"]
        if total >= 6:
            signal = "bullish"
        elif total <= 2:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = (total / facts["max_score"]) * 100
        reasoning = (
            f"Jhunjhunwala score {total}/{facts['max_score']}: "
            f"Growth={facts['growth']['revenue_growth_pct']}%, "
            f"ROE={facts['profitability']['roe_pct']}%"
        )
        return {"signal": AnalystSignal(signal=signal, confidence=confidence, reasoning=reasoning)}

    except Exception as e:
        logger.error(f"[JHUNJHUNWALA] {symbol}: EXCEPTION - {e}")
        return {
            "signal": AnalystSignal(
                signal="neutral", confidence=0,
                reasoning=f"Error: {str(e)[:80]}"
            )
        }
