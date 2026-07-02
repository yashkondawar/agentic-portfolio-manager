"""
strategy.py
===========

Deterministic implementation of the SWING-TRADING PLAYBOOK (the same rule-set the
live ``swing_trading_copilot.py`` instructs its LLM to follow). Everything here is
point-in-time: signals are computed from price history up to and including the
current day's close only.

Execution convention (enforced by ``engine.py``):
  * ENTRY signals are generated from day t's close and FILLED at day t+1's OPEN.
  * EXITS (stop / target / trail / reversal / time-stop) are evaluated against the
    current day's OHLC, so they can fill intraday.
This ordering guarantees no look-ahead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

import pandas as pd

from . import indicators as ind
from .config import BacktestConfig
from .portfolio import Position


@dataclass
class EntrySignal:
    symbol: str
    setup: str
    signal_close: float
    atr: float
    rsi: float
    score: float       # ranking score (higher = better)


# ── Entry logic ───────────────────────────────────────────────────────────────

def compute_entry_signal(
    df: pd.DataFrame,
    symbol: str,
    cfg: BacktestConfig,
    bench_ret_3m: Optional[float],
) -> Optional[EntrySignal]:
    """Return an EntrySignal if `symbol` passes the playbook entry filters as-of
    the LAST row of `df` (which must be dated <= the simulated day)."""
    if df is None or len(df) < 60:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"].fillna(0)

    price = float(close.iloc[-1])
    if price < cfg.min_price:
        return None

    sma20 = ind.sma(close, 20)
    sma50 = ind.sma(close, 50)
    sma200 = ind.sma(close, 200)
    ema20 = ind.ema(close, 20)
    ema50 = ind.ema(close, 50)
    rsi = ind.rsi(close, 14)
    atr = ind.atr(high, low, close, 14)
    avg_vol = ind.avg_volume(vol, 20)
    tv_cr = ind.traded_value_cr(close, vol, 20)
    macd_line, macd_sig, macd_hist = ind.macd(close)

    if None in (sma20, sma50, rsi, atr, avg_vol, tv_cr):
        return None
    # SMA200 may be None for short history; fall back to sma50 for trend test.
    sma200_eff = sma200 if sma200 is not None else sma50

    atr_pct = atr / price * 100.0 if price else 99.0
    vol_ratio = (float(vol.iloc[-1]) / avg_vol) if avg_vol else 0.0

    # ── Hard filters (playbook A) ────────────────────────────────────────────
    if tv_cr < cfg.min_liquidity_cr:
        return None
    if atr_pct > cfg.max_atr_pct:
        return None
    if not (cfg.rsi_min <= rsi <= cfg.rsi_max):
        return None
    # Trend: price above rising 50 & 200 DMA stack.
    if not (price > sma50 > sma200_eff and price > sma200_eff):
        return None
    if ema50 is not None and ema20 is not None and not (ema20 > ema50):
        return None
    # Momentum confirmation: MACD bullish-ish.
    if macd_hist is not None and macd_line is not None and macd_sig is not None:
        if not (macd_hist > 0 or macd_line > macd_sig):
            return None

    # ── Setup classification (playbook A.4 / B) ──────────────────────────────
    prior_high = ind.rolling_high(high, cfg.breakout_lookback, exclude_last=True)
    setup: Optional[str] = None
    if prior_high is not None and price >= prior_high:
        # Breakout — require volume confirmation, and don't chase if extended.
        extension = (price - prior_high) / prior_high * 100.0
        if vol_ratio >= cfg.min_volume_ratio and extension <= cfg.max_extension_pct:
            setup = "Breakout"
    if setup is None and ema20 is not None:
        # Pullback — price near 20-EMA support holding, RSI > 50, trend intact.
        near_ema = abs(price - ema20) / ema20 * 100.0 <= 3.0
        if near_ema and rsi > 50 and price > ema20 * 0.985:
            setup = "Pullback"
    if setup is None:
        # Momentum continuation — strong RS + above stack + volume participation.
        if vol_ratio >= cfg.min_volume_ratio and rsi >= 58:
            setup = "Momentum"
    if setup is None:
        return None

    # ── Reward:risk gate (playbook C) ────────────────────────────────────────
    stop = price - cfg.atr_stop_mult * atr
    target = price * (1 + cfg.target_profit_pct / 100.0)
    risk = price - stop
    if risk <= 0:
        return None
    rr = (target - price) / risk
    if rr < cfg.min_rr:
        return None

    # ── Composite ranking score (mirror of curator weighting, simplified) ────
    ret_1m = ind.pct_return(close, 21) or 0.0
    ret_3m = ind.pct_return(close, 63) or 0.0
    rel = (ret_3m - bench_ret_3m) if bench_ret_3m is not None else ret_3m
    rsi_sweet = max(0.0, 1.0 - abs(rsi - 60.0) / 40.0)
    setup_bonus = {"Breakout": 0.15, "Momentum": 0.08, "Pullback": 0.05}.get(setup, 0.0)
    score = (
        0.030 * ret_3m
        + 0.025 * rel
        + 0.015 * ret_1m
        + 0.40 * rsi_sweet
        + 0.20 * min(vol_ratio, 3.0)
        + setup_bonus
    )

    return EntrySignal(
        symbol=symbol,
        setup=setup,
        signal_close=price,
        atr=float(atr),
        rsi=float(rsi),
        score=round(float(score), 4),
    )


def size_position(
    fill_price: float,
    atr: float,
    equity: float,
    cash: float,
    cfg: BacktestConfig,
) -> Tuple[int, float, float]:
    """Return (shares, stop, target) using the 2% risk rule + concentration cap.
    shares == 0 means the trade is not takeable with current capital."""
    stop = fill_price - cfg.atr_stop_mult * atr
    target = fill_price * (1 + cfg.target_profit_pct / 100.0)
    risk_per_share = fill_price - stop
    if risk_per_share <= 0:
        return 0, stop, target

    risk_budget = equity * cfg.risk_per_trade_pct / 100.0
    shares = math.floor(risk_budget / risk_per_share)

    # Per-name concentration cap.
    max_notional = equity * cfg.max_position_pct / 100.0
    if fill_price > 0:
        shares = min(shares, math.floor(max_notional / fill_price))
    # Cash cap (leave room for commission).
    affordable = math.floor((cash * 0.999) / fill_price) if fill_price > 0 else 0
    shares = min(shares, affordable)

    return max(shares, 0), stop, target


# ── Exit logic ────────────────────────────────────────────────────────────────

@dataclass
class ExitOp:
    fraction: float        # portion of the position to close (1.0 = all)
    price: float
    reason: str


def evaluate_exits(
    pos: Position,
    bar: pd.Series,
    df_asof: pd.DataFrame,
    day: date,
    cfg: BacktestConfig,
) -> List[ExitOp]:
    """Decide exits for one position on `day`, given that day's OHLC (`bar`) and
    the as-of history `df_asof` (last row == today). May mutate pos.stop_loss
    (trailing) and pos.highest_close. Returns the exit operations to apply."""
    o = float(bar["Open"]); h = float(bar["High"])
    l = float(bar["Low"]); c = float(bar["Close"])
    ops: List[ExitOp] = []

    close = df_asof["Close"]
    high = df_asof["High"]
    low = df_asof["Low"]
    atr = ind.atr(high, low, close, 14) or pos.atr_at_entry
    ema20 = ind.ema(close, 20)
    sma50 = ind.sma(close, 50)

    # 1) STOP — gap-through fills at the open; otherwise at the stop level.
    if o <= pos.stop_loss:
        ops.append(ExitOp(1.0, o, "STOP-GAP"))
        return ops
    if l <= pos.stop_loss:
        ops.append(ExitOp(1.0, pos.stop_loss, "STOP"))
        return ops

    # 2) TARGET — book a partial the first time target trades; raise stop to BE.
    if not pos.partial_booked and h >= pos.target_price:
        fill = max(o, pos.target_price) if o > pos.target_price else pos.target_price
        if cfg.partial_book_frac >= 1.0:
            ops.append(ExitOp(1.0, fill, "TARGET"))
            return ops
        ops.append(ExitOp(cfg.partial_book_frac, fill, "TARGET-PARTIAL"))
        pos.stop_loss = max(pos.stop_loss, pos.entry_price)   # protect to breakeven
        pos.partial_booked = True

    # 3) TRAILING — only after a partial; trail upward by trail_atr_mult*ATR.
    pos.highest_close = max(pos.highest_close, c)
    if pos.partial_booked and atr:
        trail = pos.highest_close - cfg.trail_atr_mult * atr
        pos.stop_loss = max(pos.stop_loss, trail)

    # 4) REVERSAL — clean trend break on close (only if not already exiting).
    if ema20 is not None and sma50 is not None:
        if c < sma50 or (pos.partial_booked and c < ema20):
            ops.append(ExitOp(1.0, c, "REVERSAL"))
            return ops

    # 5) TIME-STOP — hard window breach, or soft (held long, no progress).
    held = (day - pos.entry_date).days
    pnl_pct = pos.pnl_pct(c)
    if held >= cfg.max_holding_days:
        ops.append(ExitOp(1.0, c, "TIME-STOP"))
        return ops
    if held >= cfg.time_stop_soft_frac * cfg.max_holding_days and pnl_pct < cfg.time_stop_progress_pct:
        ops.append(ExitOp(1.0, c, "TIME-STOP-SOFT"))
        return ops

    return ops
