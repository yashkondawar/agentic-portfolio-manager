"""
strategy.py
===========

The deterministic, point-in-time encoding of the quarterly-results playbook's
capital-management layer:

* **Sizing** — the live strategy is a signal/ledger tracker with no position
  sizing, so the backtest adds a risk-based sizer: risk a fixed % of equity per
  trade, where per-share risk is the ABSOLUTE ₹ trailing-stop distance (an ATR
  multiple, not a % of entry). Capped by a per-name concentration limit and
  available cash.
* **ATR stop** — the trailing stop distance is ``atr_stop_multiplier x ATR`` in
  each stock's own volatility units, decoupled from the target. This replaces
  the original ``target_pct/2`` stop, which perversely gave the tightest stops
  to the highest-conviction picks and got whipsawed by ordinary noise.
* **Exits** — a faithful OHLC-aware ratcheting trailing stop off the highest
  price seen books/protects the trade, the PE re-rating target takes profit,
  and a time-stop closes anything past the holding window. The trailing stop
  for day *t* is measured from the highest price through day *t-1* only (it is
  ratcheted AFTER the day's exits are evaluated), so there is no intraday
  look-ahead.

Execution convention (enforced by ``engine.py``): a result recognised on day *t*
is FILLED at day *t+1*'s OPEN; exits are evaluated against the current day's OHLC.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from .config import BacktestConfig
from .portfolio import Position


@dataclass
class ExitOp:
    price: float
    reason: str


def compute_atr(bars: pd.DataFrame, period: int) -> Optional[float]:
    """Wilder-style Average True Range over ``period`` sessions.

    ``bars`` must contain OHLC columns and be dated STRICTLY BEFORE the entry
    day (the caller slices it that way to preserve point-in-time integrity).
    Returns ``None`` if there is insufficient history.
    """
    if bars is None or len(bars) < period + 1:
        return None
    high = bars["High"].astype(float)
    low = bars["Low"].astype(float)
    close = bars["Close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing = exponential MA with alpha = 1/period.
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return None
    return float(atr)


def resolve_stop_distance(
    entry_price: float, atr: Optional[float], cfg: BacktestConfig
) -> float:
    """Absolute ₹ trailing-stop distance for an entry.

    Prefers ``atr_stop_multiplier x ATR``; falls back to ``fallback_stop_pct``
    of entry if ATR is unavailable (insufficient history).
    """
    if atr and atr > 0:
        return atr * cfg.atr_stop_multiplier
    return entry_price * cfg.fallback_stop_pct / 100.0


def size_position(
    entry_price: float,
    stop_distance: float,
    equity: float,
    cash: float,
    cfg: BacktestConfig,
) -> int:
    """Shares to buy under the risk rule + concentration + cash caps.

    ``stop_distance`` is the absolute ₹ per-share risk (ATR-based, see
    ``resolve_stop_distance``). ``0`` means the trade is not takeable with the
    current capital.
    """
    if entry_price <= 0 or stop_distance <= 0:
        return 0

    risk_budget = equity * cfg.risk_per_trade_pct / 100.0
    shares = math.floor(risk_budget / stop_distance)

    # Per-name concentration cap.
    max_notional = equity * cfg.max_position_pct / 100.0
    shares = min(shares, math.floor(max_notional / entry_price))
    # Cash cap (leave a little room for commission).
    affordable = math.floor((cash * 0.999) / entry_price)
    shares = min(shares, affordable)

    return max(shares, 0)


def make_position(
    symbol: str,
    fill_price: float,
    fill_date: date,
    quantity: int,
    plan,
    analysis,
    result_date: str,
    stop_distance: float,
) -> Position:
    """Build an open Position from the target plan + ATR-based stop distance."""
    stop_price = round(fill_price - stop_distance, 2)
    # Target is re-anchored to the ACTUAL fill price so the % target holds.
    target_price = round(fill_price * (1 + plan.target_pct / 100.0), 2)
    approx_stop_pct = round(stop_distance / fill_price * 100.0, 2) if fill_price else 0.0
    return Position(
        symbol=symbol,
        quantity=quantity,
        entry_price=round(fill_price, 2),
        entry_date=fill_date,
        target_price=target_price,
        target_pct=plan.target_pct,
        trailing_stop_pct=approx_stop_pct,
        stop_distance=round(stop_distance, 4),
        stop_price=stop_price,
        highest_price=round(fill_price, 2),
        result_quarter=analysis.latest_quarter,
        result_date=result_date,
        method=plan.method,
        strength_score=analysis.strength_score,
        rationale=analysis.rationale,
    )


def evaluate_exit(
    pos: Position, bar: pd.Series, day: date, cfg: BacktestConfig
) -> Optional[ExitOp]:
    """Decide the exit (if any) for one position on ``day`` given that day's OHLC.

    Priority mirrors a conservative reading of the live ledger: a stop breach is
    honoured before the target when both could fill the same session. The
    trailing stop is then ratcheted (by the ATR-fixed distance) off today's high
    for TOMORROW.
    """
    o = float(bar["Open"])
    h = float(bar["High"])
    low = float(bar["Low"])
    c = float(bar["Close"])

    # 1) TRAILING STOP — gap-through fills at the open; else at the stop level.
    if o <= pos.stop_price:
        return ExitOp(o, "trailing_stop")
    if low <= pos.stop_price:
        return ExitOp(pos.stop_price, "trailing_stop")

    # 2) TARGET — gap-through fills at the open; else at the target level.
    if o >= pos.target_price:
        return ExitOp(o, "target")
    if h >= pos.target_price:
        return ExitOp(pos.target_price, "target")

    # 3) TIME STOP — held past the max window; book at the close.
    days_held = (day - pos.entry_date).days
    if days_held >= cfg.max_holding_days:
        return ExitOp(c, "time_stop")

    # 4) No exit — ratchet the trailing stop off the new high for tomorrow.
    #    The stop DISTANCE is frozen at entry (ATR-based); only the anchor
    #    (highest price) ratchets up, never down.
    if h > pos.highest_price:
        pos.highest_price = round(h, 2)
    pos.stop_price = round(pos.highest_price - pos.stop_distance, 2)
    return None
