"""
Portfolio Manager Agent — Final decision maker.

Inspired by virattt/ai-hedge-fund architecture:
1. Pre-compute quantitative signal summary (deterministic)
2. Pass compressed signals + risk limits to LLM
3. LLM picks BUY/SELL/HOLD with entry, target, stop-loss
4. Fallback: quantitative weighted voting if no LLM

The LLM prompt is deliberately minimal — all heavy computation is done before the call.
"""

import json
import logging
from typing import Dict, Any, List, Optional

from agents.models import AnalystSignal, PortfolioDecision, RiskMetrics
from core.model_output import extract_json_object

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO MANAGER PROMPT — inspired by ai-hedge-fund
# ══════════════════════════════════════════════════════════════════════════════

PORTFOLIO_MANAGER_SYSTEM_PROMPT = """You are a senior portfolio manager making trading decisions for Indian NSE stocks.

Your role: Synthesize analyst signals into a final BUY, SELL, or HOLD verdict per stock.

Decision framework:
1. Weight signals by confidence — a 90% confidence bearish from valuation matters more than 30% neutral from sentiment
2. Look for consensus — if 4+ agents agree on direction, follow them
3. If signals conflict strongly, default to HOLD (protect capital)
4. For BUY: Set realistic target (5-10% upside) and stop-loss (3-5% downside)
5. For SELL: Means "avoid buying" or "exit if holding" — set downside target and upside stop
6. For HOLD: No strong conviction either way — wait for clearer signals

Constraints:
- NSE Indian market — NO short selling in cash segment
- Position size must NOT exceed the risk manager's limit
- Be decisive — avoid HOLD when evidence is clearly directional

Return ONLY valid JSON. No explanation outside the JSON."""

PORTFOLIO_MANAGER_HUMAN_TEMPLATE = """ANALYST SIGNALS per stock (each agent analyzed independently):
{signals}

RISK LIMITS (max position size per stock):
{risk_limits}

CURRENT PRICES:
{prices}

For each stock, return your decision in this exact JSON format:
{{
  "decisions": {{
    "TICKER": {{
      "action": "BUY" or "SELL" or "HOLD",
      "confidence": 0-100,
      "entry_price": number or null,
      "target_price": number or null,
      "stop_loss": number or null,
      "position_size_pct": number,
      "reasoning": "max 150 chars explaining WHY",
      "time_horizon": "1-3 days" or "3-7 days" or "1-2 weeks"
    }}
  }}
}}"""


def _quantitative_decision(
    signals: Dict[str, AnalystSignal],
    risk: RiskMetrics,
    current_price: float,
) -> PortfolioDecision:
    """
    Quantitative fallback when no LLM is available.
    Confidence-weighted voting with directional bias.
    """
    if not signals:
        return PortfolioDecision(
            action="HOLD", confidence=0,
            reasoning="No analyst signals available",
            time_horizon="N/A"
        )

    signal_values = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}

    # Filter out failed agents (confidence=0)
    valid_signals = {k: v for k, v in signals.items() if v.confidence > 0}

    if not valid_signals:
        return PortfolioDecision(
            action="HOLD", confidence=0,
            reasoning="All agents failed or returned zero confidence",
            time_horizon="N/A"
        )

    # Confidence-weighted directional score
    weighted_sum = 0
    total_confidence = 0
    for agent_name, signal in valid_signals.items():
        value = signal_values.get(signal.signal, 0)
        weighted_sum += value * signal.confidence
        total_confidence += signal.confidence

    net_score = weighted_sum / total_confidence if total_confidence > 0 else 0

    # Directional vote counting
    bullish_agents = [(n, s) for n, s in valid_signals.items() if s.signal == "bullish"]
    bearish_agents = [(n, s) for n, s in valid_signals.items() if s.signal == "bearish"]

    bullish_weight = sum(s.confidence for _, s in bullish_agents)
    bearish_weight = sum(s.confidence for _, s in bearish_agents)
    total_directional = bullish_weight + bearish_weight

    if total_directional > 0:
        directional_score = (bullish_weight - bearish_weight) / total_directional
    else:
        directional_score = 0

    # Use the more decisive of the two scores
    final_score = net_score if abs(net_score) > abs(directional_score) else directional_score

    # Decision thresholds
    if final_score > 0.15:
        action = "BUY"
        target_price = round(current_price * 1.07, 2)
        stop_loss = round(current_price * 0.96, 2)
        position_pct = min(risk.max_position_pct, 15.0)
    elif final_score < -0.15:
        action = "SELL"
        target_price = round(current_price * 0.93, 2)
        stop_loss = round(current_price * 1.04, 2)
        position_pct = 0
    else:
        action = "HOLD"
        target_price = None
        stop_loss = None
        position_pct = 0

    confidence = min(abs(final_score) * 130, 95)

    reasoning = (
        f"Score={final_score:.2f}. "
        f"Bullish: {len(bullish_agents)}/{len(valid_signals)} (wt={bullish_weight:.0f}). "
        f"Bearish: {len(bearish_agents)}/{len(valid_signals)} (wt={bearish_weight:.0f})."
    )

    return PortfolioDecision(
        action=action,
        confidence=confidence,
        entry_price=current_price if action == "BUY" else None,
        target_price=target_price,
        stop_loss=stop_loss,
        position_size_pct=position_pct,
        reasoning=reasoning[:150],
        time_horizon="3-7 days",
    )


def make_portfolio_decisions(
    all_signals: Dict[str, Dict[str, AnalystSignal]],
    risk_metrics: Dict[str, RiskMetrics],
    current_prices: Dict[str, float],
    llm=None,
) -> Dict[str, PortfolioDecision]:
    """
    Make final BUY/SELL/HOLD decisions for all tickers.

    With LLM: Passes compressed signals to LLM for intelligent synthesis.
    Without LLM: Uses quantitative weighted voting.
    """
    logger.info(f"[PORTFOLIO_MGR] Making decisions for {list(all_signals.keys())} | LLM={'Yes' if llm else 'No'}")

    # Always compute quantitative decisions as fallback
    quant_decisions = {}
    for ticker, signals in all_signals.items():
        price = current_prices.get(ticker, 0)
        risk = risk_metrics.get(ticker)
        if not risk:
            risk = RiskMetrics(
                daily_volatility=0.02, annualized_volatility=0.30,
                volatility_percentile=50, max_position_pct=15,
                max_position_value=150000, reasoning="default"
            )
        quant_decisions[ticker] = _quantitative_decision(signals, risk, price)

    # If no LLM, return quantitative decisions
    if llm is None:
        for ticker, dec in quant_decisions.items():
            logger.info(
                f"[PORTFOLIO_MGR] {ticker}: {dec.action} (quant, conf={dec.confidence:.0f}%) | {dec.reasoning}"
            )
        return quant_decisions

    # With LLM: build compressed signal prompt
    try:
        # Compress signals — only include agents with confidence > 0
        signals_for_prompt = {}
        for ticker, signals in all_signals.items():
            signals_for_prompt[ticker] = {}
            for agent, s in signals.items():
                if s.confidence > 0:
                    signals_for_prompt[ticker][agent] = {
                        "signal": s.signal,
                        "confidence": round(s.confidence),
                        "reasoning": s.reasoning[:80],
                    }

        risk_for_prompt = {
            ticker: {
                "max_position_pct": r.max_position_pct,
                "volatility": f"{r.annualized_volatility:.0%}",
            }
            for ticker, r in risk_metrics.items()
        }

        prices_for_prompt = {t: f"₹{p:,.2f}" for t, p in current_prices.items()}

        from langchain_core.messages import SystemMessage, HumanMessage

        human_msg = PORTFOLIO_MANAGER_HUMAN_TEMPLATE.format(
            signals=json.dumps(signals_for_prompt, indent=2),
            risk_limits=json.dumps(risk_for_prompt, indent=2),
            prices=json.dumps(prices_for_prompt, indent=2),
        )

        messages = [
            SystemMessage(content=PORTFOLIO_MANAGER_SYSTEM_PROMPT),
            HumanMessage(content=human_msg),
        ]

        logger.info(f"[PORTFOLIO_MGR] Calling LLM for final synthesis...")
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        logger.info(f"[PORTFOLIO_MGR] LLM response: {content[:300]}")

        result = extract_json_object(content, must_contain="decisions")
        decisions_raw = result.get("decisions", result)

        decisions = {}
        for ticker, dec in decisions_raw.items():
            ticker_upper = ticker.upper()
            action = dec.get("action", "HOLD").upper()
            if action not in ("BUY", "SELL", "HOLD"):
                action = "HOLD"

            decisions[ticker_upper] = PortfolioDecision(
                action=action,
                confidence=min(max(dec.get("confidence", 50), 0), 100),
                entry_price=dec.get("entry_price"),
                target_price=dec.get("target_price"),
                stop_loss=dec.get("stop_loss"),
                position_size_pct=dec.get("position_size_pct"),
                reasoning=str(dec.get("reasoning", "LLM decision"))[:150],
                time_horizon=dec.get("time_horizon", "3-7 days"),
            )
            logger.info(
                f"[PORTFOLIO_MGR] {ticker_upper}: {action} (LLM, conf={decisions[ticker_upper].confidence}%) | "
                f"{decisions[ticker_upper].reasoning}"
            )

        # Fill in any missing tickers with quantitative fallback
        for ticker in all_signals.keys():
            if ticker not in decisions:
                decisions[ticker] = quant_decisions[ticker]
                logger.warning(f"[PORTFOLIO_MGR] {ticker}: Using quant fallback (not in LLM response)")

        return decisions

    except Exception as e:
        logger.warning(f"[PORTFOLIO_MGR] LLM synthesis failed ({e}), using quantitative decisions")
        for ticker, dec in quant_decisions.items():
            logger.info(f"[PORTFOLIO_MGR] {ticker}: {dec.action} (quant fallback) | {dec.reasoning}")
        return quant_decisions
