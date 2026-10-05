"""Fail-closed, offline S18 daily extension imports (no implicit network fetches).

``load_forward(kit_path, extension_path, metals=..., as_of="YYYY-MM-DD")``
requires these UTF-8 CSVs in ``extension_path``. Headers below are required;
extra columns are allowed. Dates are ISO dates, interval endpoints inclusive,
blank ``valid_to`` / ``delisted_on`` means open-ended. ``source`` must identify
the verified exchange file/notice, not merely say "latest".

* calendar.csv: date,is_session,source
  EVERY calendar date from 2026-09-01 through at least as_of's month-end AND
  one subsequent exchange session; is_session is 0 or 1. Include special
  sessions and holidays explicitly. This is not a weekday-derived calendar.
* instruments.csv:
  identity,isin,symbol,valid_from,valid_to,listed_on,delisted_on
  One row per effective-dated alias. identity is ``ISIN:<first kit ISIN>`` for
  an existing company, retained across ISIN changes; a new company's identity
  uses its first ISIN. Cover ALL kit companies, even former members. Delisted_on
  is the first no-longer-listed date, never inferred from a missing last bar.
  All aliases for one company must agree on its listing/delisting dates.
  Include GOLD/SILVER identities from data.METAL_IDENTITIES when metals=True.
* anchors.csv: identity,date,raw_close,source
  Every continuing kit company needs its final observed kit session's verified
  as-traded close. This establishes kit_close/raw_close, not an assumed unit
  seam. A new company needs no anchor (initial multiplier 1).
* sessions.csv:
  date,nifty500_close,bhavcopy_complete,actions_complete,membership_complete,
  member_count,source
  Exactly one row per required exchange session from 2026-09-01. The three
  completeness attestations must be 1; member_count is the full PIT snapshot
  size (stocks only). The benchmark is the Nifty 500 PRICE index, not TRI.
* prices.csv: date,isin,status,open,high,low,close,prev_close
  One explicit record for EVERY listed, non-delisted instrument per required
  session, not just today's members. status is traded or suspended. A traded
  record has five positive raw NSE prices (prev_close is NOT adjusted);
  suspended records have all five price cells empty. Identity is resolved by
  ISIN plus the alias effective date, never by ticker. No missing row silently
  becomes a suspension. Include EQ, BE and BZ bhavcopy bars: the existing
  scraper's EQ/BE-only filter is not by itself complete S18 coverage.
* membership.csv: effective_from,effective_to,identity,source
  Full PIT constituent snapshots with explicit, finite validity intervals.
  All rows of a snapshot share its interval; distinct intervals must not
  overlap. Cover every required session, including removals. Never substitute
  scraper.index_membership's current list for an absent historical snapshot.
* actions.csv: identity,ex_date,kind,subject,factor,source
  May be header-only (sessions attest that actions were checked). Kinds:
  split, bonus, split_bonus, demerger, dividend, isin_change. Split/bonus
  factors use scraper.corporate_actions' subject parsers; a verified numeric
  factor may supply an otherwise unparseable ratio. If both exist they must
  agree. A demerger uses close/prev_close on the first traded session on or
  after ex_date, only when |ratio-1| > .10; its factor cell may be empty or
  equal that result. Dividends never adjust prices or credit cash.

Scale contract
--------------
Every returned OHLC series is back-adjusted into the share units at ``as_of``.
``provenance["price_scales"][identity]`` is the cumulative multiplicative
post-kit split/bonus/demerger factor applied to ALL original kit OHLC history,
default 1. For persisted state, ratio = new_scale / old_scale: qty /= ratio;
peak and historical entry/exit prices *= ratio; cost basis/cash do not change.
Do that rebasing ONCE before processing newly appended sessions.

Internally, forward raw prices first join the fixed kit unit seam using their
verified anchor. The entire joined history is then multiplied by price_scales.
``raw_to_book`` is the final-session raw quote conversion; ``raw_to_book_events``
and ``raw_to_book_anchors`` give dated historical conversions in this returned
as-of share base. ``raw_to_kit_anchors`` retains the unrebased seam evidence.
Raw-input history fingerprints deliberately do not include later-effective
actions' rebasing, so an ordinary split is not mistaken for a data revision.
``history_fingerprints`` maps each consumed forward session's ISO date to a
SHA-256 of canonical raw OHLC/prev_close records, index/coverage row, calendar
row, applicable membership/source records, effective ISIN/symbol mappings,
raw anchor evidence and that session's effective corporate-action records.
CSV row order is immaterial. A later alias or snapshot expiry does not rewrite
the earlier resolved mapping; future interval endpoints and cumulative scales
are excluded. Corrections to previously consumed inputs change their hashes.
Demergers follow the specified tape-price convention, not delivery of a child
company's shares. This is a paper model, not a brokerage execution adapter.

``canonical_indices`` reserves the original kit stock IDs followed by both
metal IDs IN EVERY MODE, then appends new companies in listing-date/ISIN order.
``canonical_identities`` is that append-only global identity list. The engine's
matrix layout remains stocks-first, enabled-metals-last; ``engine_indices``
maps identities to those columns. Persist identities, not mode-dependent gids.

The existing bhavcopy/CA/PIT stores can help produce this verified bundle, but
they do not establish complete free Nifty500, calendar and constituent coverage.
This importer deliberately does not promise automatic scraping or best effort.

After-close collection assessment (no endpoint requests made by this module)
--------------------------------------------------------------------------
Reusable pieces:
* scraper.bhavcopy provides the final UDiFF URL, NSE session/throttling, OHLC,
  prev_close and ISIN parsers, and market_bars storage. Its current URL is
  https://nsearchives.nseindia.com/content/cm/
  BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip (concatenate the two lines).
* scraper.corporate_actions provides fetch_window/fetch_symbol at
  https://www.nseindia.com/api/corporates-corporateActions with index=equities
  and from_date/to_date=DD-MM-YYYY, plus split/bonus parsers already reused here.

Those fetchers cannot certify S18 completeness unchanged: bhavcopy.fetch_day
returns "holiday" for exhausted transport/HTTP/parse failures, not just verified
holidays; run() persists that result and iterates weekdays only. Its parsers
exclude BZ and stamp the requested date without checking the payload's session.
CA fetch_window/fetch_symbol return [] on failed/non-list responses, and run()
can mark those windows complete. Empty confirmed data and fetch failure need
distinct outcomes, with immutable raw downloads and retryable pending dates.

Still missing are a verified Nifty500 PRICE-index daily-close downloader/parser;
dated ind_nifty500list.csv snapshots with announced effective reconstitution
dates (the repo's third-party interval import is not that collector); a complete
official exchange calendar including future/special sessions; effective ISIN
and symbol-change ingestion, explicit suspension/delisting notices, and an
adapter that joins these to kit anchors and emits all seven verified CSVs.
Official source candidates to validate, NOT working integrations, include the
NSE archive paths /content/indices/ind_close_all_DDMMYYYY.csv,
/content/indices/ind_nifty500list.csv, /content/equities/symbolchange.csv and
/content/equities/eq_etfseclist.csv; the NSE holiday-master API plus special
session circulars is a calendar candidate, not a verified full calendar.
No existing database coverage counter alone may set this bundle's completeness
flags. Missing September-onward constituent snapshots must be recovered from
dated evidence, never projected backward from today's membership.
"""

import calendar
import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path
import re

import numpy as np

from .data import (
    METAL_IDENTITIES,
    PRICE_FIELDS,
    RawMarket,
    content_provenance,
    load_raw_kit,
    prepare_market,
    validate_prices,
)
from .signals import compute_signals

START = date(2026, 9, 1)
HEADERS = {
    "calendar": "date,is_session,source",
    "instruments": "identity,isin,symbol,valid_from,valid_to,listed_on,delisted_on",
    "anchors": "identity,date,raw_close,source",
    "sessions": (
        "date,nifty500_close,bhavcopy_complete,actions_complete,"
        "membership_complete,member_count,source"
    ),
    "prices": "date,isin,status,open,high,low,close,prev_close",
    "membership": "effective_from,effective_to,identity,source",
    "actions": "identity,ex_date,kind,subject,factor,source",
}


def _date(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label} must be an ISO YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid {label}: {value}") from error


def _number(value, label):
    try:
        result = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{label} must be a positive finite number") from error
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return result


def _csv_bundle(folder):
    tables = {}
    files = []
    for name, headers in HEADERS.items():
        path = folder / f"{name}.csv"
        if not path.is_file():
            raise ValueError(
                f"Verified forward bundle is missing {path.name}; see feed.py schema"
            )
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            actual = reader.fieldnames or []
            if len(actual) != len(set(actual)) or set(headers.split(",")) - set(actual):
                raise ValueError(f"{path.name} requires unique headers: {headers}")
            records = list(reader)
        for row in records:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV record in {path.name}")
            row.update({key: value.strip() for key, value in row.items()})
            if "source" in row and not row["source"]:
                raise ValueError(
                    f"{path.name} needs explicit verified source provenance"
                )
        tables[name] = records
        files.append(path)
    return tables, content_provenance(folder, files)


def _exchange_calendar(records, requested):
    days, sessions = [], []
    for row in records:
        day = _date(row["date"], "calendar date")
        if row["is_session"] not in ("0", "1"):
            raise ValueError("calendar is_session must be 0 or 1")
        days.append(day)
        if row["is_session"] == "1":
            sessions.append(day)
    if (
        not days
        or days[0] != START
        or any((b - a).days != 1 for a, b in zip(days, days[1:]))
    ):
        raise ValueError(
            "calendar.csv must cover EVERY calendar date in order from 2026-09-01"
        )
    month_end = date(
        requested.year,
        requested.month,
        calendar.monthrange(requested.year, requested.month)[1],
    )
    if days[-1] < month_end or not any(d > month_end for d in sessions):
        raise ValueError(
            "Exchange calendar needs complete month-end and a subsequent session"
        )
    required = [day for day in sessions if day <= requested]
    if not required:
        raise ValueError("No completed forward exchange session on or before as_of")
    return required, sessions, days[-1]


def _instrument_table(records, raw):
    entities, aliases = {}, {}
    known = set(raw.identities)
    isin_owners = {
        isin: identity
        for identity, chain in zip(raw.identities, raw.isin_chains)
        for isin in chain
    }
    for row in records:
        identity, isin = row["identity"], row["isin"]
        if (
            not re.fullmatch(r"ISIN:[A-Z0-9]{12}", identity)
            or not re.fullmatch(r"[A-Z0-9]{12}", isin)
            or not row["symbol"]
        ):
            raise ValueError(
                "instruments require stable ISIN identities, ISINs and display symbols"
            )
        if isin in isin_owners and isin_owners[isin] != identity:
            raise ValueError(f"ISIN {isin} belongs to another kit company identity")
        start = _date(row["valid_from"], "alias valid_from")
        end = _date(row["valid_to"], "alias valid_to") if row["valid_to"] else date.max
        listed = _date(row["listed_on"], "listed_on")
        delisted = (
            _date(row["delisted_on"], "delisted_on") if row["delisted_on"] else date.max
        )
        if end < start or delisted <= listed:
            raise ValueError(f"Invalid alias/lifecycle interval for {identity}")
        entity = entities.setdefault(
            identity,
            {
                "listed": listed,
                "delisted": delisted,
                "aliases": [],
            },
        )
        if (entity["listed"], entity["delisted"]) != (listed, delisted):
            raise ValueError(f"Conflicting lifecycle dates for {identity}")
        alias = (start, end, identity, isin, row["symbol"])
        entity["aliases"].append(alias)
        aliases.setdefault(isin, []).append(alias)
    missing = known - entities.keys()
    if missing:
        raise ValueError(
            f"Missing instrument lifecycle/ISIN mapping: {sorted(missing)[:5]}"
        )
    for isin, spans in aliases.items():
        spans.sort()
        if any(a[1] >= b[0] for a, b in zip(spans, spans[1:])):
            raise ValueError(f"Ambiguous overlapping ISIN alias intervals: {isin}")
    for identity, entity in entities.items():
        entity["aliases"].sort()
        spans = entity["aliases"]
        if any(a[1] >= b[0] for a, b in zip(spans, spans[1:])):
            raise ValueError(
                f"Company {identity} has simultaneous competing ISIN aliases"
            )
        if identity not in known:
            if entity["listed"] < START or identity != "ISIN:" + spans[0][3]:
                raise ValueError(
                    f"New company {identity} needs a first-ISIN identity and post-kit listing; "
                    "older additions require a separately verified warm-up rebuild"
                )
    return entities, aliases


def _snapshots(records, entities):
    snapshots = {}
    for row in records:
        start = _date(row["effective_from"], "membership effective_from")
        end = _date(row["effective_to"], "membership effective_to")
        identity = row["identity"]
        if start > end or identity not in entities:
            raise ValueError("Invalid membership interval or unknown company identity")
        snapshot = snapshots.setdefault(
            start, {"end": end, "members": set(), "records": {}}
        )
        if snapshot["end"] != end or identity in snapshot["members"]:
            raise ValueError(
                "Conflicting membership snapshot interval or duplicate constituent"
            )
        snapshot["members"].add(identity)
        snapshot["records"][identity] = {
            "identity": identity,
            "effective_from": row["effective_from"],
            "source": row["source"],
        }
    ordered = sorted(snapshots)
    if any(snapshots[a]["end"] >= b for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Membership snapshot intervals overlap")
    return snapshots


def _raw_day_fingerprint(
    *, session, calendar_row, prices, membership, aliases, actions, anchors
):
    """Hash immutable source facts, never as-of-normalized prices or factors."""
    payload = {
        "version": "s18-raw-day-v1",
        "session": session,
        "calendar": calendar_row,
        "prices": sorted(prices, key=lambda record: record[0]),
        "membership": membership,
        "aliases": sorted(aliases),
        "actions": sorted(
            actions, key=lambda row: (row["identity"], row["ex_date"], row["kind"])
        ),
        "anchors": anchors,
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _action_factor(row, price_records, required):
    kind = row["kind"]
    if kind in ("dividend", "isin_change"):
        if row["factor"] and _number(row["factor"], "action factor") != 1:
            raise ValueError(f"{kind} must not alter the S18 price scale")
        return 1.0
    if kind == "demerger":
        candidates = [
            (day, price_records[(day, row["identity"])])
            for day in required
            if day >= row["_date"]
            and (day, row["identity"]) in price_records
            and price_records[(day, row["identity"])]["status"] == "traded"
        ]
        if not candidates:
            raise ValueError(
                f"Demerger {row['identity']} needs first traded close/prev_close "
                "on or after its ex-date; cannot guess the factor"
            )
        _, first = candidates[0]
        ratio = _number(first["close"], "demerger close") / _number(
            first["prev_close"], "demerger prev_close"
        )
        factor = ratio if abs(ratio - 1) > 0.10 else 1.0
    else:
        from scraper.corporate_actions import parse_bonus, parse_split

        split = (
            parse_split(row["subject"]) if kind in ("split", "split_bonus") else None
        )
        bonus = (
            parse_bonus(row["subject"]) if kind in ("bonus", "split_bonus") else None
        )
        parsed = {
            "split": split,
            "bonus": bonus,
            "split_bonus": split * bonus if split and bonus else None,
        }[kind]
        if parsed is None and not row["factor"]:
            raise ValueError(
                f"Unresolved {kind} factor for {row['identity']}; verify the NSE notice"
            )
        factor = (
            parsed if parsed is not None else _number(row["factor"], "action factor")
        )
    if row["factor"] and not math.isclose(
        factor, _number(row["factor"], "action factor"), rel_tol=1e-9, abs_tol=1e-12
    ):
        raise ValueError(
            f"Corporate-action factor disagrees with verified {kind} inputs"
        )
    return factor


def load_forward(
    kit_path: Path | str,
    extension_path: Path | str,
    *,
    metals: bool,
    as_of: str,
):
    """Append verified sessions, normalize raw prices and recompute all signals."""
    requested = _date(as_of, "as_of")
    if requested < START:
        raise ValueError("Use load_kit for dates before 2026-09-01")
    raw = load_raw_kit(kit_path, metals=metals)
    if raw.dates[-1] != np.datetime64("2026-08-31"):
        raise ValueError("Forward warm-up must end exactly 2026-08-31")
    tables, bundle_provenance = _csv_bundle(Path(extension_path).expanduser().resolve())
    if not metals:
        omitted_isins = {
            row["isin"]
            for row in tables["instruments"]
            if row["identity"] in METAL_IDENTITIES
        }
        for name in ("instruments", "anchors", "actions"):
            tables[name] = [
                r for r in tables[name] if r["identity"] not in METAL_IDENTITIES
            ]
        tables["prices"] = [
            r for r in tables["prices"] if r["isin"] not in omitted_isins
        ]
    required, exchange_sessions, complete_through = _exchange_calendar(
        tables["calendar"], requested
    )
    entities, aliases = _instrument_table(tables["instruments"], raw)
    snapshots = _snapshots(tables["membership"], entities)
    original_ids = raw.identities
    new_ids = sorted(
        (
            i
            for i in entities
            if i not in original_ids and entities[i]["listed"] <= required[-1]
        ),
        key=lambda i: (entities[i]["listed"], i),
    )
    stock_ids = list(original_ids[: raw.n_stocks]) + new_ids
    metal_ids = list(original_ids[raw.n_stocks :])
    identities = tuple(stock_ids + metal_ids)
    gid = {identity: i for i, identity in enumerate(identities)}
    previous_gid = {identity: i for i, identity in enumerate(original_ids)}
    all_known = set(entities)
    sessions = {}
    for row in tables["sessions"]:
        day = _date(row["date"], "session date")
        if day in sessions or day not in exchange_sessions:
            raise ValueError(
                f"Duplicate or non-exchange session in sessions.csv: {day}"
            )
        sessions[day] = row
    prices = {}
    for row in tables["prices"]:
        day = _date(row["date"], "price date")
        if day not in exchange_sessions:
            raise ValueError(f"Price record is not an exchange session: {day}")
        matches = [
            span for span in aliases.get(row["isin"], []) if span[0] <= day <= span[1]
        ]
        if len(matches) != 1:
            raise ValueError(f"Unresolved or ambiguous ISIN {row['isin']} on {day}")
        identity = matches[0][2]
        entity = entities[identity]
        if not entity["listed"] <= day < entity["delisted"]:
            raise ValueError(f"Price record outside listed lifecycle: {identity} {day}")
        key = (day, identity)
        if key in prices or row["status"] not in ("traded", "suspended"):
            raise ValueError(f"Duplicate identity/day or invalid price status: {key}")
        if row["status"] == "suspended":
            if any(row[field] for field in (*PRICE_FIELDS, "prev_close")):
                raise ValueError("Suspended records must not fabricate OHLC/prev_close")
        else:
            for field in (*PRICE_FIELDS, "prev_close"):
                _number(row[field], f"{field} for {identity} {day}")
        prices[key] = row
    anchors, anchor_evidence = {}, {}
    for row in tables["anchors"]:
        identity = row["identity"]
        if identity in anchors or identity not in previous_gid:
            raise ValueError(f"Duplicate or unknown anchor identity {identity}")
        g = previous_gid[identity]
        observed = np.flatnonzero(np.isfinite(raw.prices["close"][:, g]))
        if not len(observed):
            raise ValueError(f"Anchor has no corresponding kit history: {identity}")
        last = observed[-1]
        if _date(row["date"], "anchor date") != raw.dates[last].astype(object):
            raise ValueError(
                f"Anchor must use the final observed kit session for {identity}"
            )
        anchors[identity] = float(raw.prices["close"][last, g]) / _number(
            row["raw_close"], "anchor raw_close"
        )
        anchor_evidence[identity] = row
    scales = {}
    price_scales = {identity: 1.0 for identity in identities}
    for identity in identities:
        if identity in previous_gid and entities[identity]["delisted"] > required[0]:
            if identity not in anchors:
                raise ValueError(f"Missing verified raw-price anchor for {identity}")
        scales[identity] = anchors.get(identity, 1.0)
    actions, action_keys = {}, set()
    allowed_kinds = {
        "split",
        "bonus",
        "split_bonus",
        "demerger",
        "dividend",
        "isin_change",
    }
    for source_row in tables["actions"]:
        row = dict(source_row)
        identity = row["identity"]
        ex = _date(row["ex_date"], "corporate-action ex_date")
        if identity not in all_known or row["kind"] not in allowed_kinds or ex < START:
            raise ValueError(
                "Unknown corporate action, identity, or pre-kit action date"
            )
        entity = entities[identity]
        if not entity["listed"] <= ex < entity["delisted"]:
            raise ValueError(
                f"Corporate action outside listed lifecycle: {identity} {ex}"
            )
        key = (identity, ex, row["kind"])
        if key in action_keys:
            raise ValueError(f"Duplicate corporate action {key}")
        action_keys.add(key)
        kinds = {
            kind
            for company, day, kind in action_keys
            if company == identity and day == ex
        }
        if "split_bonus" in kinds and kinds.intersection({"split", "bonus"}):
            raise ValueError(
                "Combined split_bonus overlaps a separate split/bonus action"
            )
        row["_date"] = ex
        if ex > required[-1]:
            continue
        effective = next((d for d in required if d >= ex), None)
        if identity not in gid or effective is None:
            raise ValueError(
                f"Corporate action precedes instrument availability: {identity}"
            )
        row["_factor"] = _action_factor(row, prices, required)
        actions.setdefault(effective, []).append(row)
    n_old, n_new, groups = len(raw.dates), len(required), len(identities)
    combined = {
        name: np.full((n_old + n_new, groups), np.nan, dtype=np.float64)
        for name in PRICE_FIELDS
    }
    universe = np.zeros((n_old + n_new, groups), dtype=bool)
    for identity, old in previous_gid.items():
        new = gid[identity]
        for name in PRICE_FIELDS:
            combined[name][:n_old, new] = raw.prices[name][:, old]
        universe[:n_old, new] = raw.universe[:, old]
    index = np.concatenate((raw.benchmark, np.zeros(n_new)))
    fingerprints, scale_events, current_symbols = {}, [], {}
    calendar_records = {row["date"]: row for row in tables["calendar"]}
    snapshot_starts = sorted(snapshots)
    for offset, day in enumerate(required):
        session = sessions.get(day)
        if session is None:
            raise ValueError(
                f"Missing required Nifty500/session coverage on {day}; refusing stale data"
            )
        if any(
            session[column] != "1"
            for column in (
                "bhavcopy_complete",
                "actions_complete",
                "membership_complete",
            )
        ):
            raise ValueError(
                f"Unverified bhavcopy/actions/membership coverage on {day}"
            )
        index[n_old + offset] = _number(
            session["nifty500_close"], f"Nifty500 close {day}"
        )
        candidates = [
            start
            for start in snapshot_starts
            if start <= day <= snapshots[start]["end"]
        ]
        if len(candidates) != 1:
            raise ValueError(f"Missing point-in-time membership snapshot on {day}")
        snapshot = snapshots[candidates[0]]
        members = snapshot["members"]
        try:
            member_count = int(session["member_count"])
        except ValueError as error:
            raise ValueError(
                "member_count must be an integer full-snapshot count"
            ) from error
        if (
            member_count != len(members)
            or not members
            or not members.issubset(stock_ids)
        ):
            raise ValueError(
                f"Full PIT member_count or stock identity mismatch on {day}"
            )
        for member in members:
            if not entities[member]["listed"] <= day < entities[member]["delisted"]:
                raise ValueError(
                    f"Unlisted/delisted member in PIT snapshot: {member} {day}"
                )
        applied = []
        for action in sorted(
            actions.get(day, []), key=lambda row: (row["identity"], row["kind"])
        ):
            identity = action["identity"]
            scales[identity] /= action["_factor"]
            price_scales[identity] *= action["_factor"]
            if (
                not math.isfinite(scales[identity])
                or scales[identity] <= 0
                or not math.isfinite(price_scales[identity])
                or price_scales[identity] <= 0
            ):
                raise ValueError(
                    f"Invalid cumulative corporate-action scale: {identity}"
                )
            applied.append({k: v for k, v in action.items() if not k.startswith("_")})
            scale_events.append(
                {
                    "date": str(day),
                    "identity": identity,
                    "kind": action["kind"],
                    "factor": action["_factor"],
                    "raw_to_book": scales[identity],
                }
            )
        day_records = []
        active_aliases = []
        for identity in identities:
            entity = entities[identity]
            if not entity["listed"] <= day < entity["delisted"]:
                continue
            matches = [span for span in entity["aliases"] if span[0] <= day <= span[1]]
            if len(matches) != 1:
                raise ValueError(
                    f"Missing effective ISIN alias for {identity} on {day}"
                )
            alias = matches[0]
            current_symbols[identity] = alias[4]
            active_aliases.append((identity, alias[3], alias[4]))
            record = prices.get((day, identity))
            if record is None:
                raise ValueError(
                    f"Missing explicit traded/suspended bhavcopy record for {identity} on {day}"
                )
            day_records.append((identity, record))
            column = gid[identity]
            if record["status"] == "traded":
                for field in PRICE_FIELDS:
                    combined[field][n_old + offset, column] = (
                        float(record[field]) * scales[identity]
                    )
                universe[n_old + offset, column] = (
                    identity in members or identity in metal_ids
                )
            # Membership is PIT, but the reference ranks only today's traded stocks.
            if identity in metal_ids:
                universe[n_old + offset, column] = True
        fingerprints[str(day)] = _raw_day_fingerprint(
            session=session,
            calendar_row=calendar_records[str(day)],
            prices=day_records,
            membership=snapshot["records"],
            aliases=active_aliases,
            actions=applied,
            anchors={
                identity: anchor_evidence[identity]
                for identity, _ in day_records
                if identity in anchor_evidence
            },
        )
    # One common as-of share base makes the service's persisted-state rebase exact.
    history_scale = np.array([price_scales[identity] for identity in identities])
    for field in PRICE_FIELDS:
        combined[field] *= history_scale
    for event in scale_events:
        event["raw_to_book"] *= price_scales[event["identity"]]
    # Stock imports must be complete OHLC; raw ETF warm-up retains one missing open.
    stock_prices = {
        name: values[:, : len(stock_ids)] for name, values in combined.items()
    }
    validate_prices(stock_prices, (n_old + n_new, len(stock_ids)))
    validate_prices(
        {name: values[n_old:] for name, values in combined.items()}, (n_new, groups)
    )
    dates = np.concatenate((raw.dates, np.array(required, dtype="datetime64[D]")))
    rows = np.arange(raw.rows[0], len(dates), dtype=np.int64)
    symbols, chains = [], []
    for identity in identities:
        if identity in previous_gid:
            old = previous_gid[identity]
            symbols.append(raw.symbols[old])
            chains.append(raw.isin_chains[old])
        else:
            spans = entities[identity]["aliases"]
            symbols.append(spans[0][4])
            chains.append(tuple(dict.fromkeys(span[3] for span in spans)))
    last_rows = np.full(groups, len(rows) - 1, dtype=np.int64)
    for identity, column in gid.items():
        delisted = entities[identity]["delisted"]
        if delisted <= required[-1]:
            last_rows[column] = max(
                -1,
                int(np.searchsorted(dates, np.datetime64(delisted))) - 1 - int(rows[0]),
            )
            observed = np.flatnonzero(
                np.isfinite(combined["close"][rows, column])
                & (np.arange(len(rows)) <= last_rows[column])
            )
            last_rows[column] = int(observed[-1]) if len(observed) else -1
    provenance = dict(raw.provenance)
    canonical = list(raw.provenance["canonical_identities"]) + new_ids
    canonical_scales = {
        identity: price_scales.get(identity, 1.0) for identity in canonical
    }
    provenance.update(
        source="verified_csv_extension",
        extension_path=str(Path(extension_path).resolve()),
        extension_content_hash=bundle_provenance["content_hash"],
        extension_files=bundle_provenance["files"],
        as_of=as_of,
        stock_signals="recomputed",
        metal_signals="recomputed" if metals else "disabled",
        signals_version="s18-native-v1",
        n_stocks=len(stock_ids),
        session_calendar=[str(d) for d in raw.dates]
        + [str(d) for d in exchange_sessions],
        calendar_complete_through=str(complete_through),
        price_scales=canonical_scales,
        canonical_identities=canonical,
        canonical_indices={identity: i for i, identity in enumerate(canonical)},
        engine_indices=gid,
        raw_to_book={
            identity: scales[identity] * price_scales[identity]
            for identity in identities
        },
        raw_to_book_anchors={
            identity: value * price_scales[identity]
            for identity, value in anchors.items()
        },
        raw_to_kit_anchors=anchors,
        raw_to_book_events=scale_events,
        history_fingerprints=fingerprints,
        history_fingerprint_version="s18-raw-day-v1",
        current_symbols=current_symbols,
        delisting_policy="explicit_lifecycle_only",
        price_scale="as_of_back_adjusted_share_units",
    )
    extended = RawMarket(
        dates,
        combined,
        universe,
        index,
        rows,
        tuple(symbols),
        identities,
        tuple(chains),
        len(stock_ids),
        provenance,
    )
    panel = compute_signals(
        combined["close"], index, universe, rows, n_stocks=len(stock_ids)
    )
    return prepare_market(extended, panel, last_rows=last_rows)
