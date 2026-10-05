from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from core import storage
from backtesting.s18 import live_data
from backtesting.s18.data import RawMarket

ISINS = ("INE000000001", "INE000000002")


def response(records, label, **metadata):
    return SimpleNamespace(
        records=records,
        source=f"{label}:{live_data._hash(records)}",
        fetched_at="2026-09-03T19:00:00+05:30",
        metadata=metadata,
    )


class Sources:
    def __init__(self, today, snapshots, split=False):
        self.today = today
        self.snapshots = snapshots
        self.split = split

    def calendar(self, start, end):
        days = pd.date_range(start, end)
        return response(
            [
                {
                    "date": str(d.date()),
                    "is_session": d.weekday() < 5,
                    "source": "verified_fixture_calendar",
                }
                for d in days
            ],
            "calendar",
            complete_through=str(end),
        )

    def constituents(self, day):
        from backtesting.s18.nse_sources import SourceUnavailable

        if day not in self.snapshots:
            raise SourceUnavailable(f"Missing dated snapshot {day}")
        return response(
            [
                {"symbol": f"STOCK{i}", "isin": isin, "series": "EQ"}
                for i, isin in enumerate(ISINS)
            ],
            f"members:{day}",
        )

    def securities(self):
        return response(
            [
                {"symbol": f"STOCK{i}", "isin": isin, "listed_on": "2010-01-01"}
                for i, isin in enumerate(ISINS)
            ],
            "master",
        )

    def actions(self, start, end):
        records = []
        if self.split:
            records.append(
                {
                    "isin": ISINS[0],
                    "symbol": "STOCK0",
                    "ex_date": "2026-09-02",
                    "subject": "Face Value Split From Rs 10 To Rs 5",
                    "kind": "split",
                    "factor": 0.5,
                }
            )
        return response(records, "actions")

    def bhavcopy(self, day, **kwargs):
        records = []
        for i, isin in enumerate(ISINS):
            price = 50.0 if self.split and i == 0 and day >= date(2026, 9, 2) else 100.0
            records.append(
                {
                    "date": str(day),
                    "symbol": f"STOCK{i}",
                    "isin": isin,
                    "series": "EQ",
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "prev_close": price,
                }
            )
        return response(records, f"bhavcopy:{day}")

    def index_close(self, day, **kwargs):
        close = 519.0 if day == date(2026, 8, 31) else 530.0
        return response([{"date": str(day), "close": close}], f"index:{day}")


@pytest.fixture
def raw_setup(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "s18.sqlite3"))
    dates = pd.bdate_range(end="2026-08-31", periods=420).to_numpy(
        dtype="datetime64[D]"
    )
    raw = RawMarket(
        dates=dates,
        prices={f: np.full((420, 2), 100.0) for f in live_data.PRICE_FIELDS},
        universe=np.ones((420, 2), bool),
        benchmark=np.arange(100.0, 520.0),
        rows=np.arange(419, 420),
        symbols=("STOCK0", "STOCK1"),
        identities=tuple("ISIN:" + i for i in ISINS),
        isin_chains=tuple((i,) for i in ISINS),
        n_stocks=2,
        provenance={
            "content_hash": "fixture",
            "canonical_identities": ["ISIN:" + i for i in ISINS],
        },
    )
    monkeypatch.setattr(live_data, "load_raw_market", lambda *a, **kw: raw)
    with storage.connection_scope() as connection:
        connection.execute(
            "CREATE TABLE market_bars(symbol TEXT, trade_date TEXT, isin TEXT, "
            "open REAL, high REAL, low REAL, close REAL, source TEXT)"
        )
        connection.executemany(
            "INSERT INTO market_bars VALUES (?,?,?,?,?,?,?,?)",
            [
                (f"STOCK{i}", str(day), isin, 100.0, 100.0, 100.0, 100.0, "udiff")
                for i, isin in enumerate(ISINS)
                for day in dates
            ],
        )
    return raw, tmp_path


def collect(raw_setup, today, snapshots, *, inception=None, split=False):
    return live_data.collect_market(
        as_of=str(today),
        metals=False,
        inception=inception,
        source=Sources(today, snapshots, split=split),
        now=datetime.combine(
            today, datetime.min.time(), tzinfo=ZoneInfo("Asia/Kolkata")
        )
        + timedelta(hours=19),
    )


def test_september_bridge_does_not_invent_membership(raw_setup):
    today = date(2026, 9, 3)
    result = collect(raw_setup, today, {today})
    assert result.readiness["status"] == "ready"
    assert result.readiness["decision_start"] == str(today)
    assert np.all(result.market.sell_rank[1:3] == 32767)
    assert result.market.provenance["membership_policy"].startswith(
        "dated observations"
    )


def test_holiday_bootstrap_waits_without_backdating_snapshot(raw_setup):
    today = date(2026, 9, 5)
    result = collect(raw_setup, today, {today})
    assert result.readiness["status"] == "waiting_for_first_snapshot"
    assert result.readiness["latest_price_date"] == "2026-09-04"
    assert result.readiness["next_session"] == "2026-09-07"
    assert result.market.provenance["decision_start"] is None


def test_existing_book_requires_every_dated_snapshot(raw_setup):
    from backtesting.s18.nse_sources import SourceUnavailable

    today = date(2026, 9, 3)
    with pytest.raises(SourceUnavailable, match="2026-09-02"):
        collect(raw_setup, today, {date(2026, 9, 1), today}, inception="2026-09-01")


def test_live_split_rebases_prices_without_changing_prior_raw_hash(raw_setup):
    first_day = date(2026, 9, 1)
    before = collect(raw_setup, first_day, {first_day})
    next_day = date(2026, 9, 3)
    after = collect(
        raw_setup,
        next_day,
        {first_day, date(2026, 9, 2), next_day},
        inception="2026-09-01",
        split=True,
    )
    identity = "ISIN:" + ISINS[0]
    assert after.market.provenance["price_scales"][identity] == 0.5
    assert after.market.close[0, 0] == 50
    assert after.market.close[-1, 0] == 50
    # The earlier run's same-day membership remains the same observation.
    assert (
        before.market.provenance["history_fingerprints"]["2026-09-01"]
        == after.market.provenance["history_fingerprints"]["2026-09-01"]
    )


def test_unknown_established_constituent_requires_real_warmup(raw_setup):
    raw, _ = raw_setup
    with storage.connection_scope() as c:
        with pytest.raises(ValueError, match="Insufficient NSE warm-up"):
            live_data._new_history(
                c,
                {
                    "identity": "ISIN:INE000000003",
                    "isins": ["INE000000003"],
                    "symbol": "UNKNOWN",
                    "listed_on": "2010-01-01",
                },
                raw.dates,
                [],
            )


def test_ticker_alone_cannot_merge_distinct_isins(raw_setup):
    raw, _ = raw_setup
    new = {"symbol": "STOCK0", "isin": "INE000000003", "listed_on": "2026-09-01"}
    result = live_data._registry(raw, [new], [new], [], [])
    assert len(result) == 3
    assert result[-1]["identity"] == "ISIN:INE000000003"


def test_original_equity_scope_discloses_reits_and_dummy_components():
    snapshot = response(
        [
            {"symbol": "EQUITY", "isin": ISINS[0], "series": "EQ"},
            {"symbol": "REIT", "isin": ISINS[1], "series": "RR"},
            {"symbol": "DUMMYHEG", "isin": "DUM545A01024", "series": "EQ"},
        ],
        "members",
    )
    eligible, excluded = live_data._member_scope(snapshot)
    assert [r["symbol"] for r in eligible] == ["EQUITY"]
    assert [r["symbol"] for r in excluded] == ["REIT", "DUMMYHEG"]
    assert all(r["reason"] for r in excluded)


def test_unresolved_price_action_on_member_blocks_forward_run(raw_setup):
    _, folder = raw_setup
    today = date(2026, 9, 3)
    source = Sources(today, {today})
    source.actions = lambda *args: response(
        [
            {
                "symbol": "STOCK0",
                "isin": ISINS[0],
                "ex_date": "2026-09-01",
                "kind": "other",
                "subject": "Capital reduction",
                "factor": None,
                "requires_review": True,
            }
        ],
        "actions",
    )
    with pytest.raises(ValueError, match="needs review"):
        live_data.collect_market(
            as_of=str(today),
            metals=False,
            source=source,
            now=datetime(2026, 9, 3, 19, tzinfo=ZoneInfo("Asia/Kolkata")),
        )


def test_specified_demerger_uses_tape_despite_source_review_flag(raw_setup):
    _, folder = raw_setup
    today = date(2026, 9, 3)
    source = Sources(today, {today})
    source.actions = lambda *args: response(
        [
            {
                "symbol": "STOCK0",
                "isin": ISINS[0],
                "ex_date": "2026-09-01",
                "kind": "demerger",
                "subject": "Demerger",
                "factor": None,
                "requires_review": True,
            }
        ],
        "actions",
    )
    original = source.bhavcopy

    def bhavcopy(day, **kwargs):
        result = original(day, **kwargs)
        if day >= date(2026, 9, 1):
            result.records[0]["prev_close"] = 200.0
        return result

    source.bhavcopy = bhavcopy
    result = live_data.collect_market(
        as_of=str(today),
        metals=False,
        source=source,
        now=datetime(2026, 9, 3, 19, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert result.market.provenance["price_scales"]["ISIN:" + ISINS[0]] == 0.5


@pytest.mark.parametrize("subject", ["Buy Back", "Rights 2:21 @ Premium Rs 748/-"])
def test_voluntary_offers_preserve_price_and_disclose_nonparticipation(
    raw_setup, subject
):
    _, folder = raw_setup
    today = date(2026, 9, 3)
    source = Sources(today, {today})
    source.actions = lambda *args: response(
        [
            {
                "symbol": "STOCK0",
                "isin": ISINS[0],
                "ex_date": "2026-09-01",
                "kind": "other",
                "subject": subject,
                "factor": None,
                "requires_review": True,
            }
        ],
        "actions",
    )
    result = live_data.collect_market(
        as_of=str(today),
        metals=False,
        source=source,
        now=datetime(2026, 9, 3, 19, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert result.market.provenance["price_scales"]["ISIN:" + ISINS[0]] == 1
    assert result.market.close[-1, 0] == 100
    assert result.readiness["voluntary_offers"][0]["paper_treatment"].startswith(
        "No participation"
    )


def test_new_calendar_publication_preserves_processed_session_fingerprint(raw_setup):
    first_day, second_day = date(2026, 9, 1), date(2026, 9, 2)
    first = collect(raw_setup, first_day, {first_day})
    source = Sources(second_day, {first_day, second_day})
    original = source.calendar

    def republished(*args):
        result = original(*args)
        for row in result.records:
            row["source"] = "official-page-new-html-hash-same-calendar-facts"
        return response(result.records, "republished-calendar", **result.metadata)

    source.calendar = republished
    second = live_data.collect_market(
        as_of=str(second_day),
        inception=str(first_day),
        metals=False,
        source=source,
        now=datetime(2026, 9, 2, 19, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert (
        first.market.provenance["history_fingerprints"][str(first_day)]
        == second.market.provenance["history_fingerprints"][str(first_day)]
    )
    assert second.market.provenance["history_fingerprint_version"] == "s18-nse-day-v2"
    assert (
        first.market.provenance["calendar_evidence"]
        != second.market.provenance["calendar_evidence"]
    )


def test_real_past_session_removal_cannot_resume_as_unchanged(raw_setup):
    days = {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}
    first = collect(raw_setup, date(2026, 9, 2), days, inception="2026-09-01")
    source = Sources(date(2026, 9, 3), days)
    original = source.calendar

    def corrected(*args):
        result = original(*args)
        for row in result.records:
            if row["date"] == "2026-09-02":
                row["is_session"] = False
        return result

    source.calendar = corrected
    second = live_data.collect_market(
        as_of="2026-09-03",
        inception="2026-09-01",
        metals=False,
        source=source,
        now=datetime(2026, 9, 3, 19, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert "2026-09-02" in first.market.provenance["history_fingerprints"]
    assert "2026-09-02" not in second.market.provenance["history_fingerprints"]


def test_future_calendar_change_altering_a_past_review_changes_fingerprint(raw_setup):
    day = date(2026, 9, 16)
    days = set(pd.bdate_range("2026-09-01", "2026-09-16").date)
    first = collect(raw_setup, day, days, inception="2026-09-01")
    source = Sources(day, days)
    original = source.calendar

    def changed_review(*args):
        result = original(*args)
        for row in result.records:
            if row["date"] == "2026-09-30":
                row["is_session"] = False
        return result

    source.calendar = changed_review
    changed = live_data.collect_market(
        as_of=str(day),
        inception="2026-09-01",
        metals=False,
        source=source,
        now=datetime(2026, 9, 16, 19, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert (
        first.market.provenance["history_fingerprints"]["2026-09-16"]
        != changed.market.provenance["history_fingerprints"]["2026-09-16"]
    )
