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


# ── Entry-side filters (B4 / B6 / B7) ────────────────────────────────────────

def signal_day_confirmed(
    bars: Optional[pd.DataFrame], cfg: BacktestConfig
) -> tuple[bool, str]:
    """Signal-day confirmation: green day + uptrend.

    ``bars`` is the price frame ending on (and INCLUDING) the signal day. We
    check:
      * green close: ``close > open`` on the signal day
      * uptrend: signal-day close is above the ``trend_ma_period``-SMA AND the
        SMA has a non-negative slope (today's SMA >= SMA five sessions ago).

    Either check can be disabled from config. Returns ``(ok, reason)`` where
    ``reason`` is the first failing check (empty on success).
    """
    if bars is None or bars.empty:
        return False, "no_bars"

    last = bars.iloc[-1]
    if cfg.require_signal_day_green and float(last["Close"]) <= float(last["Open"]):
        return False, "red_signal_day"

    if cfg.require_uptrend:
        p = cfg.trend_ma_period
        if len(bars) < p + 5:
            return False, "insufficient_ma_history"
        sma = bars["Close"].rolling(p).mean()
        if pd.isna(sma.iloc[-1]) or pd.isna(sma.iloc[-6]):
            return False, "insufficient_ma_history"
        if float(last["Close"]) < float(sma.iloc[-1]):
            return False, "below_ma"
        if float(sma.iloc[-1]) < float(sma.iloc[-6]):
            return False, "ma_slope_negative"

    return True, ""


def liquidity_ok(bars: Optional[pd.DataFrame], min_rupee_turnover: float) -> bool:
    """Median 20-day rupee turnover ≥ threshold.

    Uses close × volume (a reasonable proxy for delivery turnover; VWAP would be
    marginally better but isn't available from yfinance daily bars).
    """
    if bars is None or bars.empty or "Volume" not in bars.columns:
        return False
    tail = bars.tail(20)
    if len(tail) < 10:
        return False
    turnover = (tail["Close"].astype(float) * tail["Volume"].astype(float)).median()
    return bool(turnover >= min_rupee_turnover)


def market_regime_ok(
    benchmark: Optional[pd.DataFrame], cfg: BacktestConfig
) -> bool:
    """Point-in-time market-regime gate for NEW entries.

    ``benchmark`` is the benchmark (Nifty) OHLC frame ending on/including the
    signal day (leak-free — the caller passes ``benchmark_as_of(day)``). Returns
    ``True`` (allow new buys) when the market is in an uptrend:

      * benchmark close is above its ``regime_ma_period``-SMA, and
      * (optionally) that SMA is non-declining (today's SMA >= SMA five sessions
        ago) when ``regime_require_slope`` is set.

    The point of the gate is to stop opening fresh earnings-momentum longs into a
    broad market downtrend, where they take correlated drawdowns regardless of how
    good the individual result was. Disabled (always ``True``) when
    ``regime_filter`` is off or there is insufficient history.
    """
    if not cfg.regime_filter:
        return True
    if benchmark is None or benchmark.empty or "Close" not in benchmark.columns:
        return True  # data-gap safe: don't block when we can't judge
    p = cfg.regime_ma_period
    if len(benchmark) < p + 5:
        return True
    close = benchmark["Close"].astype(float)
    sma = close.rolling(p).mean()
    if pd.isna(sma.iloc[-1]):
        return True
    if float(close.iloc[-1]) < float(sma.iloc[-1]):
        return False
    if cfg.regime_require_slope and not pd.isna(sma.iloc[-6]):
        if float(sma.iloc[-1]) < float(sma.iloc[-6]):
            return False
    return True


def pre_declaration_rs(
    stock_bars: Optional[pd.DataFrame],
    bench_bars: Optional[pd.DataFrame],
    lookback: int,
) -> Optional[float]:
    """Pre-declaration relative strength: stock return minus benchmark return
    over the trailing ``lookback`` sessions, measured as-of the last row of each
    frame (both must be sliced to bars ``<=`` the evaluation day — leak-free).

    A positive value means the stock has been out-running the market into its
    result — the "informed drift" the anticipation mode (B10) trades on. Returns
    ``None`` when either series is too short to measure.
    """
    if stock_bars is None or len(stock_bars) < lookback + 1:
        return None
    if bench_bars is None or len(bench_bars) < lookback + 1:
        return None
    s = stock_bars["Close"].astype(float)
    b = bench_bars["Close"].astype(float)
    s0, s1 = float(s.iloc[-1 - lookback]), float(s.iloc[-1])
    b0, b1 = float(b.iloc[-1 - lookback]), float(b.iloc[-1])
    if s0 <= 0 or b0 <= 0:
        return None
    return (s1 / s0 - 1.0) - (b1 / b0 - 1.0)


def clamp_static_target(strength_score: float, cfg: BacktestConfig) -> float:
    """Override the live static-tier target using the backtest's tighter tiers.

    The live tiers assign the full 20 % target to any strong result without a
    valuation anchor (banks, PSUs, holding cos). We halve them because you have
    no PE-rerating math to justify the aggressive target.
    """
    for threshold, pct in cfg.static_target_tiers:
        if strength_score >= threshold:
            return float(pct)
    return cfg.target_min_pct


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
    sector: str = "UNKNOWN",
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
        sector=sector or "UNKNOWN",
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

    # B10 — a pre-declaration ("awaiting result") position is HELD through to the
    # result decision: the whole thesis is to sit through the pre-result window
    # and let the announcement (graded in the engine) decide ride-or-dump, so we
    # don't let the trailing stop / target / time-stop knock us out beforehand.
    # We still ratchet the high so the stop is meaningful once the ride begins.
    if pos.awaiting_result:
        if h > pos.highest_price:
            pos.highest_price = round(h, 2)
        return None

    # 1) TRAILING STOP — gap-through fills at the open; else at the stop level.
    if o <= pos.stop_price:
        return ExitOp(o, "trailing_stop")
    if low <= pos.stop_price:
        return ExitOp(pos.stop_price, "trailing_stop")

    # 2) TARGET — gap-through fills at the open; else at the target level.
    #    Skipped entirely in "ride-the-wave" mode so winners run to the trail.
    if not cfg.disable_profit_target:
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
