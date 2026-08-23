"""Persistent pick ledger with a full status lifecycle.

Each pick is tracked from entry to exit. On every run the open positions are
marked against the current price: a dynamic trailing stop (ratcheted off the
highest price seen) protects gains, the target books profit, and a time stop
closes anything past the max holding window.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from qtr_results import config
from core.storage import get_document, set_document

logger = logging.getLogger("qtr_results.ledger")

PriceFn = Callable[[str], Optional[float]]


def load_ledger() -> List[Dict[str, Any]]:
    stored = get_document("qtr_results", "ledger")
    if stored is not None:
        return stored
    if config.LEDGER_PATH.exists():
        try:
            import json

            legacy = json.loads(config.LEDGER_PATH.read_text(encoding="utf-8"))
            set_document("qtr_results", "ledger", legacy)
            return legacy
        except (ValueError, OSError) as e:
            logger.warning("Could not import legacy ledger (%s); starting fresh.", e)
    return []


def save_ledger(picks: List[Dict[str, Any]]) -> None:
    set_document("qtr_results", "ledger", picks)


def has_open(picks: List[Dict[str, Any]], symbol: str) -> bool:
    symbol = symbol.strip().upper()
    return any(p["symbol"] == symbol and p["status"] == "open" for p in picks)


def open_positions(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in picks if p["status"] == "open"]


def closed_positions(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in picks if p["status"] in ("booked", "exited")]


def add_pick(
    picks,
    analysis,
    plan,
    *,
    result_date: str,
    entry_date: Optional[str] = None,
    quantity: int = 0,
    invested: float = 0.0,
):
    """Append a new pick unless one is already open for the symbol.

    ``quantity`` / ``invested`` come from the portfolio sizing layer (0 when the
    strategy is run as a pure signal tracker without a capital model). The stop
    is stored as an absolute ₹ distance (``stop_distance_abs``) so the ratchet is
    volatility-based; the percent form is kept for display / back-compat.
    Returns the created pick dict, or ``None`` if skipped (already open).
    """
    symbol = analysis.symbol
    if has_open(picks, symbol):
        logger.info("Skipping %s - already an open position.", symbol)
        return None

    entry_date = entry_date or date.today().isoformat()
    stop_abs = getattr(plan, "stop_distance_abs", None)
    if stop_abs and stop_abs > 0:
        stop_price = round(plan.entry_price - stop_abs, 2)
    else:
        stop_price = round(plan.entry_price * (1 - plan.trailing_stop_pct / 100.0), 2)
    pick: Dict[str, Any] = {
        "symbol": symbol,
        "company": analysis.company_name,
        "result_quarter": analysis.latest_quarter,
        "result_date": result_date,
        "entry_date": entry_date,
        "entry_price": plan.entry_price,
        "quantity": quantity,
        "invested": round(invested, 2),
        "target_pct": plan.target_pct,
        "target_price": plan.target_price,
        "trailing_stop_pct": plan.trailing_stop_pct,
        "stop_distance_abs": stop_abs,
        "stop_basis": getattr(plan, "stop_basis", "ratio"),
        "max_holding_days": plan.max_holding_days,
        "highest_price": plan.entry_price,
        "stop_price": stop_price,
        "status": "open",
        "method": plan.method,
        "strength_score": analysis.strength_score,
        "conviction": getattr(analysis, "conviction", None),
        "conviction_verdict": getattr(analysis, "conviction_verdict", ""),
        "conviction_summary": getattr(analysis, "conviction_summary", ""),
        "rationale": analysis.rationale,
        "target_notes": plan.notes,
        "exit_date": None,
        "exit_price": None,
        "realized_pct": None,
        "exit_reason": None,
    }
    picks.append(pick)
    logger.info(
        "Added pick %s x%d @ Rs %.2f target %.1f%% stop Rs %.2f",
        symbol, quantity, plan.entry_price, plan.target_pct, stop_price,
    )
    return pick


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError:
        return None


def update_open_positions(
    picks: List[Dict[str, Any]],
    price_fn: PriceFn,
    *,
    as_of: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Mark open positions against current prices; return those closed this run."""
    as_of = as_of or date.today()
    newly_closed: List[Dict[str, Any]] = []

    for p in open_positions(picks):
        price = price_fn(p["symbol"])
        if price is None or price <= 0:
            logger.warning("No price for open position %s; leaving unchanged.", p["symbol"])
            continue

        # Ratchet the trailing stop off the highest price seen. Prefer the
        # absolute ATR-based distance; fall back to the legacy percent for
        # positions opened before the ATR sizing was added.
        if price > p["highest_price"]:
            p["highest_price"] = round(price, 2)
        stop_abs = p.get("stop_distance_abs")
        if stop_abs and stop_abs > 0:
            p["stop_price"] = round(p["highest_price"] - stop_abs, 2)
        else:
            p["stop_price"] = round(
                p["highest_price"] * (1 - p["trailing_stop_pct"] / 100.0), 2
            )
        p["last_price"] = round(price, 2)

        entry_dt = _parse_date(p.get("entry_date"))
        days_held = (as_of - entry_dt).days if entry_dt else 0
        max_hold = p.get("max_holding_days") or config.MAX_HOLDING_DAYS

        reason: Optional[str] = None
        status: Optional[str] = None
        # Ride-the-wave: when the fixed profit target is disabled a winner is
        # only closed by the trailing stop or the time-stop, never clipped at the
        # target. Positions opened under the old capped mode keep their target.
        target_active = not config.DISABLE_PROFIT_TARGET
        if target_active and price >= p["target_price"]:
            reason, status = "target", "booked"
        elif price <= p["stop_price"]:
            reason, status = "trailing_stop", "exited"
        elif days_held >= max_hold:
            reason, status = "time_stop", "exited"

        if reason:
            p["status"] = status
            p["exit_reason"] = reason
            p["exit_date"] = as_of.isoformat()
            p["exit_price"] = round(price, 2)
            p["realized_pct"] = round(
                (price - p["entry_price"]) / p["entry_price"] * 100.0, 2
            )
            newly_closed.append(p)
            logger.info(
                "Closed %s (%s) @ Rs %.2f -> %.2f%%",
                p["symbol"], reason, price, p["realized_pct"],
            )

    return newly_closed
