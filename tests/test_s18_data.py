"""Small repo-local fixtures plus opt-in, read-only reference parity checks."""

import csv
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import uuid

import numpy as np
import pandas as pd
import pytest

from backtesting.s18 import data, feed, signals
from backtesting.s18.dataset import get_dataset


@pytest.fixture
def workspace():
    # Keep generated test inputs in this worktree, not the system temp directory.
    parent = Path.cwd() / ".s18-test-inputs"
    folder = parent / uuid.uuid4().hex
    folder.mkdir(parents=True)
    try:
        yield folder
    finally:
        shutil.rmtree(folder)
        if not any(parent.iterdir()):
            parent.rmdir()


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns.split(","))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def rewrite(bundle, table, rows):
    write_csv(bundle / f"{table}.csv", feed.HEADERS[table], rows)


def small_kit(folder, *, metals=False):
    target = folder / "data"
    (target / "signals").mkdir(parents=True)
    dates = pd.bdate_range("2012-01-02", "2026-08-31").to_numpy(dtype="datetime64[D]")
    time = np.arange(len(dates))
    index = 1000 * np.exp(0.0001 * time + 0.01 * np.sin(time / 19))
    close = np.column_stack(
        [
            100 * np.exp(0.0002 * time + 0.01 * np.sin(time / 21)),
            150 * np.exp(0.0001 * time + 0.02 * np.cos(time / 31)),
        ]
    )
    np.save(target / "dates.npy", dates)
    for field in data.PRICE_FIELDS:
        np.save(target / f"{field}.npy", close)
    np.save(target / "universe.npy", np.ones(close.shape, bool))
    np.save(target / "nifty500.npy", index)
    first = np.flatnonzero(dates == np.datetime64("2013-12-31"))[0]
    np.save(target / "signals" / "rows.npy", np.arange(first, len(dates)))
    write_csv(
        target / "companies.csv",
        "gid,symbols,isins,cols",
        [
            {
                "gid": 0,
                "symbols": "FIRST|RENAMED",
                "isins": "INE000A01001",
                "cols": "0",
            },
            {"gid": 1, "symbols": "SECOND", "isins": "INE000A01002", "cols": "1"},
        ],
    )
    if metals:
        (target / "ext").mkdir()
        np.savez(
            target / "ext" / "gold_silver.npz",
            dates=dates,
            GOLD=np.column_stack([close[:, 0] * 0.1] * 4),
            SILVER=np.column_stack([close[:, 1] * 0.2] * 4),
        )
    return folder


def small_bundle(folder, kit, *, metals=False):
    raw = data.load_raw_kit(kit, metals=metals)
    folder.mkdir()
    calendar_days = pd.date_range("2026-09-01", "2026-10-05")
    rewrite(
        folder,
        "calendar",
        [
            {
                "date": str(day.date()),
                "is_session": str(int(day.weekday() < 5)),
                "source": "synthetic-explicit-exchange-calendar",
            }
            for day in calendar_days
        ],
    )
    rewrite(
        folder,
        "instruments",
        [
            {
                "identity": identity,
                "isin": raw.isin_chains[i][-1],
                "symbol": raw.symbols[i],
                "valid_from": "2012-01-02",
                "valid_to": "",
                "listed_on": "2012-01-02",
                "delisted_on": "",
            }
            for i, identity in enumerate(raw.identities)
        ],
    )
    rewrite(
        folder,
        "anchors",
        [
            {
                "identity": identity,
                "date": "2026-08-31",
                "raw_close": raw.prices["close"][-1, i],
                "source": "synthetic-bhavcopy",
            }
            for i, identity in enumerate(raw.identities)
        ],
    )
    session_days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
    rewrite(
        folder,
        "sessions",
        [
            {
                "date": day,
                "nifty500_close": raw.benchmark[-1] * (1 + offset / 1000),
                "bhavcopy_complete": "1",
                "actions_complete": "1",
                "membership_complete": "1",
                "member_count": "2",
                "source": "synthetic-NSE",
            }
            for offset, day in enumerate(session_days)
        ],
    )
    rewrite(
        folder,
        "prices",
        [
            dict(
                date=day,
                isin=raw.isin_chains[i][-1],
                status="traded",
                **{
                    field: raw.prices["close"][-1, i] * (1 + offset / 100)
                    for field in data.PRICE_FIELDS
                },
                prev_close=raw.prices["close"][-1, i],
            )
            for offset, day in enumerate(session_days)
            for i in range(len(raw.identities))
        ],
    )
    rewrite(
        folder,
        "membership",
        [
            {
                "effective_from": "2026-09-01",
                "effective_to": "2026-09-30",
                "identity": identity,
                "source": "synthetic-PIT-notice",
            }
            for identity in raw.identities[: raw.n_stocks]
        ],
    )
    rewrite(folder, "actions", [])
    return folder


def test_beta_minimum_pairs_and_direct_covariance():
    t = np.arange(330)
    returns = 0.001 + 0.01 * np.sin(t / 13)
    benchmark = 100 * np.cumprod(1 + returns)
    full = 100 * np.cumprod(1 + 2 * returns + 0.0003)
    close = np.column_stack((full, full))
    close[:53, 1] = np.nan
    beta = signals.rolling_beta(close, benchmark)
    assert np.isnan(beta[250]).all()  # A full 252-session window is required.
    assert np.isnan(beta[252, 1])  # 199 return pairs since IPO.
    assert beta[253, 1] == pytest.approx(2, abs=1e-12)
    ri = full[-252:] / full[-253:-1] - 1
    rm = benchmark[-252:] / benchmark[-253:-1] - 1
    direct = np.cov(ri, rm, ddof=0)[0, 1] / np.var(rm)
    assert beta[-1, 0] == pytest.approx(direct, abs=1e-12)
    assert np.isnan(signals.rolling_beta(close, np.full(len(t), 100.0))).all()


def test_alpha_blocks_membership_ties_and_no_lookahead():
    t = np.arange(400)
    index = 100 * np.exp(0.001 * t + 0.01 * np.sin(t / 11))
    close = np.column_stack((index**1.1, index**1.1, index**1.2))
    members = np.ones(close.shape, bool)
    members[-1, 2] = False
    rows = np.arange(300, 400)
    result = signals.compute_signals(close, index, members, rows)
    assert result.buy_rank[-1, 0] == 1
    assert result.buy_rank[-1, 1] == 2
    assert result.buy_rank[-1, 2] == signals.NO_RANK
    expected = 1.0
    for k in range(6):
        end = 399 - 21 * (1 + k)
        ri = close[end, 0] / close[end - 21, 0] - 1
        rm = index[end] / index[end - 21] - 1
        expected *= 1 + ri - (signals.RF21 + result.beta[-1, 0] * (rm - signals.RF21))
    assert result.buy_score[-1, 0] == expected - 1
    altered = close.copy()
    altered[351:] *= 1.5
    changed = signals.compute_signals(altered, index, members, rows)
    np.testing.assert_array_equal(result.buy_score[:51], changed.buy_score[:51])


def test_gate_history_and_stock_float32_threshold():
    t = np.arange(400)
    index = 100 + np.sin(t / 13)
    close = np.full((400, 2), 100.0)
    close[301:] = 84.9999999
    members = np.ones(close.shape, bool)
    result = signals.compute_signals(
        close, index, members, np.arange(250, 400), n_stocks=1
    )
    assert not result.at_high[0].any()
    assert result.at_high[1].all()
    assert result.x63[362 - 250].all()
    assert not result.x63[363 - 250].any()
    assert result.sc15[-1, 0]  # Stored stock float32 d52 compares to float32 threshold.
    assert not result.sc15[-1, 1]  # ETF retains float64.


def test_metal_insertion_ties_and_priority_tiers():
    stock_scores = np.array([[3.0, 2.0, 1.0]])
    metal_scores = np.array([[2.0, 2.0]])
    relative = signals.metal_ranks(stock_scores, metal_scores)
    np.testing.assert_array_equal(relative, [[2, 2]])
    stock_rank = signals.rank_scores(stock_scores)
    rank = signals.insert_metal_ranks(stock_rank, relative, metal_scores)
    np.testing.assert_array_equal(rank, [[1, 4, 5, 2, 2]])
    order = signals.insert_metal_order(
        signals.order_from_ranks(stock_rank), stock_rank, relative, metal_scores
    )
    np.testing.assert_array_equal(order, [[0, 3, 4, 1, 2]])


def test_load_kit_native_without_any_baked_signals(workspace):
    kit = small_kit(workspace / "kit")
    market = data.load_kit(kit)
    assert str(market.dates[0]) == "2013-12-31"
    assert str(market.dates[-1]) == "2026-08-31"
    assert market.identities[0] == "ISIN:INE000A01001"
    assert market.symbols[0] == "FIRST"
    assert market.provenance["stock_signals"] == "recomputed"
    assert market.provenance["session_calendar"][0] == "2012-01-02"
    assert market.provenance["session_calendar"][-1] == "2026-08-31"
    assert market.provenance["canonical_identities"][-2:] == list(data.METAL_IDENTITIES)
    assert set(market.provenance["price_scales"].values()) == {1.0}
    assert all("rank.npy" not in path for path in market.provenance["files"])
    assert np.isfinite(market.close).all()
    json.dumps(market.provenance, allow_nan=False)
    before = market.provenance["content_hash"]
    (kit / "data" / "unrelated-research.txt").write_text("ignored", encoding="utf-8")
    assert data.load_raw_kit(kit).provenance["content_hash"] == before
    with pytest.raises(ValueError, match="Missing required"):
        data.load_kit(kit, recompute=False)
    for tiered in (False, True):
        for priority in (False, True):
            assert market.s1_order(tiered, priority).shape == market.buy_order.shape


def test_valuation_suspension_and_historical_terminal_rows(workspace):
    kit = small_kit(workspace / "kit")
    for field in data.PRICE_FIELDS:
        values = np.load(kit / "data" / f"{field}.npy", allow_pickle=False)
        values[-2:, 0] = np.nan
        np.save(kit / "data" / f"{field}.npy", values)
    universe = np.load(kit / "data" / "universe.npy", allow_pickle=False)
    universe[-2:, 0] = False
    np.save(kit / "data" / "universe.npy", universe)
    market = data.load_kit(kit)
    assert not market.tradable[-1, 0]
    assert market.close[-1, 0] == market.close[-3, 0]
    assert market.open[-1, 0] == market.close[-3, 0]
    assert market.last_rows[0] == len(market.dates) - 3
    with pytest.raises(ValueError, match="gid range"):
        replace(market, buy_order=np.full((len(market.dates), 1), 99))
    with pytest.raises(ValueError, match="identities"):
        replace(market, identities=(market.identities[0], market.identities[0]))


@pytest.mark.parametrize(
    "corruption", ["pickle", "date", "rows", "close", "identity", "membership"]
)
def test_kit_fails_closed_on_invalid_inputs(workspace, corruption):
    kit = small_kit(workspace / "kit")
    root = kit / "data"
    if corruption == "pickle":
        np.save(root / "close.npy", np.array([{"unsafe": True}], dtype=object))
    elif corruption == "date":
        dates = np.load(root / "dates.npy", allow_pickle=False)
        dates[-1] = dates[-2]
        np.save(root / "dates.npy", dates)
    elif corruption == "rows":
        np.save(root / "signals" / "rows.npy", np.array([2, 3, 4]))
    elif corruption == "close":
        close = np.load(root / "close.npy", allow_pickle=False)
        close[-1, 0] = -10
        np.save(root / "close.npy", close)
    elif corruption == "identity":
        rows = read_csv(root / "companies.csv")
        rows[1]["isins"] = rows[0]["isins"]
        write_csv(root / "companies.csv", "gid,symbols,isins,cols", rows)
    else:
        np.save(root / "universe.npy", np.ones((2, 2), bool))
    with pytest.raises(ValueError):
        data.load_kit(kit)


def test_forward_bundle_suspension_pit_and_prefix_stability(workspace):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    price_rows = read_csv(bundle / "prices.csv")
    for row in price_rows:
        if row["date"] >= "2026-09-03" and row["isin"] == "INE000A01002":
            row["status"] = "suspended"
            row.update({f: "" for f in (*data.PRICE_FIELDS, "prev_close")})
    rewrite(bundle, "prices", price_rows)
    membership = read_csv(bundle / "membership.csv")
    for row in membership:
        row["effective_to"] = "2026-09-02"
    membership.append(
        dict(
            effective_from="2026-09-03",
            effective_to="2026-09-30",
            identity="ISIN:INE000A01001",
            source="synthetic-removal-notice",
        )
    )
    rewrite(bundle, "membership", membership)
    session_rows = read_csv(bundle / "sessions.csv")
    for row in session_rows[2:]:
        row["member_count"] = "1"
    rewrite(bundle, "sessions", session_rows)
    first = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-02")
    later = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-05")
    assert (
        str(later.dates[-1]) == "2026-09-04"
    )  # Declared weekend, never stale fallback.
    assert not later.tradable[-1, 1]
    assert later.last_rows[1] == len(later.dates) - 1  # Suspension is not delisting.
    assert later.s2_sell_rank[-1, 1] == signals.NO_RANK
    assert later.close[-1, 1] == later.close[-3, 1]
    np.testing.assert_array_equal(first.close, later.close[: len(first.dates)])
    assert later.provenance["history_fingerprints"]["2026-09-02"] == (
        first.provenance["history_fingerprints"]["2026-09-02"]
    )
    assert later.provenance["calendar_complete_through"] == "2026-10-05"
    assert later.provenance["session_calendar"][-1] == "2026-10-05"
    future = [
        day
        for day in later.provenance["session_calendar"]
        if day > str(later.dates[-1])
    ]
    assert future[0] == "2026-09-07"
    assert later.provenance["stock_signals"] == "recomputed"


@pytest.mark.parametrize(
    "kind,subject,factor",
    [
        ("split", "Face Value Split From Rs 10 To Rs 5", 0.5),
        ("bonus", "Bonus 1:1", 0.5),
        ("split_bonus", "Bonus 1:1 / Face Value Split From Rs 10 To Rs 5", 0.25),
        ("demerger", "Scheme of arrangement", 0.6),
    ],
)
def test_forward_corporate_actions_back_adjust_history_and_preserve_rebased_nav(
    workspace, kind, subject, factor
):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    warmup = data.load_kit(kit)
    before = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-01")
    identity = warmup.identities[0]
    rewrite(
        bundle,
        "actions",
        [
            {
                "identity": identity,
                "ex_date": "2026-09-02",
                "kind": kind,
                "subject": subject,
                "factor": "",
                "source": "synthetic-exchange-action",
            }
        ],
    )
    price_rows = read_csv(bundle / "prices.csv")
    for row in price_rows:
        if row["date"] >= "2026-09-02" and row["isin"] == "INE000A01001":
            # A genuine corporate unit change with no economic move.
            row.update(
                {field: warmup.close[-1, 0] * factor for field in data.PRICE_FIELDS}
            )
    rewrite(bundle, "prices", price_rows)
    after = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    for field in data.PRICE_FIELDS:
        expected = getattr(warmup, field) * np.array([factor, 1.0])
        np.testing.assert_allclose(expected, getattr(after, field)[: len(warmup.dates)])
    np.testing.assert_allclose(after.close[-4:, 0], warmup.close[-1, 0] * factor)
    assert after.provenance["price_scales"][identity] == factor
    assert after.provenance["raw_to_book"][identity] == pytest.approx(1.0)
    assert before.provenance["history_fingerprints"]["2026-09-01"] == (
        after.provenance["history_fingerprints"]["2026-09-01"]
    )
    quantity = 1000 / warmup.close[-1, 0]
    ratio = (
        after.provenance["price_scales"][identity]
        / before.provenance["price_scales"][identity]
    )
    assert quantity / ratio * after.close[-1, 0] == pytest.approx(1000)
    assert warmup.close[-1, 0] * ratio == pytest.approx(after.close[-1, 0])


def test_forward_dividends_are_not_adjusted_and_rename_keeps_identity(workspace):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    before = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-01")
    rows = read_csv(bundle / "instruments.csv")
    rows[0]["valid_to"] = "2026-09-01"
    rows.append(
        dict(
            rows[0],
            isin="INE000A01099",
            symbol="RENAMED",
            valid_from="2026-09-02",
            valid_to="",
        )
    )
    rewrite(bundle, "instruments", rows)
    price_rows = read_csv(bundle / "prices.csv")
    for row in price_rows:
        if row["date"] >= "2026-09-02" and row["isin"] == "INE000A01001":
            row["isin"] = "INE000A01099"
    rewrite(bundle, "prices", price_rows)
    rewrite(
        bundle,
        "actions",
        [
            {
                "identity": "ISIN:INE000A01001",
                "ex_date": "2026-09-02",
                "kind": "dividend",
                "subject": "Dividend Rs 5",
                "factor": "",
                "source": "synthetic-notice",
            },
            {
                "identity": "ISIN:INE000A01001",
                "ex_date": "2026-09-02",
                "kind": "isin_change",
                "subject": "Verified ISIN replacement",
                "factor": "1",
                "source": "synthetic-notice",
            },
        ],
    )
    market = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    assert market.identities[0] == "ISIN:INE000A01001"
    assert market.symbols[0] == "FIRST"
    assert market.provenance["current_symbols"][market.identities[0]] == "RENAMED"
    assert market.provenance["raw_to_book"][market.identities[0]] == 1
    assert market.provenance["dividends"] is False
    assert before.provenance["history_fingerprints"]["2026-09-01"] == (
        market.provenance["history_fingerprints"]["2026-09-01"]
    )


@pytest.mark.parametrize(
    "correction",
    [
        "prices",
        "sessions",
        "membership",
        "instruments",
        "actions",
        "anchors",
        "calendar",
    ],
)
def test_raw_day_fingerprint_detects_historical_input_corrections(
    workspace, correction
):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    before = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-02")
    rows = read_csv(bundle / f"{correction}.csv")
    if correction == "prices":
        for field in data.PRICE_FIELDS:
            rows[0][field] = str(float(rows[0][field]) * 1.01)
    elif correction == "sessions":
        rows[0]["nifty500_close"] = str(float(rows[0]["nifty500_close"]) * 1.01)
    elif correction == "instruments":
        rows[0]["symbol"] = "CORRECTED_ALIAS"
    elif correction == "actions":
        rows.append(
            {
                "identity": "ISIN:INE000A01001",
                "ex_date": "2026-09-01",
                "kind": "dividend",
                "subject": "Previously omitted dividend",
                "factor": "",
                "source": "corrected-NSE-notice",
            }
        )
    else:
        rows[0]["source"] = "corrected-verified-source"
    rewrite(bundle, correction, rows)
    after = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-02")
    assert before.provenance["history_fingerprints"]["2026-09-01"] != (
        after.provenance["history_fingerprints"]["2026-09-01"]
    )
    assert after.provenance["history_fingerprint_version"] == "s18-raw-day-v1"
    assert all(
        len(value) == 64 for value in after.provenance["history_fingerprints"].values()
    )


def test_raw_day_fingerprints_ignore_csv_order_and_future_membership_expiry(workspace):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    rewrite(
        bundle,
        "actions",
        [
            {
                "identity": "ISIN:INE000A01001",
                "ex_date": "2026-09-01",
                "kind": "dividend",
                "subject": "Dividend Rs 5",
                "factor": "",
                "source": "NSE-action",
            },
            {
                "identity": "ISIN:INE000A01001",
                "ex_date": "2026-09-01",
                "kind": "isin_change",
                "subject": "Verified identity chain",
                "factor": "1",
                "source": "NSE-identity",
            },
        ],
    )
    before = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-02")
    for table in (
        "prices",
        "membership",
        "instruments",
        "anchors",
        "actions",
        "sessions",
    ):
        rewrite(bundle, table, list(reversed(read_csv(bundle / f"{table}.csv"))))
    reordered = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-02")
    assert (
        reordered.provenance["history_fingerprints"]
        == before.provenance["history_fingerprints"]
    )
    rows = read_csv(bundle / "membership.csv")
    for row in rows:
        row["effective_to"] = "2026-09-02"
    rows += [
        dict(
            row,
            effective_from="2026-09-03",
            effective_to="2026-09-30",
            source="next-effective-snapshot",
        )
        for row in rows
    ]
    rewrite(bundle, "membership", rows)
    later = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    for day, digest in before.provenance["history_fingerprints"].items():
        assert later.provenance["history_fingerprints"][day] == digest


def test_forward_cumulative_scale_rebases_existing_state_once(workspace):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    warmup = data.load_kit(kit)
    identity = warmup.identities[0]
    start_price = warmup.close[-1, 0]
    rewrite(
        bundle,
        "actions",
        [
            {
                "identity": identity,
                "ex_date": "2026-09-02",
                "kind": "split",
                "subject": "Face Value Split From Rs 10 To Rs 5",
                "factor": "",
                "source": "synthetic-split-notice",
            },
            {
                "identity": identity,
                "ex_date": "2026-09-04",
                "kind": "bonus",
                "subject": "Bonus 1:1",
                "factor": "",
                "source": "synthetic-bonus-notice",
            },
        ],
    )
    prices = read_csv(bundle / "prices.csv")
    for row in prices:
        if row["isin"] != "INE000A01001":
            continue
        factor = (
            0.25
            if row["date"] == "2026-09-04"
            else (0.5 if row["date"] >= "2026-09-02" else 1)
        )
        row.update({field: start_price * factor for field in data.PRICE_FIELDS})
    rewrite(bundle, "prices", prices)
    old = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-02")
    new = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    old_scale = old.provenance["price_scales"][identity]
    new_scale = new.provenance["price_scales"][identity]
    assert old_scale == 0.5
    assert new_scale == 0.25
    ratio = new_scale / old_scale
    np.testing.assert_allclose(
        old.close[:, 0] * ratio, new.close[: len(old.dates), 0], rtol=0, atol=0
    )
    basis = 1000.0
    old_qty = basis / (start_price * old_scale)
    old_peak = start_price * old_scale
    new_qty, new_peak = old_qty / ratio, old_peak * ratio
    assert new_qty * new.close[-1, 0] == pytest.approx(basis)
    assert new_peak == new.close[-1, 0]
    assert new.provenance["history_fingerprints"]["2026-09-02"] == (
        old.provenance["history_fingerprints"]["2026-09-02"]
    )
    assert new.provenance["raw_to_book_events"][0]["raw_to_book"] == 0.5
    assert new.provenance["raw_to_book_events"][1]["raw_to_book"] == 1


def test_forward_new_ipo_warmup_and_metals(workspace):
    kit = small_kit(workspace / "kit", metals=True)
    bundle = small_bundle(workspace / "bundle", kit, metals=True)
    original = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-01")
    instruments = read_csv(bundle / "instruments.csv")
    instruments.append(
        {
            "identity": "ISIN:INE000A01003",
            "isin": "INE000A01003",
            "symbol": "NEW",
            "valid_from": "2026-09-02",
            "valid_to": "",
            "listed_on": "2026-09-02",
            "delisted_on": "",
        }
    )
    rewrite(bundle, "instruments", instruments)
    price_rows = read_csv(bundle / "prices.csv")
    price_rows += [
        dict(
            date=day,
            isin="INE000A01003",
            status="traded",
            prev_close=100,
            **{field: 100 for field in data.PRICE_FIELDS},
        )
        for day in ("2026-09-02", "2026-09-03", "2026-09-04")
    ]
    rewrite(bundle, "prices", price_rows)
    market = feed.load_forward(kit, bundle, metals=True, as_of="2026-09-04")
    assert market.n_stocks == 3
    assert market.identities[2] == "ISIN:INE000A01003"
    assert market.identities[-2:] == data.METAL_IDENTITIES
    assert not market.tradable[-4, 2]
    assert market.tradable[-3, 2]
    assert (market.s2_sell_rank[:, 2] == signals.NO_RANK).all()
    assert (market.s2_sell_rank[:, 3:] == signals.NO_RANK).all()
    assert market.provenance["metal_signals"] == "recomputed"
    stocks = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    assert stocks.n_stocks == len(stocks.identities) == 3
    canonical = market.provenance["canonical_indices"]
    assert canonical == stocks.provenance["canonical_indices"]
    assert canonical[data.METAL_IDENTITIES[0]] == 2
    assert canonical["ISIN:INE000A01003"] == 4
    assert market.provenance["engine_indices"]["ISIN:INE000A01003"] == 2
    previous = original.provenance["canonical_identities"]
    assert market.provenance["canonical_identities"][: len(previous)] == previous


def test_forward_anchor_scale_and_explicit_delisting(workspace):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    baseline = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    anchors = read_csv(bundle / "anchors.csv")
    anchors[0]["raw_close"] = str(float(anchors[0]["raw_close"]) * 10)
    rewrite(bundle, "anchors", anchors)
    prices = read_csv(bundle / "prices.csv")
    for row in prices:
        if row["isin"] == "INE000A01001":
            for field in (*data.PRICE_FIELDS, "prev_close"):
                row[field] = str(float(row[field]) * 10)
    rewrite(bundle, "prices", prices)
    scaled = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    np.testing.assert_allclose(baseline.close, scaled.close, rtol=1e-15)
    assert scaled.provenance["raw_to_book"][scaled.identities[0]] == pytest.approx(0.1)
    instruments = read_csv(bundle / "instruments.csv")
    instruments[1]["delisted_on"] = "2026-09-03"
    rewrite(bundle, "instruments", instruments)
    rewrite(
        bundle,
        "prices",
        [
            row
            for row in prices
            if not (row["isin"] == "INE000A01002" and row["date"] >= "2026-09-03")
        ],
    )
    membership = read_csv(bundle / "membership.csv")
    for row in membership:
        row["effective_to"] = "2026-09-02"
    membership.append(
        dict(
            effective_from="2026-09-03",
            effective_to="2026-09-30",
            identity=scaled.identities[0],
            source="delisting-membership-notice",
        )
    )
    rewrite(bundle, "membership", membership)
    sessions = read_csv(bundle / "sessions.csv")
    for row in sessions[2:]:
        row["member_count"] = "1"
    rewrite(bundle, "sessions", sessions)
    delisted = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    assert delisted.last_rows[1] == len(delisted.dates) - 3
    assert not delisted.tradable[-2:, 1].any()
    assert delisted.close[-1, 1] == delisted.close[-3, 1]


def test_demerger_requires_observed_ex_session_and_threshold(workspace):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    rewrite(
        bundle,
        "actions",
        [
            {
                "identity": "ISIN:INE000A01001",
                "ex_date": "2026-09-04",
                "kind": "demerger",
                "subject": "Verified demerger",
                "factor": "",
                "source": "synthetic-notice",
            }
        ],
    )
    market = feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")
    assert market.provenance["raw_to_book"][market.identities[0]] == 1  # Only 3% gap.
    prices = read_csv(bundle / "prices.csv")
    for row in prices:
        if row["date"] == "2026-09-04" and row["isin"] == "INE000A01001":
            row["status"] = "suspended"
            row.update({field: "" for field in (*data.PRICE_FIELDS, "prev_close")})
    rewrite(bundle, "prices", prices)
    with pytest.raises(ValueError, match="first traded close/prev_close"):
        feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")


@pytest.mark.parametrize(
    "failure,match",
    [
        ("missing-price", "explicit traded/suspended"),
        ("missing-session", "required Nifty500/session"),
        ("membership-gap", "membership snapshot"),
        ("current-members", "member_count"),
        ("calendar-gap", "EVERY calendar date"),
        ("calendar-future", "month-end"),
        ("unverified", "Unverified"),
        ("anchor", "anchor"),
        ("bad-isin", "Unresolved"),
        ("bad-factor", "disagrees"),
        ("negative", "positive finite"),
    ],
)
def test_forward_bundle_fails_closed(workspace, failure, match):
    kit = small_kit(workspace / "kit")
    bundle = small_bundle(workspace / "bundle", kit)
    if failure == "missing-price":
        rows = read_csv(bundle / "prices.csv")
        rewrite(bundle, "prices", rows[1:])
    elif failure == "missing-session":
        rewrite(bundle, "sessions", read_csv(bundle / "sessions.csv")[1:])
    elif failure == "membership-gap":
        rows = read_csv(bundle / "membership.csv")
        for row in rows:
            row["effective_from"] = "2026-09-02"
        rewrite(bundle, "membership", rows)
    elif failure == "current-members":
        rewrite(bundle, "membership", read_csv(bundle / "membership.csv")[:1])
    elif failure == "calendar-gap":
        rewrite(bundle, "calendar", read_csv(bundle / "calendar.csv")[1:])
    elif failure == "calendar-future":
        rewrite(bundle, "calendar", read_csv(bundle / "calendar.csv")[:30])
    elif failure == "unverified":
        rows = read_csv(bundle / "sessions.csv")
        rows[0]["actions_complete"] = "0"
        rewrite(bundle, "sessions", rows)
    elif failure == "anchor":
        rewrite(bundle, "anchors", [])
    elif failure == "bad-isin":
        rows = read_csv(bundle / "prices.csv")
        rows[0]["isin"] = "INEUNKNOWN00"
        rewrite(bundle, "prices", rows)
    elif failure == "bad-factor":
        rewrite(
            bundle,
            "actions",
            [
                {
                    "identity": "ISIN:INE000A01001",
                    "ex_date": "2026-09-01",
                    "kind": "split",
                    "subject": "Face Value Split From Rs 10 To Rs 5",
                    "factor": ".25",
                    "source": "notice",
                }
            ],
        )
    elif failure == "negative":
        rows = read_csv(bundle / "prices.csv")
        rows[0]["close"] = "-1"
        rewrite(bundle, "prices", rows)
    with pytest.raises(ValueError, match=match):
        feed.load_forward(kit, bundle, metals=False, as_of="2026-09-04")


@pytest.fixture(scope="module")
def golden():
    location = os.getenv("S18_DATASET_DB")
    if not location:
        pytest.skip(
            "Set S18_DATASET_DB to check installed historical signal references"
        )
    root = get_dataset(db_path=Path(location))
    raw = data.load_raw_market(source=root, metals=True)
    panel = signals.compute_signals(
        raw.prices["close"],
        raw.benchmark,
        raw.universe,
        raw.rows,
        n_stocks=raw.n_stocks,
    )
    return root, raw, panel, data.prepare_market(raw, panel)


@pytest.mark.parametrize(
    "name,file,index",
    [
        ("buy_rank", "signals/AL_L6_G1_rank.npy", None),
        ("sell_rank", "signals/AL_L3_G2_rank.npy", None),
        ("buy_order", "signals/AL_L6_G1_orderfull.npy", None),
        ("beta", "beta_252d.npy", None),
        ("d52", "d52.npy", None),
        ("x63", "gates_fresh.npy", 6),
        ("sc15", "gates_tier.npy", 3),
        ("at_high", "gates_tier.npy", 0),
        ("risk_off", "regime_riskoff.npy", 1),
    ],
)
def test_golden_native_stock_signal_parity(golden, name, file, index):
    root, raw, panel, _ = golden
    actual = getattr(panel, name)
    expected = root.array(f"data/{file}")
    if index is not None:
        expected = expected[index]
    if name in ("beta", "d52", "x63", "sc15", "at_high"):
        actual = actual[:, : raw.n_stocks]
    if name in ("beta", "d52"):
        actual = actual.astype(np.float32)
    np.testing.assert_array_equal(actual, expected, err_msg=f"{name} parity mismatch")


@pytest.mark.parametrize("metal,column", [("GOLD", 0), ("SILVER", 1)])
def test_golden_native_metal_signal_parity(golden, metal, column):
    root, raw, panel, _ = golden
    g = raw.n_stocks + column
    with root.archive("data/ext/etf_signals.npz") as archive:
        for name, score, rank in (
            ("AL_L6_G1", panel.buy_score[:, g], panel.metal_buy_rank[:, column]),
            ("AL_L3_G2", panel.sell_score[:, g], panel.metal_sell_rank[:, column]),
        ):
            np.testing.assert_array_equal(score, archive[f"score|{metal}|{name}"])
            np.testing.assert_array_equal(rank, archive[f"rank|{metal}|{name}"])
        np.testing.assert_array_equal(panel.x63[:, g], archive[f"fresh|{metal}"][6])
        np.testing.assert_array_equal(panel.sc15[:, g], archive[f"tier|{metal}"][3])
        np.testing.assert_array_equal(panel.at_high[:, g], archive[f"tier|{metal}"][0])


def test_golden_cached_and_native_worlds_agree(golden):
    root, raw, _, native = golden
    cached = data.load_market(source=root, metals=True, recompute=False)
    assert cached.provenance["metal_signals"] == "cached"
    assert cached.provenance["stock_signals"] == "cached"
    for name in (
        *data.PRICE_FIELDS,
        "tradable",
        "last_rows",
        "benchmark",
        "risk_off",
        "buy_order",
        "sell_rank",
        "s2_buy_order",
        "s2_sell_rank",
        "x63",
        "sc15",
        "at_high",
    ):
        np.testing.assert_array_equal(getattr(native, name), getattr(cached, name))
    for tiered in (False, True):
        for priority in (False, True):
            np.testing.assert_array_equal(
                native.s1_order(tiered, priority), cached.s1_order(tiered, priority)
            )
    assert native.close.shape == (3123, 1123)
    assert native.buy_order.shape == (3123, 501)
    assert raw.dates.shape == (3617,)
    assert (native.last_rows[-2:] == 3122).all()
