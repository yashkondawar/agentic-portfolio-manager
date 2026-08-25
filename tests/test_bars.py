"""
tests/test_bars.py
==================

Tests for the shared daily bar store.

The load-bearing tests here are the ones that protect *correctness*, not speed:

* ``test_split_adjustment_drift_is_detected`` - yfinance returns split-adjusted
  prices, so a corporate action rewrites history. An incremental store that
  blindly appends would splice two adjustment bases into one series and silently
  corrupt every indicator downstream. This is the failure mode a naive cache
  would never notice.
* ``test_empty_symbol_is_not_refetched_forever`` - a stock listed in 2021 has no
  bars in 2018 no matter how often it is asked for. Without recording the
  *requested* range separately from the *stored* range, every run would re-issue
  the same permanently-empty download.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import bars  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point the store at a throwaway database for every test."""
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "test.sqlite3"))
    yield


def make_frame(start: str, days: int, first_close: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range(start=start, periods=days)
    closes = [first_close + i for i in range(days)]
    return pd.DataFrame(
        {
            "Open": [c - 0.5 for c in closes],
            "High": [c + 1.0 for c in closes],
            "Low": [c - 1.0 for c in closes],
            "Close": closes,
            "Volume": [1_000.0] * days,
        },
        index=idx,
    )


def make_downloader(frames: dict):
    """A yfinance stand-in returning a group_by='ticker' shaped frame.

    Real yfinance returns ticker-major MultiIndex columns *even for a single
    ticker*. This double used to return a flat frame in that case, which is why
    a single-symbol parse bug went unnoticed: the benchmark is always fetched
    alone, so it silently stopped updating. Keep this faithful.
    """

    def _download(tickers, start, end):
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
        parts = {}
        for ticker in tickers:
            df = frames.get(ticker)
            if df is None:
                continue
            window = df.loc[(df.index >= lo) & (df.index <= hi)]
            if not window.empty:
                parts[ticker] = window
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, axis=1)

    return _download


# ── Round trip ───────────────────────────────────────────────────────────────


def test_write_then_read_round_trips_ohlcv():
    frame = make_frame("2023-01-02", 10)
    bars.write_bars("RELIANCE", frame, date(2023, 1, 1), date(2023, 1, 31))

    got = bars.read_symbol("RELIANCE")
    assert got is not None
    assert list(got.columns) == bars.OHLCV_COLUMNS
    assert len(got) == 10
    pd.testing.assert_series_equal(
        got["Close"], frame["Close"], check_names=False, check_freq=False
    )


def test_symbol_suffixes_normalise_to_one_key():
    frame = make_frame("2023-01-02", 5)
    bars.write_bars("RELIANCE.NS", frame, date(2023, 1, 1), date(2023, 1, 31))

    assert bars.read_symbol("RELIANCE") is not None
    assert bars.read_symbol("reliance.ns") is not None
    assert len(bars.read_bars(["RELIANCE", "RELIANCE.NS"])) == 1


def test_index_tickers_keep_their_caret():
    assert bars.yf_symbol("^NSEI") == "^NSEI"
    assert bars.yf_symbol("RELIANCE") == "RELIANCE.NS"
    assert bars.yf_symbol("TCS.NS") == "TCS.NS"


def test_read_respects_the_requested_window():
    bars.write_bars(
        "TCS", make_frame("2023-01-02", 40), date(2023, 1, 1), date(2023, 3, 31)
    )
    got = bars.read_symbol("TCS", date(2023, 1, 10), date(2023, 1, 20))
    assert got is not None
    assert got.index.min() >= pd.Timestamp("2023-01-10")
    assert got.index.max() <= pd.Timestamp("2023-01-20")


def test_min_rows_filters_thin_history():
    bars.write_bars("THIN", make_frame("2023-01-02", 5), date(2023, 1, 1), date(2023, 1, 31))
    bars.write_bars("FAT", make_frame("2023-01-02", 80), date(2023, 1, 1), date(2023, 5, 31))

    frames = bars.read_bars(["THIN", "FAT"], min_rows=60)
    assert "FAT" in frames
    assert "THIN" not in frames


def test_upsert_overwrites_rather_than_duplicating():
    bars.write_bars("TCS", make_frame("2023-01-02", 5), date(2023, 1, 1), date(2023, 1, 31))
    revised = make_frame("2023-01-02", 5, first_close=200.0)
    bars.write_bars("TCS", revised, date(2023, 1, 1), date(2023, 1, 31))

    got = bars.read_symbol("TCS")
    assert len(got) == 5
    assert got["Close"].iloc[0] == pytest.approx(200.0)


# ── Fetch planning ───────────────────────────────────────────────────────────


def test_unknown_symbol_is_planned_for_full_fetch():
    jobs = bars.plan_fetches(["NEW"], date(2023, 1, 1), date(2023, 6, 30))
    assert len(jobs) == 1
    assert jobs[0].symbol == "NEW"
    assert jobs[0].is_topup is False


def test_covered_symbol_needs_no_fetch():
    bars.write_bars("TCS", make_frame("2023-01-02", 60), date(2023, 1, 1), date(2023, 6, 30))
    assert bars.plan_fetches(["TCS"], date(2023, 2, 1), date(2023, 5, 31)) == []


def test_forward_extension_only_fetches_the_tail():
    """The whole point of the store: extending the window must not refetch it."""
    bars.write_bars("TCS", make_frame("2023-01-02", 60), date(2023, 1, 1), date(2023, 3, 31))
    jobs = bars.plan_fetches(["TCS"], date(2023, 1, 1), date(2023, 6, 30))

    assert len(jobs) == 1
    job = jobs[0]
    assert job.is_topup is True
    assert job.end == date(2023, 6, 30)
    # Starts near the existing tail, not at the original start.
    assert job.start > date(2023, 2, 1)


def test_backfill_and_extension_are_two_narrow_jobs():
    bars.write_bars("TCS", make_frame("2023-03-01", 40), date(2023, 3, 1), date(2023, 4, 30))
    jobs = bars.plan_fetches(["TCS"], date(2022, 1, 1), date(2023, 12, 31))

    assert len(jobs) == 2
    assert all(j.is_topup for j in jobs)
    # Neither job spans the full two years; that is what makes this cheap.
    assert all((j.end - j.start).days < 700 for j in jobs)
    forward = [j for j in jobs if j.end == date(2023, 12, 31)]
    backfill = [j for j in jobs if j.start == date(2022, 1, 1)]
    assert len(forward) == 1 and len(backfill) == 1


def test_force_replans_even_a_covered_symbol():
    bars.write_bars("TCS", make_frame("2023-01-02", 60), date(2023, 1, 1), date(2023, 6, 30))
    jobs = bars.plan_fetches(["TCS"], date(2023, 2, 1), date(2023, 5, 31), force=True)
    assert len(jobs) == 1
    assert jobs[0].is_topup is False


# ── The corporate-action hazard ──────────────────────────────────────────────


def test_detect_drift_ignores_an_unchanged_overlap():
    frame = make_frame("2023-01-02", 20)
    assert bars.detect_drift(frame, frame) is False


def test_detect_drift_flags_a_split_adjusted_series():
    stored = make_frame("2023-01-02", 20)
    resplit = stored.copy()
    resplit[["Open", "High", "Low", "Close"]] /= 2.0  # a 2:1 split re-based history
    assert bars.detect_drift(stored, resplit) is True


def test_detect_drift_ignores_disjoint_ranges():
    a = make_frame("2023-01-02", 10)
    b = make_frame("2023-06-01", 10)
    assert bars.detect_drift(a, b) is False


def test_split_adjustment_drift_triggers_a_full_refetch():
    """A split must never leave two adjustment bases spliced in one series.

    The store holds January at the old basis. The provider then returns every
    bar halved, as yfinance does after a 2:1 split. Appending would produce a
    series that steps by 2x mid-way; the store must instead notice the overlap
    disagrees, drop the symbol and refetch the whole range at the new basis.
    """
    old_basis = make_frame("2023-01-02", 40)
    bars.write_bars("SPLITCO", old_basis, date(2023, 1, 1), date(2023, 2, 24))

    new_basis = make_frame("2023-01-02", 120)
    new_basis[["Open", "High", "Low", "Close"]] /= 2.0
    downloader = make_downloader({"SPLITCO.NS": new_basis})

    report = bars.sync(
        ["SPLITCO"], date(2023, 1, 1), date(2023, 6, 30), downloader=downloader
    )

    assert report.rebased == ["SPLITCO"]
    got = bars.read_symbol("SPLITCO")
    assert got is not None
    # Every stored bar is now on the new basis - no 2x step anywhere.
    merged = new_basis.loc[got.index, "Close"]
    pd.testing.assert_series_equal(
        got["Close"], merged, check_names=False, check_freq=False
    )
    assert got["Close"].pct_change().abs().max() < 0.5


# ── Coverage bookkeeping ─────────────────────────────────────────────────────


def test_empty_symbol_is_not_refetched_forever():
    """A pre-IPO window is legitimately empty; asking again forever is a bug.

    Coverage must record what was *requested*, not merely what was *returned*,
    otherwise the absence of data looks identical to the absence of an attempt.
    """
    downloader = make_downloader({})  # provider has nothing for this name
    first = bars.sync(["DELISTED"], date(2018, 1, 1), date(2018, 12, 31),
                      downloader=downloader)
    assert first.empty == ["DELISTED"]

    def explode(tickers, start, end):
        raise AssertionError(f"refetched a known-empty window: {tickers}")

    second = bars.sync(["DELISTED"], date(2018, 1, 1), date(2018, 12, 31),
                       downloader=explode)
    assert second.up_to_date == 1
    assert second.fetched == 0


def test_coverage_tracks_requested_range_beyond_stored_data():
    frame = make_frame("2023-03-01", 20)
    bars.write_bars("LATEIPO", frame, date(2020, 1, 1), date(2023, 6, 30))

    cov = bars.coverage(["LATEIPO"])["LATEIPO"]
    assert cov.requested_start == date(2020, 1, 1)
    assert cov.requested_end == date(2023, 6, 30)
    assert cov.first_day == date(2023, 3, 1)
    assert cov.row_count == 20
    # A window inside what we already asked for needs no work.
    assert bars.plan_fetches(["LATEIPO"], date(2021, 1, 1), date(2023, 6, 30)) == []


def test_requested_range_widens_and_never_shrinks():
    frame = make_frame("2023-01-02", 20)
    bars.write_bars("TCS", frame, date(2023, 1, 1), date(2023, 3, 31))
    bars.write_bars("TCS", frame, date(2022, 6, 1), date(2023, 2, 28))

    cov = bars.coverage(["TCS"])["TCS"]
    assert cov.requested_start == date(2022, 6, 1)
    assert cov.requested_end == date(2023, 3, 31)


def test_drop_symbols_forces_a_refetch():
    bars.write_bars("TCS", make_frame("2023-01-02", 20), date(2023, 1, 1), date(2023, 3, 31))
    assert bars.plan_fetches(["TCS"], date(2023, 1, 1), date(2023, 3, 31)) == []

    bars.drop_symbols(["TCS"])
    assert bars.read_symbol("TCS") is None
    jobs = bars.plan_fetches(["TCS"], date(2023, 1, 1), date(2023, 3, 31))
    assert len(jobs) == 1 and jobs[0].is_topup is False


# ── Staleness: a symbol must never silently stop updating ────────────────────


def test_a_lone_ticker_is_parsed_from_a_ticker_major_frame():
    """yfinance returns a MultiIndex even for one ticker.

    Taking column level 0 blindly yielded columns named after the ticker, so
    "Close" went missing and the symbol was recorded as having no data. The
    benchmark is always fetched alone, so this froze the master calendar.
    """
    frame = make_frame("2023-01-02", 10)
    ticker_major = pd.concat({"^NSEI": frame}, axis=1)
    assert isinstance(ticker_major.columns, pd.MultiIndex)

    out = bars.normalise_frame(ticker_major)

    assert out is not None and len(out) == 10
    assert "Close" in out.columns


def test_syncing_a_single_symbol_actually_stores_rows():
    frames = {"^NSEI": make_frame("2023-01-02", 20)}
    report = bars.sync(
        ["^NSEI"], date(2023, 1, 1), date(2023, 3, 31),
        downloader=make_downloader(frames),
    )

    assert report.fetched == 1
    assert report.empty == []
    stored = bars.read_symbol("^NSEI")
    assert stored is not None and len(stored) == 20


def test_a_missing_ticker_is_not_filled_from_a_neighbour():
    """The response only carried TCS, but INFY was asked for too. Falling back
    to the whole frame would file TCS's prices under INFY - a silent, and
    completely undetectable, corruption of the store."""
    frames = {"TCS.NS": make_frame("2023-01-02", 20)}
    report = bars.sync(
        ["TCS", "INFY"], date(2023, 1, 1), date(2023, 3, 31),
        downloader=make_downloader(frames),
    )

    assert report.empty == ["INFY"]
    assert bars.read_symbol("INFY") is None
    stored = bars.read_symbol("TCS")
    assert stored is not None and len(stored) == 20


def test_coverage_is_never_recorded_past_today():
    """Callers pad the end date past today; recording that pad made the symbol
    look covered until the calendar caught up, so it stopped topping up."""
    future = date.today() + timedelta(days=10)
    bars.write_bars("TCS", make_frame("2023-01-02", 20), date(2023, 1, 1), future)

    assert bars.coverage(["TCS"])["TCS"].requested_end <= date.today()


def test_a_future_coverage_window_still_allows_a_top_up():
    """Belt and braces: rows written before the clamp existed must heal.

    The store deliberately trusts "we asked through X and got all there was",
    so a poisoned row is not refetched on the same day it claims to cover -
    forcing that would also refetch every delisted name on every run. It heals
    as soon as a later session is requested. The live runner does not rely on
    this: it checks data freshness explicitly.
    """
    frame = make_frame("2023-01-02", 20)
    bars.write_bars("TCS", frame, date(2023, 1, 1), date(2023, 3, 31))
    # Simulate a poisoned row from an older build.
    conn = bars._open()
    try:
        conn.execute(
            "UPDATE bar_coverage SET requested_end = ? WHERE symbol = ?",
            ((date.today() + timedelta(days=30)).isoformat(), "TCS"),
        )
        conn.commit()
    finally:
        conn.close()

    # Without the read-side clamp this stays empty forever, because the stored
    # window swallows every future request.
    jobs = bars.plan_fetches(["TCS"], date(2023, 1, 1), date.today() + timedelta(days=1))

    assert len(jobs) == 1, "a stale symbol claiming future coverage must refetch"


# ── Sync end to end ──────────────────────────────────────────────────────────


def test_sync_populates_multiple_symbols_in_one_pass():
    frames = {
        "AAA.NS": make_frame("2023-01-02", 100),
        "BBB.NS": make_frame("2023-01-02", 100, first_close=50.0),
        "^NSEI": make_frame("2023-01-02", 100, first_close=18000.0),
    }
    report = bars.sync(
        ["AAA", "BBB", "^NSEI"], date(2023, 1, 1), date(2023, 6, 30),
        downloader=make_downloader(frames),
    )
    assert report.fetched == 3
    assert report.rows_written == 300
    stored = bars.read_bars(["AAA", "BBB", "^NSEI"])
    assert set(stored) == {"AAA", "BBB", "^NSEI"}


def test_second_sync_downloads_nothing_new():
    """The reason this store exists: a rerun must not touch the network."""
    frames = {"AAA.NS": make_frame("2023-01-02", 100)}
    bars.sync(["AAA"], date(2023, 1, 1), date(2023, 6, 30),
              downloader=make_downloader(frames))

    def explode(tickers, start, end):
        raise AssertionError("re-downloaded an already covered window")

    report = bars.sync(["AAA"], date(2023, 1, 1), date(2023, 6, 30), downloader=explode)
    assert report.up_to_date == 1
    assert report.fetched == 0


def test_sync_only_requests_the_missing_tail():
    frames = {"AAA.NS": make_frame("2023-01-02", 200)}
    bars.sync(["AAA"], date(2023, 1, 1), date(2023, 3, 31),
              downloader=make_downloader(frames))
    before = len(bars.read_symbol("AAA"))

    seen = []

    def spy(tickers, start, end):
        seen.append((start, end))
        return make_downloader(frames)(tickers, start, end)

    bars.sync(["AAA"], date(2023, 1, 1), date(2023, 8, 31), downloader=spy)

    assert len(seen) == 1
    requested_start, _ = seen[0]
    # Asked only for the tail plus a short verification overlap.
    assert requested_start > date(2023, 2, 15)
    assert len(bars.read_symbol("AAA")) > before


def test_sync_survives_a_failing_chunk():
    def flaky(tickers, start, end):
        raise RuntimeError("network down")

    report = bars.sync(["AAA", "BBB"], date(2023, 1, 1), date(2023, 6, 30),
                       downloader=flaky)
    assert set(report.failed) == {"AAA", "BBB"}
    assert report.fetched == 0
    # A failure must not be recorded as coverage, or the bars are lost forever.
    assert bars.plan_fetches(["AAA"], date(2023, 1, 1), date(2023, 6, 30))


def test_store_stats_reports_contents():
    bars.write_bars("AAA", make_frame("2023-01-02", 10), date(2023, 1, 1), date(2023, 1, 31))
    bars.write_bars("BBB", None, date(2023, 1, 1), date(2023, 1, 31))

    stats = bars.store_stats()
    assert stats["symbols"] == 1
    assert stats["bars"] == 10
    assert stats["symbols_without_data"] == 1


def test_normalise_flattens_multiindex_columns():
    frame = make_frame("2023-01-02", 5)
    wide = pd.concat({"AAA.NS": frame}, axis=1)
    out = bars.normalise_frame(wide["AAA.NS"])
    assert list(out.columns) == bars.OHLCV_COLUMNS
    assert out.index.tz is None


def test_normalise_drops_timezone_and_duplicates():
    idx = pd.to_datetime(
        ["2023-01-02", "2023-01-02", "2023-01-03"]
    ).tz_localize("Asia/Kolkata")
    frame = pd.DataFrame(
        {"Open": [1.0, 2.0, 3.0], "High": [1.0, 2.0, 3.0], "Low": [1.0, 2.0, 3.0],
         "Close": [1.0, 2.0, 3.0], "Volume": [1.0, 1.0, 1.0]},
        index=idx,
    )
    out = bars.normalise_frame(frame)
    assert len(out) == 2
    assert out.index.tz is None
    assert out["Close"].iloc[0] == 2.0  # last write wins


# ── Integration with the backtest loader ─────────────────────────────────────


def test_point_in_time_loader_reads_from_the_store(tmp_path):
    from backtesting.swing_trading.data import PointInTimeData

    frames = {
        "AAA.NS": make_frame("2022-01-03", 400),
        "^NSEI": make_frame("2022-01-03", 400, first_close=18000.0),
    }
    bars.sync(["AAA", "^NSEI"], date(2021, 6, 1), date(2023, 12, 31),
              downloader=make_downloader(frames))

    store = PointInTimeData(tmp_path)
    store.load_or_download(
        ["AAA"], "^NSEI", date(2022, 6, 1), date(2023, 6, 30), warmup_days=200
    )

    assert "AAA" in store.frames
    assert store.benchmark is not None
    # as-of slicing still refuses to look forward.
    sliced = store.as_of("AAA", date(2022, 7, 1))
    assert sliced.index.max() <= pd.Timestamp("2022-07-01")


def test_point_in_time_loader_is_offline_on_a_warm_store(tmp_path, monkeypatch):
    from backtesting.swing_trading.data import PointInTimeData

    frames = {
        "AAA.NS": make_frame("2022-01-03", 400),
        "^NSEI": make_frame("2022-01-03", 400, first_close=18000.0),
    }
    bars.sync(["AAA", "^NSEI"], date(2021, 6, 1), date(2023, 12, 31),
              downloader=make_downloader(frames))

    def explode(*args, **kwargs):
        raise AssertionError("hit the network despite a warm store")

    monkeypatch.setattr(bars, "_download", explode)

    store = PointInTimeData(tmp_path)
    store.load_or_download(
        ["AAA"], "^NSEI", date(2022, 6, 1), date(2023, 6, 30), warmup_days=200
    )
    assert "AAA" in store.frames
