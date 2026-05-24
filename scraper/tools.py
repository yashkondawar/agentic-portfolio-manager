"""
LangChain tools that wrap the scraper functions.
These tools replace Bright Data MCP tools and can be used directly by agents.
"""

import json
import logging
from typing import List

from langchain_core.tools import tool

from scraper.market_data import (
    get_stock_price,
    get_fundamentals,
    get_technical_indicators,
    get_stock_news,
    get_financial_statements,
)
from scraper.screener import scrape_fundamentals

logger = logging.getLogger(__name__)


@tool
def fetch_stock_price(symbol: str) -> str:
    """
    Get real-time stock price and market data for an NSE-listed stock.
    Provides: current price, day high/low, volume, 52-week range, market cap,
    P/E ratio, and price change.

    Args:
        symbol: NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK, INFY)
    """
    result = get_stock_price(symbol)
    return json.dumps(result, indent=2, default=str)


@tool
def fetch_fundamentals(symbol: str) -> str:
    """
    Get fundamental analysis data for an NSE stock including valuation ratios,
    margins, growth metrics, and analyst recommendations.
    Uses yfinance for quick data.

    Args:
        symbol: NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)
    """
    result = get_fundamentals(symbol)
    return json.dumps(result, indent=2, default=str)


@tool
def fetch_technical_indicators(symbol: str) -> str:
    """
    Compute comprehensive technical indicators for an NSE stock.
    Includes: RSI, MACD, moving averages (SMA 20/50/200), Bollinger Bands,
    ADX, ATR, volume analysis, support/resistance levels, and trend analysis.

    Args:
        symbol: NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)
    """
    result = get_technical_indicators(symbol)
    return json.dumps(result, indent=2, default=str)


@tool
def fetch_stock_news(symbol: str) -> str:
    """
    Get recent news articles for an NSE-listed stock.
    Returns up to 10 recent news items with title, publisher, link, and date.

    Args:
        symbol: NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)
    """
    result = get_stock_news(symbol)
    return json.dumps(result, indent=2, default=str)


@tool
def fetch_financial_statements(symbol: str) -> str:
    """
    Get quarterly and annual financial statements (income statement,
    balance sheet, cash flow) for an NSE stock from yfinance.

    Args:
        symbol: NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)
    """
    result = get_financial_statements(symbol)
    return json.dumps(result, indent=2, default=str)


@tool
def fetch_screener_fundamentals(symbol: str) -> str:
    """
    Scrape deep fundamental data from screener.in for an NSE stock.
    Provides: key ratios (P/E, Market Cap, ROCE, ROE), quarterly results
    (last 12 quarters), annual P&L (10+ years), balance sheet, cash flow,
    shareholding pattern, and financial ratios.

    Use this for more detailed Indian market-specific data than yfinance provides.

    Args:
        symbol: NSE stock symbol (e.g., RELIANCE, TCS, HDFCBANK)
    """
    result = scrape_fundamentals(symbol)
    return json.dumps(result, indent=2, default=str)


@tool
def search_nse_stocks(query: str) -> str:
    """
    Search for NSE stocks by name or symbol using screener.in search API.
    Useful for finding the correct symbol for a company.

    Args:
        query: Company name or partial symbol to search for
    """
    from scraper.screener import resolve_screener_slug, _rate_limited_get
    from urllib.parse import quote

    url = f"https://www.screener.in/api/company/search/?q={quote(query)}&v=3&fts=1"
    response = _rate_limited_get(url)

    if not response:
        return json.dumps({"error": "Search failed", "query": query})

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
        return json.dumps(
            {"query": query, "results_count": len(formatted), "results": formatted},
            indent=2,
        )
    except (ValueError, KeyError):
        return json.dumps({"error": "Failed to parse search results", "query": query})


def get_all_scraper_tools() -> List:
    """Return all scraper tools as a list for use with LangChain agents."""
    return [
        fetch_stock_price,
        fetch_fundamentals,
        fetch_technical_indicators,
        fetch_stock_news,
        fetch_financial_statements,
        fetch_screener_fundamentals,
        search_nse_stocks,
    ]
