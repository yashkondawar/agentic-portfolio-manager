"""Workbench services: durable evidence, guarded paper books, no broker writes."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
import json
import logging
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from core import storage
from .book import Book, TRADE_COLUMNS
from .calendar import review_flags
from .config import SCHEMA_VERSION, S18Config, validate_capital
from .dossier import build_workbook
from .dataset import AssetReader, get_dataset
from .replay import (
    book_fingerprint,
    combined_curve,
    input_fingerprint,
    metrics,
    reference_fingerprint,
    simulate,
    source_fingerprint,
    trade_frame,
    validate_dataset,
)

logger = logging.getLogger(__name__)
NAMESPACE = "s18"
REPORTS_ROOT = Path(__file__).resolve().parents[2] / "reports" / "s18"
WARNINGS = [
    "Paper simulation only; the workbench does not submit broker orders.",
    "Model costs are 0.02% per side. Slippage has not been tested.",
    "Actual contract-note charges are a separate shadow field; blank means unknown, not zero.",
    "Reference tax model: 20% short-term, 12.5% long-term, no exemption or carry-loss expiry.",
    "Gold/silver ETFs use equity taxation for reference compatibility, not their actual tax rules.",
    "Pre-2022-02-07 silver is a proxy. Supplied PIT data provenance is inherited, not independently certified.",
    "Demergers use synthetic tape normalization, not child-share delivery; reconcile actual broker holdings separately.",
    "Order quantities are signal-date equivalents; reconcile next-session corporate actions before any real execution.",
    "NAV includes paid annual taxes, but no hypothetical final liquidation or tax on open gains.",
]


def _export_artifacts(group_id):
    destination = REPORTS_ROOT / group_id
    storage.export_artifact_group(group_id, destination)
    return str(destination)


def _certificate(dataset: AssetReader, *, required: bool):
    fingerprint = source_fingerprint()
    stored = storage.get_document(
        NAMESPACE,
        f"golden_replay:{fingerprint}",
        storage.get_document(NAMESPACE, "golden_replay", {}),
    )
    current = (
        stored.get("status") == "passed"
        and stored.get("source_hash") == fingerprint
        and stored.get("data_hash") == input_fingerprint(dataset)
        and stored.get("reference_hash") == reference_fingerprint(dataset)
    )
    if current:
        return stored
    if required:
        raise ValueError(
            "S18 paper run blocked: no passing golden replay for the current code "
            "and database dataset. Run S18 Golden Replay in Backtest Lab first."
        )
    return {"status": "not validated", "results": []}


def run_replay() -> dict:
    dataset = get_dataset()
    runtime_key = f"golden_replay:{source_fingerprint()}"
    storage.set_document(NAMESPACE, "golden_replay", {"status": "running"})
    storage.set_document(NAMESPACE, runtime_key, {"status": "running"})
    try:
        validation, artifacts = validate_dataset(dataset)
    except (ValueError, OSError, KeyError, ImportError) as exc:
        logger.exception("S18 golden replay failed")
        storage.set_document(
            NAMESPACE, "golden_replay", {"status": "failed", "error": str(exc)}
        )
        storage.set_document(
            NAMESPACE, runtime_key, {"status": "failed", "error": str(exc)}
        )
        raise
    validation["verified_at"] = datetime.now(timezone.utc).isoformat()
    artifacts["validation.json"] = validation
    artifacts["validation.csv"] = pd.DataFrame(validation["results"]).to_csv(
        index=False
    )
    group_id, refs = storage.save_artifacts(
        "s18_replay",
        "S18 golden replay 2014-2026",
        artifacts,
        metadata=validation,
    )
    results_dir = _export_artifacts(group_id)
    validation["artifact_group_id"] = group_id
    storage.set_document(NAMESPACE, "golden_replay", validation)
    storage.set_document(NAMESPACE, runtime_key, validation)
    storage.set_document(NAMESPACE, "settings", {"dataset_id": dataset.id})
    return {
        "report": (
            "### S18 golden replay passed\n\n"
            "All 30 tranche configurations match the supplied trade logs and open books. "
            "All 15 combined NAV series match; Sharpe differences are below 0.001. "
            "This certifies reference compatibility, not execution costs or future returns."
        ),
        "validation": validation,
        "artifact_group_id": group_id,
        "results_dir": results_dir,
        "artifacts": refs,
        "warnings": WARNINGS,
        "dataset": dataset.status(),
    }


def _report(config, measured, validation, *, paper=False, overlay=None):
    result = (
        f"### S18 {config.combo} / {config.metal_mode} "
        f"{'paper book' if paper else 'backtest'}\n\n"
        f"Two 50/50 tranches; {config.n} slots per tranche. "
        f"Value: {measured['final_value']:,.2f}. "
        f"Golden replay: **{validation['status']}**."
    )
    if measured.get("sharpe") is not None:
        result += (
            f" Sharpe {measured['sharpe']:.3f}; CAGR {measured['cagr']:.2%}; "
            f"maximum drawdown {measured['max_drawdown']:.2%}."
        )
    if overlay is not None:
        result += f"\n\nSMA100 overlay: **{'risk-off' if overlay else 'risk-on'}**."
    return result + "\n\n" + " ".join(WARNINGS[:3])


def run_backtest(
    *,
    combo="P15",
    metal_mode="both_priority",
    start="2014-01-01",
    end="2026-08-31",
    capital=100000.0,
    write_dossier=True,
):
    from .data import load_market

    config = S18Config(combo, metal_mode)
    capital = validate_capital(capital)
    dataset = get_dataset()
    market = load_market(source=dataset, metals=metal_mode != "none", recompute=True)
    books = simulate(
        market, config, start=start, end=end, capital_per_tranche=capital / 2
    )
    curve = combined_curve(books, market)
    measured = metrics(curve)
    validation = _certificate(dataset, required=False)
    frame = trade_frame(books, market)
    holdings = [r for b in books for r in b.holdings(market)]
    result = {
        "report": _report(config, measured, validation),
        "metrics": measured,
        "validation": validation,
        "trades": frame.to_dict("records"),
        "holdings": holdings,
        "equity_curve": curve,
        "warnings": WARNINGS,
        "provenance": market.provenance,
        "dataset": dataset.status(),
        "portfolio_state": {"books": [b.to_dict() for b in books]},
    }
    artifacts = {
        "summary.json": measured,
        "trades.csv": frame.to_csv(index=False),
        "open_book.csv": frame[frame.reason == "open at end"].to_csv(index=False),
        "equity_curve.csv": pd.DataFrame(curve).to_csv(index=False),
        "portfolio_state.json": result["portfolio_state"],
        "report.md": result["report"],
    }
    if write_dossier:
        artifacts["s18_dossier.xlsx"] = build_workbook(
            config=config,
            metrics=measured,
            curve=curve,
            trades=result["trades"],
            holdings=holdings,
            books=books,
            validation=validation,
            warnings=WARNINGS,
        )
    group_id, refs = storage.save_artifacts(
        "s18_backtest",
        f"S18 {combo} {metal_mode} {start} to {end}",
        artifacts,
        metadata={"config": asdict(config), "validation": validation["status"]},
        content_types={
            "s18_dossier.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        },
    )
    result["artifact_group_id"] = group_id
    result["results_dir"] = _export_artifacts(group_id)
    result["artifacts"] = refs
    result["dossier"] = refs.get("s18_dossier.xlsx")
    return result


def _save_book(key: str, expected: dict | None, state: dict):
    """Compare-and-swap prevents overlapping scheduler/UI runs double-filling."""
    now = datetime.now(timezone.utc).isoformat()
    with storage.connection_scope() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT value_json FROM documents WHERE namespace = ? AND key = ?",
            (NAMESPACE, key),
        ).fetchone()
        actual = json.loads(row[0]) if row is not None else None
        if actual != expected:
            raise ValueError("S18 book changed during this run; reload before retrying")
        connection.execute(
            "INSERT INTO documents(namespace,key,value_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET "
            "value_json=excluded.value_json, updated_at=excluded.updated_at",
            (NAMESPACE, key, json.dumps(state, allow_nan=False), now, now),
        )


def _rescale_books(books, old_scales, new_scales, identities, market):
    ratios = {}
    for i, identity in enumerate(identities):
        old = float(old_scales.get(identity, 1.0))
        new = float(new_scales.get(identity, 1.0))
        if not math.isfinite(old * new) or old <= 0 or new <= 0:
            raise ValueError(f"Invalid corporate-action scale for {identity}")
        ratios[i] = new / old
    for book in books:
        for p in book.positions:
            p.qty /= ratios[p.gid]
            p.peak *= ratios[p.gid]
        for fill in book.fills:
            identity = fill["identity"]
            ratio = float(new_scales.get(identity, 1)) / float(
                old_scales.get(identity, 1)
            )
            fill["qty"] /= ratio
            fill["price"] *= ratio
        if len(book.trade_identities) != len(book.trades):
            raise ValueError("S18 trade identity ledger is incomplete; replay the book")
        for trade, identity in zip(book.trades, book.trade_identities):
            if identity not in identities:
                raise ValueError("Cannot rebase an unknown S18 trade identity")
            ratio = float(new_scales.get(identity, 1)) / float(
                old_scales.get(identity, 1)
            )
            trade["entry_px"] *= ratio
            trade["exit_px"] *= ratio


def _remap_books(books, old_identities, new_identities):
    if len(set(new_identities)) != len(new_identities):
        raise ValueError("S18 market contains duplicate company identities")
    indexes = {identity: gid for gid, identity in enumerate(new_identities)}
    if any(identity not in indexes for identity in old_identities):
        raise ValueError("S18 market dropped an existing company identity")
    mapping = [indexes[identity] for identity in old_identities]
    for book in books:
        for position in book.positions:
            position.gid = mapping[position.gid]
        for order in book.queued_buys:
            order["gid"] = mapping[order["gid"]]


def _quote_units(market, identity):
    scales = market.provenance.get("raw_to_book")
    if scales is None:
        return 1.0, "adjusted model units"
    if not isinstance(scales, dict) or identity not in scales:
        raise ValueError(f"Missing current quote conversion for {identity}")
    factor = float(scales[identity])
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError(f"Invalid current quote conversion for {identity}")
    return factor, "current-share equivalents (fractional paper units)"


def _display_holdings(books, market):
    rows = []
    for book in books:
        for holding in book.holdings(market):
            factor, units = _quote_units(market, holding["identity"])
            for name in ("qty", "close", "peak", "stop"):
                holding[f"model_{name}"] = holding[name]
                if holding[name] is not None:
                    holding[name] *= factor if name == "qty" else 1 / factor
            holding["quantity_units"] = units
            holding["raw_to_book"] = factor
            rows.append(holding)
    return rows


def _orders(books, market, next_date):
    rows = []
    for book in books:
        nav = book.equity[-1]["nav"]
        for p in book.positions:
            if p.queued_sell_reason:
                factor, units = _quote_units(market, market.identities[p.gid])
                rows.append(
                    {
                        "combo": book.config.combo,
                        "tranche": book.tranche,
                        "signal_date": book.last_date,
                        "execution_date": next_date,
                        "symbol": market.symbols[p.gid],
                        "identity": market.identities[p.gid],
                        "side": "SELL",
                        "sleeve": p.sleeve,
                        "qty": p.qty * factor,
                        "model_qty": p.qty,
                        "quantity_units": units,
                        "quantity_as_of": book.last_date,
                        "reconcile_before_execution": True,
                        "paper_only": True,
                        "weight": None,
                        "target_amount_estimate": None,
                        "reason": p.queued_sell_reason,
                        "execution": "next traded open",
                    }
                )
        for order in book.queued_buys:
            g, w = order["gid"], order["weight"]
            _, units = _quote_units(market, market.identities[g])
            rows.append(
                {
                    "combo": book.config.combo,
                    "tranche": book.tranche,
                    "signal_date": book.last_date,
                    "execution_date": next_date,
                    "symbol": market.symbols[g],
                    "identity": market.identities[g],
                    "side": "BUY",
                    "sleeve": order["sleeve"],
                    "qty": None,
                    "model_qty": None,
                    "quantity_units": units,
                    "quantity_as_of": book.last_date,
                    "reconcile_before_execution": True,
                    "paper_only": True,
                    "weight": w,
                    "target_amount_estimate": nav / book.config.n * w,
                    "reason": "entry",
                    "execution": "next open; resize for cash and open NAV",
                }
            )
    return rows


def _apply_shadow_charges(books, charges):
    if not isinstance(charges, dict):
        raise ValueError("Shadow charges must map fill IDs to charge breakdown objects")
    fills = {f["fill_id"]: f for b in books for f in b.fills}
    permitted = {
        "stt",
        "stamp_duty",
        "exchange_fees",
        "gst",
        "dp_charges",
        "brokerage",
        "other",
    }
    for fill_id, breakdown in charges.items():
        if fill_id not in fills:
            raise ValueError(f"Unknown model fill ID for shadow charges: {fill_id}")
        if (
            not isinstance(breakdown, dict)
            or not breakdown
            or set(breakdown) - permitted
        ):
            raise ValueError(f"Invalid contract-note charge breakdown for {fill_id}")
        values = {}
        for key, value in breakdown.items():
            if isinstance(value, bool):
                raise ValueError("Shadow charges must be finite nonnegative amounts")
            amount = float(value)
            if not math.isfinite(amount) or amount < 0:
                raise ValueError("Shadow charges must be finite nonnegative amounts")
            values[key] = amount
        fills[fill_id]["actual_charges"] = sum(values.values())
        fills[fill_id]["charge_breakdown"] = values


def _tranche_report(book, market, orders):
    overlay = "risk-off" if market.risk_off[book.last_row] else "risk-on"
    lines = [
        f"# S18 {book.config.combo} / {book.tranche} / {book.config.metal_mode}",
        f"Session: {book.last_date}. NAV: {book.equity[-1]['nav']:,.2f}. "
        f"Cash: {book.cash:,.2f}. SMA100: {overlay}.",
        "Holdings below use adjusted model units. Next-open CSVs label their units "
        "and convert to current-share equivalents when verified raw anchors are supplied.",
        "",
        "| Symbol | Sleeve | Quantity | Basis | Peak | Armed | Pending exit |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for p in book.positions:
        lines.append(
            f"| {market.symbols[p.gid]} | {p.sleeve} | {p.qty:.6f} | "
            f"{p.basis:.2f} | {p.peak:.4f} | {p.armed} | {p.queued_sell_reason} |"
        )
    lines.extend(["", "## Today's model fills"])
    today = [f for f in book.fills if f["date"] == book.last_date]
    lines.extend(
        f"- {f['side']} {f['symbol']}: {f['qty']:.6f} @ {f['price']:.4f} "
        f"({f['reason']}); model cost {f['model_cost']:.4f}."
        for f in today
    )
    if not today:
        lines.append("None.")
    lines.extend(["", "## Next-open model instructions"])
    pending = [o for o in orders if o["tranche"] == book.tranche]
    lines.extend(
        f"- {o['side']} {o['symbol']} ({o['sleeve']}): {o['reason']}; {o['execution']}."
        for o in pending
    )
    if not pending:
        lines.append("None.")
    lines.extend(["", *WARNINGS])
    return "\n".join(lines)


def run_daily(
    *,
    combo="P15",
    metal_mode="both_priority",
    as_of=None,
    capital=100000.0,
    book_id="default",
    persist=True,
    shadow_charges=None,
):
    from .data import load_market

    config = S18Config(combo, metal_mode)
    capital = validate_capital(capital)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", book_id):
        raise ValueError(
            "Book ID must use 1-64 letters, digits, underscores or hyphens"
        )
    dataset = get_dataset()
    validation = _certificate(dataset, required=True)
    key = f"book:{book_id}:{combo}:{metal_mode}"
    saved = storage.get_document(NAMESPACE, key)
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    requested = date.fromisoformat(as_of) if as_of else today_ist
    if requested > today_ist:
        raise ValueError("S18 paper runs cannot consume future-dated sessions")
    data_source = "nse" if requested > date(2026, 8, 31) else "database"
    if saved and saved.get("data_source", data_source) != data_source:
        raise ValueError(
            "Use a separate book ID when moving from historical simulation to live data"
        )
    readiness = None
    if data_source == "nse":
        from .live_data import collect_market

        collected = collect_market(
            dataset=dataset,
            as_of=requested.isoformat(),
            metals=metal_mode != "none",
            inception=saved.get("inception_date") if saved else None,
            tracked_identities=(
                {
                    saved["identities"][p["gid"]]
                    for book in saved["books"]
                    for p in [*book["positions"], *book["queued_buys"]]
                }
                if saved
                else ()
            ),
        )
        market, readiness = collected.market, collected.readiness
        if readiness["status"] != "ready":
            return {
                "report": (
                    f"### S18 {combo}: waiting for the first forward session\n\n"
                    f"{readiness['message']} Latest completed prices: "
                    f"{readiness['latest_price_date']}. Planned capital: {capital:,.2f} "
                    "across two tranches. No paper book or trades have been created."
                ),
                "readiness": readiness,
                "validation": validation,
                "metrics": {"planned_capital": capital},
                "holdings": [],
                "orders": [],
                "trades": [],
                "fills": [],
                "equity_curve": [],
                "portfolio_state": {},
                "state_persisted": False,
                "warnings": WARNINGS,
                "provenance": market.provenance,
                "dataset": dataset.status(),
            }
    else:
        market = load_market(
            source=dataset, metals=metal_mode != "none", recompute=True
        )
    calendar = np.asarray(
        market.provenance.get("session_calendar", market.dates), dtype="datetime64[D]"
    )
    complete_through = market.provenance.get("calendar_complete_through")
    if requested > date(2026, 8, 31):
        month_end = (pd.Timestamp(requested) + pd.offsets.MonthEnd(0)).date()
        if complete_through is None or date.fromisoformat(complete_through) < month_end:
            raise ValueError(
                "S18 daily requires a complete exchange calendar through month-end"
            )
    target = np.datetime64(
        market.provenance["as_of"] if data_source == "nse" else requested
    )
    session_index = int(np.searchsorted(calendar, target, side="right")) - 1
    if session_index < 0:
        raise ValueError("No exchange session on or before the requested date")
    session = calendar[session_index]
    last = int(np.searchsorted(market.dates, session))
    if last >= len(market.dates) or market.dates[last] != session:
        raise ValueError(f"S18 data missing required exchange session {session}")
    if session_index + 1 >= len(calendar):
        raise ValueError(
            "Extend the exchange calendar to include the next order session"
        )
    next_date = str(calendar[session_index + 1])
    identities = [str(x) for x in market.identities]
    new_scales = market.provenance.get("price_scales", {})
    fingerprints = market.provenance.get("history_fingerprints", {})
    if saved:
        if (
            saved["source_hash"] != validation["source_hash"]
            and saved.get("book_fingerprint") != book_fingerprint()
        ):
            raise ValueError(
                "S18 engine changed; use a new book ID after replay validation"
            )
        if saved["data_hash"] != validation["data_hash"]:
            raise ValueError(
                "S18 warm-up history changed; use a new book ID after validation"
            )
        if saved["capital"] != capital:
            raise ValueError(
                "Initial capital cannot change for an existing S18 paper book"
            )
        if any(
            fingerprints.get(day) != digest
            for day, digest in saved.get("history_fingerprints", {}).items()
        ):
            raise ValueError(
                "S18 processed forward data was revised; use a new book ID to replay"
            )
        for identity, anchor in saved.get("anchor_evidence", {}).items():
            if market.provenance.get("anchor_evidence", {}).get(identity) != anchor:
                raise ValueError(f"S18 raw-price anchor was revised for {identity}")
        for identity, checksum in saved.get(
            "new_constituent_warmup_hashes", {}
        ).items():
            if (
                market.provenance.get("new_constituent_warmup_hashes", {}).get(identity)
                != checksum
            ):
                raise ValueError(
                    f"S18 new-constituent warm-up was revised for {identity}"
                )
        books = [Book.from_dict(b) for b in saved["books"]]
        _remap_books(books, saved["identities"], identities)
        if any(b.last_date > str(session) for b in books):
            raise ValueError("Cannot move an existing S18 paper book backwards")
        for book in books:
            if str(market.dates[book.last_row]) != book.last_date:
                raise ValueError("S18 session history changed under an existing book")
        _rescale_books(
            books, saved.get("price_scales", {}), new_scales, identities, market
        )
        first = books[0].last_row + 1
    else:
        books = [Book.from_cash(config, t, capital / 2) for t in ("A", "B")]
        for book in books:
            book.allowed_history = [0] * 5
        first = last
    order = market.s1_order(config.tiered, metal_mode == "both_priority")
    for book in books:
        flags = review_flags(calendar, book.tranche, complete_through=complete_through)
        for row in range(first, last + 1):
            ci = int(np.searchsorted(calendar, market.dates[row]))
            if ci >= len(calendar) or calendar[ci] != market.dates[row]:
                raise ValueError("S18 price date is not in the exchange calendar")
            book.step(
                market,
                row,
                review=bool(flags[ci]),
                order=order[row],
                initial=book.last_row < 0,
            )
    if shadow_charges is not None:
        _apply_shadow_charges(books, shadow_charges)
    curve = combined_curve(books, market)
    measured = metrics(curve)
    holdings = _display_holdings(books, market)
    orders = _orders(books, market, next_date)
    trades = [r for b in books for r in b.trades]
    state = {
        "schema_version": SCHEMA_VERSION,
        "book_id": book_id,
        "config": asdict(config),
        "capital": capital,
        "source_hash": validation["source_hash"],
        "book_fingerprint": book_fingerprint(),
        "data_hash": validation["data_hash"],
        "dataset_id": dataset.id,
        "data_source": data_source,
        "inception_date": books[0].equity[0]["date"],
        "identities": identities,
        "price_scales": new_scales,
        "books": [b.to_dict() for b in books],
        "history_fingerprints": {
            day: digest for day, digest in fingerprints.items() if day <= str(session)
        },
        "history_fingerprint_version": market.provenance.get(
            "history_fingerprint_version"
        ),
        "anchor_evidence": market.provenance.get("anchor_evidence", {}),
        "new_constituent_warmup_hashes": market.provenance.get(
            "new_constituent_warmup_hashes", {}
        ),
        "as_of": str(session),
    }
    report = _report(
        config, measured, validation, paper=True, overlay=bool(market.risk_off[last])
    )
    result = {
        "report": report,
        "metrics": measured,
        "validation": validation,
        "holdings": holdings,
        "orders": orders,
        "trades": trades,
        "fills": [
            {**f, "quantity_units": "adjusted model units"}
            for b in books
            for f in b.fills
        ],
        "portfolio_state": state,
        "equity_curve": curve,
        "warnings": WARNINGS,
        "as_of": str(session),
        "next_session": next_date,
        "state_persisted": bool(persist),
        "provenance": market.provenance,
        "dataset": dataset.status(),
        "readiness": readiness or {"status": "ready", "source": "application_database"},
    }
    if persist:
        artifacts = {
            f"orders_{next_date}.csv": pd.DataFrame(orders).to_csv(index=False),
            "holdings.csv": pd.DataFrame(holdings).to_csv(index=False),
            "trades.csv": pd.DataFrame(trades, columns=TRADE_COLUMNS).to_csv(
                index=False
            ),
            "fills_and_shadow_costs.csv": pd.DataFrame(result["fills"]).to_csv(
                index=False
            ),
            "portfolio_state.json": state,
            "report.md": report,
        }
        for book in books:
            artifacts[f"{combo}_{book.tranche}_report_{session}.md"] = _tranche_report(
                book, market, orders
            )
            artifacts[f"orders_{next_date}_{book.tranche}.csv"] = pd.DataFrame(
                [o for o in orders if o["tranche"] == book.tranche]
            ).to_csv(index=False)
        group, refs = storage.save_artifacts(
            "s18_daily",
            f"S18 {book_id} {combo} {metal_mode} {session}",
            artifacts,
        )
        result["results_dir"] = _export_artifacts(group)
        state["artifact_group_id"] = group
        _save_book(key, saved, state)
        result["artifact_group_id"] = group
        result["artifacts"] = refs
    return result
