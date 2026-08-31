"""Offline tests for afund.data.india_vix.parse_nse_vix_rows — the `nse`
library's fetch_historical_vix_data() row shape (EOD_TIMESTAMP in
DD-MON-YYYY uppercase, EOD_CLOSE_INDEX_VAL float). No network."""
from __future__ import annotations

from afund.data.india_vix import parse_nse_vix_rows


def test_parses_and_sorts_real_shape_rows():
    rows = [
        {"EOD_TIMESTAMP": "03-JUL-2026", "EOD_CLOSE_INDEX_VAL": 12.35, "EOD_OPEN_INDEX_VAL": 12.1},
        {"EOD_TIMESTAMP": "01-JUL-2026", "EOD_CLOSE_INDEX_VAL": 11.9},
        {"EOD_TIMESTAMP": "02-JUL-2026", "EOD_CLOSE_INDEX_VAL": "12.05"},  # string close tolerated
    ]
    parsed = parse_nse_vix_rows(rows)
    assert parsed == [
        ("2026-07-01", 11.9),
        ("2026-07-02", 12.05),
        ("2026-07-03", 12.35),
    ]


def test_skips_rows_missing_fields_or_unparseable():
    rows = [
        {"EOD_TIMESTAMP": "03-JUL-2026"},                       # no close
        {"EOD_CLOSE_INDEX_VAL": 12.0},                          # no date
        {"EOD_TIMESTAMP": "not-a-date", "EOD_CLOSE_INDEX_VAL": 12.0},
        {"EOD_TIMESTAMP": "04-JUL-2026", "EOD_CLOSE_INDEX_VAL": "n/a"},
        {"EOD_TIMESTAMP": "05-JUL-2026", "EOD_CLOSE_INDEX_VAL": 13.1},
    ]
    assert parse_nse_vix_rows(rows) == [("2026-07-05", 13.1)]


def test_empty_input():
    assert parse_nse_vix_rows([]) == []
