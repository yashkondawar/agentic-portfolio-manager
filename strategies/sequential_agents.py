"""Sequential multi-agent research strategy powered by GitHub Copilot SDK."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List

from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)

_DEFAULT_QUERY = (
    "Provide comprehensive stock analysis and trading recommendations for "
    "promising NSE-listed stocks suitable for short-term trading in the "
    "current market conditions."
)


@register
class SequentialAgentsStrategy(BaseStrategy):
    id = "sequential_agents"
    name = "Sequential Agent System"
    description = (
        "Copilot SDK agents that run in sequence "
        "(stock finder -> market data -> news -> recommendation)."
    )
    long_description = (
        "Uses authenticated GitHub Copilot SDK sessions with Claude Opus 4.7 "
        "by default. Specialized agents run one after another and synthesize "
        "their outputs into BUY/SELL/HOLD recommendations. Works with the "
        "free scraper tools by default, or Bright Data MCP when configured."
    )
    category = StrategyCategory.RESEARCH

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                name="query",
                label="Analysis request",
                type=ParamType.TEXT,
                required=False,
                default=_DEFAULT_QUERY,
                help="Free-form instruction describing what to analyze.",
            ),
            ParamSpec(
                name="use_free_scraper",
                label="Use free scraper (no Bright Data)",
                type=ParamType.BOOL,
                required=False,
                default=True,
                help="Prefer free yfinance/screener.in tools over paid Bright Data.",
                group="Data",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        from core.llm import validate_copilot_configuration

        validate_copilot_configuration()

        from main import StockResearchSystem, extract_recommendations

        # Honour the toggle by setting the env var the system reads on init.
        os.environ["USE_FREE_SCRAPER"] = (
            "true" if params.get("use_free_scraper", True) else "false"
        )

        query = params.get("query") or _DEFAULT_QUERY
        system = StockResearchSystem(
            bright_data_api_token=os.getenv("BRIGHT_DATA_API_TOKEN"),
        )

        results = asyncio.run(system.analyze_stocks(query))
        report = system.format_results_for_display(results)

        try:
            recommendations = extract_recommendations(results.get("messages", []))
        except Exception:
            recommendations = []

        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=report,
            data={
                "recommendations": recommendations,
                "timestamp": results.get("timestamp"),
            },
        )
