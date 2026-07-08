"""
strategy.py
===========

The deterministic, point-in-time encoding of the quarterly-results playbook's
capital-management layer:

* **Sizing** — the live strategy is a signal/ledger tracker with no position
  sizing, so the backtest adds a risk-based sizer (same model as the swing
  backtest): risk a fixed % of equity per trade, where per-share risk is the
  initial trailing-stop distance ``entry * trailing_stop_pct/100``. Capped by a
  per-name concentration limit and available cash.
* **Exits** — a faithful OHLC-aware version of ``qtr_results.ledger``: a trailing
  stop ratcheted off the highest price seen books/protects the trade, the PE
  re-rating target takes profit, and a time-stop closes anything past the holding
  window. The trailing stop for day *t* is measured from the highest price through
  day *t-1* only (it is ratcheted AFTER the day's exits are evaluated), so there is
  no intraday look-ahead.

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


def size_position(
    entry_price: float,
    trailing_stop_pct: float,
    equity: float,
    cash: float,
    cfg: BacktestConfig,
) -> int:
    """Shares to buy under the 2%-risk rule + concentration + cash caps.

    ``0`` means the trade is not takeable with the current capital.
    """
    if entry_price <= 0 or trailing_stop_pct <= 0:
        return 0
    risk_per_share = entry_price * trailing_stop_pct / 100.0
    if risk_per_share <= 0:
        return 0

    risk_budget = equity * cfg.risk_per_trade_pct / 100.0
    shares = math.floor(risk_budget / risk_per_share)

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
) -> Position:
    """Build an open Position from the target plan (mirrors ledger.add_pick)."""
    stop_price = round(fill_price * (1 - plan.trailing_stop_pct / 100.0), 2)
    # Target is re-anchored to the ACTUAL fill price so the % target holds.
    target_price = round(fill_price * (1 + plan.target_pct / 100.0), 2)
    return Position(
        symbol=symbol,
        quantity=quantity,
        entry_price=round(fill_price, 2),
        entry_date=fill_date,
        target_price=target_price,
        target_pct=plan.target_pct,
        trailing_stop_pct=plan.trailing_stop_pct,
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
    trailing stop is then ratcheted off today's high for TOMORROW.
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
    if h > pos.highest_price:
        pos.highest_price = round(h, 2)
    pos.stop_price = round(pos.highest_price * (1 - pos.trailing_stop_pct / 100.0), 2)
    return None
