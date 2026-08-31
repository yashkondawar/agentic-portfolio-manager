"""Daily NAV computation for the paper portfolio.

`compute_nav` marks every open position to market (carry-forward pricing —
see `price_on_or_before`), sums it with the cash balance, and upserts one
row per date into `nav_history`. `run_daily_nav` is the orchestrator-facing
job function (wired into the `daily_nav` trigger, and as the final step of
`daily_data`).
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from afund.data.base import log_job_run
from afund.portfolio.ledger import cash_balance


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def price_on_or_before(conn: sqlite3.Connection, instrument_id: int, date: str) -> float | None:
    """Most recent known price for `instrument_id` on or before `date`.

    STOCK/ETF/INDEX_FUND -> daily_prices.close.
    MUTUAL_FUND          -> mf_navs.nav, joined via instruments.amfi_scheme_code.
    Returns None if there is no price at or before `date` at all (carry-forward
    has nothing to carry).
    """
    inst = conn.execute(
        "SELECT instrument_type, amfi_scheme_code FROM instruments WHERE id = ?",
        (instrument_id,),
    ).fetchone()
    if inst is None:
        return None

    if inst["instrument_type"] == "MUTUAL_FUND":
        scheme_code = inst["amfi_scheme_code"]
        if not scheme_code:
            return None
        row = conn.execute(
            """
            SELECT nav FROM mf_navs
             WHERE scheme_code = ? AND date <= ? AND nav IS NOT NULL
             ORDER BY date DESC LIMIT 1
            """,
            (scheme_code, date),
        ).fetchone()
        return row["nav"] if row else None

    row = conn.execute(
        """
        SELECT close FROM daily_prices
         WHERE instrument_id = ? AND date <= ? AND close IS NOT NULL
         ORDER BY date DESC LIMIT 1
        """,
        (instrument_id, date),
    ).fetchone()
    return row["close"] if row else None


def compute_nav(conn: sqlite3.Connection, date: str) -> dict:
    """Mark-to-market the portfolio as of `date` and upsert `nav_history`.

    market_value = sum(qty * price_on_or_before(instrument, date)) over all
    open positions (qty != 0). Positions with NO price at all (not even a
    carry-forward candidate) are skipped from market_value and reported in
    the returned dict's `missing_prices` list rather than crashing the run.

    daily_return is computed against the immediately preceding nav_history
    row (by date, not necessarily yesterday) as
    (total_nav - prev_total_nav) / prev_total_nav; None if there is no prior
    row or prev_total_nav is 0.
    """
    positions = conn.execute(
        "SELECT instrument_id, qty FROM positions WHERE qty != 0"
    ).fetchall()

    market_value = 0.0
    missing_prices: list[int] = []
    for pos in positions:
        price = price_on_or_before(conn, pos["instrument_id"], date)
        if price is None:
            missing_prices.append(pos["instrument_id"])
            continue
        market_value += pos["qty"] * price

    cash = cash_balance(conn)
    total_nav = market_value + cash

    prev_row = conn.execute(
        "SELECT total_nav FROM nav_history WHERE date < ? ORDER BY date DESC LIMIT 1",
        (date,),
    ).fetchone()
    daily_return = None
    if prev_row is not None and prev_row["total_nav"]:
        daily_return = (total_nav - prev_row["total_nav"]) / prev_row["total_nav"]

    conn.execute(
        """
        INSERT INTO nav_history (date, market_value, cash, total_nav, daily_return)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            market_value = excluded.market_value,
            cash = excluded.cash,
            total_nav = excluded.total_nav,
            daily_return = excluded.daily_return
        """,
        (date, market_value, cash, total_nav, daily_return),
    )
    conn.commit()

    return {
        "date": date,
        "market_value": market_value,
        "cash": cash,
        "total_nav": total_nav,
        "daily_return": daily_return,
        "missing_prices": missing_prices,
    }


def run_daily_nav(conn: sqlite3.Connection, date: str | None = None) -> dict:
    """Orchestrator job entry point: compute_nav for `date` (default today),
    logging a job_runs row. Missing prices are logged as a warning in
    job_runs.error rather than raising (a NAV run must never crash the
    pipeline over one bad price)."""
    job_name = "daily_nav"
    date = date or dt.date.today().isoformat()
    started_at = _now_iso()
    try:
        result = compute_nav(conn, date)
        finished_at = _now_iso()
        error = None
        if result["missing_prices"]:
            error = (
                f"WARNING: missing price for instrument_id(s) "
                f"{result['missing_prices']} as of {date}; excluded from market_value"
            )
        log_job_run(conn, job_name, "SUCCESS", 1, started_at, finished_at, error)
        return result
    except Exception as exc:  # noqa: BLE001 - a NAV run must not crash the caller
        finished_at = _now_iso()
        error_text = f"{type(exc).__name__}: {exc}"
        log_job_run(conn, job_name, "FAILED", 0, started_at, finished_at, error_text)
        raise
