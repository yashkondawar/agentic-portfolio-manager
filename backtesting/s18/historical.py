"""Strict historical execution using actual NSE quotes, not rounded model units."""

import hashlib
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core import storage
from .book import Book
from .calendar import review_flags
from .data import PRICE_FIELDS, load_raw_market, prepare_market
from .signals import compute_signals
from .sizing import ExecutionDataError

# The fund's pre-2019 ISIN appears under GOLDBEES in the historical NSE tape.
GOLD_ISINS = ("INF732E01102", "INF204KB17I5")
SILVER_ISINS = ("INF204KC1402",)


class HistoricalExecutionBlocked(ValueError):
    def __init__(self, day, tranche, reason, completed_through, symbol=None):
        self.details = {
            "date": str(day), "tranche": tranche, "reason": str(reason),
            "completed_through": completed_through,
            "symbol": symbol,
        }
        super().__init__(f"{day}, tranche {tranche}, {symbol or 'unknown symbol'}: {reason}")


def _raw_quotes(raw, db_path):
    columns = {}
    for gid, chain in enumerate(raw.isin_chains):
        for isin in chain:
            columns.setdefault(isin, []).append(gid)
    if len(raw.symbols) > raw.n_stocks:
        for offset, chain in enumerate((GOLD_ISINS, SILVER_ISINS)):
            for isin in chain:
                gids = columns.setdefault(isin, [])
                if raw.n_stocks + offset not in gids:
                    gids.append(raw.n_stocks + offset)
    shape = raw.prices["close"].shape
    prices = {f: np.full(shape, np.nan) for f in PRICE_FIELDS}
    seen = np.zeros(shape, dtype=bool)
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as connection:
        tables = {
            r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"market_bars", "corporate_actions"} <= tables:
            raise ValueError("Strict S18 backtest needs raw NSE bars and corporate actions")
        for frame in pd.read_sql_query(
            "SELECT trade_date,isin,open,high,low,close,source FROM market_bars "
            "WHERE trade_date BETWEEN ? AND ?",
            connection, params=(str(raw.dates[0]), str(raw.dates[-1])), chunksize=100000,
        ):
            frame = frame[frame["isin"].isin(columns)].copy()
            frame["gid"] = frame["isin"].map(columns)
            frame = frame.explode("gid")
            if frame.empty:
                continue
            dates = frame["trade_date"].to_numpy(dtype="datetime64[D]")
            rows = np.searchsorted(raw.dates, dates)
            if np.any(rows >= len(raw.dates)) or np.any(raw.dates[rows] != dates):
                raise ValueError("Raw NSE dates disagree with the S18 session calendar")
            gids = frame["gid"].to_numpy(dtype=int)
            if frame.duplicated(["trade_date", "gid"]).any() or seen[rows, gids].any():
                raise ValueError("Ambiguous historical NSE quotes for an S18 identity")
            if frame["source"].fillna("").eq("").any():
                raise ValueError("Historical NSE quotes lack source provenance")
            seen[rows, gids] = True
            for field in PRICE_FIELDS:
                values = frame[field].to_numpy(dtype=float)
                if not np.isfinite(values).all() or np.any(values <= 0):
                    raise ValueError(f"Invalid raw historical NSE {field}")
                prices[field][rows, gids] = values
        actions = connection.execute(
            "SELECT isin,ex_date,kind,factor,subject FROM corporate_actions "
            "WHERE ex_date BETWEEN ? AND ? AND "
            "(factor IS NOT NULL OR kind LIKE '%demerger%')",
            (str(raw.dates[0]), str(raw.dates[-1])),
        ).fetchall()
    return prices, actions, columns


def _combined_share_factor(entries):
    aliases = {
        "split+bonus": "split_bonus",
        "split+dividend": "split",
        "bonus+dividend": "bonus",
    }
    kinds = [aliases.get(kind, kind) for kind, _, _ in entries]
    if (
        not kinds or set(kinds) - {"split", "bonus", "split_bonus"}
        or len(kinds) != len(set(kinds))
        or ("split_bonus" in kinds and len(kinds) > 1)
    ):
        return None
    factors = [float(f) for _, f, _ in entries if f is not None]
    if len(factors) != len(entries) or any(not math.isfinite(f) or f <= 0 for f in factors):
        return None
    return math.prod(factors)


def load_execution_market(*, source, metals):
    raw = load_raw_market(source=source, metals=metals)
    prices, actions, columns = _raw_quotes(raw, getattr(source, "db_path", storage.database_path()))
    factor = np.divide(
        raw.prices["close"], prices["close"],
        out=np.full(prices["close"].shape, np.nan),
        where=np.isfinite(prices["close"]),
    )
    for field in PRICE_FIELDS:
        valid = np.isfinite(raw.prices[field]) & np.isfinite(prices[field])
        mismatch = valid & ~np.isclose(
            raw.prices[field], prices[field] * factor, rtol=1e-6, atol=1e-6
        )
        if mismatch.any():
            row, gid = np.argwhere(mismatch)[0]
            raise ValueError(
                f"Unverified historical price scale: {raw.symbols[gid]} "
                f"{raw.dates[row]} {field}"
            )
    known_actions = {}
    for isin, ex_date, kind, adjustment, subject in actions:
        row = int(np.searchsorted(raw.dates, np.datetime64(ex_date)))
        if row >= len(raw.dates):
            continue
        for gid in columns.get(isin, []):
            known_actions.setdefault((row, gid), []).append((kind, adjustment, subject))
    events = {}
    share_factors = {key: _combined_share_factor(entries) for key, entries in known_actions.items()}
    for (row, gid), entries in known_actions.items():
        if any("demerger" in kind for kind, _, _ in entries):
            events[row, gid] = "demerger"
        elif share_factors[row, gid] is None:
            events[row, gid] = "unverified"
    for gid in range(len(raw.symbols)):
        rows = np.flatnonzero(np.isfinite(factor[:, gid]))
        if not len(rows):
            continue
        current = factor[rows[0], gid]
        for row in range(int(rows[0]) + 1, len(raw.dates)):
            observed = factor[row, gid]
            expected = share_factors.get((row, gid))
            if not math.isfinite(observed):
                if expected is not None and (row, gid) not in events:
                    current /= expected
                    events[row, gid] = "split_bonus"
                # Carry the share-unit scale, never a tradable price. A missing
                # tape row still cannot execute a buy or queued sell.
                factor[row, gid] = current
                continue
            adjustment = current / observed
            if expected is None and math.isclose(adjustment, 1.0, rel_tol=1e-6, abs_tol=1e-8):
                factor[row, gid] = current
                continue
            verified = (
                expected if expected is not None
                and math.isclose(expected, adjustment, rel_tol=1e-6, abs_tol=1e-8)
                else None
            )
            if (row, gid) not in events:
                events[row, gid] = "split_bonus" if verified is not None else "unverified"
            current = current / verified if verified is not None else observed
            factor[row, gid] = current
    # The imported adjusted panel contains rounding noise. One verified scale
    # per action interval prevents that noise from inventing fractional shares.
    verified_quotes = np.logical_and.reduce([
        np.isfinite(raw.prices[field]) & np.isfinite(prices[field])
        for field in PRICE_FIELDS
    ])
    for field in PRICE_FIELDS:
        raw.prices[field][verified_quotes] = (prices[field] * factor)[verified_quotes]
        raw.prices[field][~verified_quotes] = np.nan
    raw.universe[~verified_quotes] = False
    availability = []
    for gid in range(raw.n_stocks, len(raw.symbols)):
        available = verified_quotes[:, gid]
        if not available.any():
            raise ValueError(f"No actual exchange history for {raw.symbols[gid]}")
        availability.append({
            "symbol": raw.symbols[gid],
            "first_verified_quote": str(raw.dates[np.flatnonzero(available)[0]]),
        })
        for field in PRICE_FIELDS:
            raw.prices[field][~available, gid] = np.nan
        raw.universe[~available, gid] = False
    digest = hashlib.sha256()
    for field in PRICE_FIELDS:
        digest.update(prices[field].tobytes())
    raw.provenance.update(
        execution_quote_source="raw NSE market_bars matched by ISIN and session",
        execution_quote_hash=digest.hexdigest(),
        execution_action_hash=hashlib.sha256(
            json.dumps(actions, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        metal_availability=availability,
        raw_to_book_events=[
            {
                "date": str(raw.dates[row]), "identity": raw.identities[gid],
                "kind": kind,
                "factor": (
                    float(factor[row - 1, gid] / factor[row, gid])
                    if row > 0 and np.isfinite(factor[row - 1:row + 1, gid]).all()
                    else 1.0
                ),
            }
            for (row, gid), kind in sorted(events.items())
        ],
    )
    signal = compute_signals(
        raw.prices["close"], raw.benchmark, raw.universe, raw.rows, n_stocks=raw.n_stocks
    )
    prepared = prepare_market(
        raw, signal,
        last_rows=np.full(len(raw.symbols), len(raw.rows) - 1, dtype=np.int64),
    )
    prepared.execution_factors = factor[raw.rows]
    return prepared


def simulate_live(
    market, config, *, start, end, capital_per_tranche, whole_shares=True
):
    start_date, end_date = np.datetime64(start, "D"), np.datetime64(end, "D")
    first = int(np.searchsorted(market.dates, start_date))
    last = int(np.searchsorted(market.dates, end_date, side="right")) - 1
    if start_date > end_date or first > last or first >= len(market.dates):
        raise ValueError("S18 backtest window has no valid ordered exchange sessions")
    if start_date < market.dates[0] or end_date > market.dates[-1]:
        raise ValueError("S18 backtest window is outside verified historical coverage")
    calendar = np.asarray(market.provenance["session_calendar"], dtype="datetime64[D]")
    flags = {
        tranche: review_flags(
            calendar, tranche,
            complete_through=market.provenance.get("calendar_complete_through"),
        )
        for tranche in ("A", "B")
    }
    order = market.s1_order(config.tiered, config.metal_mode == "both_priority")
    books = [
        Book.from_cash(config, t, capital_per_tranche, whole_shares=whole_shares)
        for t in ("A", "B")
    ]
    for book in books:
        book.allowed_history = [0] * 5
    for row in range(first, last + 1):
        ci = int(np.searchsorted(calendar, market.dates[row]))
        if ci >= len(calendar) or calendar[ci] != market.dates[row]:
            raise ValueError("Historical S18 price session is missing from the calendar")
        for book in books:
            try:
                book.step(
                    market, row, review=bool(flags[book.tranche][ci]),
                    order=order[row], initial=row == first,
                )
            except ExecutionDataError as exc:
                completed = str(market.dates[row - 1]) if row > first else None
                raise HistoricalExecutionBlocked(
                    market.dates[row], book.tranche, exc, completed,
                    market.symbols[market.identities.index(exc.identity)]
                    if exc.identity is not None else None,
                ) from exc
    return books
