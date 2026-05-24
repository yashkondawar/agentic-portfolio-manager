"""
Market data provider using yfinance for real-time prices and technical analysis.
Uses the `ta` library for computing technical indicators on OHLCV data.
"""

import logging
from typing import Dict, Any, Optional

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


def _nse_symbol(symbol: str) -> str:
    """Ensure symbol has .NS suffix for NSE stocks."""
    symbol = symbol.strip().upper()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol = f"{symbol}.NS"
    return symbol


def get_stock_price(symbol: str) -> Dict[str, Any]:
    """
    Get real-time stock price and basic market data for an NSE stock.
    Data is ~15 minutes delayed on free tier.
    """
    ticker_symbol = _nse_symbol(symbol)
    logger.info(f"Fetching price data for {ticker_symbol}")

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        if not info or info.get("regularMarketPrice") is None:
            return {"error": f"No data found for {symbol}. Check if symbol is valid."}

        return {
            "symbol": symbol,
            "ticker": ticker_symbol,
            "company_name": info.get("longName", info.get("shortName", "")),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("regularMarketPreviousClose"),
            "open": info.get("regularMarketOpen"),
            "day_high": info.get("regularMarketDayHigh"),
            "day_low": info.get("regularMarketDayLow"),
            "volume": info.get("regularMarketVolume"),
            "avg_volume_10d": info.get("averageDailyVolume10Day"),
            "market_cap": info.get("marketCap"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_book": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
            "eps": info.get("trailingEps"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "price_change": _calc_change(
                info.get("currentPrice") or info.get("regularMarketPrice"),
                info.get("regularMarketPreviousClose"),
            ),
            "price_change_pct": _calc_change_pct(
                info.get("currentPrice") or info.get("regularMarketPrice"),
                info.get("regularMarketPreviousClose"),
            ),
        }
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        return {"error": f"Failed to fetch data for {symbol}: {str(e)}"}


def get_fundamentals(symbol: str) -> Dict[str, Any]:
    """Get fundamental data from yfinance (quick, less detailed than screener.in)."""
    ticker_symbol = _nse_symbol(symbol)
    logger.info(f"Fetching fundamentals for {ticker_symbol}")

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        if not info:
            return {"error": f"No data found for {symbol}"}

        return {
            "symbol": symbol,
            "company_name": info.get("longName", ""),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            "profit_margins": info.get("profitMargins"),
            "operating_margins": info.get("operatingMargins"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
            "book_value": info.get("bookValue"),
            "total_revenue": info.get("totalRevenue"),
            "total_debt": info.get("totalDebt"),
            "total_cash": info.get("totalCash"),
            "free_cashflow": info.get("freeCashflow"),
            "recommendation": info.get("recommendationKey"),
            "target_mean_price": info.get("targetMeanPrice"),
            "num_analyst_opinions": info.get("numberOfAnalystOpinions"),
        }
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol}: {e}")
        return {"error": f"Failed to fetch fundamentals for {symbol}: {str(e)}"}


def get_technical_indicators(symbol: str) -> Dict[str, Any]:
    """
    Compute technical indicators using OHLCV history from yfinance + ta library.
    Includes RSI, MACD, moving averages, Bollinger Bands, ADX, volume analysis.
    """
    ticker_symbol = _nse_symbol(symbol)
    logger.info(f"Computing technical indicators for {ticker_symbol}")

    try:
        import ta

        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="1y", interval="1d")

        if df.empty:
            return {"error": f"No historical data available for {symbol}"}

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        # Current price info
        current_price = close.iloc[-1]
        prev_close = close.iloc[-2] if len(close) > 1 else current_price

        # Moving Averages
        sma_20 = ta.trend.sma_indicator(close, window=20).iloc[-1]
        sma_50 = ta.trend.sma_indicator(close, window=50).iloc[-1]
        sma_200 = ta.trend.sma_indicator(close, window=200).iloc[-1]
        ema_20 = ta.trend.ema_indicator(close, window=20).iloc[-1]

        # RSI
        rsi = ta.momentum.rsi(close, window=14).iloc[-1]

        # MACD
        macd_line = ta.trend.macd(close)
        macd_signal = ta.trend.macd_signal(close)
        macd_histogram = ta.trend.macd_diff(close)
        macd_value = macd_line.iloc[-1]
        macd_signal_value = macd_signal.iloc[-1]
        macd_hist_value = macd_histogram.iloc[-1]

        # Bollinger Bands
        bb_high = ta.volatility.bollinger_hband(close).iloc[-1]
        bb_low = ta.volatility.bollinger_lband(close).iloc[-1]
        bb_mid = ta.volatility.bollinger_mavg(close).iloc[-1]

        # ADX (trend strength)
        adx = ta.trend.adx(high, low, close).iloc[-1]

        # ATR (volatility)
        atr = ta.volatility.average_true_range(high, low, close).iloc[-1]

        # Volume analysis
        avg_volume_20 = volume.rolling(window=20).mean().iloc[-1]
        current_volume = volume.iloc[-1]
        volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 0

        # Trend analysis
        price_7d_ago = close.iloc[-6] if len(close) > 6 else close.iloc[0]
        price_30d_ago = close.iloc[-22] if len(close) > 22 else close.iloc[0]
        trend_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100
        trend_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100

        # Support and Resistance (simple pivot-based)
        recent_high = high.tail(20).max()
        recent_low = low.tail(20).min()
        pivot = (recent_high + recent_low + current_price) / 3
        support_1 = (2 * pivot) - recent_high
        resistance_1 = (2 * pivot) - recent_low

        # Determine signals
        rsi_signal = (
            "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
        )
        macd_signal_text = "Bullish" if macd_hist_value > 0 else "Bearish"
        trend_strength = (
            "Strong" if adx > 25 else "Weak" if adx < 20 else "Moderate"
        )

        price_vs_sma50 = ((current_price - sma_50) / sma_50) * 100
        price_vs_sma200 = ((current_price - sma_200) / sma_200) * 100

        return {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "indicators": {
                "rsi": round(rsi, 2),
                "rsi_signal": rsi_signal,
                "macd": round(macd_value, 2),
                "macd_signal": round(macd_signal_value, 2),
                "macd_histogram": round(macd_hist_value, 2),
                "macd_trend": macd_signal_text,
                "adx": round(adx, 2),
                "trend_strength": trend_strength,
                "atr": round(atr, 2),
            },
            "moving_averages": {
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2),
                "sma_200": round(sma_200, 2),
                "ema_20": round(ema_20, 2),
                "price_vs_sma50_pct": round(price_vs_sma50, 2),
                "price_vs_sma200_pct": round(price_vs_sma200, 2),
            },
            "bollinger_bands": {
                "upper": round(bb_high, 2),
                "middle": round(bb_mid, 2),
                "lower": round(bb_low, 2),
            },
            "volume_analysis": {
                "current_volume": int(current_volume),
                "avg_volume_20d": int(avg_volume_20),
                "volume_ratio": round(volume_ratio, 2),
                "volume_status": (
                    "Above Average"
                    if volume_ratio > 1.2
                    else "Below Average" if volume_ratio < 0.8 else "Normal"
                ),
            },
            "trends": {
                "7_day_change_pct": round(trend_7d, 2),
                "30_day_change_pct": round(trend_30d, 2),
                "momentum": (
                    "Strong Bullish"
                    if trend_7d > 3 and trend_30d > 5
                    else "Bullish"
                    if trend_7d > 0 and trend_30d > 0
                    else "Strong Bearish"
                    if trend_7d < -3 and trend_30d < -5
                    else "Bearish"
                    if trend_7d < 0 and trend_30d < 0
                    else "Sideways"
                ),
            },
            "support_resistance": {
                "support_1": round(support_1, 2),
                "resistance_1": round(resistance_1, 2),
                "pivot": round(pivot, 2),
                "recent_high_20d": round(recent_high, 2),
                "recent_low_20d": round(recent_low, 2),
            },
        }
    except ImportError:
        logger.error("'ta' library not installed. Run: pip install ta")
        return {"error": "Technical analysis library 'ta' not installed"}
    except Exception as e:
        logger.error(f"Error computing technicals for {symbol}: {e}")
        return {"error": f"Failed to compute technical indicators: {str(e)}"}


def get_stock_news(symbol: str) -> Dict[str, Any]:
    """Get recent news for a stock using yfinance."""
    ticker_symbol = _nse_symbol(symbol)
    logger.info(f"Fetching news for {ticker_symbol}")

    try:
        ticker = yf.Ticker(ticker_symbol)
        news = ticker.news

        if not news:
            return {"symbol": symbol, "news": [], "message": "No recent news found"}

        formatted_news = []
        for item in news[:10]:  # Limit to 10 most recent
            # Handle both old and new yfinance news format
            content = item.get("content", item)
            title = content.get("title", item.get("title", ""))
            publisher = ""
            if "provider" in content:
                publisher = content["provider"].get("displayName", "")
            else:
                publisher = item.get("publisher", "")

            link = ""
            if "canonicalUrl" in content:
                link = content["canonicalUrl"].get("url", "")
            else:
                link = item.get("link", "")

            pub_date = content.get("pubDate", "")
            summary = content.get("summary", "")

            formatted_news.append(
                {
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "published": pub_date,
                    "summary": summary[:200] if summary else "",
                }
            )

        return {
            "symbol": symbol,
            "news_count": len(formatted_news),
            "news": formatted_news,
        }
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return {"error": f"Failed to fetch news for {symbol}: {str(e)}"}


def get_financial_statements(symbol: str) -> Dict[str, Any]:
    """Get quarterly and annual financial statements from yfinance."""
    ticker_symbol = _nse_symbol(symbol)
    logger.info(f"Fetching financial statements for {ticker_symbol}")

    try:
        ticker = yf.Ticker(ticker_symbol)

        def df_to_dict(df: pd.DataFrame) -> Dict:
            if df is None or df.empty:
                return {}
            # Convert columns (dates) to strings and transpose for readability
            result = {}
            for col in df.columns:
                period = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                result[period] = {
                    str(idx): _safe_value(val) for idx, val in df[col].items()
                }
            return result

        return {
            "symbol": symbol,
            "income_statement_annual": df_to_dict(ticker.income_stmt),
            "income_statement_quarterly": df_to_dict(ticker.quarterly_income_stmt),
            "balance_sheet_annual": df_to_dict(ticker.balance_sheet),
            "balance_sheet_quarterly": df_to_dict(ticker.quarterly_balance_sheet),
            "cashflow_annual": df_to_dict(ticker.cashflow),
            "cashflow_quarterly": df_to_dict(ticker.quarterly_cashflow),
        }
    except Exception as e:
        logger.error(f"Error fetching financials for {symbol}: {e}")
        return {"error": f"Failed to fetch financial statements: {str(e)}"}


def _calc_change(current, previous) -> Optional[float]:
    if current is not None and previous is not None:
        return round(current - previous, 2)
    return None


def _calc_change_pct(current, previous) -> Optional[float]:
    if current is not None and previous is not None and previous != 0:
        return round(((current - previous) / previous) * 100, 2)
    return None


def _safe_value(val) -> Any:
    """Convert numpy/pandas values to JSON-serializable types."""
    if pd.isna(val):
        return None
    if hasattr(val, "item"):
        return val.item()
    return val
