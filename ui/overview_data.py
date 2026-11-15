"""Read-only dashboard projections of saved books, prices and run metadata.

Book state never comes from the latest run: that run may be a preview or failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
import logging
import math
import sqlite3
from typing import Callable

import pandas as pd

from core import storage
from core.run_history import get_run

logger = logging.getLogger(__name__)
READ_ERRORS = (OSError, sqlite3.Error, ValueError, TypeError, KeyError, ImportError)
RESEARCH_IDS = ("parallel_agents", "sequential_agents", "watchlist_curation")
INVEST_IDS = (
    "gfs_live",
    "breakout_ath_daily",
    "qtr_results",
    "s18_daily",
    "swing_trading",
    "portfolio_analysis",
)
BACKTEST_IDS = ("swing_backtest", "breakout_ath_backtest", "s18_backtest", "s18_replay")


@dataclass
class BookView:
    key: str
    name: str
    route: str
    mode: str
    exists: bool = False
    as_of: str | None = None
    timestamp_label: str = "Saved close"
    value: float | None = None
    cash: float | None = None
    starting_capital: float | None = None
    pnl: float | None = None
    unrealized: float | None = None
    realized: float | None = None
    return_pct: float | None = None
    holdings: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    activity: list[dict] = field(default_factory=list)
    curve: list[dict] = field(default_factory=list)
    pending_cash_in_lieu: list[dict] = field(default_factory=list)
    cash_in_lieu: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    selection: dict = field(default_factory=dict)
    error: str | None = None
    last_run: dict | None = None
    action_label: str = "Next-session instructions"

    @property
    def action_count(self) -> int:
        return sum(not bool(row.get("blocked")) for row in self.orders)

    @property
    def state_label(self) -> str:
        if self.error:
            return "Unavailable"
        if self.exists:
            return "Saved state"
        return "No local snapshot" if self.key == "ath" else "Not started"


def number(value) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Saved financial data contains a non-finite number")
    return result


def _first(row: dict, *keys):
    return next((row[key] for key in keys if row.get(key) is not None), None)


def holding_rows(rows: list[dict]) -> list[dict]:
    """Normalize labels only; retain source quantities and do not invent marks."""
    return [
        {
            "Symbol": str(row["symbol"]),
            "Tranche": row.get("tranche"),
            "Quantity": number(_first(row, "quantity", "qty")),
            "Units": row.get("quantity_units"),
            "Last mark": number(_first(row, "last_price", "price", "close")),
            "Value": number(_first(row, "market_value", "value")),
            "P&L": number(_first(row, "unrealized_pnl", "unrealised_pnl", "pnl")),
            "Stop": number(_first(row, "stop_price", "stop_level", "stop")),
        }
        for row in rows
    ]


def order_rows(rows: list[dict], *, side: str | None = None) -> list[dict]:
    return [
        {
            "Action": side or _first(row, "action", "side") or "Review",
            "Symbol": str(row["symbol"]),
            "Tranche": row.get("tranche"),
            "Quantity": number(_first(row, "quantity", "qty")),
            "Units": row.get("quantity_units"),
            "Reference": number(_first(row, "reference_price", "price")),
            "Allocation": number(_first(row, "target_amount_estimate", "budget")),
            "Share value": number(row.get("estimated_value")),
            "Model cost": number(row.get("estimated_cost")),
            "Cash required": number(row.get("estimated_amount")),
            "Sizing": row.get("sizing_status"),
            "Session": row.get("execution_date"),
            "Status": (
                f"Blocked: {row.get('blocked_reason') or row.get('sizing_status') or row.get('reason') or 'risk cap'}"
                if _order_blocked(row)
                else row.get("sizing_status") or row.get("reason") or "Review"
            ),
            "blocked": _order_blocked(row),
        }
        for row in rows
    ]


def _order_blocked(row: dict) -> bool:
    return bool(row.get("blocked")) or (
        row.get("quantity_units") == "whole exchange shares"
        and _first(row, "action", "side") == "BUY"
        and number(_first(row, "quantity", "qty")) == 0
    )


def _apply_snapshot(view: BookView, snap: dict) -> None:
    view.exists = bool(snap.get("exists", snap.get("as_of")))
    if not view.exists:
        return
    book = snap["book"]
    view.as_of = snap.get("as_of")
    view.value = number(book.get("equity"))
    view.cash = number(book.get("cash"))
    capital = number(book.get("starting_capital"))
    view.starting_capital = capital
    # NAV minus initial capital includes model costs/tax, unlike gross trade P&L.
    if view.value is not None and capital is not None:
        view.pnl = view.value - capital
        view.return_pct = 100 * view.pnl / capital if capital else None
    view.unrealized = number(book.get("unrealized_pnl"))
    view.realized = number(book.get("realized_pnl"))
    view.holdings = holding_rows(snap.get("holdings") or [])
    view.orders = order_rows(snap.get("orders") or [])
    view.curve = [
        {"date": row["date"], "value": number(_first(row, "equity", "nav"))}
        for row in snap.get("equity_curve") or []
    ]
    fresh = snap.get("freshness") or {}
    if fresh.get("stale"):
        view.notes.append(
            f"Saved marks are {fresh['weekdays_behind']} weekdays behind. "
            "Refresh the strategy before acting; stops also use those old marks."
        )


def _load_gfs(view: BookView) -> None:
    from gfs.engine import ledger_snapshot

    _apply_snapshot(view, ledger_snapshot())
    view.action_label = "Next-open queue (indicative quantities)"
    view.notes.append(
        "Modelled next-open fills; not synced to your broker. The engine may use entry price where a saved closing mark is missing."
    )


def _load_ath(view: BookView) -> None:
    from backtesting.breakout_ath.config import STATE_PATH
    from backtesting.breakout_ath.daily import ledger_snapshot

    # The legacy engine reseeds on unreadable JSON. The dashboard must instead
    # distinguish damaged state from a genuinely unstarted book.
    if STATE_PATH.exists():
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not raw.get("last_session"):
            raise ValueError(
                "Saved ATH state has no valid last session; inspect the strategy book"
            )
    snap = ledger_snapshot(state_path=STATE_PATH)
    _apply_snapshot(view, snap)
    view.orders = order_rows(snap.get("pending_entries") or [], side="BUY")
    view.action_label = f"Buys awaiting fill confirmation ({snap.get('pending_session') or 'saved session'})"
    view.notes.append(
        "Buys are suggestions until confirmed in Daily strategies. Exits are model-applied; no broker sync."
    )


def _load_qtr(view: BookView) -> None:
    from qtr_results.engine import ledger_snapshot

    raw = storage.get_document("qtr_results", "portfolio")
    ledger = storage.get_document("qtr_results", "ledger")
    if raw is None and ledger is None:
        return
    if raw is None or ledger is None:
        raise ValueError(
            "Quarterly ledger and capital record are incomplete; inspect the saved portfolio"
        )
    for key in ("cash", "starting_capital", "realized_pnl"):
        if number(raw[key]) is None:
            raise ValueError(f"Quarterly portfolio is missing {key}")
    snap = ledger_snapshot()
    with storage.connection_scope() as connection:
        updated = connection.execute(
            "SELECT MAX(updated_at) FROM documents WHERE namespace='qtr_results' "
            "AND key IN ('portfolio','ledger')"
        ).fetchone()[0]
        # These are historical actions already applied to the ledger, not a queue.
        row = connection.execute(
            "SELECT id FROM runs WHERE strategy_id='qtr_results' "
            "AND status IN ('completed','completed_with_warnings') "
            "AND json_extract(data_json,'$.dry_run')=0 "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    value = snap["cash"] + sum(h["market_value"] for h in snap["holdings"])
    _apply_snapshot(
        view,
        {
            "exists": True,
            "as_of": updated,
            "book": {**snap, "equity": value},
            "holdings": snap["holdings"],
        },
    )
    view.timestamp_label = "Ledger saved"
    view.action_label = "Latest recorded activity (already applied)"
    view.notes.append(
        "Ledger save time is not a quote timestamp. Missing closing marks may use entry prices."
    )
    if row:
        record = get_run(row["id"])
        view.activity = order_rows(
            [
                item
                for item in record["data"].get("actions", [])
                if item.get("action") in ("BUY", "SELL")
            ]
        )
        view.notes.append(
            f"Activity recorded {record['created_at'][:19]} UTC; not pending orders."
        )
    else:
        view.notes.append(
            "No committed run activity available. The ledger remains authoritative."
        )


def _load_s18(view: BookView) -> None:
    from backtesting.s18.portfolio import ledger_snapshot, latest_portfolio_run

    snap = ledger_snapshot(**view.selection)
    _apply_snapshot(view, snap)
    view.last_run = latest_portfolio_run(**view.selection)
    view.pending_cash_in_lieu = snap.get("pending_cash_in_lieu") or []
    view.cash_in_lieu = snap.get("cash_in_lieu") or []
    view.action_label = (
        f"Next-session instructions ({snap.get('next_session') or 'not available'})"
    )
    view.notes.append(
        "A and B remain separate holdings. "
        + (
            "Whole exchange shares; buy quantities and cash requirements are estimates "
            "at the last close, resized at the next open for prices, cash and model costs. "
            "Zero-quantity buys are not actionable."
            if snap.get("execution_mode") == "whole_shares"
            else "Fractional reference-model units, not whole-share orders."
        )
        + " No broker orders are submitted."
    )


def _read_book(
    view: BookView, loader: Callable[[BookView], None], strategy_id: str
) -> BookView:
    try:
        loader(view)
        if strategy_id != "s18_daily":
            runs = recent_runs((strategy_id,), limit=1)
            view.last_run = runs[0] if runs else None
    except READ_ERRORS as exc:
        logger.exception("Unable to read portfolio %s", view.key)
        view.error = str(exc)
    return view


def load_books() -> list[BookView]:
    """Every persisted strategy book, including every S18 selection, uncollapsed."""
    books = [
        _read_book(
            BookView(
                "gfs",
                "GFS multi-timeframe",
                "strategies",
                "Paper book",
                selection={"daily_strategy": "GFS multi-timeframe"},
            ),
            _load_gfs,
            "gfs_live",
        ),
        _read_book(
            BookView(
                "ath",
                "ATH breakout",
                "strategies",
                "Tracked sleeve",
                selection={"daily_strategy": "ATH breakout"},
            ),
            _load_ath,
            "breakout_ath_daily",
        ),
        _read_book(
            BookView(
                "quarterly",
                "Quarterly results",
                "strategies",
                "Model ledger",
                selection={"daily_strategy": "Quarterly results"},
            ),
            _load_qtr,
            "qtr_results",
        ),
    ]
    try:
        with storage.connection_scope() as connection:
            keys = [
                row[0]
                for row in connection.execute(
                    "SELECT key FROM documents WHERE namespace='s18' AND key LIKE 'book:%' ORDER BY key"
                )
            ]
        if not keys:
            defaults = storage.get_document("strategy_defaults", "s18_daily", {})
            keys = [
                f"book:{defaults.get('book_id', 'default')}:{defaults.get('combo', 'P15')}:{defaults.get('metal_mode', 'both_priority')}"
            ]
        for key in keys:
            parts = key.split(":")
            if len(parts) != 4:
                books.append(
                    BookView(
                        key,
                        "S18 unreadable selection",
                        "s18",
                        "Paper book",
                        error=f"Malformed saved portfolio key: {key}",
                    )
                )
                continue
            _, book_id, combo, metal_mode = parts
            view = BookView(
                key,
                f"S18 / {book_id} / {combo} / {metal_mode}",
                "s18",
                f"{combo} / {metal_mode.replace('_', ' ')}",
                selection={
                    "book_id": book_id,
                    "combo": combo,
                    "metal_mode": metal_mode,
                },
            )
            books.append(_read_book(view, _load_s18, "s18_daily"))
    except READ_ERRORS as exc:
        logger.exception("Unable to enumerate S18 portfolios")
        books.append(
            BookView(
                "s18-error", "S18 portfolios", "s18", "Paper books", error=str(exc)
            )
        )
    return books


def recent_runs(
    strategy_ids: tuple[str, ...] = (), *, limit: int = 20, status: str | None = None
) -> list[dict]:
    clauses, values = [], []
    if strategy_ids:
        clauses.append(f"strategy_id IN ({','.join('?' for _ in strategy_ids)})")
        values.extend(strategy_ids)
    if status:
        clauses.append("status=?")
        values.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with storage.connection_scope() as connection:
        rows = connection.execute(
            "SELECT id,strategy_id,status,created_at,duration_ms,error FROM runs"
            + where
            + " ORDER BY created_at DESC, rowid DESC LIMIT ?",
            [*values, max(1, int(limit))],
        ).fetchall()
    return [dict(row) for row in rows]


def run_activity(days: int = 30) -> pd.DataFrame:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with storage.connection_scope() as connection:
        rows = connection.execute(
            "SELECT substr(created_at,1,10) AS day,status,COUNT(*) AS count "
            "FROM runs WHERE julianday(created_at)>=julianday(?) GROUP BY day,status ORDER BY day",
            (cutoff,),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows], columns=["day", "status", "count"])


def saved_prices(symbols: list[str], *, days: int = 366) -> dict[str, pd.DataFrame]:
    from core.bars import read_bars

    return read_bars(symbols, start=date.today() - timedelta(days=days))


def filtered_curve(
    curve: list[dict], period: str, *, drawdown: bool = False
) -> pd.DataFrame:
    frame = pd.DataFrame(curve, columns=["date", "value"])
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    if frame["date"].isna().any():
        raise ValueError("Portfolio history has missing dates")
    frame["value"] = pd.to_numeric(frame["value"], errors="raise")
    if frame["value"].isna().any() or not frame["value"].map(math.isfinite).all():
        raise ValueError("Portfolio history has missing or non-finite values")
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    if drawdown:
        # Compute the peak over ALL stored history, before cropping the viewport.
        peak = frame["value"].cummax()
        frame["value"] = (frame["value"] / peak.where(peak != 0) - 1) * 100
    days = {"1M": 31, "3M": 93, "1Y": 366}.get(period)
    if days:
        frame = frame[frame["date"] >= frame["date"].max() - pd.Timedelta(days=days)]
    return frame
