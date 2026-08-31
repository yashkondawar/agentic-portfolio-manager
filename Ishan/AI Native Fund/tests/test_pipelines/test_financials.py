"""Offline parser tests for financials.py's screener.in HTML parsing. No network."""
from __future__ import annotations

from pathlib import Path

from afund.data.financials import (
    _snake_case,
    _to_number,
    parse_statement_section,
    parse_top_ratios,
    quarterly_rows_to_financials,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _html():
    return (FIXTURES / "screener_infy_snippet.html").read_text(encoding="utf-8")


def test_parse_top_ratios():
    ratios = parse_top_ratios(_html())
    assert ratios["stock_p_e"] > 0
    assert ratios["roe"] > 0
    assert ratios["roce"] > 0
    assert ratios["face_value"] == 5.0
    # "High / Low" splits into two distinct keys
    assert "52w_high" in ratios
    assert "52w_low" in ratios
    assert ratios["52w_high"] > ratios["52w_low"]


def test_parse_statement_section_quarters():
    quarters = parse_statement_section(_html(), "quarters")
    assert quarters is not None
    assert len(quarters["periods"]) == 13
    assert quarters["periods"][-1] == "2026-03-31"
    assert "Sales" in quarters["rows"]
    assert "Net Profit" in quarters["rows"]
    assert "EPS in Rs" in quarters["rows"]


def test_parse_statement_section_missing_section_returns_none():
    assert parse_statement_section(_html(), "does-not-exist") is None


def test_quarterly_rows_to_financials_maps_labels():
    quarters = parse_statement_section(_html(), "quarters")
    records = quarterly_rows_to_financials(quarters)

    assert len(records) == 13
    last = records[-1]
    assert last["period_end"] == "2026-03-31"
    assert last["revenue"] == 46402.0
    assert last["operating_profit"] == 11167.0
    assert last["net_profit"] == 8509.0
    assert last["eps"] == 20.96
    assert last["ebitda"] is None
    assert "Sales" in last["raw_json"]


def test_snake_case():
    assert _snake_case("Stock P/E") == "stock_p_e"
    assert _snake_case("ROCE") == "roce"
    assert _snake_case("  Dividend Yield  ") == "dividend_yield"


def test_to_number():
    assert _to_number("1,234.5") == 1234.5
    assert _to_number("24%") == 24.0
    assert _to_number("-") is None
    assert _to_number("") is None
