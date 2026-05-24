# stock_research_system_free.py
"""
Stock Research System using free data sources (no Bright Data required).
Uses yfinance + screener.in scraping + ta library for technical analysis.
"""

import os
import uuid
import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime

from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langgraph_supervisor import create_supervisor

from logging_config import setup_logging, session_id_ctx, agent_id_ctx
from prompts import (
    get_supervisor_prompt,
    get_stock_finder_prompt,
    get_market_data_prompt,
    get_news_analyst_prompt,
    get_recommendation_prompt,
)
from scraper import get_all_scraper_tools


load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)


class StockResearchSystemFree:
    """
    Stock research system using free data sources.
    Replaces Bright Data MCP with:
    - yfinance for prices, fundamentals, news
    - screener.in scraping for deep Indian market data
    - ta library for technical indicators
    """

    def __init__(self):
        self.supervisor = None

    async def initialize(self):
        """Initialize the agent system with free scraper tools."""
        logger.info("Initializing StockResearchSystemFree (no paid APIs)")

        # Get all scraper tools (LangChain tools wrapping our free scrapers)
        tools = get_all_scraper_tools()
        logger.info(f"Loaded {len(tools)} free scraper tools")

        # Initialize LLM
        model = ChatGroq(
            model=os.getenv("MODEL_NAME", "llama-3.3-70b-versatile"),
            api_key=os.getenv("GROQ_API_KEY"),
        )

        # Load prompts
        stock_finder_prompt = get_stock_finder_prompt()
        market_data_prompt = get_market_data_prompt()
        news_analyst_prompt = get_news_analyst_prompt()
        recommendation_prompt = get_recommendation_prompt()
        supervisor_prompt = get_supervisor_prompt()

        # Tool availability note appended to each agent's prompt
        tools_note = self._get_tools_note(tools)

        # Create specialized agents
        logger.info("Creating agents with free scraper tools")

        stock_finder_agent = create_react_agent(
            model,
            tools,
            prompt=stock_finder_prompt + tools_note,
            name="stock_finder_agent",
        )

        market_data_agent = create_react_agent(
            model,
            tools,
            prompt=market_data_prompt + tools_note,
            name="market_data_agent",
        )

        news_analyst_agent = create_react_agent(
            model,
            tools,
            prompt=news_analyst_prompt + tools_note,
            name="news_analyst_agent",
        )

        recommendation_agent = create_react_agent(
            model,
            tools,
            prompt=recommendation_prompt + tools_note,
            name="recommendation_agent",
        )

        # Create supervisor
        self.supervisor = create_supervisor(
            model=ChatGroq(
                model=os.getenv("MODEL_NAME", "llama-3.3-70b-versatile"),
                api_key=os.getenv("GROQ_API_KEY"),
            ),
            agents=[
                stock_finder_agent,
                market_data_agent,
                news_analyst_agent,
                recommendation_agent,
            ],
            prompt=supervisor_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        ).compile()

        logger.info("StockResearchSystemFree initialized ✅")

    def _get_tools_note(self, tools) -> str:
        """Generate a note about available tools for agent prompts."""
        tool_names = [t.name for t in tools]
        tool_list = "\n".join(f"  {i+1}. {name}" for i, name in enumerate(tool_names))

        return f"""

================================================================================
🔧 AVAILABLE TOOLS (FREE - No API Key Required)
================================================================================
{tool_list}

⚠️ TOOL USAGE RULES:
1. Use ONLY the exact tool names listed above
2. All tools accept an NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK, INFY)
3. DO NOT invent or guess tool names
4. For stock discovery, use search_nse_stocks with a query
5. For prices, use fetch_stock_price
6. For technical analysis, use fetch_technical_indicators
7. For fundamentals, use fetch_fundamentals or fetch_screener_fundamentals (more detailed)
8. For news, use fetch_stock_news
9. For financial statements, use fetch_financial_statements
================================================================================
"""

    async def analyze_stocks(self, user_query: str = None) -> Dict[str, Any]:
        """Run the complete stock analysis workflow."""
        session_id = str(uuid.uuid4())
        session_id_ctx.set(session_id)
        agent_id_ctx.set("supervisor")

        logger.info("Starting stock analysis session (free mode)")

        if not self.supervisor:
            await self.initialize()

        if not user_query:
            user_query = (
                "Provide comprehensive stock analysis and trading recommendations "
                "for promising NSE-listed stocks suitable for short-term trading "
                "in the current market conditions."
            )

        try:
            logger.info("Starting supervisor execution")
            all_messages = []

            async for chunk in self.supervisor.astream(
                {"messages": [{"role": "user", "content": user_query}]}
            ):
                all_messages.append(chunk)

            logger.info(
                "Supervisor execution completed ✅",
                extra={"total_chunks": len(all_messages)},
            )
        except Exception:
            logger.exception("Stock analysis failed")
            raise

        final_chunk = all_messages[-1] if all_messages else {}
        final_messages = final_chunk.get("supervisor", {}).get("messages", [])

        logger.info(
            "Stock analysis completed ✅",
            extra={"message_count": len(final_messages)},
        )

        return {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "messages": final_messages,
            "raw_output": all_messages,
        }

    def format_results_for_display(self, results: Dict[str, Any]) -> str:
        """Format the analysis results for display."""
        if not results.get("messages"):
            return "No analysis results available."

        final_messages = results["messages"]
        if not final_messages:
            return "Analysis completed but no recommendations generated."

        for message in reversed(final_messages):
            if hasattr(message, "content") and message.content:
                return str(message.content)
            elif isinstance(message, dict) and message.get("content"):
                return str(message["content"])

        return "Analysis completed. Please check the detailed output."


if __name__ == "__main__":
    system = StockResearchSystemFree()
    results = asyncio.run(system.analyze_stocks())

    print("*" * 80)
    print("STOCK ANALYSIS RESULTS (Free Mode)")
    print("*" * 80)
    print(system.format_results_for_display(results))
