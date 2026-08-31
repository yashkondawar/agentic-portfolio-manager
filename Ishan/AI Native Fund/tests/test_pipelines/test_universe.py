"""Offline parser test for universe.py's constituents CSV parser. No network."""
from __future__ import annotations

from pathlib import Path

from afund.data.universe import parse_constituents_csv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_constituents_csv():
    raw = (FIXTURES / "nifty_total_market_sample.csv").read_text(encoding="utf-8")
    rows = parse_constituents_csv(raw)

    assert len(rows) == 15
    first = rows[0]
    assert first["symbol"] == "360ONE"
    assert first["name"] == "360 ONE WAM Ltd."
    assert first["sector"] == "Financial Services"
    assert first["isin"] == "INE466L01038"

    symbols = {r["symbol"] for r in rows}
    assert "ABB" in symbols
    assert "AARTIPHARM" in symbols


def test_parse_constituents_csv_skips_blank_symbol_rows():
    raw = "Company Name,Industry,Symbol,Series,ISIN Code\nSome Co,Sector,,EQ,INE000000000\n"
    rows = parse_constituents_csv(raw)
    assert rows == []
