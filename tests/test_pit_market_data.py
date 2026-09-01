"""Tests for the point-in-time market data layer.

These three modules exist to remove survivorship bias from the backtest, so
the tests care most about the cases where bias leaks back in: a delisted
company disappearing, a renamed company failing to join, an unadjusted split
faking a crash, and a company appearing in the index before it was listed.
"""
from __future__ import annotations

from datetime import date

import pytest

from scraper import (bhavcopy, conn_cache, corporate_actions,
                     index_membership, pit_universe)


@pytest.fixture()
def conn(tmp_path):
    connection = bhavcopy.open_store(tmp_path / "pit.sqlite3")
    connection.executescript(index_membership._SCHEMA)
    connection.executescript(corporate_actions._SCHEMA)
    connection.commit()
    yield connection
    connection.close()


def add_bar(connection, symbol, day, *, close=100.0, isin="", turnover=1e7):
    connection.execute(
        "INSERT OR REPLACE INTO market_bars (symbol, trade_date, series, isin,"
        " open, high, low, close, prev_close, volume, turnover, trades,"
        " source)"
        " VALUES (?,?,'EQ',?,?,?,?,?,?,1000,?,10,'test')",
        (symbol, day.isoformat(), isin, close, close, close, close, close,
         turnover),
    )


def add_member(connection, symbol, valid_from, valid_to=None, source="test"):
    connection.execute(
        "INSERT OR REPLACE INTO index_membership (index_name, symbol,"
        " valid_from, valid_to, source, source_url, imported_at)"
        " VALUES (?,?,?,?,?,'','2026-01-01')",
        (index_membership.DEFAULT_INDEX, symbol, valid_from.isoformat(),
         valid_to.isoformat() if valid_to else None, source),
    )


# ── bhavcopy parsing ─────────────────────────────────────────────────────────
def test_legacy_parse_keeps_equity_series_only():
    rows = [
        {"SYMBOL": "RELIANCE", "SERIES": "EQ", "OPEN": "100", "HIGH": "110",
         "LOW": "99", "CLOSE": "105", "PREVCLOSE": "98", "TOTTRDQTY": "5",
         "TOTTRDVAL": "500", "TOTALTRADES": "3", "ISIN": "INE002A01018"},
        {"SYMBOL": "SOMEBOND", "SERIES": "N1", "CLOSE": "99", "ISIN": "X"},
    ]
    out = bhavcopy.parse_legacy(rows, date(2015, 1, 2))
    assert [r[0] for r in out] == ["RELIANCE"]
    assert out[0][1] == "2015-01-02"
    assert out[0][7] == 105.0


def test_legacy_parse_keeps_trade_to_trade_series():
    """BE names are kept: distressed companies often end their lives there."""
    rows = [{"SYMBOL": "DHFL", "SERIES": "BE", "CLOSE": "17", "ISIN": "I"}]
    assert bhavcopy.parse_legacy(rows, date(2020, 1, 1))[0][0] == "DHFL"


def test_udiff_parse_ignores_derivative_rows():
    rows = [
        {"TckrSymb": "INFY", "SctySrs": "EQ", "FinInstrmTp": "STK",
         "ClsPric": "1500", "ISIN": "INE009A01021"},
        {"TckrSymb": "INFY", "SctySrs": "EQ", "FinInstrmTp": "IDF",
         "ClsPric": "1500", "ISIN": "INE009A01021"},
    ]
    out = bhavcopy.parse_udiff(rows, date(2024, 5, 2))
    assert len(out) == 1
    assert out[0][12] == "udiff"


def test_url_format_switches_at_2024():
    assert "cm01JAN2015bhav" in bhavcopy.legacy_url(date(2015, 1, 1))
    assert "20240102" in bhavcopy.udiff_url(date(2024, 1, 2))


# ── corporate actions ────────────────────────────────────────────────────────
@pytest.mark.parametrize("subject, expected", [
    ("Face Value Split (Sub-Division) - From Rs 2 Per Share To Rs 1 Per Share",
     0.5),
    ("Bonus 1:1", 0.5),
    ("Bonus Issue 3:5", 0.625),
    ("Bonus 1 : 1250", 1250 / 1251),
    ("Face Value Split From Rs 10 To Re 1", 0.1),
    ("Bonus 1:1 / Face Value Split From Rs 10/- Per Share To Rs 2/", 0.1),
])
def test_classify_extracts_price_factor(subject, expected):
    _, factor, _ = corporate_actions.classify(subject)
    assert factor == pytest.approx(expected)


@pytest.mark.parametrize("subject", [
    "Annual General Meeting",
    "Scheme of Arrangement",
    "Dividend Of Rs 1.80/- Per Share",
])
def test_classify_returns_no_factor_for_non_capital_events(subject):
    _, factor, _ = corporate_actions.classify(subject)
    assert factor is None


def test_dividend_amount_is_captured_but_not_a_price_factor():
    kind, factor, amount = corporate_actions.classify(
        "Interim Dividend Rs 10/- Per Share"
    )
    assert kind == "dividend"
    assert factor is None
    assert amount == pytest.approx(10.0)


def test_adjustment_series_removes_the_fake_split_crash():
    """HDFCBANK's 1:2 split shows as a 49.67% fall in raw bhavcopy closes."""
    sessions = [date(2019, 9, 18), date(2019, 9, 19), date(2019, 9, 20)]
    raw = [2187.75, 1101.05, 1110.0]
    factors = corporate_actions.adjustment_series(
        [(date(2019, 9, 19), 0.5)], sessions
    )
    adjusted = [price * factor for price, factor in zip(raw, factors)]
    raw_return = raw[1] / raw[0] - 1
    adjusted_return = adjusted[1] / adjusted[0] - 1
    assert raw_return < -0.49
    assert abs(adjusted_return) < 0.02


def test_adjustment_series_is_flat_without_events():
    sessions = [date(2020, 1, 1), date(2020, 1, 2)]
    assert corporate_actions.adjustment_series([], sessions) == [1.0, 1.0]


# ── membership ───────────────────────────────────────────────────────────────
def test_membership_is_half_open_on_the_exit_date(conn):
    add_member(conn, "DHFL", date(2014, 1, 1), date(2020, 6, 26))
    conn.commit()
    on = index_membership.canonical_members_on
    assert "DHFL" in on(conn, date(2020, 6, 25))
    assert "DHFL" not in on(conn, date(2020, 6, 26))


def test_delisted_company_stays_in_history(conn):
    add_member(conn, "JETAIRWAYS", date(2014, 1, 1), date(2019, 9, 24))
    conn.commit()
    members = index_membership.canonical_members_on(conn, date(2016, 6, 30))
    assert "JETAIRWAYS" in members


def test_rename_resolves_through_isin(conn):
    """Membership uses today's ticker; the tape uses the ticker of the day."""
    add_bar(conn, "ADANITRANS", date(2015, 6, 30), isin="INE931S01010")
    add_bar(conn, "ADANIENSOL", date(2024, 6, 28), isin="INE931S01010")
    add_member(conn, "ADANIENSOL", date(2014, 1, 1))
    conn.commit()
    resolved = index_membership.members_on(conn, date(2015, 6, 30))
    assert resolved == {"ADANITRANS"}
    assert index_membership.canonical_members_on(
        conn, date(2015, 6, 30)
    ) == {"ADANIENSOL"}


def test_import_replaces_previous_intervals(conn):
    rows = [
        {"index_name": "Nifty 500", "symbol": "ACME",
         "valid_from": "2014-01-01", "valid_to": "",
         "source": "press_release", "source_url": "u"},
        {"index_name": "Nifty 50", "symbol": "OTHER",
         "valid_from": "2014-01-01", "valid_to": "2020-01-01",
         "source": "press_release", "source_url": "u"},
    ]
    assert index_membership.import_membership(
        conn, rows, indices=["Nifty 500"]
    ) == 1
    stored = index_membership.membership_intervals(conn)
    assert [row["symbol"] for row in stored] == ["ACME"]
    assert stored[0]["valid_to"] is None


# ── point-in-time universe ───────────────────────────────────────────────────
def test_universe_drops_members_that_were_not_listed_yet(conn):
    """The membership dataset back-dates entries; the tape must veto them."""
    day = date(2015, 6, 30)
    for offset in range(40):
        bar_day = date.fromordinal(day.toordinal() - offset)
        add_bar(conn, "RELIANCE", bar_day, isin="INE002A01018")
    add_member(conn, "RELIANCE", date(2014, 1, 1))
    add_member(conn, "ALKEM", date(2014, 1, 1), source="snapshot_floor")
    conn.commit()
    assert pit_universe.pit_universe(conn, day) == {"RELIANCE"}


def test_universe_drops_members_below_the_liquidity_floor(conn):
    day = date(2015, 6, 30)
    for offset in range(40):
        bar_day = date.fromordinal(day.toordinal() - offset)
        add_bar(conn, "BIG", bar_day, turnover=1e9)
        add_bar(conn, "TINY", bar_day, turnover=1.0)
    add_member(conn, "BIG", date(2014, 1, 1))
    add_member(conn, "TINY", date(2014, 1, 1))
    conn.commit()
    assert pit_universe.pit_universe(conn, day, top_n=1) == {"BIG"}
    assert pit_universe.pit_universe(
        conn, day, apply_liquidity_gate=False
    ) == {"BIG", "TINY"}


def test_universe_keeps_a_company_that_later_went_bust(conn):
    day = date(2018, 6, 29)
    for offset in range(40):
        bar_day = date.fromordinal(day.toordinal() - offset)
        add_bar(conn, "DHFL", bar_day, turnover=1e8)
    add_member(conn, "DHFL", date(2014, 1, 1), date(2020, 6, 26))
    conn.commit()
    assert "DHFL" in pit_universe.pit_universe(conn, day)


def test_diagnostics_account_for_every_dropped_name(conn):
    day = date(2015, 6, 30)
    for offset in range(40):
        bar_day = date.fromordinal(day.toordinal() - offset)
        add_bar(conn, "BIG", bar_day, turnover=1e9)
        add_bar(conn, "TINY", bar_day, turnover=1.0)
    add_member(conn, "BIG", date(2014, 1, 1))
    add_member(conn, "TINY", date(2014, 1, 1))
    add_member(conn, "UNLISTED", date(2014, 1, 1))
    conn.commit()
    stats = pit_universe.universe_diagnostics(conn, day, top_n=1)
    assert stats["members"] == 3
    assert stats["not_listed"] == 1
    assert stats["tradable"] == 2
    assert stats["below_liquidity"] == 1
    assert stats["universe"] == 1


def test_universe_cache_is_independent_of_call_order(conn):
    """Asking mid-month first must not poison the answer for the month."""
    day = date(2015, 6, 30)
    for offset in range(120):
        bar_day = date.fromordinal(day.toordinal() - offset)
        add_bar(conn, "BIG", bar_day, turnover=1e9)
    add_member(conn, "BIG", date(2014, 1, 1))
    conn.commit()

    forwards = pit_universe.PitUniverse(conn)
    assert forwards.on(date(2015, 6, 1)) == forwards.on(day)

    backwards = pit_universe.PitUniverse(conn)
    assert backwards.on(day) == backwards.on(date(2015, 6, 1))
    assert forwards.on(day) == backwards.on(day) == {"BIG"}
    assert backwards.contains("BIG", day)
    assert not backwards.contains("NOPE", day)
    assert backwards.contains("ANYTHING", None)


# -- corporate actions: variants found in the real NSE feed -------------------
@pytest.mark.parametrize("subject, expected", [
    ("Fv Splt Frm Rs 10 To Re 1", 0.1),
    ("Face Value Split Rs.10/- To Re.1/-", 0.1),
    ("Face Valus Split Rs 10 Per To Rs 2 Per", 0.2),
    ("Bonus- 1:2", pytest.approx(2 / 3)),
])
def test_classify_handles_abbreviated_and_misspelt_filings(subject, expected):
    """NSE subject lines are typed by hand and are not a controlled format."""
    _, factor, _ = corporate_actions.classify(subject)
    assert factor == expected


@pytest.mark.parametrize("subject", [
    "Bonus Ncrps 4:1",
    "Bonus Debentures 1:1",
    "Bonus Preference Shares 21:1",
])
def test_bonus_of_another_instrument_never_adjusts_the_equity_price(subject):
    """These hand out a *different* security, so the share base is unchanged.

    Treating one as a 1:1 equity bonus would halve every earlier price and
    manufacture a 50% crash that never happened.
    """
    _, factor, _ = corporate_actions.classify(subject)
    assert factor is None


def test_split_is_read_from_the_split_phrase_not_a_leading_dividend():
    """A payout stated first must not be mistaken for the old face value."""
    _, factor, _ = corporate_actions.classify(
        "Dividend Rs 5 Per Share/Face Value Split From Rs 10 To Rs 2"
    )
    assert factor == pytest.approx(0.2)


def test_demerger_is_flagged_rather_than_guessed():
    """The parent's fall equals the child's value, which the filing omits."""
    assert corporate_actions.is_demerger("Composite Scheme Of Arrangement")
    kind, factor, _ = corporate_actions.classify("Demerger")
    assert kind == "demerger"
    assert factor is None


def add_action(connection, symbol, ex_date, subject, *, kind="", factor=None):
    connection.execute(
        "INSERT OR REPLACE INTO corporate_actions (symbol, ex_date, subject,"
        " isin, face_value, kind, factor, dividend, fetched_at)"
        " VALUES (?,?,?,'',NULL,?,?,NULL,'2026-01-01')",
        (symbol, ex_date.isoformat(), subject, kind, factor),
    )


def test_factors_reach_prices_printed_under_a_former_ticker(conn):
    """NSE files an action under the company's present-day ticker only."""
    add_bar(conn, "CROMPGREAV", date(2016, 3, 14), isin="INE067A01029")
    add_bar(conn, "CGPOWER", date(2024, 3, 14), isin="INE067A01029")
    add_action(conn, "CGPOWER", date(2016, 3, 15), "Bonus 1:1", factor=0.5)
    conn.commit()
    factors = corporate_actions.load_factors(conn)
    assert factors["CROMPGREAV"] == [(date(2016, 3, 15), 0.5)]
    assert corporate_actions.load_factors(
        conn, resolve_renames=False
    ).get("CROMPGREAV") is None


def test_an_event_filed_under_both_tickers_is_only_applied_once(conn):
    add_bar(conn, "OLD", date(2016, 3, 14), isin="INE111A01011")
    add_bar(conn, "NEW", date(2024, 3, 14), isin="INE111A01011")
    add_action(conn, "OLD", date(2016, 3, 15), "Bonus 1:1", factor=0.5)
    add_action(conn, "NEW", date(2016, 3, 15), "Bonus 1:1", factor=0.5)
    conn.commit()
    assert corporate_actions.load_factors(conn)["OLD"] == [
        (date(2016, 3, 15), 0.5)
    ]


def test_demerger_dates_also_resolve_through_isin(conn):
    """Otherwise a demerger stays invisible on the very prices it explains."""
    add_bar(conn, "CENTURYTEX", date(2019, 10, 10), isin="INE055A01016")
    add_bar(conn, "ABREL", date(2024, 10, 10), isin="INE055A01016")
    add_action(conn, "ABREL", date(2019, 10, 11), "Demerger", kind="demerger")
    conn.commit()
    demergers = corporate_actions.load_demergers(conn)
    assert demergers["CENTURYTEX"] == {date(2019, 10, 11)}
    assert corporate_actions.load_demergers(
        conn, resolve_renames=False
    ).get("CENTURYTEX") is None


# -- per-connection memo ------------------------------------------------------
def test_connection_memo_actually_caches(conn):
    """sqlite3.Connection has no __dict__, so attribute caching silently fails.

    The first attempt at this hung the value off the connection inside a
    try/except; the assignment always raised and every call rebuilt the table.
    """
    calls = []

    def build():
        calls.append(1)
        return {"value": len(calls)}

    first = conn_cache.cached(conn, "probe", build)
    second = conn_cache.cached(conn, "probe", build)
    assert first is second
    assert calls == [1]

    conn_cache.clear(conn, "probe")
    assert conn_cache.cached(conn, "probe", build) is not first
    assert calls == [1, 1]


def test_isin_lookups_are_rebuilt_after_new_bars_arrive(conn):
    """A nightly import can add a ticker, so a stale memo would hide it."""
    add_bar(conn, "OLD", date(2016, 3, 14), isin="INE222A01011")
    conn.commit()
    assert index_membership.isin_map(conn) == {"OLD": "INE222A01011"}

    bhavcopy.store_bars(conn, [(
        "NEW", "2024-03-14", "EQ", "INE222A01011",
        1.0, 1.0, 1.0, 1.0, 1.0, 1, 1.0, 1, "test",
    )])
    conn.commit()
    assert index_membership.symbols_by_isin(conn)["INE222A01011"] == {
        "OLD", "NEW"
    }
