"""Point-in-time technicals for the live quarterly-results strategy.

Ports the exact measurements the backtest sizes and filters on -- ATR (for the
volatility-based trailing stop and risk sizing), a 20-day SMA + slope (the
"not broken" uptrend filter) and median 20-day rupee turnover (the liquidity
floor) -- so the LIVE run reasons in the same units as the winning backtest.

One yfinance OHLC history call per shortlisted symbol (cached in-process for the
run, like ``sectors.py``), computed on the trailing window up to *today* (which
is the correct point-in-time for a live decision). Every function DEGRADES
SAFELY: any fetch/parse failure yields ``None`` so the caller treats it as "no
opinion" and never rejects a name on missing data -- the same data-gap-safe
philosophy as the debt gate (the GESHIP lesson).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from qtr_results import config

logger = logging.getLogger("qtr_results.technicals")

_cache: Dict[str, "Technicals"] = {}


@dataclass
class Technicals:
    """Trailing-window technicals for one symbol (any field may be ``None``)."""
    atr: Optional[float] = None            # Wilder ATR in ₹
    last_close: Optional[float] = None
    sma: Optional[float] = None            # SMA(TREND_MA_PERIOD)
    sma_slope_up: Optional[bool] = None    # SMA rising vs a period ago
    median_turnover_20d: Optional[float] = None  # ₹ median 20d close*volume

    @property
    def in_uptrend(self) -> Optional[bool]:
        """True/False when computable, else None (missing data => no opinion)."""
        if self.last_close is None or self.sma is None or self.sma_slope_up is None:
            return None
        return self.last_close > self.sma and self.sma_slope_up


def _yf_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    return s if s.endswith(".NS") else f"{s}.NS"


def _compute_atr(df, period: int) -> Optional[float]:
    """Wilder-style ATR over ``period`` sessions (mirrors the backtest)."""
    if df is None or len(df) < period + 1:
        return None
    try:
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)
        prev_close = close.shift(1)
        import pandas as pd

        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
        if pd.isna(atr) or atr <= 0:
            return None
        return float(atr)
    except Exception as e:  # noqa: BLE001 - never break sizing on a math/parse issue
        logger.debug("ATR computation failed: %s", e)
        return None


def _fetch(symbol: str) -> "Technicals":
    try:
        import yfinance as yf

        df = yf.Ticker(_yf_symbol(symbol)).history(
            period=config.HISTORY_PERIOD, interval="1d"
        )
    except Exception as e:  # noqa: BLE001 - offline / rate-limit / bad symbol
        logger.warning("Technicals fetch failed for %s (%s).", symbol, e)
        return Technicals()

    if df is None or df.empty:
        return Technicals()

    t = Technicals()
    t.atr = _compute_atr(df, config.ATR_PERIOD)
    try:
        close = df["Close"].astype(float)
        t.last_close = float(close.iloc[-1])
        n = config.TREND_MA_PERIOD
        if len(close) >= n:
            sma_series = close.rolling(n).mean()
            t.sma = float(sma_series.iloc[-1])
            # Slope: current SMA vs the SMA one period ago (non-declining = up).
            if len(sma_series.dropna()) >= 2:
                prev = sma_series.iloc[-min(n, len(sma_series) - 1) - 1]
                if prev == prev:  # not NaN
                    t.sma_slope_up = t.sma >= float(prev)
        if "Volume" in df.columns and len(df) >= 20:
            vol = df["Volume"].astype(float)
            turnover = (close * vol).tail(20)
            t.median_turnover_20d = float(turnover.median())
    except Exception as e:  # noqa: BLE001
        logger.debug("Technicals derive failed for %s: %s", symbol, e)
    return t


def get_technicals(symbol: str) -> "Technicals":
    """Cached trailing-window technicals for ``symbol`` (empty on any failure)."""
    key = symbol.strip().upper()
    cached = _cache.get(key)
    if cached is None:
        cached = _fetch(key)
        _cache[key] = cached
    return cached


def clear_cache() -> None:
    """Drop the in-process cache (used by tests / between runs)."""
    _cache.clear()
