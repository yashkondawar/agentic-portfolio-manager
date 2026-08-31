"""Technical indicators: 50/200 DMA, RSI(14), 52w high/low distance.

Pure functions over price history pulled from daily_prices/index_data —
nothing is written back to the database. Uses the `ta` library (already a
project dependency) for RSI; moving averages and 52w range are simple
enough to compute directly with pandas.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator

RSI_WINDOW = 14
DMA_SHORT_WINDOW = 50
DMA_LONG_WINDOW = 200
WEEKS_52_TRADING_DAYS = 252


def _price_frame(conn: sqlite3.Connection, *, instrument_id: int | None = None,
                  index_name: str | None = None) -> pd.DataFrame:
    if instrument_id is not None:
        rows = conn.execute(
            "SELECT date, close FROM daily_prices WHERE instrument_id = ? AND close IS NOT NULL ORDER BY date ASC",
            (instrument_id,),
        ).fetchall()
    elif index_name is not None:
        rows = conn.execute(
            "SELECT date, close FROM index_data WHERE index_name = ? AND close IS NOT NULL ORDER BY date ASC",
            (index_name,),
        ).fetchall()
    else:
        raise ValueError("must pass either instrument_id or index_name")

    if not rows:
        return pd.DataFrame(columns=["date", "close"])
    return pd.DataFrame([(r["date"], r["close"]) for r in rows], columns=["date", "close"])


def compute_technicals(conn: sqlite3.Connection, *, instrument_id: int | None = None,
                        index_name: str | None = None) -> dict:
    """Compute the latest technical snapshot for one instrument or index.

    Returns a dict with dma_50, dma_200, rsi_14, high_52w, low_52w,
    pct_from_52w_high, pct_from_52w_low, last_close, last_date — any value
    is None when there isn't enough history to compute it.
    """
    df = _price_frame(conn, instrument_id=instrument_id, index_name=index_name)

    result = {
        "last_date": None,
        "last_close": None,
        "dma_50": None,
        "dma_200": None,
        "rsi_14": None,
        "high_52w": None,
        "low_52w": None,
        "pct_from_52w_high": None,
        "pct_from_52w_low": None,
    }

    if df.empty:
        return result

    result["last_date"] = df["date"].iloc[-1]
    last_close = float(df["close"].iloc[-1])
    result["last_close"] = last_close

    if len(df) >= DMA_SHORT_WINDOW:
        dma50_series = SMAIndicator(close=df["close"], window=DMA_SHORT_WINDOW).sma_indicator()
        result["dma_50"] = float(dma50_series.iloc[-1])

    if len(df) >= DMA_LONG_WINDOW:
        dma200_series = SMAIndicator(close=df["close"], window=DMA_LONG_WINDOW).sma_indicator()
        result["dma_200"] = float(dma200_series.iloc[-1])

    if len(df) >= RSI_WINDOW + 1:
        rsi_series = RSIIndicator(close=df["close"], window=RSI_WINDOW).rsi()
        rsi_value = rsi_series.iloc[-1]
        result["rsi_14"] = float(rsi_value) if pd.notna(rsi_value) else None

    window_52w = df.tail(WEEKS_52_TRADING_DAYS)
    if not window_52w.empty:
        high_52w = float(window_52w["close"].max())
        low_52w = float(window_52w["close"].min())
        result["high_52w"] = high_52w
        result["low_52w"] = low_52w
        if high_52w:
            result["pct_from_52w_high"] = (last_close - high_52w) / high_52w
        if low_52w:
            result["pct_from_52w_low"] = (last_close - low_52w) / low_52w

    return result
