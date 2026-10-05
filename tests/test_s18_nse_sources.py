import csv
import io
import json
import zipfile
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from backtesting.s18 import nse_sources as nse
from core import storage


DAY = date(2026, 10, 1)
NOW = datetime(2026, 10, 4, 19, tzinfo=nse.IST)
ISIN = "INE000000001"
FIELDS = [
    "TradDt",
    "BizDt",
    "Sgmt",
    "Src",
    "FinInstrmTp",
    "ISIN",
    "TckrSymb",
    "SctySrs",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "PrvsClsgPric",
]


def csv_bytes(fields, rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue().encode()


def bhav(*, changes=None, extra=None):
    row = dict(
        zip(
            FIELDS,
            [
                str(DAY),
                str(DAY),
                "CM",
                "NSE",
                "STK",
                ISIN,
                "STOCK",
                "EQ",
                "100",
                "110",
                "90",
                "105",
                "99",
            ],
        )
    )
    row.update(changes or {})
    rows = [row]
    if extra:
        rows.append({**row, **extra})
    payload = csv_bytes(FIELDS, [[r[k] for k in FIELDS] for r in rows])
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("bhav.csv", payload)
    return result.getvalue()


class Response:
    def __init__(self, payload, status=200, headers=None):
        self.payload, self.status_code = payload, status
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.payload

    def close(self):
        self.closed = True


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"Unexpected HTTP call: {url}")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    monkeypatch.setattr(nse, "MIN_REQUEST_INTERVAL", 0)
    monkeypatch.setattr(
        nse.existing_bhavcopy,
        "get_session",
        lambda: pytest.fail("Unit tests must not bootstrap a live NSE session"),
    )


@pytest.fixture
def client(tmp_path):
    def create(*responses, now=NOW):
        return nse.NseSources(tmp_path / "nse.sqlite3", Session(responses), now)

    return create


def test_bhavcopy_bz_is_preserved_and_snapshot_is_immutable(client):
    response = Response(
        bhav(extra={"TckrSymb": "SURVEIL", "ISIN": "INE000000002", "SctySrs": "BZ"})
    )
    source = client(response)
    result = source.bhavcopy(DAY)
    assert [r["series"] for r in result.records] == ["EQ", "BZ"]
    assert result.records[0]["close"] == 105
    assert result.source.startswith("sqlite://artifacts/s18-nse-sha256-")
    assert result == source.bhavcopy(DAY)
    assert len(source.session.calls) == 1
    assert response.closed
    assert source.session.calls[0][1] == {"timeout": (10, 30), "stream": True}
    with storage.connection_scope(source.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 1
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('market_bars','bhavcopy_days')"
        ).fetchall()


@pytest.mark.parametrize(
    "changes",
    [
        {"TradDt": "2026-09-30"},
        {"BizDt": "2026-09-30"},
        {"Src": "BSE"},
        {"Sgmt": "FO"},
        {"ClsPric": "NaN"},
        {"OpnPric": "0"},
        {"PrvsClsgPric": "-1"},
        {"ClsPric": "111"},
        {"ISIN": ""},
    ],
)
def test_bhavcopy_rejects_wrong_dates_identity_market_and_prices(client, changes):
    source = client(Response(bhav(changes=changes)))
    with pytest.raises(ValueError):
        source.bhavcopy(DAY)
    with storage.connection_scope(source.db_path) as db:
        rows = db.execute(
            "SELECT value_json FROM documents WHERE namespace=? AND key LIKE 'audit:%'",
            (nse.NAMESPACE,),
        ).fetchall()
        assert any(json.loads(r[0])["outcome"] == "invalid" for r in rows)
        assert db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"TckrSymb": "OTHER", "SctySrs": "BE"},
        {"ISIN": "INE000000002", "SctySrs": "BZ"},
    ],
)
def test_duplicate_identity_is_not_deduplicated(client, extra):
    with pytest.raises(ValueError, match="Duplicate security"):
        client(Response(bhav(extra=extra))).bhavcopy(DAY)


@pytest.mark.parametrize(
    "payload", [b"<html>access denied</html>", b'{"error":"blocked"}', b"not a zip"]
)
def test_non_archive_response_is_not_a_holiday(client, payload):
    with pytest.raises(ValueError):
        client(Response(payload)).bhavcopy(DAY)


def test_legacy_dates_are_validated(client):
    def archive(day):
        data = csv_bytes(
            [
                "SYMBOL",
                "SERIES",
                "ISIN",
                "TIMESTAMP",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "PREVCLOSE",
            ],
            [["OLD", "BZ", ISIN, day, 100, 110, 90, 105, 99]],
        )
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("old.csv", data)
        return stream.getvalue()

    source = client(Response(archive("02-JAN-2023")), Response(archive("03-JAN-2023")))
    assert source.bhavcopy(date(2023, 1, 2)).records[0]["series"] == "BZ"
    with pytest.raises(ValueError, match="TIMESTAMP"):
        source.bhavcopy(date(2023, 1, 2), refresh=True)
    assert source.bhavcopy(date(2023, 1, 2)).records[0]["date"] == "2023-01-02"


def test_network_failure_retries_only_twice_and_records_attempts(client):
    source = client(requests.Timeout("bounded"), Response(b'{"error":"server"}', 503))
    with pytest.raises(nse.SourceUnavailable):
        source.bhavcopy(DAY)
    assert len(source.session.calls) == 2
    with storage.connection_scope(source.db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM documents WHERE namespace=? AND key LIKE 'audit:%'",
                (nse.NAMESPACE,),
            ).fetchone()[0]
            == 2
        )


def test_404_is_distinct_not_a_holiday_or_successful_result(client):
    source = client(Response(b"not found", 404))
    with pytest.raises(nse.SourceNotFound, match="not holiday evidence"):
        source.bhavcopy(DAY)
    assert len(source.session.calls) == 1
    assert source._get(f"result:bhavcopy:{DAY}") is None


def test_payload_size_bound(client, monkeypatch):
    monkeypatch.setattr(nse, "MAX_PAYLOAD", 10)
    source = client(Response(b"x" * 11), Response(b"x" * 11))
    with pytest.raises(nse.SourceUnavailable, match="exceeds"):
        source.bhavcopy(DAY)


def index_csv(day="01-10-2026", name="Nifty 500"):
    return csv_bytes(
        ["Index Name", "Index Date", "Closing Index Value"],
        [[name, day, "21857.75"], ["Nifty 50", day, "22421.95"]],
    )


def test_index_exact_name_date_and_price(client):
    result = client(Response(index_csv())).index_close(DAY)
    assert result.records == [{"date": str(DAY), "close": 21857.75}]


@pytest.mark.parametrize(
    "payload",
    [
        index_csv(day="30-09-2026"),
        index_csv(name="Nifty 500 TRI"),
        b'{"error":"denied"}',
        b"<html>denied</html>",
    ],
)
def test_index_rejects_wrong_dates_names_and_non_csv(client, payload):
    with pytest.raises(ValueError):
        client(Response(payload)).index_close(DAY)


def members(duplicate=False):
    rows = [[f"STOCK{i}", f"INE{i:08d}0", "EQ"] for i in range(500)]
    if duplicate:
        rows[-1][1] = rows[0][1]
    return csv_bytes(["Symbol", "ISIN Code", "Series"], rows)


def test_membership_is_observed_today_never_backdated(client):
    source = client(Response(members()))
    with pytest.raises(nse.SourceUnavailable, match="cannot be backdated"):
        source.constituents(DAY)
    assert not source.session.calls
    result = source.constituents(NOW.date())
    assert result.metadata["observed_on"] == "2026-10-04"
    source.now = NOW.replace(day=5)
    assert source.constituents(date(2026, 10, 4)) == result
    assert len(source.session.calls) == 1


def test_membership_duplicate_isin_is_rejected(client):
    with pytest.raises(ValueError, match="Duplicate"):
        client(Response(members(duplicate=True))).constituents(NOW.date())


def test_intraday_membership_is_refetched_after_close_then_reused(client):
    morning = NOW.replace(day=5, hour=10)
    changed = members().replace(b"STOCK0,", b"RENAMED0,")
    source = client(Response(members()), Response(changed), now=morning)
    intraday = source.constituents(morning.date())
    assert not intraday.metadata["observed_after_close_cutoff"]
    source.now = morning.replace(hour=17)
    assert source.constituents(morning.date()) == intraday
    assert len(source.session.calls) == 1
    source.now = morning.replace(hour=18)
    closing = source.constituents(morning.date())
    assert closing.metadata["observed_after_close_cutoff"]
    assert closing.records[0]["symbol"] == "RENAMED0"
    assert closing.source != intraday.source
    source.now = morning.replace(hour=20)
    assert source.constituents(morning.date()) == closing
    source.now += timedelta(days=1)
    assert source.constituents(morning.date()) == closing
    assert len(source.session.calls) == 2
    assert (
        len(
            storage.list_artifact_groups(category="s18.nse.raw", db_path=source.db_path)
        )
        == 2
    )


def test_preclose_download_cache_cannot_be_promoted_to_a_close(client):
    morning = NOW.replace(day=5, hour=10)
    source = client(Response(members()), Response(members()), now=morning)
    source._download(nse.CONSTITUENTS_URL)
    source.now = morning.replace(hour=18)
    closing = source.constituents(morning.date())
    assert datetime.fromisoformat(closing.fetched_at).hour == 18
    assert len(source.session.calls) == 2


def test_missed_close_cannot_reuse_a_previous_intraday_snapshot(client):
    morning = NOW.replace(day=5, hour=10)
    source = client(Response(members()), now=morning)
    source.constituents(morning.date())
    source.now += timedelta(days=1)
    with pytest.raises(nse.SourceUnavailable, match="Only a pre-close"):
        source.constituents(morning.date())
    assert len(source.session.calls) == 1


def test_failed_postclose_refresh_does_not_fall_back_to_intraday_membership(client):
    morning = NOW.replace(day=5, hour=10)
    source = client(
        Response(members()),
        Response(b"unavailable", 503),
        Response(b"unavailable", 503),
        now=morning,
    )
    source.constituents(morning.date())
    source.now = morning.replace(hour=18)
    with pytest.raises(nse.SourceUnavailable):
        source.constituents(morning.date())
    source.now += timedelta(days=1)
    with pytest.raises(nse.SourceUnavailable, match="pre-close"):
        source.constituents(morning.date())


def test_holiday_observation_is_informational_and_not_previous_session_membership(
    client,
):
    holiday = NOW.replace(hour=10)
    source = client(Response(members()), now=holiday)
    result = source.constituents(holiday.date())
    assert result.metadata["observed_on"] == "2026-10-04"
    assert not result.metadata["observed_after_close_cutoff"]
    assert "holiday observations are informational" in result.metadata["use_constraint"]
    with pytest.raises(nse.SourceUnavailable, match="cannot be backdated"):
        source.constituents(DAY)


def test_live_clock_override_cannot_backdate_downloaded_observations(client):
    earlier = datetime.now(nse.IST) - timedelta(days=1)
    source = client(now=earlier)
    source.session = None
    with pytest.raises(nse.SourceUnavailable, match="clock override"):
        source.constituents(earlier.date())
    with pytest.raises(nse.SourceUnavailable, match="clock override"):
        source.securities()
    assert source._get(f"result:constituents:{earlier.date()}") is None


def test_equity_and_etf_master_preserve_official_listing_dates(client):
    equity = csv_bytes(
        ["SYMBOL", "ISIN NUMBER", "DATE OF LISTING", "SERIES"],
        [["STOCK", ISIN, "06-OCT-2008", "BE"]],
    )
    etf = csv_bytes(
        ["Symbol", "ISINNumber", "DateofListing"],
        [["GOLD", "INF000000001", "19-Mar-07"], ["SILVER", "INF000000002", "-"]],
    )
    source = client(Response(equity), Response(etf))
    result = source.securities()
    assert [r["listed_on"] for r in result.records] == [
        "2008-10-06",
        "2007-03-19",
        None,
    ]
    assert source.securities().records == result.records
    assert result.records[0]["series"] == "BE"
    assert "series" not in result.records[1]
    assert len(source.session.calls) == 2


def test_symbol_changes_are_headerless_and_dated(client):
    result = client(Response(b"Company,OLD,NEW,01-OCT-2026\n")).symbol_changes()
    assert result.records == [
        {"old_symbol": "OLD", "new_symbol": "NEW", "effective_date": str(DAY)}
    ]


def action(subject, **kwargs):
    return {
        "symbol": "STOCK",
        "isin": ISIN,
        "exDate": "01-Oct-2026",
        "subject": subject,
        **kwargs,
    }


def test_actions_normalize_compounds_and_flag_unknown_reorganizations(client):
    records = [
        action("Bonus 1:1 / Face Value Split From Rs 10 To Rs 2 / Dividend Rs 3"),
        action("Rights 2:21 @ Premium Rs 748/-"),
        action("Annual General Meeting"),
    ]
    source = client(Response(json.dumps(records).encode()))
    result = source.actions(DAY, NOW.date())
    assert result.records[0]["kind"] == "split_bonus"
    assert result.records[0]["factor"] == pytest.approx(0.1)
    assert result.records[0]["dividend"] == 3
    assert result.records[1]["requires_review"]
    assert result.records[1]["kind"] == "other"
    assert not result.records[2]["requires_review"]
    assert len(result.metadata["requires_review"]) == 1
    assert "from_date=01-10-2026&to_date=04-10-2026" in source.session.calls[0][0]


def test_non_equity_bonus_is_not_an_equity_split_or_demerger(client):
    result = client(
        Response(
            json.dumps(
                [
                    action("Scheme Of Arrangement - Bonus Ncrps 46:1"),
                ]
            ).encode()
        )
    ).actions(DAY, NOW.date())
    assert result.records[0]["kind"] == "other"
    assert result.records[0]["factor"] is None
    assert result.records[0]["requires_review"]


def test_membership_is_preserved_but_bhavcopy_retains_only_eq_be_bz(client):
    payload = members().replace(b"STOCK0,INE000000000,EQ", b"STOCK0,INE000000000,RR")
    source = client(
        Response(payload),
        Response(
            bhav(
                extra={
                    "TckrSymb": "REIT",
                    "ISIN": "INE000000002",
                    "SctySrs": "RR",
                }
            )
        ),
    )
    assert len(source.constituents(NOW.date()).records) == 500
    result = source.bhavcopy(DAY)
    assert [r["series"] for r in result.records] == ["EQ"]
    assert result.metadata["payload_record_count"] == 2
    assert result.metadata["retained_record_count"] == 1
    assert result.metadata["excluded_record_count"] == 1
    assert result.metadata["retained_series"] == ["EQ", "BE", "BZ"]


def test_constituent_series_remain_explicit_including_reits_and_dummy_components(
    client,
):
    payload = (
        members()
        .replace(b"STOCK0,INE000000000,EQ", b"BAGMANE,INE2OVN25015,RR")
        .replace(b"STOCK1,INE000000010,EQ", b"DUMMYHEG,DUM545A01024,EQ")
    )
    source = client(Response(payload))
    result = source.constituents(NOW.date())
    by_symbol = {r["symbol"]: r for r in result.records}
    assert len(by_symbol) == 500
    assert by_symbol["BAGMANE"]["series"] == "RR"
    assert by_symbol["DUMMYHEG"] == {
        "symbol": "DUMMYHEG",
        "isin": "DUM545A01024",
        "series": "EQ",
    }
    assert result.metadata["series_by_isin"]["INE2OVN25015"] == "RR"
    assert result.metadata["series_by_isin"]["DUM545A01024"] == "EQ"
    assert len(source.session.calls) == 1


def test_old_cached_membership_gains_series_from_original_raw_not_a_new_download(
    client,
):
    source = client(Response(members()))
    original = source.constituents(NOW.date())
    key = f"result:constituents:{NOW.date()}"
    old = source._get(key)
    for record in old["records"]:
        record.pop("series", None)
    source._put(key, old)
    source.now += timedelta(days=1)
    result = source.constituents(NOW.date())
    assert result == original
    assert all(r["series"] == "EQ" for r in result.records)
    assert len(source.session.calls) == 1


def test_old_normalization_is_reparsed_from_immutable_raw_without_http(client):
    source = client(
        Response(
            bhav(
                extra={
                    "TckrSymb": "REIT",
                    "ISIN": "INE000000002",
                    "SctySrs": "RR",
                }
            )
        )
    )
    old = source._result(
        f"bhavcopy:{DAY}",
        nse.existing_bhavcopy.udiff_url(DAY),
        lambda p: [{"symbol": "REIT", "series": "RR"}],
        metadata={"parser_version": "old"},
    )
    current = source.bhavcopy(DAY)
    assert current.source == old.source
    assert [r["series"] for r in current.records] == ["EQ"]
    assert len(source.session.calls) == 1
    with storage.connection_scope(source.db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM documents WHERE namespace=? AND key LIKE 'observation:bhavcopy:%'",
                (nse.NAMESPACE,),
            ).fetchone()[0]
            == 2
        )


@pytest.mark.parametrize(
    "data",
    [
        {"error": "denied"},
        {},
        [action("Face Value Split terms pending")],
        [action("Bonus 1:1", exDate="30-Sep-2026")],
        [action("Dividend"), action("Dividend", symbol="CONFLICT")],
    ],
)
def test_action_errors_never_hide_as_empty_success(client, data):
    with pytest.raises(ValueError):
        client(Response(json.dumps(data).encode())).actions(DAY, NOW.date())


def test_actual_empty_action_list_has_raw_evidence(client):
    result = client(Response(b"[]")).actions(DAY, NOW.date())
    assert result.records == []
    assert result.metadata["source_snapshots"]


def test_exact_normalized_action_duplicates_collapse_with_raw_evidence_and_counts(
    client,
):
    rows = [
        action(
            "Extra Ordinary General Meeting",
            faceVal="10",
            bcStartDate="02-Oct-2026",
            bcEndDate="08-Oct-2026",
            recDate="-",
        ),
        action(
            "Extra Ordinary General Meeting",
            faceVal="10.00",
            bcStartDate="-",
            bcEndDate="-",
            recDate="01-Oct-2026",
        ),
    ]
    source = client(Response(json.dumps(rows).encode()))
    result = source.actions(DAY, NOW.date())
    assert len(result.records) == 1
    assert result.metadata["raw_record_count"] == 2
    assert result.metadata["duplicate_count"] == 1
    assert result.metadata["windows"][0]["duplicate_count"] == 1
    raw_uri = result.metadata["windows"][0]["source"]
    group = raw_uri.split("/")[-2]
    assert (
        json.loads(
            storage.get_artifact(group, "payload", db_path=source.db_path).payload
        )
        == rows
    )
    assert source.actions(DAY, NOW.date()).metadata["duplicate_count"] == 1
    assert len(source.session.calls) == 1


@pytest.mark.parametrize(
    "rows",
    [
        [action("Bonus 1:1", faceVal="10"), action("Bonus 1:1", faceVal="2")],
        [action("Bonus 1:1"), action("Bonus 1:2")],
        [
            action("Face Value Split From Rs 10 To Rs 2"),
            action("Face Value Split From Rs 10 To Rs 5"),
        ],
    ],
)
def test_conflicting_financial_action_records_fail(client, rows):
    with pytest.raises(ValueError, match="Conflicting"):
        client(Response(json.dumps(rows).encode())).actions(DAY, NOW.date())


def test_distinct_dividend_components_are_not_deduplicated(client):
    rows = [
        action("Interim Dividend Rs 3 Per Share"),
        action("Special Dividend Rs 5 Per Share"),
    ]
    result = client(Response(json.dumps(rows).encode())).actions(DAY, NOW.date())
    assert [r["dividend"] for r in result.records] == [3, 5]
    assert result.metadata["duplicate_count"] == 0


def test_monthly_duplicate_counts_are_aggregated(client):
    september = action("Dividend Rs 3", exDate="30-Sep-2026")
    october = action("Dividend Rs 5")
    source = client(
        Response(json.dumps([september, september]).encode()),
        Response(json.dumps([october, october]).encode()),
    )
    result = source.actions(date(2026, 9, 30), DAY)
    assert result.metadata["raw_record_count"] == 4
    assert result.metadata["duplicate_count"] == 2
    assert result.metadata["record_count"] == 2


def test_actions_window_long_initial_history_by_calendar_month_without_gaps(client):
    start, end = date(2025, 2, 20), date(2026, 10, 4)
    source = client(*(Response(b"[]") for _ in range(21)))
    result = source.actions(start, end)
    assert result.metadata["window_policy"] == "calendar_months"
    assert len(result.metadata["windows"]) == 21
    assert result.metadata["record_count"] == 0
    previous_end = start - timedelta(days=1)
    for url, _ in source.session.calls:
        params = parse_qs(urlparse(url).query)
        first = datetime.strptime(params["from_date"][0], "%d-%m-%Y").date()
        last = datetime.strptime(params["to_date"][0], "%d-%m-%Y").date()
        assert first == previous_end + timedelta(days=1)
        assert (first.year, first.month) == (last.year, last.month)
        previous_end = last
    assert previous_end == end
    source.actions(start, end)
    assert len(source.session.calls) == 21


def test_actions_do_not_return_partial_history_if_a_later_month_fails(client):
    source = client(Response(b"[]"), Response(b'{"error":"range unavailable"}'))
    with pytest.raises(ValueError, match="JSON list"):
        source.actions(date(2026, 8, 20), date(2026, 10, 4))
    assert len(source.session.calls) == 2


def calendar_responses(*, holidays=None, note="Official holidays"):
    if holidays is None:
        holidays = [
            {"tradingDate": d, "description": "Holiday"}
            for d in [
                "26-Jan-2026",
                "03-Mar-2026",
                "03-Apr-2026",
                "01-May-2026",
                "02-Oct-2026",
            ]
        ]
    return [
        Response(b"<html>Equities Normal market 09:15 15:30</html>"),
        Response(f"<html>{note}</html>".encode()),
        Response(json.dumps({"CM": holidays}).encode()),
    ]


def test_calendar_future_regular_sessions_use_publications(client):
    source = client(*calendar_responses())
    result = source.calendar(date(2026, 10, 5), date(2026, 10, 6))
    assert all(r["is_session"] for r in result.records)
    assert result.metadata["complete_through"] == "2026-10-06"
    assert result.metadata["caveats"]
    assert len(result.metadata["source_snapshots"]) == 3


@pytest.mark.parametrize(
    "holidays", [[], [{"tradingDate": "26-Jan-2027", "description": "Wrong year"}]]
)
def test_empty_or_wrong_year_calendar_fails(client, holidays):
    with pytest.raises(ValueError):
        client(*calendar_responses(holidays=holidays)).calendar(
            date(2026, 10, 5), date(2026, 10, 6)
        )


def test_future_muhurat_requires_explicit_official_evidence(client):
    responses = calendar_responses()
    rows = json.loads(responses[-1].payload)["CM"]
    rows.append({"tradingDate": "08-Nov-2026", "description": "Diwali Laxmi Pujan*"})
    responses[-1] = Response(json.dumps({"CM": rows}).encode())
    source = client(*responses)
    with pytest.raises(nse.SourceUnavailable, match="Special-session status"):
        source.calendar(date(2026, 11, 8), date(2026, 11, 8))


def test_official_muhurat_note_overrides_holiday_without_inventing_hours(client):
    responses = calendar_responses(
        note=(
            "November 08, 2026, shall be a trading holiday on account of Diwali Laxmi Pujan. "
            "Muhurat Trading will be conducted on that day. Timings shall be notified subsequently."
        )
    )
    rows = json.loads(responses[-1].payload)["CM"]
    rows.append({"tradingDate": "08-Nov-2026", "description": "Diwali Laxmi Pujan*"})
    responses[-1] = Response(json.dumps({"CM": rows}).encode())
    result = client(*responses).calendar(date(2026, 11, 8), date(2026, 11, 8))
    assert result.records[0]["is_session"]
    assert result.metadata["annotations"][0]["kind"] == "published_override"


def test_weekend_archive_is_a_positive_session_override(client):
    weekend = date(2026, 10, 3)
    source = client(
        *calendar_responses(),
        Response(
            bhav(
                changes={
                    "TradDt": str(weekend),
                    "BizDt": str(weekend),
                }
            )
        ),
    )
    result = source.calendar(weekend, weekend)
    assert result.records[0]["is_session"]
    assert result.metadata["annotations"][0]["kind"] == "observed_archive"


def test_closed_date_404_uses_calendar_rule_but_network_error_is_fatal(client):
    weekend = date(2026, 10, 3)
    source = client(*calendar_responses(), Response(b"absent", 404))
    assert not source.calendar(weekend, weekend).records[0]["is_session"]
    source.now = NOW.replace(day=5)
    source.session = Session(
        calendar_responses() + [Response(b"broken", 503), Response(b"broken", 503)]
    )
    with pytest.raises(nse.SourceUnavailable):
        source.calendar(date(2026, 10, 4), date(2026, 10, 4))


def test_override_loader_requires_official_dated_quote(client):
    quote = "October 10, 2026 is a special cash-market trading session."
    source = client(Response(quote.encode()), *calendar_responses())
    source.load_special_sessions(
        [{"date": "2026-10-10", "is_session": True, "evidence": quote}],
        source_url="https://www.nseindia.com/official-notice",
    )
    assert source.calendar(date(2026, 10, 10), date(2026, 10, 10)).records[0][
        "is_session"
    ]
    with pytest.raises(ValueError, match="official NSE"):
        source.load_special_sessions([], source_url="https://example.com/notice")
