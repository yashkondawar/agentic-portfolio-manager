"""Average-cost paper-portfolio ledger over `transactions` / `positions`.

Average-cost accounting method (documented here since it drives every
number this module produces):

  BUY:
    new_qty      = old_qty + qty
    new_avg_cost = (old_qty * old_avg_cost + qty * price + fees) / new_qty
    (fees are capitalized into the cost basis, same as a real brokerage
    would typically do for a buy.)

  SELL:
    realized_pnl += qty * (price - avg_cost) - fees
    avg_cost stays UNCHANGED (average cost basis of the remaining shares
    doesn't move when you sell some of them)
    qty -= sold qty
    (fees reduce realized P&L directly on a sell, rather than adjusting
    the cost basis, since there's no remaining basis for them to load onto
    once the position is fully closed.)

`add_transaction` validates before inserting (SELL qty must not exceed the
currently held qty; BUY total cost must not exceed the current cash
balance) and then calls `rebuild_positions` so `positions` is always a
deterministic replay of `transactions` — never hand-patched.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from afund.config import load_settings

_VALID_SIDES = ("BUY", "SELL")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _resolve_instrument_id(conn: sqlite3.Connection, symbol_or_instrument_id: int | str) -> int:
    """Accept either an instruments.id (int) or a symbol (str) and return the id."""
    if isinstance(symbol_or_instrument_id, int):
        row = conn.execute(
            "SELECT id FROM instruments WHERE id = ?", (symbol_or_instrument_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"No instrument with id={symbol_or_instrument_id}")
        return row["id"]

    row = conn.execute(
        "SELECT id FROM instruments WHERE symbol = ? ORDER BY id LIMIT 1",
        (symbol_or_instrument_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No instrument with symbol={symbol_or_instrument_id!r}")
    return row["id"]


def cash_balance(conn: sqlite3.Connection) -> float:
    """initial_capital - sum(BUY qty*price+fees) + sum(SELL qty*price-fees).

    Computed fresh from `transactions` every call (not cached) so it's
    always consistent with the ledger, regardless of insert order.
    """
    settings = load_settings()
    initial_capital = float(settings.get("portfolio", {}).get("initial_capital", 0))

    rows = conn.execute("SELECT side, qty, price, fees FROM transactions").fetchall()
    cash = initial_capital
    for row in rows:
        qty = row["qty"] or 0.0
        price = row["price"] or 0.0
        fees = row["fees"] or 0.0
        if row["side"] == "BUY":
            cash -= qty * price + fees
        elif row["side"] == "SELL":
            cash += qty * price - fees
    return cash


def _current_qty(conn: sqlite3.Connection, instrument_id: int) -> float:
    row = conn.execute(
        "SELECT qty FROM positions WHERE instrument_id = ?", (instrument_id,)
    ).fetchone()
    return row["qty"] if row and row["qty"] is not None else 0.0


def add_transaction(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    symbol_or_instrument_id: int | str,
    side: str,
    qty: float,
    price: float,
    fees: float = 0.0,
    decision_id: int | None = None,
) -> int:
    """Validate, insert a transaction row, then rebuild `positions`.

    Validation (raises ValueError with a clear message on violation):
      - qty > 0, price > 0
      - side in ('BUY', 'SELL')
      - SELL: qty must not exceed the instrument's currently held qty
      - BUY: total cost (qty*price + fees) must not exceed current cash

    Returns the new transactions.id.
    """
    if side not in _VALID_SIDES:
        raise ValueError(f"side must be BUY|SELL, got {side!r}")
    if qty is None or qty <= 0:
        raise ValueError(f"qty must be > 0, got {qty!r}")
    if price is None or price <= 0:
        raise ValueError(f"price must be > 0, got {price!r}")
    fees = fees or 0.0
    if fees < 0:
        raise ValueError(f"fees must be >= 0, got {fees!r}")

    instrument_id = _resolve_instrument_id(conn, symbol_or_instrument_id)

    if side == "SELL":
        held_qty = _current_qty(conn, instrument_id)
        if qty > held_qty + 1e-9:
            raise ValueError(
                f"Cannot SELL qty={qty} of instrument_id={instrument_id}: "
                f"only {held_qty} currently held"
            )
    else:  # BUY
        total_cost = qty * price + fees
        available_cash = cash_balance(conn)
        if total_cost > available_cash + 1e-9:
            raise ValueError(
                f"Cannot BUY: total cost {total_cost} exceeds available cash {available_cash}"
            )

    cur = conn.execute(
        """
        INSERT INTO transactions
            (trade_date, instrument_id, side, qty, price, fees, decision_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (trade_date, instrument_id, side, qty, price, fees, decision_id, _now_iso()),
    )
    conn.commit()
    transaction_id = cur.lastrowid

    rebuild_positions(conn)

    return transaction_id


def rebuild_positions(conn: sqlite3.Connection) -> None:
    """Replay ALL transactions chronologically into `positions`.

    Idempotent and deterministic: clears `positions` and recomputes it from
    scratch from `transactions`, ordered by (trade_date, id) so same-day
    trades replay in insertion order. Positions with qty reduced to (near)
    zero are still kept as a row (qty ~0) so realized_pnl history isn't lost.
    """
    rows = conn.execute(
        """
        SELECT instrument_id, side, qty, price, fees
          FROM transactions
         ORDER BY trade_date ASC, id ASC
        """
    ).fetchall()

    book: dict[int, dict[str, float]] = {}
    for row in rows:
        instrument_id = row["instrument_id"]
        state = book.setdefault(instrument_id, {"qty": 0.0, "avg_cost": 0.0, "realized_pnl": 0.0})
        qty = row["qty"] or 0.0
        price = row["price"] or 0.0
        fees = row["fees"] or 0.0

        if row["side"] == "BUY":
            new_qty = state["qty"] + qty
            if new_qty > 0:
                state["avg_cost"] = (
                    state["qty"] * state["avg_cost"] + qty * price + fees
                ) / new_qty
            state["qty"] = new_qty
        else:  # SELL
            state["realized_pnl"] += qty * (price - state["avg_cost"]) - fees
            state["qty"] -= qty
            # avg_cost intentionally unchanged on SELL.

    conn.execute("DELETE FROM positions")
    today = dt.date.today().isoformat()
    for instrument_id, state in book.items():
        conn.execute(
            """
            INSERT INTO positions (instrument_id, qty, avg_cost, realized_pnl, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (instrument_id, state["qty"], state["avg_cost"], state["realized_pnl"], today),
        )
    conn.commit()
