"""Persistent pick ledger with a full status lifecycle.

Each pick is tracked from entry to exit. On every run the open positions are
marked against the current price: a dynamic trailing stop (ratcheted off the
highest price seen) protects gains, the target books profit, and a time stop
closes anything past the max holding window.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from qtr_results import config

logger = logging.getLogger("qtr_results.ledger")

PriceFn = Callable[[str], Optional[float]]


def load_ledger() -> List[Dict[str, Any]]:
    if not config.LEDGER_PATH.exists():
        return []
    try:
        return json.loads(config.LEDGER_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        logger.warning("Could not read ledger (%s); starting fresh.", e)
        return []


def save_ledger(picks: List[Dict[str, Any]]) -> None:
    config.ensure_state_dir()
    config.LEDGER_PATH.write_text(
        json.dumps(picks, indent=2, default=str), encoding="utf-8"
    )


def has_open(picks: List[Dict[str, Any]], symbol: str) -> bool:
    symbol = symbol.strip().upper()
    return any(p["symbol"] == symbol and p["status"] == "open" for p in picks)


def open_positions(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in picks if p["status"] == "open"]


def closed_positions(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in picks if p["status"] in ("booked", "exited")]


def add_pick(picks, analysis, plan, *, result_date: str, entry_date: Optional[str] = None):
    """Append a new pick unless one is already open for the symbol.

    Returns the created pick dict, or ``None`` if skipped (already open).
    """
    symbol = analysis.symbol
    if has_open(picks, symbol):
        logger.info("Skipping %s - already an open position.", symbol)
        return None

    entry_date = entry_date or date.today().isoformat()
    pick: Dict[str, Any] = {
        "symbol": symbol,
        "company": analysis.company_name,
        "result_quarter": analysis.latest_quarter,
        "result_date": result_date,
        "entry_date": entry_date,
        "entry_price": plan.entry_price,
        "target_pct": plan.target_pct,
        "target_price": plan.target_price,
        "trailing_stop_pct": plan.trailing_stop_pct,
        "highest_price": plan.entry_price,
        "stop_price": round(
            plan.entry_price * (1 - plan.trailing_stop_pct / 100.0), 2
        ),
        "status": "open",
        "method": plan.method,
        "strength_score": analysis.strength_score,
        "rationale": analysis.rationale,
        "target_notes": plan.notes,
        "exit_date": None,
        "exit_price": None,
        "realized_pct": None,
        "exit_reason": None,
    }
    picks.append(pick)
    logger.info(
        "Added pick %s @ Rs %.2f target %.1f%% stop %.1f%%",
        symbol, plan.entry_price, plan.target_pct, plan.trailing_stop_pct,
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

        # Ratchet the trailing stop off the highest price seen.
        if price > p["highest_price"]:
            p["highest_price"] = round(price, 2)
        p["stop_price"] = round(
            p["highest_price"] * (1 - p["trailing_stop_pct"] / 100.0), 2
        )
        p["last_price"] = round(price, 2)

        entry_dt = _parse_date(p.get("entry_date"))
        days_held = (as_of - entry_dt).days if entry_dt else 0

        reason: Optional[str] = None
        status: Optional[str] = None
        if price >= p["target_price"]:
            reason, status = "target", "booked"
        elif price <= p["stop_price"]:
            reason, status = "trailing_stop", "exited"
        elif days_held >= config.MAX_HOLDING_DAYS:
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
