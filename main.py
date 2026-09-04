"""Sequential stock research, runnable on any configured model provider."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from dotenv import load_dotenv

from core.console import safe_print
from core.llm import (
    copilot_client,
    run_copilot_prompt,
    validate_copilot_configuration,
)
from logging_config import agent_id_ctx, session_id_ctx, setup_logging
from prompts import (
    get_market_data_prompt,
    get_news_analyst_prompt,
    get_recommendation_prompt,
    get_stock_finder_prompt,
)

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

_DEFAULT_QUERY = (
    "Provide comprehensive stock analysis and trading recommendations for "
    "promising NSE-listed stocks suitable for short-term trading in the "
    "current market conditions."
)

_STAGE_TOOLS = {
    "stock_finder_agent": {
        "search_nse_stocks",
        "fetch_nse_declared_results",
        "fetch_nse_upcoming_results",
    },
    "market_data_agent": {
        "fetch_stock_price",
        "fetch_fundamentals",
        "fetch_technical_indicators",
        "fetch_financial_statements",
        "fetch_screener_fundamentals",
    },
    "news_analyst_agent": {"fetch_stock_news"},
    "recommendation_agent": set(),
}


class StockAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class NewsSentiment(Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


@dataclass
class StockRecommendation:
    symbol: str
    company_name: str
    current_price: float
    action: StockAction
    target_price: float
    confidence: str
    reasoning: str
    technical_indicators: Dict[str, Any]
    news_sentiment: NewsSentiment
    volume_analysis: str


@dataclass
class MarketData:
    symbol: str
    current_price: float
    previous_close: float
    volume: int
    price_change_pct: float
    rsi: Optional[float]
    moving_avg_50: Optional[float]
    moving_avg_200: Optional[float]
    trend_7d: str
    trend_30d: str


class StockResearchSystem:
    """Run discovery, data, news, and recommendation agents in sequence."""

    def __init__(self, bright_data_api_token: str | None = None) -> None:
        self.bright_data_api_token = bright_data_api_token
        self.use_free_scraper = os.getenv("USE_FREE_SCRAPER", "true").lower() == "true"
        self.client = None
        self.tools: list[Any] = []
        self.backend: str = ""
        """Resolved lazily; empty until :meth:`initialize` or first use."""

    def _resolve_backend(self) -> str:
        """Return the selected backend, detecting it once if needed.

        Detection is deferred rather than done in ``__init__`` so that merely
        constructing the system never inspects the environment or emits the
        one-time provider announcement.
        """
        if not self.backend:
            from core.agent.detect import detect_backend

            self.backend = detect_backend().backend
        return self.backend

    async def initialize(self) -> None:
        """Load read-only research tools and validate provider readiness."""
        if self._resolve_backend() == "copilot_cli":
            validate_copilot_configuration()
        if self.use_free_scraper:
            self.tools = self._get_free_tools()
        else:
            self.tools = await self._get_bright_data_tools()
        logger.info(
            "Sequential research initialized",
            extra={"tool_count": len(self.tools), "backend": self.backend},
        )

    def _get_free_tools(self) -> list[Any]:
        logger.info("Using free scraper tools")
        from scraper import get_all_scraper_tools

        return get_all_scraper_tools()

    async def _get_bright_data_tools(self) -> list[Any]:
        logger.info("Using Bright Data MCP tools")
        from langchain_mcp_adapters.client import MultiServerMCPClient

        self.client = MultiServerMCPClient(
            {
                "bright_data": {
                    "command": "npx",
                    "args": ["@brightdata/mcp"],
                    "env": {
                        "API_TOKEN": self.bright_data_api_token or "",
                        "WEB_UNLOCKER_ZONE": os.getenv(
                            "WEB_UNLOCKER_ZONE", "unblocker"
                        ),
                        "BROWSER_ZONE": os.getenv("BROWSER_ZONE", "scraping_browser"),
                    },
                    "transport": "stdio",
                }
            }
        )
        return await self.client.get_tools()

    def _tools_for_stage(self, stage_name: str) -> list[Any]:
        if not self.use_free_scraper:
            return self.tools
        allowed = _STAGE_TOOLS[stage_name]
        return [tool for tool in self.tools if getattr(tool, "name", "") in allowed]

    @staticmethod
    def _stage_prompt(
        *,
        stage_name: str,
        instructions: str,
        user_query: str,
        context: str,
        tools: list[Any],
    ) -> str:
        tool_names = ", ".join(getattr(tool, "name", str(tool)) for tool in tools)
        tool_guidance = (
            f"Available read-only research tools: {tool_names}."
            if tool_names
            else "No tools are available in this stage; use only the context."
        )
        return (
            f"{instructions}\n\n"
            f"You are the {stage_name} stage in a sequential stock-research "
            "workflow. Complete only this stage and return a self-contained "
            "markdown result for the next agent. Never invent market data.\n\n"
            f"{tool_guidance}\n\n"
            f"ORIGINAL USER REQUEST:\n{user_query}\n\n"
            f"PRIOR STAGE CONTEXT:\n{context or 'None'}"
        )

    async def _run_stage(
        self,
        *,
        client: Any,
        stage_name: str,
        instructions: str,
        user_query: str,
        context: str,
    ) -> str:
        agent_id_ctx.set(stage_name)
        backend = self._resolve_backend()
        tools = self._tools_for_stage(stage_name)
        logger.info("Starting sequential stage", extra={"backend": backend})
        prompt = self._stage_prompt(
            stage_name=stage_name,
            instructions=instructions,
            user_query=user_query,
            context=context,
            tools=tools,
        )

        if backend == "copilot_cli":
            output = await run_copilot_prompt(prompt, client=client, tools=tools)
        else:
            # Same in-process LangChain tools, driven by the shared tool loop.
            # `client` is the unbound chat model; the loop binds the tools.
            from core.agent.loop import run_tool_loop

            output = await run_tool_loop(model=client, tools=tools, prompt=prompt)

        logger.info("Completed sequential stage")
        return output

    @asynccontextmanager
    async def _stage_host(self) -> AsyncIterator[Any]:
        """Yield whatever the selected backend needs held open across stages.

        Copilot reuses one SDK client for all four stages; the native path has
        no session to keep alive, so it yields a chat model instead. Both are
        passed to ``_run_stage`` as ``client``.
        """
        if self._resolve_backend() == "copilot_cli":
            async with copilot_client() as client:
                yield client
            return

        from core.llm import get_llm

        yield get_llm()

    async def analyze_stocks(self, user_query: str | None = None) -> Dict[str, Any]:
        """Run the complete four-stage research workflow on any provider."""
        session_id = str(uuid.uuid4())
        session_id_ctx.set(session_id)
        agent_id_ctx.set("supervisor")
        query = user_query or _DEFAULT_QUERY

        if not self.tools:
            await self.initialize()

        stages = [
            ("stock_finder_agent", get_stock_finder_prompt()),
            ("market_data_agent", get_market_data_prompt()),
            ("news_analyst_agent", get_news_analyst_prompt()),
            ("recommendation_agent", get_recommendation_prompt()),
        ]
        messages: list[dict[str, str]] = []
        context_parts: list[str] = []

        async with self._stage_host() as client:
            for stage_name, instructions in stages:
                output = await self._run_stage(
                    client=client,
                    stage_name=stage_name,
                    instructions=instructions,
                    user_query=query,
                    context="\n\n".join(context_parts),
                )
                messages.append(
                    {
                        "role": "assistant",
                        "name": stage_name,
                        "content": output,
                    }
                )
                context_parts.append(
                    f"## {stage_name.replace('_', ' ').title()}\n{output}"
                )

        agent_id_ctx.set("supervisor")
        return {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "messages": messages,
            "raw_output": messages,
        }

    @staticmethod
    def format_results_for_display(results: Dict[str, Any]) -> str:
        """Return the final recommendation-stage response."""
        messages = results.get("messages") or []
        if not messages:
            return "No analysis results available."
        final_message = messages[-1]
        if isinstance(final_message, dict):
            return str(final_message.get("content") or "")
        return str(getattr(final_message, "content", final_message))


def pretty_print_message(message: Any, indent: bool = False) -> str:
    """Pretty print a single message."""
    if hasattr(message, "pretty_repr"):
        rendered = message.pretty_repr(html=True)
    elif isinstance(message, dict):
        rendered = str(message.get("content", message))
    else:
        rendered = str(message)
    if indent:
        return "\n".join("\t" + line for line in rendered.splitlines())
    return rendered


def extract_recommendations(
    final_messages: List[Any],
) -> List[Dict[str, Any]]:
    """Extract basic recommendation fields from agent markdown."""
    recommendations: list[dict[str, Any]] = []
    for message in final_messages:
        if hasattr(message, "content"):
            content = str(message.content)
        elif isinstance(message, dict):
            content = str(message.get("content", ""))
        else:
            content = ""

        if "RECOMMENDATION:" not in content or "TARGET PRICE:" not in content:
            continue

        recommendation: dict[str, Any] = {}
        for line in content.splitlines():
            if "STOCK_SYMBOL" in line or "Symbol:" in line:
                recommendation["symbol"] = line.split(":")[-1].strip()
            elif "RECOMMENDATION:" in line:
                recommendation["action"] = line.split(":")[-1].strip()
            elif "TARGET PRICE:" in line:
                value = line.split(":")[-1].strip().replace("₹", "")
                try:
                    recommendation["target_price"] = float(value)
                except ValueError:
                    recommendation["target_price"] = value
            elif "Current Price:" in line:
                value = line.split(":")[-1].strip().replace("₹", "")
                try:
                    recommendation["current_price"] = float(value)
                except ValueError:
                    recommendation["current_price"] = value

        if recommendation:
            recommendations.append(recommendation)
    return recommendations


if __name__ == "__main__":
    research_system = StockResearchSystem(os.getenv("BRIGHT_DATA_API_TOKEN"))
    analysis = asyncio.run(research_system.analyze_stocks())
    safe_print(research_system.format_results_for_display(analysis))
