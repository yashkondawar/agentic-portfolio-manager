"""Workbench services: durable evidence, guarded paper books, no broker writes."""

from __future__ import annotations

from copy import deepcopy
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
    source_fingerprint,
    trade_frame,
    validate_dataset,
)
from .sizing import quote_factor, whole_quantity

logger = logging.getLogger(__name__)
NAMESPACE = "s18"
REPORTS_ROOT = Path(__file__).resolve().parents[2] / "reports" / "s18"
LEGACY_FRACTIONAL_BOOK = "c3d75fbf0e41665d4b5c87cf4fc3e7b794c67e5e13e32d44d16535a8aa94967a"
WARNINGS = [
    "Paper simulation only; the workbench does not submit broker orders.",
    "Model costs are 0.02% per side. Slippage has not been tested.",
    "Actual contract-note charges are a separate shadow field; blank means unknown, not zero.",
    "Reference tax model: 20% short-term, 12.5% long-term, no exemption or carry-loss expiry.",
    "Gold/silver ETFs use equity taxation for reference compatibility, not their actual tax rules.",
    "Pre-2022-02-07 silver is a proxy. Supplied PIT data provenance is inherited, not independently certified.",
    "Golden Replay normalizes demerger prices; whole-share books instead require holdings reconciliation.",
    "Order quantities are signal-date equivalents; reconcile next-session corporate actions before any real execution.",
    "NAV includes paid annual taxes, but no hypothetical final liquidation or tax on open gains.",
    "Whole-share books model split/bonus fractions as cash at the first available ex-date-or-later open, "
    "with zero settlement fees and proportional basis. This is not a verified company payment or its actual tax treatment.",
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
            "and database dataset. Run S18 Golden Replay in the same Python "
            "environment as this run (including the scheduler)."
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
    from .historical import HistoricalExecutionBlocked, load_execution_market, simulate_live

    config = S18Config(combo, metal_mode)
    capital = validate_capital(capital)
    dataset = get_dataset()
    market = load_execution_market(source=dataset, metals=metal_mode != "none")
    simulation = dict(start=start, end=end, capital_per_tranche=capital / 2)
    blocked = None
    try:
        books = simulate_live(market, config, **simulation)
    except HistoricalExecutionBlocked as exc:
        logger.error("Strict S18 backtest stopped: %s", exc)
        blocked = exc.details
        if not blocked["completed_through"]:
            raise
        simulation["end"] = blocked["completed_through"]
        books = simulate_live(market, config, **simulation)
    curve = combined_curve(books, market)
    measured = metrics(curve)
    validation = _certificate(dataset, required=False)
    frame = trade_frame(books, market)
    holdings = _display_holdings(books, market)
    fractional = simulate_live(market, config, **simulation, whole_shares=False)
    comparison = []
    for label, scenario in (("Fractional diagnostic", fractional), ("Whole-share live rules", books)):
        comparison.append({
            "scenario": label,
            **metrics(combined_curve(scenario, market)),
            "buy_fills": sum(f["side"] == "BUY" for b in scenario for f in b.fills),
            "closed_trades": sum(len(b.trades) for b in scenario),
            "unaffordable_buys": sum(len(b.skipped_buys) for b in scenario),
            "modeled_settlements": sum(len(b.cash_in_lieu) for b in scenario),
            "modeled_settlement_cash": sum(s["amount"] for b in scenario for s in b.cash_in_lieu),
            "pending_entitlement_value": sum(
                p["value"] for b in scenario for p in b.entitlement_rows(market)
            ),
        })
    warnings = [
        *WARNINGS[:5], *WARNINGS[7:],
        "Only verified split/bonus fractions receive modeled cash-in-lieu; demergers and unexplained fractions still block.",
        "Backtest and live use the same startup lag, complete-calendar reviews and whole-share execution.",
        "ETF proxy periods are excluded from prices and signal warm-up; raw NSE quotes establish share units.",
        "Historical constituent membership is inherited from the imported point-in-time dataset.",
        "Fractional diagnostic uses the same inputs and dates solely to isolate sizing effects.",
    ]
    report = _report(config, measured, validation)
    if blocked:
        warnings.append(
            f"INCOMPLETE: requested {start} to {end}; processed only through "
            f"{blocked['completed_through']}. No full-period performance claim is available."
        )
        report = (
            f"### S18 backtest stopped on {blocked['date']}\n\n"
            f"Symbol: **{blocked['symbol'] or 'unresolved'}**, tranche {blocked['tranche']}.\n\n"
            f"{blocked['reason']}\n\n{warnings[-1]}\n\n"
            "The comparison below covers only the successfully processed prefix."
        )
    result = {
        "report": report,
        "metrics": measured if not blocked else {},
        "partial_metrics": measured if blocked else {},
        "blocked": blocked,
        "comparison": comparison,
        "requested_window": {"start": str(start), "end": str(end)},
        "execution_mode": "whole_shares",
        "validation": validation,
        "trades": frame.to_dict("records"),
        "holdings": holdings,
        "equity_curve": curve,
        "fills": _display_fills(books),
        "cash_in_lieu": [s for b in books for s in b.cash_in_lieu],
        "pending_cash_in_lieu": [p for b in books for p in b.entitlement_rows(market)],
        "warnings": warnings,
        "provenance": market.provenance,
        "dataset": dataset.status(),
        "portfolio_state": {"books": [b.to_dict() for b in books]},
    }
    artifacts = {
        "summary.json": {
            "metrics": result["metrics"], "partial_metrics": result["partial_metrics"],
            "blocked": blocked, "comparison": comparison,
            "requested_window": result["requested_window"],
        },
        "sizing_comparison.csv": pd.DataFrame(comparison).to_csv(index=False),
        "holdings.csv": pd.DataFrame(holdings).to_csv(index=False),
        "fills.csv": pd.DataFrame(result["fills"]).to_csv(index=False),
        "cash_in_lieu.csv": pd.DataFrame(result["cash_in_lieu"]).to_csv(index=False),
        "pending_cash_in_lieu.csv": pd.DataFrame(result["pending_cash_in_lieu"]).to_csv(index=False),
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
            warnings=warnings,
            fills=result["fills"],
            comparison=comparison,
            pending_cash_in_lieu=result["pending_cash_in_lieu"],
        )
    group_id, refs = storage.save_artifacts(
        "s18_backtest",
        f"S18 {combo} {metal_mode} {start} to {end}",
        artifacts,
        metadata={
            "config": asdict(config), "validation": validation["status"],
            "execution_mode": "whole_shares", "blocked": blocked,
        },
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
        for p in book.pending_cash_in_lieu:
            p.qty /= ratios[p.gid]
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
        for position in [*book.positions, *book.pending_cash_in_lieu]:
            position.gid = mapping[position.gid]
        for order in book.queued_buys:
            order["gid"] = mapping[order["gid"]]


def _quote_units(market, identity, *, row=None, whole_shares=False):
    if whole_shares:
        return quote_factor(market, identity, row), "whole exchange shares"
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
            factor, units = _quote_units(
                market, holding["identity"], row=book.last_row,
                whole_shares=book.whole_shares,
            )
            for name in ("qty", "close", "peak", "stop"):
                holding[f"model_{name}"] = holding[name]
                if holding[name] is not None:
                    holding[name] *= factor if name == "qty" else 1 / factor
            if book.whole_shares:
                holding["qty"] = whole_quantity(holding["qty"], holding["identity"])
            holding["quantity_units"] = units
            holding["raw_to_book"] = factor
            rows.append(holding)
    return rows


def _display_fills(books):
    rows = []
    for book in books:
        for fill in book.fills:
            row = {**fill, "quantity_units": "adjusted model units"}
            if book.whole_shares:
                row.update(
                    model_qty=fill["qty"], model_price=fill["price"],
                    qty=fill["share_qty"], price=fill["share_price"],
                    quantity_units="whole shares at execution",
                )
            rows.append(row)
    return rows


def _orders(books, market, next_date):
    rows = []
    for book in books:
        nav = book.equity[-1]["nav"]
        estimates = {}
        skipped = {}
        if book.whole_shares:
            preview = deepcopy(book)
            fill_count, skipped_count = len(preview.fills), len(preview.skipped_buys)
            preview._open(
                market, book.last_row, at_close=True, execution_date=next_date
            )
            estimates = {
                f["identity"]: f for f in preview.fills[fill_count:] if f["side"] == "BUY"
            }
            skipped = {
                s["identity"]: s["reason"] for s in preview.skipped_buys[skipped_count:]
            }
        for p in book.positions:
            if p.queued_sell_reason:
                factor, units = _quote_units(
                    market, market.identities[p.gid], row=book.last_row,
                    whole_shares=book.whole_shares,
                )
                qty = p.qty * factor
                if book.whole_shares:
                    qty = whole_quantity(qty, market.identities[p.gid])
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
                        "qty": qty,
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
            factor, units = _quote_units(
                market, market.identities[g], row=book.last_row,
                whole_shares=book.whole_shares,
            )
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
            if book.whole_shares:
                fill = estimates.get(market.identities[g])
                qty = fill["share_qty"] if fill else 0
                price = float(market.close[book.last_row, g]) / factor
                rows[-1].update(
                    qty=qty,
                    reference_price=price,
                    estimated_value=qty * price,
                    estimated_cost=fill["model_cost"] if fill else 0.0,
                    estimated_amount=fill["amount"] if fill else 0.0,
                    sizing_status=(
                        "Estimated at last close" if fill else
                        skipped.get(market.identities[g], "Not fillable at last close")
                    ),
                    execution="whole shares at next open; resize for price, cash and costs",
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
        (
            "Holdings and fills use whole exchange shares. Buy instructions are "
            "estimates at the last close; final sizing uses the next opening price."
            if book.whole_shares else
            "Holdings below use adjusted model units. Next-open CSVs label their units "
            "and convert to current-share equivalents when verified raw anchors are supplied."
        ),
        "",
        "| Symbol | Sleeve | Quantity | Basis | Peak | Armed | Pending exit |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for p in book.positions:
        factor = (
            quote_factor(market, market.identities[p.gid], book.last_row)
            if book.whole_shares else 1.0
        )
        qty = (
            str(whole_quantity(p.qty * factor, market.identities[p.gid]))
            if book.whole_shares else f"{p.qty:.6f}"
        )
        lines.append(
            f"| {market.symbols[p.gid]} | {p.sleeve} | {qty} | "
            f"{p.basis:.2f} | {p.peak / factor:.4f} | {p.armed} | {p.queued_sell_reason} |"
        )
    lines.extend(["", "## Today's model fills"])
    today = [f for f in _display_fills([book]) if f["date"] == book.last_date]
    lines.extend(
        f"- {f['side']} {f['symbol']}: "
        f"{format(f['qty'], '.0f' if book.whole_shares else '.6f')} @ {f['price']:.4f} "
        f"({f['reason']}); model cost {f['model_cost']:.4f}."
        for f in today
    )
    if not today:
        lines.append("None.")
    lines.extend(["", "## Next-open model instructions"])
    pending = [o for o in orders if o["tranche"] == book.tranche]
    lines.extend(
        f"- {o['side']} {o['symbol']} ({o['sleeve']}): {o['reason']}; {o['execution']}."
        + (
            f" Estimated qty {o['qty']}, value {o['estimated_value']:.2f}, "
            f"cash including model cost {o['estimated_amount']:.2f}."
            if "estimated_amount" in o else ""
        )
        for o in pending
    )
    if not pending:
        lines.append("None.")
    lines.extend(
        f"- Skipped {s['symbol']}: {s['reason']}."
        for s in book.skipped_buys if s["date"] == book.last_date
    )
    lines.extend(["", *WARNINGS])
    return "\n".join(lines)


def _migrate_cash_only(saved, requested):
    if (
        not saved
        or saved.get("data_source") != "nse"
        or saved.get("book_fingerprint") != LEGACY_FRACTIONAL_BOOK
        or saved.get("schema_version") != SCHEMA_VERSION
        or saved.get("as_of") != str(requested)
    ):
        raise ValueError(
            "Cash-only migration requires the verified legacy live book at its saved date"
        )
    books = saved["books"]
    if len(books) != 2 or {b["tranche"] for b in books} != {"A", "B"}:
        raise ValueError("Cash-only migration requires both original tranches")
    for book in books:
        if (
            book.get("whole_shares", False)
            or any(book.get(k) for k in ("positions", "fills", "trades", "tax_ledger"))
            or any(book.get(k, 0) != 0 for k in (
                "realised_st", "realised_lt", "carry_st", "carry_lt", "tax_paid", "model_cost"
            ))
            or book["cash"] != saved["capital"] / 2
            or book["last_date"] != saved["as_of"]
            or not book["equity"]
            or any(
                e["cash"] != book["cash"] or e["nav"] != book["cash"] or e["positions"]
                for e in book["equity"]
            )
        ):
            raise ValueError(
                "Only a never-traded cash-only S18 book can migrate; "
                "existing fills or fractional holdings require a separate book"
            )
    migrated = deepcopy(saved)
    for book in migrated["books"]:
        book["whole_shares"] = True
    migrated["book_fingerprint"] = book_fingerprint()
    migrated["sizing_migration"] = {
        "from": "fractional_model", "to": "whole_shares",
        "as_of": saved["as_of"],
        "previous_artifact_group_id": saved["artifact_group_id"],
        "previous_book_fingerprint": saved["book_fingerprint"],
        "migrated_at": datetime.now(timezone.utc).isoformat(),
    }
    return migrated


def run_daily(
    *,
    combo="P15",
    metal_mode="both_priority",
    as_of=None,
    capital=100000.0,
    book_id="default",
    persist=True,
    shadow_charges=None,
    migrate_cash_only=False,
):
    from .data import load_market

    config = S18Config(combo, metal_mode)
    capital = validate_capital(capital)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", book_id):
        raise ValueError(
            "Book ID must use 1-64 letters, digits, underscores or hyphens"
        )
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    requested = date.fromisoformat(as_of) if as_of else today_ist
    if requested > today_ist:
        raise ValueError("S18 paper runs cannot consume future-dated sessions")
    data_source = "nse" if requested > date(2026, 8, 31) else "database"
    source = None
    if data_source == "nse":
        from .nse_sources import NseSources

        # Unlike prices, a missed membership observation cannot be downloaded later.
        source = NseSources()
        source.constituents(today_ist)
    dataset = get_dataset()
    validation = _certificate(dataset, required=True)
    key = f"book:{book_id}:{combo}:{metal_mode}"
    saved = storage.get_document(NAMESPACE, key)
    expected = saved
    if migrate_cash_only:
        saved = _migrate_cash_only(saved, requested)
    if saved and saved.get("data_source", data_source) != data_source:
        raise ValueError(
            "Use a separate book ID when moving from historical simulation to live data"
        )
    readiness = None
    if data_source == "nse":
        from .live_data import collect_market

        collected = collect_market(
            dataset=dataset,
            source=source,
            as_of=requested.isoformat(),
            metals=metal_mode != "none",
            inception=saved.get("inception_date") if saved else None,
            tracked_identities=(
                {
                    saved["identities"][p["gid"]]
                    for book in saved["books"]
                    for p in [
                        *book["positions"], *book["queued_buys"],
                        *book.get("pending_cash_in_lieu", []),
                    ]
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
        if data_source == "nse" and not all(b.whole_shares for b in books):
            raise ValueError(
                "This S18 live book uses fractional model sizing. Explicitly migrate "
                "a never-traded cash book, or start a separate whole-share book."
            )
        if migrate_cash_only and str(session) != saved["as_of"]:
            raise ValueError("Cash-only migration cannot advance the saved session")
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
        books = [
            Book.from_cash(config, t, capital / 2, whole_shares=data_source == "nse")
            for t in ("A", "B")
        ]
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
        "execution_mode": "whole_shares" if books[0].whole_shares else "fractional_model",
    }
    if saved and saved.get("sizing_migration"):
        state["sizing_migration"] = saved["sizing_migration"]
    report = _report(
        config, measured, validation, paper=True, overlay=bool(market.risk_off[last])
    )
    if books[0].whole_shares:
        report += (
            "\n\nLive sizing: **whole exchange shares**. Buy quantities are rounded "
            "down after model costs; unused allocation stays in cash. Next-session "
            "quantities and amounts are estimates at the last close, resized at the open."
        )
    result = {
        "report": report,
        "metrics": measured,
        "validation": validation,
        "holdings": holdings,
        "orders": orders,
        "trades": trades,
        "fills": _display_fills(books),
        "cash_in_lieu": [s for b in books for s in b.cash_in_lieu],
        "pending_cash_in_lieu": [p for b in books for p in b.entitlement_rows(market)],
        "skipped_buys": [s for b in books for s in b.skipped_buys],
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
            "cash_in_lieu.csv": pd.DataFrame(result["cash_in_lieu"]).to_csv(index=False),
            "pending_cash_in_lieu.csv": pd.DataFrame(result["pending_cash_in_lieu"]).to_csv(index=False),
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
        _save_book(key, expected, state)
        result["artifact_group_id"] = group
        result["artifacts"] = refs
    return result
