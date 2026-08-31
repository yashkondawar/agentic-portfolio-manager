"""Offline tests for newsletters.py's period-extraction regexes. No network."""
from __future__ import annotations

from afund.data.newsletters import _period_from_aequitas_url, _period_from_dsp_filename


def test_dsp_period_hyphenated_full_month():
    url = "https://www.dspim.com/latest-literature/dspnetra-april-26.pdf"
    assert _period_from_dsp_filename(url) == "2026-04"


def test_dsp_period_hyphenated_abbreviation():
    url = "https://www.dspim.com/latest-literature/dspnetra-feb-26.pdf"
    assert _period_from_dsp_filename(url) == "2026-02"


def test_dsp_period_non_hyphenated_abbreviation():
    url = "https://www.dspim.com/latest-literature/dspnetra-mar26.pdf"
    assert _period_from_dsp_filename(url) == "2026-03"
    url2 = "https://www.dspim.com/latest-literature/dspnetra-may26.pdf"
    assert _period_from_dsp_filename(url2) == "2026-05"


def test_dsp_period_unrecognized_filename_returns_none():
    assert _period_from_dsp_filename("https://www.dspim.com/other-doc.pdf") is None


def test_aequitas_period_from_url_path():
    url = "https://www.aequitasindia.in/wp-content/uploads/2026/06/Aequitas-Newsletter_Top-Down-Bottom-Up_Jun26_with-Preview.pdf"
    assert _period_from_aequitas_url(url) == "2026-06"


def test_aequitas_period_variants():
    cases = {
        "https://www.aequitasindia.in/wp-content/uploads/2026/01/Aequitas-Newsletter_Top-Down-Bottom-Up_Jan26_Final.pdf": "2026-01",
        "https://www.aequitasindia.in/wp-content/uploads/2026/03/Aequitas-Newsletter_Top-Down-Bottom-Up_Mar26_Final-with-Preview.pdf": "2026-03",
    }
    for url, expected in cases.items():
        assert _period_from_aequitas_url(url) == expected


def test_aequitas_period_unrelated_pdf_still_parses_path_but_would_be_filtered_upstream():
    # The URL-path regex itself doesn't know about content — filtering out
    # non-newsletter PDFs (e.g. Grievance Redressal Policy) happens in
    # find_aequitas_pdfs() via the "top-down-bottom-up" substring check, not here.
    url = "https://www.aequitasindia.in/wp-content/uploads/2025/11/Grievance_Redressal_Policy_Final_1.pdf"
    assert _period_from_aequitas_url(url) == "2025-11"
