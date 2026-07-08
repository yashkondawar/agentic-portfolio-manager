"""
MCP Server for Indian Stock Market Data (Free Alternative to Bright Data).

This MCP server provides the same functionality as Bright Data MCP but uses
free data sources (yfinance, screener.in, ta library).

Run as: python mcp_server.py
Configure in main.py as a local MCP server (stdio transport).
"""

import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from scraper.market_data import (
    get_stock_price,
    get_fundamentals,
    get_technical_indicators,
    get_stock_news,
    get_financial_statements,
)
from scraper.screener import scrape_fundamentals, _rate_limited_get
from scraper.nse_events import (
    recent_declared_results,
    upcoming_result_declarations,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

# Create MCP server
server = Server("indian-stock-data")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="fetch_stock_price",
            description=(
                "Get real-time stock price and market data for an NSE-listed stock. "
                "Returns: current price, open, day high/low, volume, 52-week range, "
                "market cap, P/E ratio, price change amount and percentage."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK, INFY)",
                    }
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="fetch_fundamentals",
            description=(
                "Get fundamental analysis data for an NSE stock. "
                "Returns: P/E, forward P/E, PEG, P/B, EV/EBITDA, profit margins, "
                "operating margins, ROE, ROA, debt-to-equity, current ratio, "
                "revenue growth, earnings growth, analyst recommendations and target price."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)",
                    }
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="fetch_technical_indicators",
            description=(
                "Compute comprehensive technical indicators for an NSE stock. "
                "Returns: RSI (14-period), MACD (line, signal, histogram), "
                "moving averages (SMA 20/50/200, EMA 20), Bollinger Bands, "
                "ADX (trend strength), ATR (volatility), volume analysis "
                "(current vs 20-day average), 7-day and 30-day price trends, "
                "momentum assessment, and support/resistance levels."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)",
                    }
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="fetch_stock_news",
            description=(
                "Get recent news articles for an NSE-listed stock. "
                "Returns up to 10 recent news items with title, publisher, "
                "link, publication date, and summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)",
                    }
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="fetch_financial_statements",
            description=(
                "Get quarterly and annual financial statements for an NSE stock. "
                "Returns: income statement, balance sheet, and cash flow statement "
                "in both annual and quarterly formats."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)",
                    }
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="fetch_screener_fundamentals",
            description=(
                "Scrape deep fundamental data from screener.in for an NSE stock. "
                "Returns: key ratios (P/E, Market Cap, ROCE, ROE, Book Value), "
                "quarterly results (last 12 quarters with Sales, Profit, OPM%), "
                "annual P&L (10+ years), balance sheet, cash flow statement, "
                "shareholding pattern (Promoter/FII/DII/Public %), and financial ratios. "
                "More detailed Indian market-specific data than yfinance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)",
                    }
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="search_nse_stocks",
            description=(
                "Search for NSE stocks by company name or symbol. "
                "Useful for finding the correct NSE symbol for a company, "
                "or discovering stocks in a particular sector."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company name or partial symbol to search (e.g., 'Reliance', 'HDFC', 'Tata')",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="fetch_nse_declared_results",
            description=(
                "Get NSE companies that have ACTUALLY declared/filed quarterly "
                "results in the last N days, from the authoritative NSE "
                "corporates-financial-results feed. Reliable first-party source of "
                "'just declared results'. Returns symbol, company, result_date, "
                "relating_to (which quarter)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "lookback_days": {
                        "type": "integer",
                        "description": "How many days back (including today) to include. Default 2.",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="fetch_nse_upcoming_results",
            description=(
                "Get NSE companies with board meetings SCHEDULED to declare results "
                "in the next N days, from the NSE corporate-filing events calendar. "
                "Forward-looking watch list (results not out yet). Returns symbol, "
                "company, event_date, purpose."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to include. Default 14.",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="scrape_url",
            description=(
                "Scrape any URL and return its text content. "
                "Use this as a fallback for fetching data from financial websites "
                "like moneycontrol.com, economictimes.com, or livemint.com. "
                "Returns plain text extracted from the page."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to scrape (e.g., https://www.moneycontrol.com/...)",
                    }
                },
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with args: {arguments}")

    try:
        if name == "fetch_stock_price":
            result = get_stock_price(arguments["symbol"])

        elif name == "fetch_fundamentals":
            result = get_fundamentals(arguments["symbol"])

        elif name == "fetch_technical_indicators":
            result = get_technical_indicators(arguments["symbol"])

        elif name == "fetch_stock_news":
            result = get_stock_news(arguments["symbol"])

        elif name == "fetch_financial_statements":
            result = get_financial_statements(arguments["symbol"])

        elif name == "fetch_screener_fundamentals":
            result = scrape_fundamentals(arguments["symbol"])

        elif name == "search_nse_stocks":
            result = _search_stocks(arguments["query"])

        elif name == "fetch_nse_declared_results":
            result = {
                "declared_results": recent_declared_results(
                    lookback_days=int(arguments.get("lookback_days", 2))
                )
            }

        elif name == "fetch_nse_upcoming_results":
            result = {
                "upcoming_results": upcoming_result_declarations(
                    days_ahead=int(arguments.get("days_ahead", 14))
                )
            }

        elif name == "scrape_url":
            result = _scrape_url(arguments["url"])

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


def _search_stocks(query: str) -> dict:
    """Search for stocks on screener.in."""
    from urllib.parse import quote

    url = f"https://www.screener.in/api/company/search/?q={quote(query)}&v=3&fts=1"
    response = _rate_limited_get(url)

    if not response:
        return {"error": "Search failed", "query": query}

    try:
        results = response.json()
        formatted = []
        for item in results[:10]:
            formatted.append(
                {
                    "name": item.get("name", ""),
                    "url": item.get("url", ""),
                    "id": item.get("id", ""),
                }
            )
        return {"query": query, "results_count": len(formatted), "results": formatted}
    except (ValueError, KeyError):
        return {"error": "Failed to parse search results", "query": query}


def _scrape_url(url: str) -> dict:
    """Generic URL scraper — fallback for any financial website."""
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "url": url}

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Limit to first 5000 chars to avoid overwhelming the LLM
        if len(text) > 5000:
            text = text[:5000] + "\n... [truncated]"

        return {"url": url, "content": text}
    except Exception as e:
        return {"error": str(e), "url": url}


async def main():
    """Run the MCP server."""
    logger.info("Starting Indian Stock Data MCP Server")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
