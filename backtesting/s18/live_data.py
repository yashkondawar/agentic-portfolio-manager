"""Official-NSE forward data, with a price-only bridge before paper inception.

September prices are usable for warm-up; today's constituent list is NOT a
September membership observation. Only dated snapshots collected on their
actual observation day may drive paper decisions. The original kit stays read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from core import storage
from .data import (
    METAL_IDENTITIES,
    PRICE_FIELDS,
    RawMarket,
    load_raw_market,
    prepare_market,
)
from .signals import compute_signals
from .calendar import review_flags

START = date(2026, 9, 1)
NAMESPACE = "s18.live"
WARMUP_SESSIONS = 315  # 252-close high at each of the last 63 sessions.


@dataclass
class LiveData:
    market: object
    readiness: dict


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _source_info(result):
    return {
        "source": result.source,
        "fetched_at": result.fetched_at,
        "metadata": result.metadata,
    }


def _voluntary_offer(action):
    return action["kind"] == "other" and bool(
        re.search(r"\bbuy[\s-]*back\b|\brights\b", action["subject"], re.IGNORECASE)
    )


def _member_scope(snapshot):
    eligible, excluded = [], []
    series_map = snapshot.metadata.get("series_by_isin", {})
    for record in snapshot.records:
        series = record.get("series") or series_map.get(record["isin"])
        if not series:
            raise ValueError(
                f"Missing official constituent series for {record['symbol']}"
            )
        reason = None
        if series not in ("EQ", "BE", "BZ"):
            reason = f"NSE series {series} is outside the original S18 EQ/BE/BZ scope"
        elif record["isin"].startswith("DUM") and record["symbol"].startswith("DUMMY"):
            reason = (
                "Non-executable synthetic index component; no exchange share history"
            )
        if reason:
            excluded.append({**record, "series": series, "reason": reason})
        else:
            eligible.append(record)
    if not eligible:
        raise ValueError("No eligible stocks in the official constituent observation")
    return eligible, excluded


def _read_cached_anchor(connection, chain, day):
    marks = ",".join("?" for _ in chain)
    rows = connection.execute(
        f"SELECT isin,close,source FROM market_bars WHERE isin IN ({marks}) "
        "AND trade_date=? AND close>0",
        (*chain, str(day)),
    ).fetchall()
    if not rows:
        return None
    values = {float(r["close"]) for r in rows}
    if len(values) != 1:
        raise ValueError(f"Ambiguous raw NSE anchor for {chain} on {day}")
    value = values.pop()
    return value, {
        "date": str(day),
        "close": value,
        "source": "market_bars",
        "isins": list(chain),
        "row_hash": _hash([dict(r) for r in rows]),
    }


def _anchors(raw, source, connection, required):
    anchors, evidence = {}, {}
    archive = {}
    for g, identity in enumerate(raw.identities):
        if identity not in required:
            anchors[identity] = 1.0
            evidence[identity] = {"source": "inactive_unheld_history_only"}
            continue
        seen = np.flatnonzero(np.isfinite(raw.prices["close"][:, g]))
        if not len(seen):
            anchors[identity] = 1.0
            evidence[identity] = {"source": "no_observed_kit_prices"}
            continue
        row = int(seen[-1])
        day = raw.dates[row].astype(object)
        chain = raw.isin_chains[g]
        found = _read_cached_anchor(connection, chain, day)
        if found is None:
            if day not in archive:
                archive[day] = source.bhavcopy(day)
            matches = [r for r in archive[day].records if r["isin"] in chain]
            if len(matches) != 1:
                raise ValueError(
                    f"Cannot establish raw-price seam for {identity} on {day}"
                )
            found = float(matches[0]["close"]), {
                **_source_info(archive[day]),
                "record": matches[0],
            }
        raw_close, record = found
        factor = float(raw.prices["close"][row, g]) / raw_close
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError(f"Invalid raw-price seam for {identity}")
        anchors[identity], evidence[identity] = factor, record
    return anchors, evidence


def _registry(raw, securities, members, actions, saved):
    entries = [
        {"identity": identity, "isins": list(chain), "symbol": symbol}
        for identity, chain, symbol in zip(raw.identities, raw.isin_chains, raw.symbols)
    ]
    by_id = {e["identity"]: e for e in entries}
    for entry in saved or []:
        if entry["identity"] in by_id:
            known = by_id[entry["identity"]]
            known["isins"] = list(dict.fromkeys([*known["isins"], *entry["isins"]]))
        else:
            entries.append(dict(entry))
            by_id[entry["identity"]] = entries[-1]
    by_isin = {isin: e for e in entries for isin in e["isins"]}
    by_symbol = {}
    for entry in entries:
        by_symbol.setdefault(entry["symbol"], []).append(entry)
    # An observed corporate-action filing, not a ticker match alone, bridges
    # a new equity ISIN to the already-known company.
    for action in actions:
        isin, symbol = action["isin"], action["symbol"]
        if isin in by_isin or action["kind"] not in (
            "split",
            "bonus",
            "split_bonus",
            "isin_change",
        ):
            continue
        matches = by_symbol.get(symbol, [])
        if len(matches) == 1 and isin:
            matches[0]["isins"].append(isin)
            by_isin[isin] = matches[0]
    masters = {r["isin"]: r for r in securities}
    for member in members:
        if member["isin"] in by_isin:
            continue
        master = masters.get(member["isin"])
        if master is None or not master.get("listed_on"):
            raise ValueError(f"Missing NSE listing evidence for {member['symbol']}")
        identity = "ISIN:" + member["isin"]
        entry = {
            "identity": identity,
            "isins": [member["isin"]],
            "symbol": member["symbol"],
            "listed_on": master["listed_on"],
        }
        entries.append(entry)
        by_isin[member["isin"]] = entry
    stocks = [e for e in entries if e["identity"] not in METAL_IDENTITIES]
    metals = [e for e in entries if e["identity"] in METAL_IDENTITIES]
    return stocks + metals


def _new_history(connection, entry, dates, actions):
    """NSE raw-cache warm-up for older stocks newly entering the index."""
    n = len(dates)
    result = {f: np.full(n, np.nan) for f in PRICE_FIELDS}
    first = max(0, n - WARMUP_SESSIONS)
    marks = ",".join("?" for _ in entry["isins"])
    rows = connection.execute(
        f"SELECT trade_date,open,high,low,close,isin FROM market_bars "
        f"WHERE isin IN ({marks}) AND trade_date BETWEEN ? AND ? ORDER BY trade_date",
        (*entry["isins"], str(dates[first]), str(dates[-1])),
    ).fetchall()
    by_day = {}
    for row in rows:
        day = row["trade_date"]
        if day in by_day:
            raise ValueError(f"Ambiguous warm-up identity {entry['identity']} on {day}")
        by_day[day] = dict(row)
    relevant = [
        a
        for a in actions
        if a["isin"] in entry["isins"]
        and str(dates[first]) <= a["ex_date"] <= str(dates[-1])
    ]
    needs_review = [
        a for a in relevant if a.get("requires_review") and not _voluntary_offer(a)
    ]
    if needs_review:
        raise ValueError(
            f"New-constituent warm-up action needs review: {entry['symbol']} "
            f"{needs_review[0]['ex_date']} {needs_review[0]['subject']}"
        )
    coverage = {
        r[0]
        for r in connection.execute(
            "SELECT DISTINCT trade_date FROM market_bars "
            "WHERE trade_date BETWEEN ? AND ?",
            (str(dates[first]), str(dates[-1])),
        )
    }
    absent = [str(day) for day in dates[first:] if str(day) not in coverage]
    if absent:
        raise ValueError(f"Raw NSE cache has missing warm-up sessions: {absent[:3]}")
    for i in range(first, n):
        row = by_day.get(str(dates[i]))
        if row is None:
            continue
        if any(
            row[f] is None or not math.isfinite(row[f]) or row[f] <= 0
            for f in PRICE_FIELDS
        ):
            raise ValueError(f"Invalid cached NSE warm-up bar for {entry['identity']}")
        factor = 1.0
        for action in relevant:
            if action["ex_date"] <= row["trade_date"]:
                continue
            if action["kind"] in ("split", "bonus", "split_bonus"):
                factor *= _numeric_factor(action)
            elif action["kind"] == "demerger":
                raise ValueError(
                    f"New constituent {entry['symbol']} needs reviewed pre-kit demerger adjustment"
                )
        for field in PRICE_FIELDS:
            result[field][i] = row[field] * factor
    listed = date.fromisoformat(entry["listed_on"])
    if (
        listed <= dates[first].astype(object)
        and not np.isfinite(result["close"][first : first + 10]).any()
    ):
        raise ValueError(
            f"Insufficient NSE warm-up for established constituent {entry['symbol']}; "
            "backfill its raw history before forward operation"
        )
    return result, _hash({"rows": list(by_day.values()), "actions": relevant})


def _numeric_factor(action):
    factor = action.get("factor")
    if factor is None or not math.isfinite(float(factor)) or float(factor) <= 0:
        raise ValueError(
            f"Unresolved corporate action: {action['symbol']} {action['subject']}"
        )
    return float(factor)


def collect_market(
    *,
    as_of,
    metals=True,
    inception=None,
    source=None,
    db_path=None,
    now=None,
    tracked_identities=(),
    dataset=None,
) -> LiveData:
    if source is None:
        from .nse_sources import NseSources

        source = NseSources(db_path=db_path, now=now)
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    today = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
    requested = date.fromisoformat(as_of)
    if requested > today or requested < START:
        raise ValueError(
            "Live NSE collection requires a completed date from 2026-09-01 onwards"
        )
    raw = load_raw_market(source=dataset, metals=metals)
    index_anchor = source.index_close(raw.dates[-1].astype(object))
    if (
        len(index_anchor.records) != 1
        or index_anchor.records[0]["date"] != str(raw.dates[-1])
        or not math.isclose(
            float(index_anchor.records[0]["close"]),
            float(raw.benchmark[-1]),
            rel_tol=0.0001,
            abs_tol=0.02,
        )
    ):
        raise ValueError(
            "NSE Nifty500 price-index anchor does not match the S18 warm-up seam"
        )
    month_after = (pd.Timestamp(requested) + pd.offsets.MonthBegin(1)).date()
    calendar_result = source.calendar(START, month_after + timedelta(days=6))
    calendar_records = calendar_result.records
    calendar_days = [
        date.fromisoformat(r["date"]) for r in calendar_records if r["is_session"]
    ]
    complete_calendar = np.concatenate(
        (raw.dates, np.array(calendar_days, dtype="datetime64[D]"))
    )
    reviews = {
        tranche: review_flags(
            complete_calendar,
            tranche,
            complete_through=calendar_result.metadata["complete_through"],
        )
        for tranche in ("A", "B")
    }
    cutoff = requested
    if requested == today and now.astimezone(ZoneInfo("Asia/Kolkata")).hour < 18:
        cutoff -= timedelta(days=1)
    sessions = [d for d in calendar_days if d <= cutoff]
    if not sessions:
        raise ValueError("No completed post-kit exchange session is available")
    last = sessions[-1]
    next_session = next((d for d in calendar_days if d > last), None)
    if next_session is None:
        raise ValueError("NSE calendar does not include the next exchange session")

    # Capture today's snapshot even on holidays, but never use it for an
    # earlier decision date. This is the bootstrap for genuinely forward PIT data.
    observed = source.constituents(today)
    snapshots = {}
    decision_start = date.fromisoformat(inception) if inception else last
    pending = False
    from .nse_sources import SourceUnavailable

    for day in sessions:
        if day < decision_start:
            continue
        try:
            snapshots[day] = source.constituents(day)
        except SourceUnavailable:
            if inception or requested != today or day != last:
                raise
            pending = True
    masters = source.securities()
    action_result = source.actions(START, last)
    actions = action_result.records
    key = raw.provenance["content_hash"]
    saved_registry = storage.get_document(
        NAMESPACE, f"identities:{key}", [], db_path=db_path
    )
    membership_inputs = list(snapshots.values()) if snapshots else [observed]
    all_members = {
        r["isin"]: r
        for snapshot in membership_inputs
        for r in _member_scope(snapshot)[0]
    }
    entries = _registry(
        raw, masters.records, list(all_members.values()), actions, saved_registry
    )
    if any(
        e["identity"] not in raw.identities
        and date.fromisoformat(e["listed_on"]) < START
        for e in entries
    ):
        action_start = raw.dates[max(0, len(raw.dates) - WARMUP_SESSIONS)].astype(
            object
        )
        older_actions = source.actions(action_start, START - timedelta(days=1))
        actions = [*older_actions.records, *actions]
    identities = tuple(e["identity"] for e in entries)
    by_isin = {isin: i for i, e in enumerate(entries) for isin in e["isins"]}
    n_stocks = sum(e["identity"] not in METAL_IDENTITIES for e in entries)
    old_gid = {identity: i for i, identity in enumerate(raw.identities)}
    n_old = len(raw.dates)
    dates = np.concatenate((raw.dates, np.array(sessions, dtype="datetime64[D]")))
    prices = {f: np.full((len(dates), len(entries)), np.nan) for f in PRICE_FIELDS}
    universe = np.zeros((len(dates), len(entries)), dtype=bool)
    new_history_hashes = {}
    continuing_isins = {r["isin"] for r in masters.records} | set(all_members)
    required_anchors = (
        {
            entry["identity"]
            for entry in entries
            if entry["identity"] in old_gid
            and continuing_isins.intersection(entry["isins"])
        }
        | {
            identity
            for g, identity in enumerate(raw.identities)
            if np.isfinite(raw.prices["close"][-1, g])
        }
        | set(raw.identities[raw.n_stocks :])
    )
    from scraper.bhavcopy import open_store

    connection = open_store(db_path)
    connection.close()
    with storage.connection_scope(db_path) as connection:
        anchors, anchor_evidence = _anchors(raw, source, connection, required_anchors)
        for g, entry in enumerate(entries):
            identity = entry["identity"]
            if identity in old_gid:
                old = old_gid[identity]
                for field in PRICE_FIELDS:
                    prices[field][:n_old, g] = raw.prices[field][:, old]
                universe[:n_old, g] = raw.universe[:, old]
            else:
                history, checksum = _new_history(connection, entry, raw.dates, actions)
                for field in PRICE_FIELDS:
                    prices[field][:n_old, g] = history[field]
                anchors[identity] = 1.0
                new_history_hashes[identity] = checksum
    benchmark = np.concatenate((raw.benchmark, np.zeros(len(sessions))))
    scales = dict(anchors)
    adjustments = {identity: 1.0 for identity in identities}
    day_bars, source_days = {}, {}
    current_symbols = dict(zip(raw.identities, raw.symbols))
    for day in sessions:
        bars = source.bhavcopy(day)
        index = source.index_close(day)
        if len(index.records) != 1 or index.records[0]["date"] != str(day):
            raise ValueError(f"Unverified Nifty500 close on {day}")
        selected = {}
        for record in bars.records:
            if record["isin"] not in by_isin:
                continue
            g = by_isin[record["isin"]]
            if (
                anchor_evidence.get(identities[g], {}).get("source")
                == "inactive_unheld_history_only"
            ):
                raise ValueError(
                    f"Previously inactive {record['symbol']} resumed trading; "
                    "verify its raw-price anchor before adding it to the live panel"
                )
            if g in selected:
                raise ValueError(
                    f"Competing NSE ISIN aliases for {identities[g]} on {day}"
                )
            selected[g] = record
            current_symbols[identities[g]] = record["symbol"]
        day_bars[day] = selected
        source_days[day] = (bars, index)
    master_isins = {r["isin"] for r in masters.records}
    for identity in tracked_identities:
        entry = next((e for e in entries if e["identity"] == identity), None)
        if entry is None:
            raise ValueError(f"Held identity cannot be resolved: {identity}")
        g = identities.index(identity)
        if g not in day_bars[last] and not master_isins.intersection(entry["isins"]):
            raise ValueError(
                f"Held {entry['symbol']} is absent from both the NSE master and latest tape; "
                "verify suspension/delisting before advancing its paper book"
            )
    fingerprints, events, voluntary_offers = {}, [], []
    action_days = {}
    for action in actions:
        ex = date.fromisoformat(action["ex_date"])
        if ex < START or ex > last:
            continue
        if action["isin"] not in by_isin:
            matching = [
                e
                for e in entries
                if current_symbols.get(e["identity"], e["symbol"]) == action["symbol"]
            ]
            if matching and action["kind"] in (
                "split",
                "bonus",
                "split_bonus",
                "demerger",
            ):
                raise ValueError(
                    f"Unresolved corporate-action ISIN for {action['symbol']}"
                )
            continue
        g = by_isin[action["isin"]]
        voluntary = _voluntary_offer(action)
        if voluntary:
            voluntary_offers.append(
                {
                    **action,
                    "identity": identities[g],
                    "paper_treatment": "No participation; no new units, cash, or price adjustment",
                }
            )
        if (
            action.get("requires_review")
            and not voluntary
            and action["kind"] not in ("demerger", "isin_change")
            and (
                identities[g] in tracked_identities
                or any(r["isin"] in entries[g]["isins"] for r in all_members.values())
            )
        ):
            raise ValueError(
                f"Price-affecting corporate action needs review: {action['symbol']} "
                f"{action['ex_date']} {action['subject']}"
            )
        if action["kind"] == "other" and not voluntary:
            if any(
                word in action["subject"].lower()
                for word in ("rights", "merger", "consolidat", "reduction", "delist")
            ) and (
                identities[g] in tracked_identities
                or any(r["isin"] in entries[g]["isins"] for r in all_members.values())
            ):
                raise ValueError(
                    f"Corporate-action review required: {action['symbol']} {action['subject']}"
                )
            continue
        effective = next((d for d in sessions if d >= ex), None)
        if effective is not None:
            action_days.setdefault(effective, []).append((g, action))
    for offset, day in enumerate(sessions):
        bars, index = source_days[day]
        benchmark[n_old + offset] = float(index.records[0]["close"])
        applied = []
        seen_actions = set()
        for g, action in action_days.get(day, []):
            signature = (g, action["kind"])
            if signature in seen_actions and action["kind"] not in (
                "dividend",
                "isin_change",
                "other",
            ):
                raise ValueError(f"Duplicate price action on {day}: {action['symbol']}")
            kinds = {kind for column, kind in seen_actions if column == g} | {
                action["kind"]
            }
            if "split_bonus" in kinds and kinds.intersection({"split", "bonus"}):
                raise ValueError(
                    f"Overlapping split/bonus actions on {day}: {action['symbol']}"
                )
            seen_actions.add(signature)
            factor = 1.0
            if action["kind"] in ("split", "bonus", "split_bonus"):
                factor = _numeric_factor(action)
            elif action["kind"] == "demerger":
                first = next(
                    (day_bars[d][g] for d in sessions if d >= day and g in day_bars[d]),
                    None,
                )
                if first is None:
                    raise ValueError(
                        f"Demerger needs first post-ex-date tape: {action['symbol']}"
                    )
                ratio = float(first["close"]) / float(first["prev_close"])
                factor = ratio if abs(ratio - 1) > 0.10 else 1.0
            identity = identities[g]
            scales[identity] /= factor
            adjustments[identity] *= factor
            applied.append(action)
            events.append(
                {
                    "date": str(day),
                    "identity": identity,
                    "factor": factor,
                    "kind": action["kind"],
                    "raw_to_book": scales[identity],
                }
            )
        for g, record in day_bars[day].items():
            for field in PRICE_FIELDS:
                value = float(record[field])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(
                        f"Invalid NSE {field} for {record['symbol']} on {day}"
                    )
                prices[field][n_old + offset, g] = value * scales[identities[g]]
        snapshot = snapshots.get(day)
        if snapshot is not None:
            for member in _member_scope(snapshot)[0]:
                g = by_isin.get(member["isin"])
                if g is None or g >= n_stocks:
                    raise ValueError(
                        f"Unresolved stock constituent {member['symbol']} on {day}"
                    )
                universe[n_old + offset, g] = g in day_bars[day]
        universe[n_old + offset, n_stocks:] = True
        fingerprints[str(day)] = _hash(
            {
                "version": "s18-nse-day-v2",
                "date": str(day),
                "bhavcopy": bars.source,
                "index": index.source,
                "membership": (
                    snapshot.source if snapshot is not None else "price_only_warmup"
                ),
                "actions": sorted(applied, key=lambda a: (a["isin"], a["subject"])),
                "calendar": {
                    "date": str(day),
                    "is_session": True,
                    "reviews": {
                        tranche: bool(
                            flags[
                                int(
                                    np.searchsorted(
                                        complete_calendar, np.datetime64(day)
                                    )
                                )
                            ]
                        )
                        for tranche, flags in reviews.items()
                    },
                },
            }
        )
    bootstrap_hash = _hash(
        {
            "anchors": anchor_evidence,
            "new_constituent_warmup": new_history_hashes,
        }
    )
    factors = np.array([adjustments[i] for i in identities])
    for field in PRICE_FIELDS:
        prices[field] *= factors
    rows = np.arange(raw.rows[0], len(dates), dtype=np.int64)
    provenance = {
        **raw.provenance,
        "source": "official_nse_live",
        "as_of": str(last),
        "stock_signals": "recomputed",
        "metal_signals": "recomputed" if metals else "disabled",
        "price_scales": adjustments,
        "raw_to_book": {i: scales[i] * adjustments[i] for i in identities},
        "raw_to_kit_anchors": anchors,
        "anchor_evidence": anchor_evidence,
        "index_anchor": _source_info(index_anchor),
        "new_constituent_warmup_hashes": new_history_hashes,
        "bootstrap_hash": bootstrap_hash,
        "raw_to_book_events": [
            {**e, "raw_to_book": e["raw_to_book"] * adjustments[e["identity"]]}
            for e in events
        ],
        "session_calendar": [str(d) for d in raw.dates]
        + [str(d) for d in calendar_days],
        "calendar_complete_through": calendar_result.metadata["complete_through"],
        "calendar_evidence": _source_info(calendar_result),
        "history_fingerprints": fingerprints,
        "history_fingerprint_version": "s18-nse-day-v2",
        "decision_start": str(decision_start) if not pending else None,
        "membership_policy": "dated observations only; pre-inception bridge is price-only",
        "instrument_scope": "EQ/BE/BZ stocks plus enabled metal ETFs; RR REITs excluded",
        "excluded_constituents": _member_scope(membership_inputs[-1])[1],
        "voluntary_offer_policy": "No participation in rights offers or buybacks",
        "voluntary_offers": voluntary_offers,
        "current_symbols": current_symbols,
        "delisting_policy": "not inferred from missing quotes; unresolved events require review",
        "engine_indices": {identity: i for i, identity in enumerate(identities)},
    }
    assembled = RawMarket(
        dates,
        prices,
        universe,
        benchmark,
        rows,
        tuple(current_symbols.get(e["identity"], e["symbol"]) for e in entries),
        identities,
        tuple(tuple(e["isins"]) for e in entries),
        n_stocks,
        provenance,
    )
    signal = compute_signals(
        prices["close"], benchmark, universe, rows, n_stocks=n_stocks
    )
    # Absence from a complete bhavcopy proves non-trading, not delisting.
    prepared = prepare_market(
        assembled,
        signal,
        last_rows=np.full(len(entries), len(rows) - 1, dtype=np.int64),
    )
    readiness = {
        "status": "waiting_for_first_snapshot" if pending else "ready",
        "latest_price_date": str(last),
        "next_session": str(next_session),
        "observed_constituents_date": str(today),
        "price_bridge_sessions": len(sessions),
        "decision_start": provenance["decision_start"],
        "excluded_constituents": provenance["excluded_constituents"],
        "voluntary_offers": voluntary_offers,
        "message": (
            "Warm-up collected. No retrospective paper trades or constituent assumptions; "
            "the book starts on the next session with a fresh dated snapshot."
            if pending
            else "Official NSE inputs validated for paper decisions."
        ),
    }
    storage.set_document(NAMESPACE, f"identities:{key}", entries, db_path=db_path)
    storage.set_document(NAMESPACE, f"readiness:{key}", readiness, db_path=db_path)
    return LiveData(prepared, readiness)
