"""
Unified data provider for the multi-analyst system.
Fetches once per symbol per session, caches results, merges yfinance + screener.in.

Usage:
    from scraper.data_provider import get_stock_data
    data = get_stock_data("RELIANCE")
    # data.price, data.fundamentals, data.technicals, data.news, data.financials
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# In-memory cache: symbol -> StockData (valid for current process lifetime)
_cache: Dict[str, "StockData"] = {}
_cache_lock = threading.Lock()
_fetch_locks: Dict[str, threading.Lock] = {}
_fetch_locks_lock = threading.Lock()


@dataclass
class StockData:
    """All data for a single stock, fetched once and reused by all agents."""
    symbol: str
    # Price data
    current_price: float = 0.0
    previous_close: float = 0.0
    open_price: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    volume: int = 0
    avg_volume: int = 0
    market_cap: float = 0.0
    fifty_two_week_high: float = 0.0
    fifty_two_week_low: float = 0.0
    beta: float = 0.0
    sector: str = ""
    industry: str = ""
    company_name: str = ""

    # Fundamentals (yfinance)
    pe_ratio: float = 0.0
    forward_pe: float = 0.0
    price_to_book: float = 0.0
    ev_to_ebitda: float = 0.0
    roe: float = 0.0
    roa: float = 0.0
    debt_to_equity: float = 0.0
    current_ratio: float = 0.0
    revenue_growth: float = 0.0
    earnings_growth: float = 0.0
    operating_margins: float = 0.0
    profit_margins: float = 0.0
    dividend_yield: float = 0.0
    free_cashflow: float = 0.0
    total_revenue: float = 0.0
    total_debt: float = 0.0
    enterprise_value: float = 0.0
    book_value: float = 0.0
    peg_ratio: float = 0.0

    # Screener.in deep fundamentals
    screener_ratios: Dict[str, str] = field(default_factory=dict)
    quarterly_results: List[Dict] = field(default_factory=list)
    profit_loss: List[Dict] = field(default_factory=list)
    balance_sheet: List[Dict] = field(default_factory=list)
    cash_flow: List[Dict] = field(default_factory=list)
    shareholding: List[Dict] = field(default_factory=list)
    financial_ratios: List[Dict] = field(default_factory=list)

    # Technical data (OHLCV history as dict for flexibility)
    price_history: Any = None  # pandas DataFrame
    technicals: Dict[str, Any] = field(default_factory=dict)

    # News
    news: List[Dict[str, str]] = field(default_factory=list)

    # Metadata
    fetch_time: float = 0.0
    errors: List[str] = field(default_factory=list)


def _nse_symbol(symbol: str) -> str:
    """Ensure symbol has .NS suffix."""
    symbol = symbol.strip().upper()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        return f"{symbol}.NS"
    return symbol


def _fetch_yfinance_data(symbol: str) -> Dict[str, Any]:
    """Fetch all yfinance data for a symbol in one go."""
    import yfinance as yf

    ticker_symbol = _nse_symbol(symbol)
    result = {"info": {}, "history": None, "news": []}

    try:
        ticker = yf.Ticker(ticker_symbol)
        result["info"] = ticker.info or {}
        result["history"] = ticker.history(period="1y", interval="1d")
        result["news"] = ticker.news or []
    except Exception as e:
        logger.warning(f"[DATA] {symbol}: yfinance error: {e}")
        result["error"] = str(e)

    return result


def _fetch_screener_data(symbol: str) -> Dict[str, Any]:
    """Fetch screener.in data."""
    from scraper.screener import scrape_fundamentals
    try:
        return scrape_fundamentals(symbol)
    except Exception as e:
        logger.warning(f"[DATA] {symbol}: screener.in error: {e}")
        return {"error": str(e)}


def _compute_technicals(df) -> Dict[str, Any]:
    """Compute technical indicators from price DataFrame."""
    if df is None or df.empty:
        return {}

    try:
        import ta
        import numpy as np

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        current_price = close.iloc[-1]

        # Moving Averages
        sma_20 = ta.trend.sma_indicator(close, window=20).iloc[-1]
        sma_50 = ta.trend.sma_indicator(close, window=50).iloc[-1]
        sma_200 = ta.trend.sma_indicator(close, window=200).iloc[-1] if len(close) >= 200 else None
        ema_12 = ta.trend.ema_indicator(close, window=12).iloc[-1]
        ema_26 = ta.trend.ema_indicator(close, window=26).iloc[-1]

        # RSI
        rsi_14 = ta.momentum.rsi(close, window=14).iloc[-1]

        # MACD
        macd_line = ta.trend.macd(close).iloc[-1]
        macd_signal = ta.trend.macd_signal(close).iloc[-1]
        macd_histogram = ta.trend.macd_diff(close).iloc[-1]

        # Bollinger Bands
        bb_high = ta.volatility.bollinger_hband(close).iloc[-1]
        bb_low = ta.volatility.bollinger_lband(close).iloc[-1]
        bb_mid = ta.volatility.bollinger_mavg(close).iloc[-1]

        # ADX
        adx = ta.trend.adx(high, low, close).iloc[-1]

        # ATR
        atr = ta.volatility.average_true_range(high, low, close).iloc[-1]

        # Volume
        avg_volume_20 = volume.rolling(window=20).mean().iloc[-1]
        volume_ratio = volume.iloc[-1] / avg_volume_20 if avg_volume_20 > 0 else 1.0

        # Stochastic
        stoch_k = ta.momentum.stoch(high, low, close).iloc[-1]
        stoch_d = ta.momentum.stoch_signal(high, low, close).iloc[-1]

        # Returns
        returns = close.pct_change().dropna()
        volatility_annual = float(returns.std() * np.sqrt(252))

        # Trends
        price_7d_ago = close.iloc[-6] if len(close) > 6 else close.iloc[0]
        price_30d_ago = close.iloc[-22] if len(close) > 22 else close.iloc[0]
        price_90d_ago = close.iloc[-63] if len(close) > 63 else close.iloc[0]

        # Support/Resistance
        recent_high = high.tail(20).max()
        recent_low = low.tail(20).min()

        return {
            "current_price": float(current_price),
            "sma_20": float(sma_20),
            "sma_50": float(sma_50),
            "sma_200": float(sma_200) if sma_200 is not None else None,
            "ema_12": float(ema_12),
            "ema_26": float(ema_26),
            "rsi_14": float(rsi_14),
            "macd_line": float(macd_line),
            "macd_signal": float(macd_signal),
            "macd_histogram": float(macd_histogram),
            "bb_upper": float(bb_high),
            "bb_lower": float(bb_low),
            "bb_middle": float(bb_mid),
            "adx": float(adx),
            "atr": float(atr),
            "atr_pct": float(atr / current_price * 100),
            "volume_ratio": float(volume_ratio),
            "stoch_k": float(stoch_k),
            "stoch_d": float(stoch_d),
            "volatility_annual": volatility_annual,
            "trend_7d_pct": float((current_price - price_7d_ago) / price_7d_ago * 100),
            "trend_30d_pct": float((current_price - price_30d_ago) / price_30d_ago * 100),
            "trend_90d_pct": float((current_price - price_90d_ago) / price_90d_ago * 100),
            "high_20d": float(recent_high),
            "low_20d": float(recent_low),
            "distance_from_high_pct": float((current_price - recent_high) / recent_high * 100),
            "above_sma_20": current_price > sma_20,
            "above_sma_50": current_price > sma_50,
            "above_sma_200": current_price > sma_200 if sma_200 else None,
            "golden_cross": sma_50 > sma_200 if sma_200 else None,
        }
    except Exception as e:
        logger.warning(f"[DATA] Technical computation error: {e}")
        return {"error": str(e)}


def get_stock_data(symbol: str, use_cache: bool = True) -> StockData:
    """
    Fetch all available data for a stock symbol.
    Combines yfinance (prices, technicals, news) + screener.in (deep fundamentals).
    Results are cached per symbol for the process lifetime.
    Thread-safe: concurrent calls for the same symbol wait for the first fetch.
    """
    symbol = symbol.strip().upper().replace(".NS", "").replace(".BO", "")

    # Fast path: check cache without lock
    if use_cache and symbol in _cache:
        logger.info(f"[DATA] {symbol}: Using cached data (fetched {time.time() - _cache[symbol].fetch_time:.0f}s ago)")
        return _cache[symbol]

    # Get per-symbol lock to prevent duplicate fetches
    with _fetch_locks_lock:
        if symbol not in _fetch_locks:
            _fetch_locks[symbol] = threading.Lock()
        sym_lock = _fetch_locks[symbol]

    with sym_lock:
        # Double-check after acquiring lock (another thread may have fetched it)
        if use_cache and symbol in _cache:
            logger.info(f"[DATA] {symbol}: Using cached data (fetched {time.time() - _cache[symbol].fetch_time:.0f}s ago)")
            return _cache[symbol]

        start = time.time()
        logger.info(f"[DATA] {symbol}: Fetching from yfinance + screener.in...")

        data = StockData(symbol=symbol)

        # Fetch yfinance and screener.in in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            yf_future = executor.submit(_fetch_yfinance_data, symbol)
            screener_future = executor.submit(_fetch_screener_data, symbol)

            yf_data = yf_future.result()
            screener_data = screener_future.result()

        # --- Populate from yfinance ---
        info = yf_data.get("info", {})
        if info:
            data.current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            data.previous_close = info.get("regularMarketPreviousClose") or 0
            data.open_price = info.get("regularMarketOpen") or 0
            data.day_high = info.get("regularMarketDayHigh") or 0
            data.day_low = info.get("regularMarketDayLow") or 0
            data.volume = info.get("regularMarketVolume") or 0
            data.avg_volume = info.get("averageDailyVolume10Day") or 0
            data.market_cap = info.get("marketCap") or 0
            data.fifty_two_week_high = info.get("fiftyTwoWeekHigh") or 0
            data.fifty_two_week_low = info.get("fiftyTwoWeekLow") or 0
            data.beta = info.get("beta") or 0
            data.sector = info.get("sector") or ""
            data.industry = info.get("industry") or ""
            data.company_name = info.get("longName") or info.get("shortName") or ""

            # Fundamentals
            data.pe_ratio = info.get("trailingPE") or 0
            data.forward_pe = info.get("forwardPE") or 0
            data.price_to_book = info.get("priceToBook") or 0
            data.ev_to_ebitda = info.get("enterpriseToEbitda") or 0
            data.roe = info.get("returnOnEquity") or 0
            data.roa = info.get("returnOnAssets") or 0
            data.debt_to_equity = info.get("debtToEquity") or 0
            data.current_ratio = info.get("currentRatio") or 0
            data.revenue_growth = info.get("revenueGrowth") or 0
            data.earnings_growth = info.get("earningsGrowth") or 0
            data.operating_margins = info.get("operatingMargins") or 0
            data.profit_margins = info.get("profitMargins") or 0
            data.dividend_yield = info.get("dividendYield") or 0
            data.free_cashflow = info.get("freeCashflow") or 0
            data.total_revenue = info.get("totalRevenue") or 0
            data.total_debt = info.get("totalDebt") or 0
            data.enterprise_value = info.get("enterpriseValue") or 0
            data.book_value = info.get("bookValue") or 0
            data.peg_ratio = info.get("pegRatio") or 0
        else:
            data.errors.append("yfinance returned no info")

        # Price history + technicals
        history = yf_data.get("history")
        if history is not None and not history.empty:
            data.price_history = history
            data.technicals = _compute_technicals(history)
        else:
            data.errors.append("No price history from yfinance")

        # News
        raw_news = yf_data.get("news", [])
        for item in raw_news[:15]:
            content = item.get("content", {}) if isinstance(item, dict) else {}
            title = content.get("title", "") if isinstance(content, dict) else item.get("title", "")
            link = content.get("canonicalUrl", {}).get("url", "") if isinstance(content, dict) else item.get("link", "")
            publisher = content.get("provider", {}).get("displayName", "") if isinstance(content, dict) else item.get("publisher", "")
            pub_date = content.get("pubDate", "") if isinstance(content, dict) else ""
            if title:
                data.news.append({
                    "title": title,
                    "link": link,
                    "publisher": publisher,
                    "date": pub_date,
                })

        # --- Populate from screener.in ---
        if "error" not in screener_data:
            data.screener_ratios = screener_data.get("top_ratios", {})
            data.quarterly_results = screener_data.get("quarterly_results", [])
            data.profit_loss = screener_data.get("profit_loss", [])
            data.balance_sheet = screener_data.get("balance_sheet", [])
            data.cash_flow = screener_data.get("cash_flow", [])
            data.shareholding = screener_data.get("shareholding", [])
            data.financial_ratios = screener_data.get("financial_ratios", [])
            if screener_data.get("company_name") and not data.company_name:
                data.company_name = screener_data["company_name"]
            logger.info(f"[DATA] {symbol}: Screener.in OK - ratios={len(data.screener_ratios)}, quarters={len(data.quarterly_results)}, shareholding={len(data.shareholding)}")
        else:
            data.errors.append(f"screener.in: {screener_data['error']}")
            logger.warning(f"[DATA] {symbol}: Screener.in failed: {screener_data.get('error')}")

        data.fetch_time = time.time()
        elapsed = time.time() - start
        logger.info(f"[DATA] {symbol}: All data fetched in {elapsed:.1f}s | Price=₹{data.current_price:,.2f} | Errors={len(data.errors)}")

        # Cache
        _cache[symbol] = data
        return data


def clear_cache(symbol: Optional[str] = None):
    """Clear cached data. If symbol given, clear just that one."""
    if symbol:
        _cache.pop(symbol.upper(), None)
    else:
        _cache.clear()


def prefetch_stocks(symbols: List[str]):
    """Pre-fetch data for multiple symbols in parallel."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(get_stock_data, s): s for s in symbols}
        for f in futures:
            f.result()  # Wait for all to complete
