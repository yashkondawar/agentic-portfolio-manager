"""Tests for the screener -> shared fundamentals store import.

The point of this module is that two sources land in one table with one shape,
so the tests concentrate on the seam: label normalisation, quarter parsing, and
above all the source ranking that stops restated figures overwriting as-filed
ones regardless of import order.
"""
from datetime import date, datetime

import pytest

from scraper import fundamentals_store as store
from scraper import screener_fundamentals as sf
from scraper.nse_fundamentals import QuarterlyResult


@pytest.fixture()
def conn(tmp_path):
    connection = store.open_store(tmp_path / "test.sqlite3")
    yield connection
    connection.close()


def payload(**columns):
    """Build a screener-shaped quarterly_results table."""
    return {
        "company_name": "Acme Ltd",
        "source": "https://screener.in/company/ACME/",
        "quarterly_results": [
            {"": "Sales+", **columns.get("sales", {})},
            {"": "Expenses+", **columns.get("expenses", {})},
            {"": "Operating Profit", **columns.get("op", {})},
            {"": "OPM %", **columns.get("opm", {})},
            {"": "Other Income+", **columns.get("oi", {})},
            {"": "Interest", **columns.get("interest", {})},
            {"": "Depreciation", **columns.get("dep", {})},
            {"": "Profit before tax", **columns.get("pbt", {})},
            {"": "Net Profit+", **columns.get("np", {})},
            {"": "EPS in Rs", **columns.get("eps", {})},
        ],
    }


# --------------------------------------------------------------- parsing ----

@pytest.mark.parametrize(
    "label, expected",
    [
        ("Mar 2025", date(2025, 3, 31)),
        ("Jun 2026", date(2026, 6, 30)),
        ("Dec 2011", date(2011, 12, 31)),
        ("Feb 2024", date(2024, 2, 29)),
        ("", None),
        ("Notaquarter", None),
        ("Xyz 2024", None),
    ],
)
def test_parse_quarter(label, expected):
    assert sf._parse_quarter(label) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("60,583", 60583.0),
        ("-96", -96.0),
        ("25%", 25.0),
        ("", None),
        ("-", None),
        (None, None),
        (1234, 1234.0),
    ],
)
def test_parse_number(raw, expected):
    assert sf._parse_number(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Sales+", "sales"),
        ("Net Profit+", "net profit"),
        ("EPS in Rs", "eps in rs"),
        ("OPM %", "opm"),
        ("Profit before tax", "profit before tax"),
    ],
)
def test_clean_label(raw, expected):
    assert sf._clean_label(raw) == expected


def test_profit_before_tax_does_not_claim_the_net_profit_slot():
    """The bug that made 'net profit growth' mean pre-tax growth must not recur.

    Screener orders PBT above Net Profit, so a loose label match plus
    first-wins indexing silently swaps the two.
    """
    rows = sf.rows_for_symbol(
        "ACME",
        payload(
            np={"Mar 2025": "100"},
            pbt={"Mar 2025": "150"},
        ),
    )
    (row,) = rows
    assert row.net_profit == 100.0
    assert row.profit_before_tax == 150.0


# ------------------------------------------------------------ conversion ----

def test_rows_for_symbol_maps_fields_and_quarter():
    rows = sf.rows_for_symbol(
        "ACME",
        payload(
            sales={"Mar 2025": "1,000", "Jun 2025": "1,100"},
            np={"Mar 2025": "100", "Jun 2025": "120"},
            eps={"Mar 2025": "10", "Jun 2025": "12"},
        ),
    )
    assert [r.period_end for r in rows] == [date(2025, 3, 31), date(2025, 6, 30)]
    assert rows[0].sales == 1000.0
    assert rows[0].net_profit == 100.0
    assert rows[0].eps == 10.0
    assert rows[0].source == "screener"
    assert rows[0].consolidated is True
    assert rows[0].company == "Acme Ltd"


def test_rows_carry_declaration_date_when_known():
    rows = sf.rows_for_symbol(
        "ACME",
        payload(np={"Mar 2025": "100"}),
        declaration_dates={date(2025, 3, 31): date(2025, 4, 18)},
    )
    assert rows[0].broadcast_at == datetime(2025, 4, 18)


def test_rows_without_a_declaration_date_are_left_undated():
    rows = sf.rows_for_symbol("ACME", payload(np={"Mar 2025": "100"}))
    assert rows[0].broadcast_at is None


def test_since_filters_old_quarters():
    rows = sf.rows_for_symbol(
        "ACME",
        payload(np={"Mar 2020": "10", "Mar 2025": "100"}),
        since=date(2024, 1, 1),
    )
    assert [r.period_end for r in rows] == [date(2025, 3, 31)]


def test_bank_schedule_is_recognised():
    bank = {
        "company_name": "Acme Bank",
        "quarterly_results": [
            {"": "Revenue", "Mar 2025": "500"},
            {"": "Interest", "Mar 2025": "200"},
            {"": "Financing Profit", "Mar 2025": "150"},
            {"": "Net Profit+", "Mar 2025": "90"},
        ],
    }
    (row,) = sf.rows_for_symbol("ACMEBANK", bank)
    assert row.sales == 500.0
    assert row.bank_operating_profit == 150.0
    assert row.is_bank is True


def test_empty_or_malformed_payloads_yield_nothing():
    assert sf.rows_for_symbol("ACME", {}) == []
    assert sf.rows_for_symbol("ACME", {"quarterly_results": None}) == []
    assert sf.rows_for_symbol("ACME", {"quarterly_results": ["junk"]}) == []


# -------------------------------------------------------- source ranking ----

def as_filed(**kw):
    base = dict(
        symbol="ACME",
        period_end=date(2024, 12, 31),
        consolidated=True,
        net_profit=100.0,
        source="xbrl",
    )
    base.update(kw)
    return QuarterlyResult(**base)


def screener_row(**kw):
    return as_filed(source="screener", **kw)


def test_screener_cannot_overwrite_as_filed(conn):
    store.store_results(conn, [as_filed(net_profit=100.0)])
    store.store_results(conn, [screener_row(net_profit=999.0)])

    (row,) = store.load_results(conn)
    assert row.net_profit == 100.0, "restated figures must not clobber as-filed"
    assert row.source == "xbrl"


def test_as_filed_overwrites_screener_regardless_of_order(conn):
    """Import order must not matter — that is the whole point of the ranking."""
    store.store_results(conn, [screener_row(net_profit=999.0)])
    store.store_results(conn, [as_filed(net_profit=100.0)])

    (row,) = store.load_results(conn)
    assert row.net_profit == 100.0
    assert row.source == "xbrl"


def test_as_filed_still_updates_as_filed(conn):
    store.store_results(conn, [as_filed(net_profit=100.0)])
    store.store_results(conn, [as_filed(net_profit=110.0, source="html")])
    (row,) = store.load_results(conn)
    assert row.net_profit == 110.0


def test_screener_updates_screener(conn):
    store.store_results(conn, [screener_row(net_profit=10.0)])
    store.store_results(conn, [screener_row(net_profit=20.0)])
    (row,) = store.load_results(conn)
    assert row.net_profit == 20.0


def test_screener_extends_history_where_as_filed_is_absent(conn):
    store.store_results(conn, [as_filed(period_end=date(2024, 12, 31))])
    store.store_results(
        conn, [screener_row(period_end=date(2025, 3, 31), net_profit=120.0)]
    )
    rows = store.load_results(conn)
    assert [r.period_end for r in rows] == [date(2024, 12, 31), date(2025, 3, 31)]
    assert [r.source for r in rows] == ["xbrl", "screener"]


def test_load_results_can_filter_to_as_filed_only(conn):
    store.store_results(conn, [as_filed()])
    store.store_results(
        conn, [screener_row(period_end=date(2025, 3, 31))]
    )
    rows = store.load_results(conn, sources=["xbrl", "html"])
    assert [r.source for r in rows] == ["xbrl"]


def test_coverage_reports_the_source_mix(conn):
    store.store_results(conn, [as_filed()])
    store.store_results(conn, [screener_row(period_end=date(2025, 3, 31))])
    assert store.coverage(conn)["by_source"] == {"xbrl": 1, "screener": 1}


def test_import_screener_writes_through_the_store(conn):
    written = sf.import_screener(
        conn,
        {"ACME": payload(np={"Mar 2025": "100"}, sales={"Mar 2025": "1,000"})},
        declaration_dates={"ACME": {date(2025, 3, 31): date(2025, 4, 18)}},
    )
    assert written == 1
    (row,) = store.load_results(conn)
    assert row.symbol == "ACME"
    assert row.net_profit == 100.0
    assert row.broadcast_at == datetime(2025, 4, 18)


def test_import_screener_respects_the_symbol_filter(conn):
    sf.import_screener(
        conn,
        {
            "ACME": payload(np={"Mar 2025": "100"}),
            "OTHER": payload(np={"Mar 2025": "200"}),
        },
        symbols=["acme"],
    )
    assert [r.symbol for r in store.load_results(conn)] == ["ACME"]


def test_import_screener_on_an_empty_snapshot_is_a_no_op(conn):
    assert sf.import_screener(conn, {}) == 0
    assert store.load_results(conn) == []


# ------------------------------------------------------------- migration ----

def test_legacy_nse_table_is_adopted(tmp_path):
    """The original backfill lived in nse_quarterly_results and must survive."""
    from core.storage import connect

    path = tmp_path / "legacy.sqlite3"
    raw = connect(path)
    raw.executescript(
        """
        CREATE TABLE nse_quarterly_results (
            symbol TEXT NOT NULL, period_end TEXT NOT NULL,
            consolidated INTEGER NOT NULL, isin TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '', period_start TEXT,
            quarter_label TEXT, relating_to TEXT NOT NULL DEFAULT '',
            audited TEXT NOT NULL DEFAULT '', broadcast_at TEXT,
            sales REAL, other_income REAL, expenses REAL, depreciation REAL,
            finance_costs REAL, operating_profit REAL,
            bank_operating_profit REAL, profit_before_tax REAL,
            tax_expense REAL, net_profit REAL, eps REAL,
            source TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (symbol, period_end, consolidated)
        );
        INSERT INTO nse_quarterly_results
            (symbol, period_end, consolidated, net_profit, source, fetched_at)
        VALUES ('LEGACY', '2020-03-31', 1, 42.0, 'xbrl', '2024-01-01');
        """
    )
    raw.commit()
    raw.close()

    conn = store.open_store(path)
    try:
        (row,) = store.load_results(conn)
        assert row.symbol == "LEGACY"
        assert row.net_profit == 42.0
        # And the migration is idempotent.
        store.open_store(path).close()
        assert len(store.load_results(conn)) == 1
    finally:
        conn.close()
