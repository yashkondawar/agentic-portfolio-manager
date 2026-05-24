"""
Free Indian Stock Market Data Scraper Module.

Replaces Bright Data MCP with direct scraping from:
- yfinance: Real-time prices, OHLCV history, fundamentals, news
- screener.in: Deep fundamentals, quarterly results, shareholding
- ta (technical analysis): RSI, MACD, moving averages, Bollinger Bands

No paid API keys required.
"""

from scraper.tools import get_all_scraper_tools

__all__ = ["get_all_scraper_tools"]
