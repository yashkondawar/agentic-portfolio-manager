"""Offline parser test for amfi_nav.py's NAVAll.txt parser. No network."""
from __future__ import annotations

from pathlib import Path

from afund.data.amfi_nav import _parse_date, parse_navall

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_navall_skips_headers_blanks_and_category_lines():
    raw = (FIXTURES / "navall_sample.txt").read_text(encoding="utf-8")
    rows = parse_navall(raw)

    assert len(rows) > 0
    for row in rows:
        assert row["scheme_code"].isdigit()
        assert isinstance(row["nav"], float)
        # Most rows are dated the latest NAV date, but thinly-traded schemes
        # (e.g. old bonus-option plans) can carry a stale last-NAV date —
        # just assert every date parses to a valid ISO-8601 string.
        assert len(row["date"]) == 10 and row["date"][4] == "-" and row["date"][7] == "-"

    dates = {row["date"] for row in rows}
    assert "2026-07-02" in dates


def test_parse_navall_first_row_values():
    raw = (FIXTURES / "navall_sample.txt").read_text(encoding="utf-8")
    rows = parse_navall(raw)
    first = rows[0]
    assert first["scheme_code"] == "119551"
    assert first["isin_growth"] == "INF209KA12Z1"
    assert first["isin_div"] == "INF209KA13Z9"
    assert first["nav"] == 106.7721
    assert "Aditya Birla" in first["scheme_name"]


def test_parse_navall_dash_isin_becomes_none():
    raw = (FIXTURES / "navall_sample.txt").read_text(encoding="utf-8")
    rows = parse_navall(raw)
    row = next(r for r in rows if r["scheme_code"] == "119552")
    assert row["isin_div"] is None


def test_parse_date_valid():
    assert _parse_date("02-Jul-2026") == "2026-07-02"


def test_parse_date_invalid_returns_none():
    assert _parse_date("not-a-date") is None
    assert _parse_date("") is None
