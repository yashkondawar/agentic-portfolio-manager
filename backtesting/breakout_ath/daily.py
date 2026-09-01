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
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from . import signals
from .config import STATE_PATH, AthBreakoutConfig
from .data import load_prices
from .engine import _reset_key
from .universe import industry_map

logger = logging.getLogger(__name__)

STATE_VERSION = 2


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
        "pending_entries": [],
        "pending_session": None,
        "marks": {},
        "equity": float(capital),
        "opened_on": None,
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
    state["pending_entries"] = list(payload.get("pending_entries", []))
    state["marks"] = dict(payload.get("marks", {}))
    state["version"] = STATE_VERSION
    return state


def save_state(path: Path, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _canonical(symbol: str) -> str:
    """The one symbol form the sleeve uses internally.

    Price columns, the industry map and the backtest all key on ``SYMBOL.NS``.
    A position stored as a bare ``SYMBOL`` silently fails every one of those
    lookups, so it is never marked, never exited, and gets suggested again as
    if it were not held. Accept either form on the way in, store one on the
    way out.
    """
    text = str(symbol or "").strip().upper()
    if text.endswith(".NS"):
        text = text[:-3]
    return f"{text}.NS" if text else ""


def _normalize_position(item: Any) -> dict:
    item = dict(item or {})
    return {
        "symbol": _canonical(item.get("symbol", "")),
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

    # end_date pins the *backtest* window so the dossier stays reproducible.
    # A live run must read to the run-through date instead, or it scans a
    # frozen close forever and every session looks identical.
    through = as_of or date.today()
    cfg = replace(cfg, end_date=through)

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
    # Two views, exactly as the engine keeps them: entries may only fire on a
    # session the stock actually traded, but marking and stop-checking use the
    # last known close so a non-trading day cannot blank out the book.
    live = closes.iloc[-1]
    filled = closes.ffill().iloc[-1]
    industries = industry_map()

    def industry_of(symbol: str, fallback: str = "Unknown") -> str:
        return industries.get(symbol) or industries.get(f"{symbol}.NS", fallback)

    exits = _exit_actions(cfg, state, filled, today, industry_of)
    for item in exits:
        item["exit_date"] = today.isoformat()
    _apply_exits(cfg, state, exits)

    marks = {p["symbol"]: _mark(filled, p) for p in state["positions"]}
    deployed = sum(
        p["quantity"] * marks.get(p["symbol"], 0.0) for p in state["positions"]
    )
    equity = state["cash"] + deployed

    _refresh_budget(cfg, state, today, equity)
    entries = _entry_actions(cfg, state, closes, live, industry_of)

    # The suggestions are parked on the book rather than committed: nothing has
    # actually been bought yet. They are committed by confirm_fills once the
    # orders really fill, which is also where a different fill price is taken
    # into account.
    state["pending_entries"] = entries
    state["pending_session"] = today.isoformat()
    state["marks"] = marks
    state["equity"] = equity
    state["last_session"] = today.isoformat()
    if state.get("opened_on") is None:
        state["opened_on"] = today.isoformat()
    if persist and portfolio_state is None:
        save_state(path, state)

    holds = _hold_actions(cfg, state, filled)
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
        "holds": holds,
        "freshness": _freshness(today.isoformat(), date.today()),
        "persisted": bool(persist and portfolio_state is None),
        "state": state,
    }
    report["report"] = render_report(report)
    return report


def _mark(prices: pd.Series, position: dict) -> float:
    """Last known close for a holding, never NaN.

    A name that has stopped trading entirely still has to be worth something on
    the book; falling back to the entry price keeps equity a real number rather
    than letting one stale symbol turn the whole total into NaN.
    """
    price = prices.get(position["symbol"])
    if price is None or pd.isna(price) or float(price) <= 0.0:
        return float(position.get("entry_price") or 0.0)
    return float(price)


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
        entry_value = e["entry_price"] * e["quantity"]
        pnl = e["proceeds"] - cost - entry_value
        e["pnl"] = pnl
        state["closed"].append(
            {
                "symbol": e["symbol"],
                "industry": e.get("industry", "Unknown"),
                "entry_date": e["entry_date"],
                "exit_date": e.get("exit_date"),
                "entry_price": e["entry_price"],
                "exit_price": e["price"],
                "quantity": e["quantity"],
                "exit_reason": e["reason"],
                "pnl": pnl,
                "pnl_pct": e["return_pct"] * 100.0,
                "proceeds": e["proceeds"],
                "cost": cost,
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


def apply_entries(
    state: dict, entries: List[dict], day: date, *, cost_rate: float = 0.0025
) -> dict:
    """Commit filled entries to the book.

    Each entry carries the budget the run allocated to it. If it actually
    filled at a different price than the close the suggestion was priced off,
    pass that price as ``fill_price``: the budget is what was spent either way,
    so the quantity is re-derived rather than the risk silently changing.
    """
    for e in entries:
        symbol = _canonical(e.get("symbol", ""))
        budget = float(e.get("budget") or 0.0)
        price = float(e.get("fill_price") or e.get("price") or 0.0)
        if not symbol or budget <= 0.0 or price <= 0.0:
            continue
        budget = min(budget, state["cash"])
        if budget <= 0.0:
            continue
        cost = budget * cost_rate
        quantity = (budget - cost) / price
        state["cash"] -= budget
        state["positions"].append(
            {
                "symbol": symbol,
                "industry": e.get("industry", "Unknown"),
                "entry_date": day.isoformat(),
                "entry_price": price,
                "quantity": quantity,
                "anchor": price,
            }
        )
    return state


def confirm_fills(
    fills: List[dict],
    *,
    day: Optional[date] = None,
    state_path: Optional[Path] = None,
    capital: float = 0.0,
    cost_rate: float = 0.0025,
) -> dict:
    """Commit some or all of the parked suggestions, then save the book.

    Each fill is matched to its parked suggestion by symbol, so a caller can
    confirm with nothing but a symbol and let the budget and price default to
    what the run proposed. Anything left in ``pending_entries`` is dropped: a
    suggestion you chose not to place should not linger and be mistaken for a
    holding.
    """
    path = Path(state_path or STATE_PATH)
    state = load_state(path, capital)

    parked = {_canonical(e.get("symbol", "")): e for e in state["pending_entries"]}
    merged = []
    for fill in fills:
        symbol = _canonical(fill.get("symbol", ""))
        entry = dict(parked.get(symbol) or {})
        entry.update({k: v for k, v in fill.items() if v not in (None, "")})
        entry["symbol"] = symbol
        merged.append(entry)

    apply_entries(state, merged, day or date.today(), cost_rate=cost_rate)
    state["pending_entries"] = []
    state["pending_session"] = None
    save_state(path, state)
    return state


# ── Book view ────────────────────────────────────────────────────────────────


def ledger_snapshot(
    cfg: Optional[AthBreakoutConfig] = None,
    *,
    state_path: Optional[Path] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """The saved book, read straight off disk — no network, no price download.

    Positions are marked at the closes the last run saw, which is why the
    freshness block matters: an old book prices every stop off an old close.
    """
    cfg = cfg or AthBreakoutConfig()
    path = Path(state_path or STATE_PATH)
    if not path.exists():
        return {"as_of": None, "exists": False}

    state = load_state(path, cfg.start_capital)
    marks = state.get("marks") or {}
    holdings = []
    deployed = 0.0
    for pos in state["positions"]:
        price = float(marks.get(pos["symbol"]) or pos["entry_price"])
        deployed += pos["quantity"] * price
        stop = pos["anchor"] * cfg.stop_multiple
        holdings.append(
            {
                "symbol": pos["symbol"],
                "industry": pos.get("industry", "Unknown"),
                "quantity": pos["quantity"],
                "entry_date": pos["entry_date"],
                "entry_price": pos["entry_price"],
                "price": price,
                "value": pos["quantity"] * price,
                "anchor": pos["anchor"],
                "stop_level": stop,
                "headroom_pct": (price / stop - 1.0) * 100.0 if stop else 0.0,
                "return_pct": (
                    (price / pos["entry_price"] - 1.0) * 100.0
                    if pos["entry_price"]
                    else 0.0
                ),
            }
        )
    holdings.sort(key=lambda r: r["headroom_pct"])

    closed = state.get("closed") or []
    realized = sum(float(t.get("pnl") or 0.0) for t in closed)
    wins = [t for t in closed if float(t.get("pnl") or 0.0) > 0]
    equity = state["cash"] + deployed
    capital = float(state.get("capital") or cfg.start_capital)

    return {
        "exists": True,
        "as_of": state.get("last_session"),
        "book": {
            "equity": equity,
            "cash": state["cash"],
            "deployed": deployed,
            "exposure_pct": round(deployed / equity * 100.0, 1) if equity else 0.0,
            "open_positions": len(state["positions"]),
            "free_slots": max(0, cfg.max_positions - len(state["positions"])),
            "budget_per_slot": state.get("budget"),
            "realized_pnl": realized,
            "closed_trades": len(closed),
            "win_rate_pct": (
                round(len(wins) / len(closed) * 100.0, 1) if closed else 0.0
            ),
            "starting_capital": capital,
            "total_return_pct": (
                round((equity / capital - 1.0) * 100.0, 2) if capital else 0.0
            ),
            "opened_on": state.get("opened_on"),
        },
        "holdings": holdings,
        "pending_entries": state.get("pending_entries") or [],
        "pending_session": state.get("pending_session"),
        "tradebook": list(reversed(closed)),
        "num_closed": len(closed),
        "freshness": _freshness(state.get("last_session"), today or date.today()),
    }


def _freshness(last_session: Optional[str], today: date) -> dict:
    """How many weekdays the saved book is behind, ignoring weekends."""
    if not last_session:
        return {"stale": False, "last_session": None, "weekdays_behind": 0}
    try:
        last = date.fromisoformat(str(last_session))
    except ValueError:
        return {"stale": False, "last_session": last_session, "weekdays_behind": 0}
    behind = sum(
        1
        for offset in range(1, (today - last).days + 1)
        if (last + timedelta(days=offset)).weekday() < 5
    )
    return {
        "stale": behind > 1,
        "last_session": last.isoformat(),
        "today": today.isoformat(),
        "weekdays_behind": behind,
    }


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
