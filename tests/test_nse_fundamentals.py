"""Offline tests for the NSE historical fundamentals extractor.

Every fixture is a real filing downloaded from NSE, so these lock in the
quirks that were found empirically rather than a synthetic idea of the format.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from scraper import nse_fundamentals as nf

FIXTURES = Path(__file__).parent / "fixtures" / "nse"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _parse_xbrl_fixture(name: str, start: date, end: date):
    result = nf.QuarterlyResult(symbol="X", period_start=start, period_end=end)
    values = nf.parse_xbrl(_fixture(name), period_start=start, period_end=end)
    for key, value in values.items():
        setattr(result, key, value)
    return nf.derive_operating_profit(result)


def _parse_html_fixture(name: str):
    result = nf.QuarterlyResult(symbol="X")
    values = nf.parse_html(_fixture(name).decode("utf-8", "replace"))
    for key, value in values.items():
        setattr(result, key, value)
    return nf.derive_operating_profit(result)


# ── the OneD / FourD trap ───────────────────────────────────────────────────
def test_quarter_context_wins_over_year_to_date():
    """NSE declares FourD (year-to-date) with the *quarter's* dates.

    Coromandel's Q4 FY24 filing declares OneD and FourD with identical
    01-Jan-2024..31-Mar-2024 periods, but FourD holds the full-year figure.
    Date matching alone therefore cannot separate them, and picking FourD
    would report annual revenue as a quarter.
    """
    result = _parse_xbrl_fixture(
        "coromandel_q4fy24.xml", date(2024, 1, 1), date(2024, 3, 31)
    )
    assert result.sales == pytest.approx(3912.72, rel=1e-4)   # quarter
    assert result.sales < 5000                                # not FY24's 22058


def test_declared_contexts_are_ambiguous_by_date():
    """Guards the reason the id convention is preferred over date matching."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(_fixture("coromandel_q4fy24.xml"))
    contexts = nf._xbrl_duration_contexts(root)
    assert contexts["OneD"] == contexts["FourD"]


def test_cumulative_context_is_never_a_fallback():
    assert "FourD" in nf._CUMULATIVE_CONTEXTS
    assert nf._QUARTER_CONTEXT not in nf._CUMULATIVE_CONTEXTS


# ── EBITDA reconstruction ───────────────────────────────────────────────────
def test_operating_profit_adds_back_depreciation_and_finance_costs():
    """XBRL ``Expenses`` bundles depreciation and finance costs; screener's
    operating profit excludes both. Delhivery Q4 FY24: 2075.5 sales,
    2257.2 expenses, 200.4 depreciation, 27.1 finance costs -> ~45.8 EBITDA."""
    result = _parse_xbrl_fixture(
        "delhivery_q4fy24.xml", date(2024, 1, 1), date(2024, 3, 31)
    )
    assert result.sales == pytest.approx(2075.539, rel=1e-4)
    assert result.depreciation == pytest.approx(200.402, rel=1e-4)
    assert result.finance_costs == pytest.approx(27.145, rel=1e-4)
    assert result.operating_profit == pytest.approx(45.8, abs=1.0)
    assert result.opm == pytest.approx(2.2, abs=0.3)


def test_ebit_would_be_wrong():
    """Without the add-back the margin is negative, which is the bug this
    guards: EBIT margin is not what the strategy compares against."""
    result = _parse_xbrl_fixture(
        "delhivery_q4fy24.xml", date(2024, 1, 1), date(2024, 3, 31)
    )
    assert result.sales - result.expenses < 0
    assert result.operating_profit > 0


# ── HTML era ────────────────────────────────────────────────────────────────
def test_html_lakhs_are_converted_to_crores():
    """TCS Q3 FY14 filed 2129396 lakhs of revenue = 21293.96 crore."""
    result = _parse_html_fixture("tcs_q3fy14.html")
    assert result.sales == pytest.approx(21293.96, rel=1e-4)
    assert result.net_profit == pytest.approx(5333.43, rel=1e-4)
    assert result.eps == pytest.approx(27.20, rel=1e-3)


def test_bank_schedule_is_parsed_and_flagged():
    """Banks file a different schedule: no sales line, and their labels use
    ``Net Profit(+) / Loss(-)`` rather than ``Net Profit / (Loss)``."""
    result = _parse_html_fixture("hdfcbank_q3fy14.html")
    assert result.is_bank
    assert result.net_profit == pytest.approx(2325.70, rel=1e-4)
    assert result.sales == pytest.approx(12738.95, rel=1e-4)
    assert result.eps == pytest.approx(9.8, rel=1e-3)


def test_bank_operating_profit_is_taken_as_stated():
    """Interest expense is an operating cost for a bank, so the corporate
    add-back must not fire."""
    result = _parse_html_fixture("hdfcbank_q3fy14.html")
    assert result.operating_profit == pytest.approx(result.bank_operating_profit)
    assert result.operating_profit == pytest.approx(3887.97, rel=1e-4)


# ── label normalisation ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw",
    [
        "Net Profit(+) / Loss(-) for the Period",
        "Net Profit / (Loss) for the Period",
        "  net profit (+) / loss (-)  for the period ",
        "5. Net Profit(+) / Loss(-) for the Period",
    ],
)
def test_label_variants_collapse_to_one_key(raw):
    assert nf._normalise_label(raw) == "net profit / loss for the period"


def test_mangled_header_rows_are_dropped():
    from bs4 import BeautifulSoup

    html = "<table><tr><td>" + ("x" * 200) + "</td><td>123</td></tr></table>"
    assert nf._html_rows(BeautifulSoup(html, "html.parser")) == []


# ── numeric + date helpers ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234.5", 1234.5),
        ("(1,234)", -1234.0),
        ("-12", -12.0),
        ("", None),
        ("-", None),
        ("  ", None),
        ("abc", None),
    ],
)
def test_to_float(raw, expected):
    assert nf._to_float(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("01-Oct-2013", date(2013, 10, 1)),
        ("30-Mar-2024 12:46:07", date(2024, 3, 30)),
        ("2020-10-01", date(2020, 10, 1)),
        (None, None),
        ("nonsense", None),
    ],
)
def test_parse_nse_date(raw, expected):
    assert nf.parse_nse_date(raw) == expected


def test_quarter_label_matches_screener_column_format():
    result = nf.QuarterlyResult(symbol="X", period_end=date(2024, 3, 31))
    assert result.quarter_label == "Mar 2024"
    assert nf.QuarterlyResult(symbol="X").quarter_label is None


def test_opm_is_none_without_sales():
    result = nf.QuarterlyResult(symbol="X", operating_profit=10.0, sales=0.0)
    assert result.opm is None


# ── de-duplication ──────────────────────────────────────────────────────────
def test_select_best_prefers_consolidated():
    standalone = nf.QuarterlyResult(
        symbol="A", period_end=date(2024, 3, 31), consolidated=False,
        sales=1.0, net_profit=1.0, eps=1.0, operating_profit=1.0,
    )
    consolidated = nf.QuarterlyResult(
        symbol="A", period_end=date(2024, 3, 31), consolidated=True, sales=2.0,
    )
    best = nf.select_best([standalone, consolidated])
    assert best[("A", "Mar 2024")].sales == 2.0


def test_select_best_prefers_the_more_complete_record():
    sparse = nf.QuarterlyResult(
        symbol="A", period_end=date(2024, 3, 31), consolidated=True, sales=1.0,
    )
    full = nf.QuarterlyResult(
        symbol="A", period_end=date(2024, 3, 31), consolidated=True,
        sales=2.0, net_profit=1.0, eps=1.0, operating_profit=1.0,
    )
    best = nf.select_best([sparse, full])
    assert best[("A", "Mar 2024")].sales == 2.0


def test_select_best_skips_results_without_a_period():
    assert nf.select_best([nf.QuarterlyResult(symbol="A")]) == {}


# ── index row mapping ───────────────────────────────────────────────────────
def test_result_from_row_maps_metadata():
    row = {
        "symbol": "tcs",
        "isin": "INE467B01029",
        "companyName": "Tata Consultancy Services Limited",
        "fromDate": "01-Jan-2024",
        "toDate": "31-Mar-2024",
        "relatingTo": "Fourth Quarter",
        "consolidated": "Consolidated",
        "audited": "Audited",
        "broadCastDate": "12-Apr-2024 16:30:00",
    }
    result = nf.result_from_row(row)
    assert result.symbol == "TCS"
    assert result.consolidated is True
    assert result.period_end == date(2024, 3, 31)
    assert result.broadcast_at == datetime(2024, 4, 12, 16, 30, 0)
    assert result.quarter_label == "Mar 2024"


def test_result_from_row_rejects_a_missing_symbol():
    assert nf.result_from_row({"symbol": "  "}) is None
