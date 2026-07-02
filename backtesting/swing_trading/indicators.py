"""
indicators.py
=============

Point-in-time technical indicators computed from a price history DataFrame whose
LAST row is the "as-of" day. Every function only looks BACKWARD, so as long as
the caller passes a slice of history with rows dated <= the simulated day, there
is no look-ahead leak.

These mirror the calculations used by ``scraper/data_provider.py`` and
``watchlist_curator.py`` so the backtest reasons with the same numbers the live
system would have computed on that date.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> Optional[float]:
    if len(close) < window:
        return None
    return float(close.rolling(window).mean().iloc[-1])


def ema(close: pd.Series, window: int) -> Optional[float]:
    if len(close) < window:
        return None
    return float(close.ewm(span=window, adjust=False).mean().iloc[-1])


def rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    val = (100 - 100 / (1 + rs)).iloc[-1]
    return float(val) if not math.isnan(val) else None


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (macd_line, signal_line, histogram) at the as-of day."""
    if len(close) < slow + signal:
        return None, None, None
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1])


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    prev_close = close.shift()
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = tr1.combine(tr2, max).combine(tr3, max)
    val = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().iloc[-1]
    return float(val) if not math.isnan(val) else None


def avg_volume(volume: pd.Series, window: int = 20) -> Optional[float]:
    if len(volume) < window:
        return None
    return float(volume.rolling(window).mean().iloc[-1])


def traded_value_cr(close: pd.Series, volume: pd.Series, window: int = 20) -> Optional[float]:
    """Average daily traded value over `window` days, in ₹ crore."""
    if len(close) < window:
        return None
    val = (close * volume).rolling(window).mean().iloc[-1]
    return float(val) / 1e7 if not math.isnan(val) else None


def pct_return(close: pd.Series, lookback: int) -> Optional[float]:
    if len(close) <= lookback:
        return None
    a = close.iloc[-1]
    b = close.iloc[-1 - lookback]
    if b and not math.isnan(b):
        return (a / b - 1.0) * 100.0
    return None


def rolling_high(series: pd.Series, window: int, exclude_last: bool = True) -> Optional[float]:
    """Highest value over the prior `window` bars. If exclude_last, the current
    bar is excluded — used so a "breakout above prior high" test is leak-free."""
    s = series.iloc[:-1] if exclude_last else series
    if len(s) < window:
        return None
    return float(s.tail(window).max())


def rolling_low(series: pd.Series, window: int, exclude_last: bool = False) -> Optional[float]:
    s = series.iloc[:-1] if exclude_last else series
    if len(s) < window:
        return None
    return float(s.tail(window).min())
