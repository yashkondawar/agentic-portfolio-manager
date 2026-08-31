"""Offline tests for afund.data.macro_bis.parse_bis_credit_gap_csv — a CSV
fragment replicating the REAL bulk-file shape, including the live-confirmed
column quirk: the data rows leave the TIME_FORMAT/Time Format/TITLE_TS cells
(cols 10-12) empty and put the Q:IN:P:A:C key in col 13 ("Series"), which is
exactly why the parser matches on BORROWERS_CTY + CG_DTYPE instead of the
TITLE_TS header position. No network."""
from __future__ import annotations

from afund.data.macro_bis import parse_bis_credit_gap_csv

HEADER = (
    "FREQ,Frequency,BORROWERS_CTY,Borrowers' country,TC_BORROWERS,Borrowing sector,"
    "TC_LENDERS,Lending sector,CG_DTYPE,Credit gap data type,TIME_FORMAT,Time Format,"
    "TITLE_TS,Series,1961-Q2,1961-Q3,2025-Q3,2025-Q4"
)

# Note cols 10-12 empty, key in col 13 — the live file's actual layout.
INDIA_RATIO_ROW = (
    'Q,Quarterly,IN,India,P,Private non-financial sector,A,All sectors,'
    'A,Credit-to-GDP ratios (actual data),,,,Q:IN:P:A:A,25.2,26.1,101.5,102.3'
)
INDIA_TREND_ROW = (
    'Q,Quarterly,IN,India,P,Private non-financial sector,A,All sectors,'
    'B,Credit-to-GDP trend (HP filter),,,,Q:IN:P:A:B,27.0,27.4,99.9,100.6'
)
INDIA_GAP_ROW = (
    'Q,Quarterly,IN,India,P,Private non-financial sector,A,All sectors,'
    'C,Credit-to-GDP gaps (actual-trend),,,,Q:IN:P:A:C,-1.4614,-2.1019,,1.7416'
)
US_GAP_ROW = (
    'Q,Quarterly,US,United States,P,Private non-financial sector,A,All sectors,'
    'C,Credit-to-GDP gaps (actual-trend),,,,Q:US:P:A:C,3.1,3.2,-4.5,-4.2'
)


def _csv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def test_extracts_only_the_india_gap_row():
    text = _csv(INDIA_RATIO_ROW, INDIA_TREND_ROW, INDIA_GAP_ROW, US_GAP_ROW)
    rows = parse_bis_credit_gap_csv(text)
    # Only the CG_DTYPE=C India row; blank 2025-Q3 cell skipped, never
    # zero-filled. Quarter labels become first-day-of-quarter dates.
    assert rows == [
        ("1961-04-01", -1.4614),
        ("1961-07-01", -2.1019),
        ("2025-10-01", 1.7416),
    ]


def test_ratio_and_trend_rows_are_not_mistaken_for_the_gap():
    text = _csv(INDIA_RATIO_ROW, INDIA_TREND_ROW)
    assert parse_bis_credit_gap_csv(text) == []


def test_non_india_gap_row_is_skipped():
    text = _csv(US_GAP_ROW)
    assert parse_bis_credit_gap_csv(text) == []


def test_empty_and_headerless_inputs():
    assert parse_bis_credit_gap_csv("") == []
    assert parse_bis_credit_gap_csv("A,B,C\n1,2,3\n") == []
