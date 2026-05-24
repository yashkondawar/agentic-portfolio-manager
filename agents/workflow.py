"""
Parallel Multi-Analyst Workflow — orchestrates all agents.

Uses concurrent execution (ThreadPoolExecutor) for analyst fan-out.
No LangGraph dependency — keeps it simple and robust.

Flow:
1. Parse tickers from user query
2. Fan-out: Run all 6 analysts in parallel per ticker
3. Fan-in: Collect all AnalystSignals
4. Risk Manager: Compute position limits
5. Portfolio Manager: Synthesize final BUY/SELL/HOLD decisions
6. Format output report
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional

from agents.models import AnalystSignal, StockAnalysis, PortfolioDecision
from agents.technical_analyst import analyze_technical
from agents.fundamentals_analyst import analyze_fundamentals
from agents.valuation_analyst import analyze_valuation
from agents.sentiment_analyst import analyze_sentiment
from agents.investor_agents import analyze_buffett, analyze_jhunjhunwala
from agents.risk_manager import analyze_risk
from agents.portfolio_manager import make_portfolio_decisions

logger = logging.getLogger(__name__)


def _get_current_price(symbol: str) -> float:
    """Fetch current price via the unified data provider."""
    from scraper.data_provider import get_stock_data

    try:
        data = get_stock_data(symbol)
        price = data.current_price or 0
        logger.info(f"[PRICE] {symbol}: ₹{float(price):,.2f}")
        return float(price)
    except Exception as e:
        logger.warning(f"[PRICE] {symbol}: FAILED - {e}")
        return 0.0


def _run_analyst(analyst_func, symbol: str, analyst_name: str) -> tuple:
    """Run a single analyst and return (name, AnalystSignal)."""
    import time as _time
    start = _time.time()
    try:
        result = analyst_func(symbol)
        elapsed = _time.time() - start

        if isinstance(result, AnalystSignal):
            signal = result
        elif isinstance(result, dict):
            sig = result.get("signal")
            if isinstance(sig, AnalystSignal):
                signal = sig
            else:
                signal = AnalystSignal(
                    signal=sig if sig in ("bullish", "bearish", "neutral") else "neutral",
                    confidence=result.get("confidence", 50),
                    reasoning=str(result.get("reasoning", "No reasoning"))[:200],
                )
        else:
            signal = AnalystSignal(signal="neutral", confidence=0, reasoning="Invalid result format")

        status = "PASS" if signal.confidence > 0 else "FAIL (zero confidence)"
        logger.info(
            f"[AGENT] {analyst_name:15s} | {symbol:10s} | {status} | "
            f"signal={signal.signal:7s} | confidence={signal.confidence:5.1f}% | "
            f"time={elapsed:.1f}s | reason={signal.reasoning[:80]}"
        )
        return analyst_name, signal

    except Exception as e:
        elapsed = _time.time() - start
        logger.error(
            f"[AGENT] {analyst_name:15s} | {symbol:10s} | EXCEPTION | "
            f"time={elapsed:.1f}s | error={str(e)[:100]}"
        )
        return analyst_name, AnalystSignal(
            signal="neutral", confidence=0, reasoning=f"Error: {str(e)[:100]}"
        )


def run_parallel_analysis(
    symbols: List[str],
    llm=None,
    portfolio_value: float = 1000000.0,
) -> Dict[str, StockAnalysis]:
    """
    Run the full parallel multi-analyst pipeline.

    Args:
        symbols: List of NSE stock symbols (e.g., ["RELIANCE", "TCS"])
        llm: Optional LLM for portfolio manager enhanced reasoning
        portfolio_value: Total portfolio value in ₹ (default ₹10L)

    Returns:
        Dict[symbol → StockAnalysis] with complete analysis
    """
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(f"[WORKFLOW] Starting parallel analysis for {symbols}")
    logger.info(f"[WORKFLOW] Portfolio value: ₹{portfolio_value:,.0f} | LLM: {'Yes' if llm else 'No (quantitative only)'}")
    logger.info("=" * 80)

    # Define all analyst functions
    # Pure math agents (no LLM needed)
    math_analysts = [
        (analyze_technical, "technical"),
        (analyze_fundamentals, "fundamentals"),
        (analyze_valuation, "valuation"),
        (analyze_sentiment, "sentiment"),
    ]

    # LLM-powered persona agents (use LLM if available, fallback to quant)
    def _buffett_with_llm(symbol):
        return analyze_buffett(symbol, llm=llm)

    def _jhunjhunwala_with_llm(symbol):
        return analyze_jhunjhunwala(symbol, llm=llm)

    persona_analysts = [
        (_buffett_with_llm, "buffett"),
        (_jhunjhunwala_with_llm, "jhunjhunwala"),
    ]

    analysts = math_analysts + persona_analysts

    # Step 1: Fan-out — run all analysts for all tickers in parallel
    logger.info(f"[STEP 1] Fan-out: Running {len(analysts)} analysts x {len(symbols)} stocks = {len(analysts)*len(symbols)} tasks")
    all_signals: Dict[str, Dict[str, AnalystSignal]] = {s: {} for s in symbols}
    current_prices: Dict[str, float] = {}

    with ThreadPoolExecutor(max_workers=12) as executor:
        # Submit all analyst tasks
        futures = {}
        for symbol in symbols:
            for analyst_func, analyst_name in analysts:
                future = executor.submit(_run_analyst, analyst_func, symbol, analyst_name)
                futures[future] = (symbol, analyst_name)

            # Also fetch current prices in parallel
            price_future = executor.submit(_get_current_price, symbol)
            futures[price_future] = (symbol, "__price__")

        # Collect results
        for future in as_completed(futures):
            symbol, name = futures[future]
            try:
                if name == "__price__":
                    current_prices[symbol] = future.result()
                else:
                    agent_name, signal = future.result()
                    all_signals[symbol][agent_name] = signal
            except Exception as e:
                logger.error(f"[STEP 1] Future failed for {symbol}/{name}: {e}")

    # Log signal summary per stock
    logger.info("-" * 80)
    logger.info("[STEP 1] SIGNAL SUMMARY:")
    for symbol in symbols:
        signals = all_signals[symbol]
        passed = sum(1 for s in signals.values() if s.confidence > 0)
        failed = len(signals) - passed
        bullish = sum(1 for s in signals.values() if s.signal == "bullish" and s.confidence > 0)
        bearish = sum(1 for s in signals.values() if s.signal == "bearish" and s.confidence > 0)
        neutral = passed - bullish - bearish
        logger.info(
            f"  {symbol:10s}: {passed}/{len(signals)} agents passed | "
            f"Bullish={bullish} Bearish={bearish} Neutral={neutral} | "
            f"Price=₹{current_prices.get(symbol, 0):,.2f}"
        )
    logger.info("-" * 80)

    # Step 2: Risk analysis
    logger.info(f"[STEP 2] Risk Manager: Computing position limits for {symbols}")
    risk_metrics = analyze_risk(symbols, portfolio_value)
    for symbol, rm in risk_metrics.items():
        logger.info(
            f"[RISK] {symbol:10s}: Vol={rm.annualized_volatility:.1%} | "
            f"Max position={rm.max_position_pct:.1f}% (₹{rm.max_position_value:,.0f}) | "
            f"{rm.reasoning}"
        )

    # Step 3: Portfolio decisions
    logger.info(f"[STEP 3] Portfolio Manager: Synthesizing signals into decisions")
    decisions = make_portfolio_decisions(
        all_signals=all_signals,
        risk_metrics=risk_metrics,
        current_prices=current_prices,
        llm=llm,
    )

    # Log final decisions
    logger.info("=" * 80)
    logger.info("[FINAL DECISIONS]")
    for symbol, dec in decisions.items():
        target_str = f"Target=₹{dec.target_price:,.2f}" if dec.target_price else "Target=N/A"
        sl_str = f"SL=₹{dec.stop_loss:,.2f}" if dec.stop_loss else "SL=N/A"
        logger.info(
            f"  {symbol:10s}: {dec.action:4s} | Confidence={dec.confidence:.0f}% | "
            f"{target_str} | {sl_str} | {dec.reasoning}"
        )
    logger.info("=" * 80)

    # Step 4: Assemble final results
    results = {}
    for symbol in symbols:
        results[symbol] = StockAnalysis(
            symbol=symbol,
            current_price=current_prices.get(symbol),
            analyst_signals=all_signals.get(symbol, {}),
            risk_metrics=risk_metrics.get(symbol),
            final_decision=decisions.get(symbol),
        )

    elapsed = time.time() - start_time
    logger.info(f"[WORKFLOW] Completed in {elapsed:.1f}s for {len(symbols)} stocks")

    return results


def format_analysis_report(results: Dict[str, StockAnalysis]) -> str:
    """
    Format the analysis results into a readable markdown report.
    This is what gets shown to the user.
    """
    lines = []
    lines.append("# 📊 Multi-Analyst Stock Analysis Report\n")

    for symbol, analysis in results.items():
        lines.append(f"## {symbol}")

        if analysis.current_price:
            lines.append(f"**Current Price:** ₹{analysis.current_price:,.2f}\n")

        # Final Decision
        if analysis.final_decision:
            dec = analysis.final_decision
            emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(dec.action, "⚪")
            lines.append(f"### {emoji} Decision: **{dec.action}** (Confidence: {dec.confidence:.0f}%)")
            lines.append(f"- **Reasoning:** {dec.reasoning}")
            if dec.entry_price:
                lines.append(f"- **Entry:** ₹{dec.entry_price:,.2f}")
            if dec.target_price:
                lines.append(f"- **Target:** ₹{dec.target_price:,.2f}")
            if dec.stop_loss:
                lines.append(f"- **Stop Loss:** ₹{dec.stop_loss:,.2f}")
            if dec.position_size_pct:
                lines.append(f"- **Position Size:** {dec.position_size_pct:.1f}% of portfolio")
            lines.append(f"- **Time Horizon:** {dec.time_horizon}")
            lines.append("")

        # Analyst Signals
        lines.append("### Analyst Signals")
        lines.append("| Agent | Signal | Confidence | Key Reasoning |")
        lines.append("|-------|--------|-----------|---------------|")

        for agent_name, signal in analysis.analyst_signals.items():
            emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(signal.signal, "⚪")
            reasoning_short = signal.reasoning[:80] + "..." if len(signal.reasoning) > 80 else signal.reasoning
            lines.append(f"| {agent_name.title()} | {emoji} {signal.signal} | {signal.confidence:.0f}% | {reasoning_short} |")

        lines.append("")

        # Risk Metrics
        if analysis.risk_metrics:
            rm = analysis.risk_metrics
            lines.append("### Risk Assessment")
            lines.append(f"- **Annualized Volatility:** {rm.annualized_volatility:.1%}")
            lines.append(f"- **Max Position:** {rm.max_position_pct:.1f}% (₹{rm.max_position_value:,.0f})")
            lines.append(f"- **Note:** {rm.reasoning}")
            lines.append("")

        lines.append("---\n")

    # Summary table
    lines.append("## Summary")
    lines.append("| Stock | Action | Confidence | Target | Stop Loss |")
    lines.append("|-------|--------|-----------|--------|-----------|")
    for symbol, analysis in results.items():
        if analysis.final_decision:
            dec = analysis.final_decision
            target = f"₹{dec.target_price:,.2f}" if dec.target_price else "N/A"
            sl = f"₹{dec.stop_loss:,.2f}" if dec.stop_loss else "N/A"
            lines.append(f"| {symbol} | {dec.action} | {dec.confidence:.0f}% | {target} | {sl} |")

    return "\n".join(lines)


def create_parallel_workflow(llm=None, portfolio_value: float = 1000000.0):
    """
    Factory function that returns a callable workflow.
    Compatible interface for integration with main.py.
    """

    def workflow(symbols: List[str]) -> str:
        results = run_parallel_analysis(symbols, llm=llm, portfolio_value=portfolio_value)
        return format_analysis_report(results)

    return workflow
