"""Parallel multi-analyst research strategy.

Wraps ``agents.workflow.run_parallel_analysis``: fan-out of six analysts
(technical, fundamentals, valuation, sentiment, Buffett, Jhunjhunwala) run
concurrently per ticker, then fan-in through the risk manager and portfolio
manager into final BUY/SELL/HOLD decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.config import DEFAULT_PORTFOLIO_VALUE
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


@register
class ParallelAgentsStrategy(BaseStrategy):
    id = "parallel_agents"
    name = "Parallel Agent System"
    description = (
        "Six analysts run concurrently per stock, then risk + portfolio "
        "managers synthesize final decisions."
    )
    long_description = (
        "A ThreadPoolExecutor fan-out runs technical, fundamentals, "
        "valuation, sentiment, Buffett and Jhunjhunwala analysts in parallel "
        "for each ticker. Signals are aggregated by a risk manager (position "
        "sizing) and a portfolio manager into BUY/SELL/HOLD calls with "
        "targets and stop losses. GitHub Copilot SDK with Claude Opus 4.7 "
        "provides persona and portfolio reasoning by default."
    )
    category = StrategyCategory.RESEARCH

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                name="symbols",
                label="NSE symbols",
                type=ParamType.SYMBOLS,
                required=True,
                help="Comma/space separated tickers, e.g. RELIANCE, TCS, INFY.",
            ),
            ParamSpec(
                name="portfolio_value",
                label="Portfolio value (₹)",
                type=ParamType.FLOAT,
                required=False,
                default=DEFAULT_PORTFOLIO_VALUE,
                help="Total capital used for position-sizing.",
                min=1,
                group="Capital & risk",
            ),
            ParamSpec(
                name="use_llm",
                label="Use GitHub Copilot for persona agents",
                type=ParamType.BOOL,
                required=False,
                default=True,
                help=(
                    "Use Copilot SDK reasoning for Buffett/Jhunjhunwala and "
                    "the portfolio manager. Disable for quantitative-only mode."
                ),
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        from agents.workflow import run_parallel_analysis, format_analysis_report

        symbols: List[str] = params.get("symbols") or []
        if not symbols:
            raise ValueError("At least one symbol is required.")

        portfolio_value = float(params.get("portfolio_value", DEFAULT_PORTFOLIO_VALUE))

        llm = None
        if params.get("use_llm"):
            from core.llm import get_llm

            llm = get_llm()

        results = run_parallel_analysis(
            symbols, llm=llm, portfolio_value=portfolio_value
        )
        report = format_analysis_report(results)

        decisions = {
            symbol: {
                "action": a.final_decision.action if a.final_decision else None,
                "confidence": a.final_decision.confidence if a.final_decision else None,
                "current_price": a.current_price,
                "entry_price": (
                    a.final_decision.entry_price if a.final_decision else None
                ),
                "target_price": (
                    a.final_decision.target_price if a.final_decision else None
                ),
                "stop_loss": a.final_decision.stop_loss if a.final_decision else None,
                "position_size_pct": (
                    a.final_decision.position_size_pct if a.final_decision else None
                ),
                "time_horizon": (
                    a.final_decision.time_horizon if a.final_decision else None
                ),
                "reasoning": (a.final_decision.reasoning if a.final_decision else None),
            }
            for symbol, a in results.items()
        }

        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=report,
            data={"symbols": symbols, "decisions": decisions},
        )
