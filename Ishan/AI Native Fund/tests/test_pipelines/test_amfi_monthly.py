"""Offline tests for afund.data.amfi_monthly — listing-page PDF-link
discovery and the monthly-report table parser, against the captured real
page-0 text of the May-2026 report (tests/fixtures/
amfi_monthly_page0_sample.txt). No network, no PDF library needed (the
fixture is the already-extracted text)."""
from __future__ import annotations

from pathlib import Path

import pytest

from afund.data.amfi_monthly import find_latest_pdf_url, parse_amfi_monthly_text

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "amfi_monthly_page0_sample.txt"

LISTING_HTML = """
<html><body>
<a href="https://portal.amfiindia.com/spages/ammay2026repo.pdf">May 2026</a>
<a href="https://portal.amfiindia.com/spages/amapr2026repo.pdf">April 2026</a>
<a href="https://portal.amfiindia.com/spages/amdec2025repo.pdf">December 2025</a>
<a href="https://example.com/not-a-repo.pdf">decoy</a>
</body></html>
"""


def test_find_latest_pdf_url_picks_newest():
    found = find_latest_pdf_url(LISTING_HTML)
    assert found is not None
    url, period = found
    assert url == "https://portal.amfiindia.com/spages/ammay2026repo.pdf"
    assert period == "2026-05"


def test_find_latest_pdf_url_survives_reordered_page():
    # Defensive: newest link NOT first in page order — max((year, month))
    # must still win.
    reordered = LISTING_HTML.replace("ammay2026", "TMP").replace("amdec2025", "ammay2026").replace("TMP", "amdec2025")
    found = find_latest_pdf_url(reordered)
    assert found is not None
    assert found[1] == "2026-05"


def test_find_latest_pdf_url_none_when_no_links():
    assert find_latest_pdf_url("<html><body>nothing here</body></html>") is None


def test_parse_real_may_2026_page0_text():
    text = FIXTURE.read_text(encoding="utf-8")
    parsed = parse_amfi_monthly_text(text)
    # Values cross-checked against AMFI's published May-2026 figures.
    assert parsed["MF_EQUITY_NET_INFLOW"] == pytest.approx(22907.77)
    assert parsed["MF_TOTAL_AUM"] == pytest.approx(8158341.65)
    assert set(parsed) == {"MF_EQUITY_NET_INFLOW", "MF_TOTAL_AUM"}


def test_sub_total_iii_is_not_mistaken_for_ii():
    # Regression guard for the string-prefix bug: "Sub Total - II" is a
    # literal prefix of "Sub Total - III", so a naive startswith() match
    # would grab the Hybrid-schemes row.
    text = (
        "Sub Total - III (i+ii) 182 1,95,18,382 40,313.86 29,753.63 10,560.24 11,15,645.34 11,98,256.72\n"
    )
    assert "MF_EQUITY_NET_INFLOW" not in parse_amfi_monthly_text(text)


def test_integer_columns_are_counted():
    # Regression guard for the number-regex bug: the leading scheme-count
    # (569) and folio-count (18,49,15,510) columns are integers with no
    # decimal part — if the regex required a decimal point they'd be
    # silently dropped and every downstream index would shift.
    line = (
        "Sub Total - II (i+ii) 569 18,49,15,510 57,603.83 34,696.05 22,907.77 "
        "36,13,718.41 36,12,941.46\n"
    )
    parsed = parse_amfi_monthly_text(line)
    assert parsed["MF_EQUITY_NET_INFLOW"] == pytest.approx(22907.77)


def test_partial_extraction_returns_only_what_it_finds():
    assert parse_amfi_monthly_text("no table rows here at all") == {}
    grand_only = "Grand Total 1,946 27,65,67,797 12,02,732.09 12,66,753.26 -64,021.17 81,58,341.65 83,46,578.72\n"
    parsed = parse_amfi_monthly_text(grand_only)
    assert set(parsed) == {"MF_TOTAL_AUM"}
    assert parsed["MF_TOTAL_AUM"] == pytest.approx(8158341.65)
