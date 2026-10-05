"""Read-only portfolio views from committed S18 state, without data ingestion."""

from __future__ import annotations

from io import StringIO
import json
import math
import re

import pandas as pd

from core import storage
from .config import S18Config
from .data import METAL_IDENTITIES


def _selection(book_id, combo, metal_mode):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", book_id):
        raise ValueError(
            "Portfolio ID must use 1-64 letters, digits, underscores or hyphens"
        )
    return S18Config(combo, metal_mode)


def _artifact_rows(group, name):
    artifact = storage.get_artifact(group, name)
    if artifact is None:
        raise ValueError(
            f"Saved S18 portfolio is missing {name}; run an update to rebuild its view"
        )
    if not artifact.text.strip():
        return []
    frame = pd.read_csv(StringIO(artifact.text))
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def ledger_snapshot(*, book_id="default", combo="P15", metal_mode="both_priority"):
    config = _selection(book_id, combo, metal_mode)
    state = storage.get_document("s18", f"book:{book_id}:{combo}:{metal_mode}")
    if state is None:
        return {
            "exists": False,
            "book_id": book_id,
            "config": {
                "combo": combo,
                "metal_mode": metal_mode,
            },
        }
    books = state["books"]
    if len(books) != 2 or {b["tranche"] for b in books} != {"A", "B"}:
        raise ValueError("Saved S18 portfolio must contain both A and B tranches")
    dates = [[row["date"] for row in b["equity"]] for b in books]
    if not dates[0] or dates[0] != dates[1] or dates[0][-1] != state["as_of"]:
        raise ValueError("Saved S18 tranche dates do not agree")
    group = state.get("artifact_group_id")
    if not group:
        raise ValueError("Saved S18 portfolio has no committed holdings snapshot")
    holdings = _artifact_rows(group, "holdings.csv")
    position_count = sum(len(b["positions"]) for b in books)
    if len(holdings) != position_count:
        raise ValueError("Saved holdings do not match the committed S18 portfolio")
    for holding in holdings:
        basis, value = float(holding["basis"]), float(holding["value"])
        holding["unrealised_pnl"] = value - basis
        holding["return_pct"] = 100 * (value / basis - 1) if basis else None
        holding["average_cost"] = (
            basis / float(holding["qty"]) if holding["qty"] else None
        )
    nav = sum(float(b["equity"][-1]["nav"]) for b in books)
    cash = sum(float(b["cash"]) for b in books)
    deployed = sum(float(h["value"]) for h in holdings)
    if not math.isclose(nav, cash + deployed, rel_tol=1e-9, abs_tol=1e-6):
        raise ValueError(
            "Saved S18 holdings and cash do not reconcile to portfolio value"
        )
    invested = sum(float(h["basis"]) for h in holdings)
    trades = [r for b in books for r in b["trades"]]
    fills = [f for b in books for f in b["fills"]]
    tax = sum(float(b["tax_paid"]) for b in books)
    capital = float(state["capital"])
    curve = [
        {"date": a["date"], "nav": a["nav"] + b["nav"]}
        for a, b in zip(books[0]["equity"], books[1]["equity"])
    ]
    used_slots = sum(
        2 if config.n > 15 and h["identity"] in METAL_IDENTITIES else 1
        for h in holdings
    )
    with storage.connection_scope() as connection:
        candidates = [
            r[0]
            for r in connection.execute(
                "SELECT name FROM artifacts WHERE group_id=? AND name LIKE 'orders_%.csv'",
                (group,),
            )
        ]
    order_files = [
        name
        for name in candidates
        if re.fullmatch(r"orders_\d{4}-\d{2}-\d{2}\.csv", name)
    ]
    if len(order_files) != 1:
        raise ValueError(
            "Saved S18 portfolio has no unambiguous next-session instruction snapshot"
        )
    orders = _artifact_rows(group, order_files[0])
    return {
        "exists": True,
        "book_id": book_id,
        "config": state["config"],
        "as_of": state["as_of"],
        "opened_on": state.get("inception_date", dates[0][0]),
        "next_session": order_files[0][7:-4],
        "holdings": holdings,
        "orders": orders,
        "tradebook": trades,
        "fills": fills,
        "equity_curve": curve,
        "book": {
            "equity": nav,
            "cash": cash,
            "deployed": deployed,
            "invested": invested,
            "starting_capital": capital,
            "unrealized_pnl": deployed - invested,
            "realized_pnl": sum(float(t["gain"]) for t in trades),
            "tax_paid": tax,
            "total_pnl": nav - capital,
            "total_return_pct": 100 * (nav / capital - 1),
            "open_positions": position_count,
            "free_slots": max(0, 2 * config.n - used_slots),
        },
    }


def latest_portfolio_run(*, book_id="default", combo="P15", metal_mode="both_priority"):
    """A preview/failed run is visible below, never used as the saved portfolio."""
    _selection(book_id, combo, metal_mode)
    with storage.connection_scope() as connection:
        row = connection.execute(
            """
            SELECT id,strategy_id,status,created_at,duration_ms,params_json,report,data_json,error
            FROM runs WHERE strategy_id='s18_daily'
              AND COALESCE(json_extract(data_json,'$.portfolio_state.book_id'),
                           json_extract(params_json,'$.book_id'),'default')=?
              AND COALESCE(json_extract(data_json,'$.portfolio_state.config.combo'),
                           json_extract(params_json,'$.combo'),'P15')=?
              AND COALESCE(json_extract(data_json,'$.portfolio_state.config.metal_mode'),
                           json_extract(params_json,'$.metal_mode'),'both_priority')=?
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (book_id, combo, metal_mode),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["data"] = json.loads(result.pop("data_json"))
    result["params"] = json.loads(result.pop("params_json"))
    return result
