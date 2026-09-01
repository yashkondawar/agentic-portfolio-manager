"""Tests for the durable NSE filing store and the backtest adapter over it."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backtesting.qtr_results import nse_source
from scraper import fundamentals_store
from scraper.nse_fundamentals import QuarterlyResult


@pytest.fixture()
def conn(tmp_path):
    connection = fundamentals_store.open_store(tmp_path / "test.sqlite3")
    yield connection
    connection.close()


def make(
    symbol="ACME",
    period_end=date(2024, 3, 31),
    *,
    consolidated=True,
    sales=100.0,
    net_profit=10.0,
    eps=5.0,
    **kw,
):
    return QuarterlyResult(
        symbol=symbol,
        period_start=date(period_end.year, period_end.month - 2, 1),
        period_end=period_end,
        consolidated=consolidated,
        sales=sales,
        net_profit=net_profit,
        eps=eps,
        url=kw.pop("url", f"http://x/{symbol}-{period_end}-{consolidated}.xml"),
        source=kw.pop("source", "xbrl"),
        **kw,
    )


# ── store ────────────────────────────────────────────────────────────────────

def test_store_round_trips_a_filing(conn):
    stored = fundamentals_store.store_results(conn, [make(broadcast_at=datetime(2024, 4, 20, 18, 5))])
    assert stored == 1

    (row,) = fundamentals_store.load_results(conn)
    assert row.symbol == "ACME"
    assert row.period_end == date(2024, 3, 31)
    assert row.consolidated is True
    assert row.sales == 100.0
    assert row.net_profit == 10.0
    assert row.broadcast_at == datetime(2024, 4, 20, 18, 5)


def test_restoring_the_same_quarter_updates_rather_than_duplicates(conn):
    fundamentals_store.store_results(conn, [make(net_profit=10.0)])
    fundamentals_store.store_results(conn, [make(net_profit=12.0)])

    rows = fundamentals_store.load_results(conn)
    assert len(rows) == 1, "the (symbol, quarter, basis) key must be unique"
    assert rows[0].net_profit == 12.0


def test_standalone_and_consolidated_are_kept_apart(conn):
    fundamentals_store.store_results(conn, [
        make(consolidated=True, net_profit=12.0),
        make(consolidated=False, net_profit=9.0),
    ])
    assert len(fundamentals_store.load_results(conn)) == 2


def test_load_results_can_filter_to_a_universe(conn):
    fundamentals_store.store_results(conn, [make(symbol="ACME"), make(symbol="OTHER")])
    rows = fundamentals_store.load_results(conn, symbols=["acme"])
    assert [r.symbol for r in rows] == ["ACME"]


def test_attempt_ledger_lets_a_resumed_run_skip_permanent_failures(conn):
    fundamentals_store.record_attempt(conn, "http://x/a.xml", "ACME", ok=True)
    fundamentals_store.record_attempt(conn, "http://x/b.htm", "ACME", ok=False)
    assert fundamentals_store.attempted_urls(conn) == {"http://x/a.xml", "http://x/b.htm"}


def test_completed_windows_make_a_rerun_a_no_op(conn):
    assert fundamentals_store.completed_windows(conn) == set()
    fundamentals_store.mark_window(conn, date(2024, 1, 1), date(2024, 3, 31), 300, 260)
    assert ("2024-01-01", "2024-03-31") in fundamentals_store.completed_windows(conn)


def test_coverage_summarises_progress(conn):
    fundamentals_store.store_results(conn, [
        make(period_end=date(2023, 3, 31), broadcast_at=datetime(2023, 4, 20)),
        make(period_end=date(2024, 3, 31)),
    ])
    stats = fundamentals_store.coverage(conn)
    assert stats["rows"] == 2
    assert stats["symbols"] == 1
    assert stats["first_quarter"] == "2023-03-31"
    assert stats["last_quarter"] == "2024-03-31"
    assert stats["dated"] == 1


def test_opening_the_store_twice_is_safe(tmp_path):
    path = tmp_path / "twice.sqlite3"
    first = fundamentals_store.open_store(path)
    first.close()
    second = fundamentals_store.open_store(path)
    second.close()


def test_store_survives_a_row_with_almost_nothing_in_it(conn):
    bare = QuarterlyResult(symbol="THIN", period_end=date(2024, 3, 31))
    assert fundamentals_store.store_results(conn, [bare]) == 1
    assert fundamentals_store.load_results(conn)[0].sales is None


# ── EPS rebasing ─────────────────────────────────────────────────────────────

def test_implied_share_count_comes_from_the_filing_itself():
    row = make(net_profit=100.0, eps=10.0)
    assert nse_source._implied_shares(row) == pytest.approx(10.0)


def test_a_near_zero_eps_is_not_trusted_as_a_share_count():
    assert nse_source._implied_shares(make(net_profit=100.0, eps=0.01)) is None


def test_absurd_share_counts_are_rejected():
    assert nse_source._implied_shares(make(net_profit=1e9, eps=1.0)) is None


def test_reference_share_count_ignores_one_off_oddities():
    rows = [make(net_profit=100.0, eps=10.0) for _ in range(6)]
    rows.append(make(net_profit=1.0, eps=5.0))  # exceptional-item quarter
    assert nse_source.reference_share_count(rows) == pytest.approx(10.0)


def test_a_split_no_longer_reads_as_an_earnings_collapse():
    """A 1:10 split halves nothing, but as-filed EPS drops 90%."""
    rows = [
        make(period_end=date(2023, 3, 31), net_profit=100.0, eps=100.0),   # 1cr shares
        make(period_end=date(2024, 3, 31), net_profit=110.0, eps=11.0),    # 10cr shares
    ]
    shares = nse_source.reference_share_count(rows)
    section = nse_source.build_quarterly_section(rows, shares=shares)
    eps = next(r for r in section if r[""] == "EPS in Rs")

    grew = (eps["Mar 2024"] - eps["Mar 2023"]) / eps["Mar 2023"] * 100
    assert grew == pytest.approx(10.0, abs=0.01), "EPS growth must track profit growth"


def test_eps_falls_back_to_as_filed_when_no_share_count_can_be_derived():
    rows = [make(net_profit=None, eps=7.5, period_end=date(2024, 3, 31))]
    section = nse_source.build_quarterly_section(rows, shares=None)
    eps = next(r for r in section if r[""] == "EPS in Rs")
    assert eps["Mar 2024"] == 7.5


# ── screener-shaped output ───────────────────────────────────────────────────

def test_section_uses_the_row_labels_the_engine_looks_for():
    rows = [make(period_end=date(2024, 3, 31), operating_profit=20.0)]
    labels = {r[""] for r in nse_source.build_quarterly_section(rows, shares=2.0)}
    assert {"Sales+", "Operating Profit", "OPM %", "Net Profit+", "EPS in Rs"} <= labels


def test_a_bank_gets_the_financing_schedule_so_the_debt_filter_is_skipped():
    rows = [
        make(
            period_end=date(2024, 3, 31),
            sales=1000.0,
            bank_operating_profit=300.0,
            source="xbrl",
        )
    ]
    rows[0].bank_operating_profit = 300.0
    labels = {r[""] for r in nse_source.build_quarterly_section(rows, shares=2.0)}
    assert "Financing Profit" in labels
    assert "Sales+" not in labels


def test_operating_margin_is_a_percentage_of_the_top_line():
    rows = [make(period_end=date(2024, 3, 31), sales=1000.0, operating_profit=175.0)]
    section = nse_source.build_quarterly_section(rows, shares=2.0)
    opm = next(r for r in section if r[""] == "OPM %")
    assert opm["Mar 2024"] == pytest.approx(17.5)


def test_margin_is_blank_rather_than_wrong_when_the_top_line_is_missing():
    rows = [make(period_end=date(2024, 3, 31), sales=None, operating_profit=175.0)]
    section = nse_source.build_quarterly_section(rows, shares=2.0)
    opm = next(r for r in section if r[""] == "OPM %")
    assert opm["Mar 2024"] is None


def test_consolidated_wins_when_both_bases_were_filed():
    rows = [
        make(consolidated=False, net_profit=9.0),
        make(consolidated=True, net_profit=12.0),
    ]
    picked = nse_source._dedupe(rows)
    assert len(picked) == 1
    assert picked[0].net_profit == 12.0


def test_quarters_come_back_in_chronological_order():
    rows = [
        make(period_end=date(2024, 3, 31)),
        make(period_end=date(2023, 6, 30)),
        make(period_end=date(2023, 12, 31)),
    ]
    ends = [r.period_end for r in nse_source._dedupe(rows)]
    assert ends == sorted(ends)


def test_quarter_labels_match_screener_column_headings():
    assert nse_source._label(date(2024, 3, 31)) == "Mar 2024"
    assert nse_source._label(date(2023, 12, 31)) == "Dec 2023"


# ── build() ──────────────────────────────────────────────────────────────────

def _seed(conn, symbol="ACME", quarters=10):
    rows = []
    for i in range(quarters):
        year = 2022 + i // 4
        month = (3, 6, 9, 12)[i % 4]
        end = date(year, month, 30 if month in (6, 9) else 31)
        rows.append(
            make(
                symbol=symbol,
                period_end=end,
                net_profit=10.0 + i,
                eps=5.0 + i / 2,
                operating_profit=20.0,
                broadcast_at=datetime(year, month, 28, 17, 0),
                url=f"http://x/{symbol}-{i}.xml",
            )
        )
    fundamentals_store.store_results(conn, rows)


def test_build_renders_a_symbol_the_engine_can_read(conn):
    _seed(conn)
    raw, calendar = nse_source.build(["ACME"], connection=conn)
    assert "ACME" in raw
    assert raw["ACME"]["source"] == "nse"
    assert raw["ACME"]["quarterly_results"]
    assert calendar["ACME"][date(2024, 3, 31)] == date(2024, 3, 28)


def test_build_drops_symbols_without_enough_history_to_grade(conn):
    _seed(conn, symbol="THIN", quarters=3)
    raw, _ = nse_source.build(["THIN"], min_quarters=8, connection=conn)
    assert raw == {}


def test_build_borrows_the_annual_sections_it_cannot_file(conn):
    _seed(conn)
    screener = {"ACME": {"balance_sheet": [{"": "Borrowings+", "Mar 2023": "100"}]}}
    raw, _ = nse_source.build(["ACME"], screener_raw=screener, connection=conn)
    assert raw["ACME"]["balance_sheet"][0][""] == "Borrowings+"


def test_build_still_works_when_screener_has_never_seen_the_symbol(conn):
    _seed(conn)
    raw, _ = nse_source.build(["ACME"], screener_raw={}, connection=conn)
    assert raw["ACME"]["balance_sheet"] == []


def test_the_engine_can_parse_what_build_produces(conn):
    """End-to-end shape check against the real analysis indexer."""
    from backtesting.qtr_results.analysis import parse_quarters

    _seed(conn)
    raw, _ = nse_source.build(["ACME"], connection=conn)
    quarters, metrics = parse_quarters(raw["ACME"])
    assert len(quarters) == 10
    assert metrics["net_profit"][quarters[-1]] == pytest.approx(19.0)
    assert metrics["sales"][quarters[-1]] == pytest.approx(100.0)


def test_a_missing_database_is_reported_clearly(tmp_path):
    conn = fundamentals_store.open_store(tmp_path / "empty.sqlite3")
    try:
        assert fundamentals_store.load_results(conn) == []
        assert fundamentals_store.coverage(conn)["rows"] == 0
    finally:
        conn.close()


def test_a_filing_with_no_quarter_is_dropped_rather_than_stored(conn):
    """A filing we cannot date is unusable point-in-time, so it never lands."""
    assert fundamentals_store.store_results(conn, [QuarterlyResult(symbol="X")]) == 0
    assert fundamentals_store.load_results(conn) == []
