"""The once-a-day live workflow for the ATH breakout sleeve.

Run this after the close. It marks the book you already hold, tells you what
to sell tomorrow, and ranks what to buy with whatever slots that frees.

Entry and exit are evaluated with the very same functions the backtest uses
(:mod:`backtesting.breakout_ath.signals`), so the live sleeve cannot drift
away from the strategy that was validated.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from . import signals
from .config import STATE_PATH, AthBreakoutConfig
from .data import load_prices
from .engine import _reset_key
from .universe import industry_map

logger = logging.getLogger(__name__)

STATE_VERSION = 1


# ── Persisted state ──────────────────────────────────────────────────────────


def empty_state(capital: float) -> dict:
    return {
        "version": STATE_VERSION,
        "capital": float(capital),
        "cash": float(capital),
        "budget": None,
        "budget_key": None,
        "positions": [],
        "closed": [],
        "last_session": None,
    }


def load_state(path: Path, capital: float) -> dict:
    path = Path(path)
    if not path.exists():
        return empty_state(capital)
    try:
        return normalize_state(json.loads(path.read_text(encoding="utf-8")), capital)
    except (json.JSONDecodeError, OSError):
        logger.warning("Unreadable state at %s; starting a fresh book", path)
        return empty_state(capital)


def normalize_state(payload: Any, capital: float) -> dict:
    if not isinstance(payload, dict):
        return empty_state(capital)
    state = empty_state(capital)
    state.update({k: v for k, v in payload.items() if k in state})
    state["positions"] = [_normalize_position(p) for p in payload.get("positions", [])]
    state["closed"] = list(payload.get("closed", []))
    return state


def save_state(path: Path, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _normalize_position(item: Any) -> dict:
    item = dict(item or {})
    return {
        "symbol": str(item.get("symbol", "")).upper().replace(".NS", ""),
        "industry": item.get("industry", "Unknown"),
        "entry_date": str(item.get("entry_date", "")),
        "entry_price": float(item.get("entry_price", 0.0)),
        "quantity": float(item.get("quantity", 0.0)),
        "anchor": float(item.get("anchor", item.get("entry_price", 0.0))),
    }


# ── The daily run ────────────────────────────────────────────────────────────


def run_daily(
    cfg: Optional[AthBreakoutConfig] = None,
    *,
    state_path: Optional[Path] = None,
    portfolio_state: Optional[dict] = None,
    as_of: Optional[date] = None,
    download: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Produce today's exit and entry instructions.

    Pass ``portfolio_state`` to drive the run from a caller-held book (that is
    what the UI does); otherwise the sleeve's own JSON state file is used.
    """
    cfg = cfg or AthBreakoutConfig()
    cfg.validate()

    path = Path(state_path or STATE_PATH)
    state = (
        normalize_state(portfolio_state, cfg.start_capital)
        if portfolio_state is not None
        else load_state(path, cfg.start_capital)
    )

    prices = load_prices(cfg, download=download)
    closes = prices.closes
    if as_of is not None:
        closes = closes.loc[: pd.Timestamp(as_of)]
    if closes.empty:
        raise RuntimeError("no price history available for the daily run")

    session = closes.index[-1]
    today = session.date()
    live = closes.iloc[-1]
    industries = industry_map()

    def industry_of(symbol: str, fallback: str = "Unknown") -> str:
        return industries.get(symbol) or industries.get(f"{symbol}.NS", fallback)

    exits = _exit_actions(cfg, state, live, today, industry_of)
    for item in exits:
        item["exit_date"] = today.isoformat()
    _apply_exits(cfg, state, exits)

    marks = {p["symbol"]: float(live.get(p["symbol"], 0.0)) for p in state["positions"]}
    deployed = sum(
        p["quantity"] * marks.get(p["symbol"], 0.0) for p in state["positions"]
    )
    equity = state["cash"] + deployed

    _refresh_budget(cfg, state, today, equity)
    entries = _entry_actions(cfg, state, closes, live, industry_of)

    state["last_session"] = today.isoformat()
    if persist and portfolio_state is None:
        save_state(path, state)

    report = {
        "as_of": today.isoformat(),
        "equity": equity,
        "cash": state["cash"],
        "deployed": deployed,
        "open_positions": len(state["positions"]),
        "free_slots": max(0, cfg.max_positions - len(state["positions"])),
        "budget_per_slot": state["budget"],
        "exits": exits,
        "entries": entries,
        "holds": _hold_actions(cfg, state, live),
        "state": state,
    }
    report["report"] = render_report(report)
    return report


def _exit_actions(
    cfg: AthBreakoutConfig,
    state: dict,
    live: pd.Series,
    today: date,
    industry_of: Any,
) -> List[dict]:
    """Positions whose close has broken the trailing stop."""
    out: List[dict] = []
    for pos in state["positions"]:
        price = float(live.get(pos["symbol"], float("nan")))
        if not price or pd.isna(price):
            continue
        anchor = max(pos["anchor"], price)
        pos["anchor"] = anchor
        stop = anchor * cfg.stop_multiple
        if price < stop:
            proceeds = pos["quantity"] * price
            out.append(
                {
                    "action": "EXIT",
                    "symbol": pos["symbol"],
                    "industry": industry_of(pos["symbol"], pos["industry"]),
                    "reason": "TRAIL_SL",
                    "price": price,
                    "quantity": pos["quantity"],
                    "anchor": anchor,
                    "stop_level": stop,
                    "entry_price": pos["entry_price"],
                    "entry_date": pos["entry_date"],
                    "return_pct": (
                        price / pos["entry_price"] - 1.0 if pos["entry_price"] else 0.0
                    ),
                    "proceeds": proceeds,
                    "note": (
                        f"close {price:,.2f} is below the trailing stop {stop:,.2f} "
                        f"({cfg.sl_pct:.0%} under the {anchor:,.2f} peak close)"
                    ),
                }
            )
    return out


def _apply_exits(cfg: AthBreakoutConfig, state: dict, exits: List[dict]) -> None:
    if not exits:
        return
    sold = {e["symbol"] for e in exits}
    for e in exits:
        cost = e["proceeds"] * cfg.cost_rate
        e["cost"] = cost
        state["cash"] += e["proceeds"] - cost
        state["closed"].append(
            {
                "symbol": e["symbol"],
                "entry_date": e["entry_date"],
                "exit_date": e.get("exit_date"),
                "entry_price": e["entry_price"],
                "exit_price": e["price"],
                "quantity": e["quantity"],
                "exit_reason": e["reason"],
            }
        )
    state["positions"] = [p for p in state["positions"] if p["symbol"] not in sold]


def _refresh_budget(
    cfg: AthBreakoutConfig, state: dict, today: date, equity: float
) -> None:
    """Reset the per-slot budget on the configured cadence."""
    key = str(_reset_key(today, cfg.slot_reset_freq))
    if state.get("budget") is None or state.get("budget_key") != key:
        state["budget"] = equity / cfg.max_positions
        state["budget_key"] = key


def _entry_actions(
    cfg: AthBreakoutConfig,
    state: dict,
    closes: pd.DataFrame,
    live: pd.Series,
    industry_of: Any,
) -> List[dict]:
    """Rank today's breakouts and fill whatever slots are free."""
    free = cfg.max_positions - len(state["positions"])
    if free <= 0:
        return []

    frame = closes.ffill()
    eligible = signals.entry_matrix(
        frame, lookback=cfg.lookback, floor=cfg.ath_floor
    ).iloc[-1]
    ranks = signals.ranking_matrix(
        frame, cfg.selection_rule, cfg.momentum_lookback
    ).iloc[-1]

    held = {p["symbol"] for p in state["positions"]}
    candidates = [
        s
        for s in eligible.index
        if bool(eligible.get(s))
        and s not in held
        and not pd.isna(live.get(s))
        and float(live.get(s, 0.0)) > 0.0
    ]
    candidates.sort(key=lambda s: _score(ranks.get(s)), reverse=True)

    budget = float(state["budget"] or 0.0)
    out: List[dict] = []
    cash = state["cash"]
    for symbol in candidates:
        if len(out) >= free:
            break
        spend = min(budget, cash)
        if spend <= 0.0:
            break
        price = float(live[symbol])
        cost = spend * cfg.cost_rate
        value = spend - cost
        qty = value / price
        cash -= spend
        out.append(
            {
                "action": "ENTER",
                "symbol": symbol,
                "industry": industry_of(symbol),
                "reason": "ENTRY",
                "price": price,
                "quantity": qty,
                "budget": spend,
                "cost": cost,
                "value": value,
                "momentum": _score(ranks.get(symbol)),
                "initial_stop": price * cfg.stop_multiple,
                "note": (
                    f"closed at a {cfg.lookback}-session high and sits within "
                    f"{cfg.ath_band:.0%} of its lifetime closing high"
                ),
            }
        )
    return out


def _hold_actions(cfg: AthBreakoutConfig, state: dict, live: pd.Series) -> List[dict]:
    out = []
    for pos in state["positions"]:
        price = float(live.get(pos["symbol"], float("nan")))
        if pd.isna(price):
            continue
        stop = pos["anchor"] * cfg.stop_multiple
        out.append(
            {
                "action": "HOLD",
                "symbol": pos["symbol"],
                "price": price,
                "anchor": pos["anchor"],
                "stop_level": stop,
                "headroom_pct": price / stop - 1.0 if stop else 0.0,
                "return_pct": (
                    price / pos["entry_price"] - 1.0 if pos["entry_price"] else 0.0
                ),
                "entry_date": pos["entry_date"],
            }
        )
    out.sort(key=lambda r: r["headroom_pct"])
    return out


def apply_entries(state: dict, entries: List[dict], day: date) -> dict:
    """Commit the suggested entries to the book (used after they actually fill)."""
    for e in entries:
        state["cash"] -= e["budget"]
        state["positions"].append(
            {
                "symbol": e["symbol"],
                "industry": e["industry"],
                "entry_date": day.isoformat(),
                "entry_price": e["price"],
                "quantity": e["quantity"],
                "anchor": e["price"],
            }
        )
    return state


def _score(value: Any) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float("-inf")
    return f if f == f else float("-inf")


def render_report(data: dict) -> str:
    lines = [
        f"ATH breakout sleeve - {data['as_of']}",
        f"  equity {data['equity']:,.0f} | cash {data['cash']:,.0f} "
        f"| {data['open_positions']} open | {data['free_slots']} slots free",
    ]
    if data["exits"]:
        lines.append(f"  SELL ({len(data['exits'])}):")
        for e in data["exits"]:
            lines.append(f"    {e['symbol']:<14} {e['return_pct']:+7.1%}  {e['note']}")
    else:
        lines.append("  SELL: nothing - no position has broken its trailing stop.")

    if data["entries"]:
        lines.append(f"  BUY ({len(data['entries'])}):")
        for e in data["entries"]:
            lines.append(
                f"    {e['symbol']:<14} {e['price']:>10,.2f}  "
                f"qty {e['quantity']:>10,.2f}  stop {e['initial_stop']:,.2f}"
            )
    else:
        lines.append("  BUY: nothing - no fresh breakout, or the book is full.")

    tight = [h for h in data["holds"] if h["headroom_pct"] < 0.05]
    if tight:
        lines.append("  Close to their stops:")
        for h in tight:
            lines.append(
                f"    {h['symbol']:<14} {h['headroom_pct']:+6.1%} above stop "
                f"{h['stop_level']:,.2f}"
            )
    return "\n".join(lines)
