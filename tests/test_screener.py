"""Screener transport and page validation, without network access."""

import logging
from unittest.mock import Mock

import pytest
import requests

from scraper import screener
from qtr_results import analysis


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    monkeypatch.setattr(
        screener._session, "get", lambda *a, **kw: pytest.fail("Unexpected live request")
    )
    monkeypatch.setattr(analysis, "sector_for", lambda symbol: "Industrials")


def response(body, *, encoding=None, standalone=False):
    result = requests.Response()
    result.status_code = 200
    result.url = (
        "https://www.screener.in/company/ACME/"
        if standalone
        else "https://www.screener.in/company/ACME/consolidated/"
    )
    result.encoding = "utf-8"
    result._content = body.encode() if isinstance(body, str) else body
    if encoding:
        result.headers["Content-Encoding"] = encoding
    return result


def company_page(quarters=("Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026")):
    header = "<th></th>" + "".join(f"<th>{q}</th>" for q in quarters)
    rows = []
    for label, values in (
        ("Sales+", [1000, 1100, 1200, 1300, 1500]),
        ("Profit before tax", [150, 160, 170, 180, 190]),
        ("Net Profit+", [100, 110, 120, 130, 150]),
        ("EPS in Rs", [10, 11, 12, 13, 15]),
    ):
        cells = "".join(f"<td>{v}</td>" for v in values[:len(quarters)])
        rows.append(f"<tr><td>{label}</td>{cells}</tr>")
    return (
        "<html><body><h1>Acme Ltd</h1>"
        '<section id="quarters"><table>'
        f"<thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody>"
        "</table></section></body></html>"
    )


def test_session_does_not_advertise_uninstalled_compression_decoders():
    assert "Accept-Encoding" not in screener.HEADERS
    assert screener._session.headers["Accept-Encoding"] == (
        requests.utils.default_headers()["Accept-Encoding"]
    )


@pytest.mark.parametrize(
    "body",
    [
        b"\x00\x81\xff\x03compressed-not-html",
        "<html><h1>Service unavailable</h1><p>Try again later</p></html>",
        "<html><h1>Acme Ltd</h1></html>",
        '{"error": "unavailable"}',
    ],
)
def test_http_200_without_company_financials_is_a_source_error(
    monkeypatch, caplog, body
):
    monkeypatch.setattr(
        screener, "_rate_limited_get", Mock(return_value=response(body, encoding="br"))
    )
    with caplog.at_level(logging.INFO, logger="scraper.screener"):
        result = screener.scrape_fundamentals("ACME")
    assert "Invalid Screener company page" in result["error"]
    assert "Content-Encoding: br" in result["error"]
    assert "Successfully scraped" not in caplog.text
    assert "Could not parse" in caplog.text
    assert "quarterly_results" not in result


def test_bad_response_is_not_misreported_as_short_quarterly_history(monkeypatch):
    monkeypatch.setattr(
        screener, "_rate_limited_get", Mock(return_value=response(b"\x00\xffbinary"))
    )
    result = analysis.analyze_symbol("ACME")
    assert "Invalid Screener company page" in result.error
    assert "insufficient quarterly history" not in result.error
    assert not result.is_strong


def test_valid_company_page_reaches_quarterly_growth_analysis(monkeypatch):
    monkeypatch.setattr(
        screener, "_rate_limited_get", Mock(return_value=response(company_page()))
    )
    result = analysis.analyze_symbol("ACME")
    assert result.error is None
    assert result.company_name == "Acme Ltd"
    assert result.latest_quarter == "Sep 2026"
    assert result.yoy_profit_growth == pytest.approx(50)
    assert result.yoy_sales_growth == pytest.approx(50)
    assert result.yoy_eps_growth == pytest.approx(50)
    assert result.qoq_profit_growth == pytest.approx(100 * (150 / 130 - 1))
    assert result.reporting_basis == "consolidated"
    assert result.source_url.endswith("/ACME/consolidated/")


def test_real_short_history_is_still_reported_as_short_history(monkeypatch):
    monkeypatch.setattr(
        screener,
        "_rate_limited_get",
        Mock(return_value=response(company_page(quarters=("Sep 2026",)))),
    )
    assert analysis.analyze_symbol("ACME").error == "insufficient quarterly history"


def test_standalone_fallback_still_parses_financials(monkeypatch):
    fetch = Mock(side_effect=[None, response(company_page(), standalone=True)])
    monkeypatch.setattr(screener, "_rate_limited_get", fetch)
    result = screener.scrape_fundamentals("ACME")
    assert "error" not in result
    assert result["quarterly_results"][2]["Sep 2026"] == "150"
    assert result["reporting_basis"] == "standalone"
    assert fetch.call_args.args[0] == "https://www.screener.in/company/ACME/"


def test_resolved_slug_page_is_validated_too(monkeypatch):
    monkeypatch.setattr(screener, "resolve_screener_slug", lambda symbol: "123456")
    monkeypatch.setattr(
        screener,
        "_rate_limited_get",
        Mock(side_effect=[None, None, response("<h1>No financials</h1>")]),
    )
    result = screener.scrape_fundamentals("ACME")
    assert "Invalid Screener company page" in result["error"]


@pytest.mark.parametrize(
    ("consolidated_quarters", "standalone_quarters", "expected"),
    [
        ((), ("Jun 2026", "Sep 2026"), "standalone"),
        (("Mar 2024", "Dec 2024", "Mar 2025"), ("Jun 2026", "Sep 2026"), "standalone"),
        (("Jun 2026", "Sep 2026"), ("Jun 2026", "Sep 2026"), "consolidated"),
        (("Jun 2026", "Sep 2026"), ("Mar 2026", "Jun 2026"), "consolidated"),
        (("Jun 2026", "Sep 2026"), (), "consolidated"),
    ],
)
def test_choose_freshest_quarter_and_prefer_consolidated_on_ties(
    monkeypatch, consolidated_quarters, standalone_quarters, expected
):
    monkeypatch.setattr(
        screener,
        "_rate_limited_get",
        Mock(side_effect=[
            response(company_page(consolidated_quarters)),
            response(company_page(standalone_quarters), standalone=True),
        ]),
    )
    result = screener.scrape_fundamentals("ACME")
    assert result["reporting_basis"] == expected
    assert result["source_url"].endswith(
        "/consolidated/" if expected == "consolidated" else "/ACME/"
    )
    assert list(result["quarterly_results"][0])[1:] == list(
        consolidated_quarters if expected == "consolidated" else standalone_quarters
    )


def test_empty_future_column_does_not_make_a_page_fresher(monkeypatch):
    pending = company_page(("Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"))
    pending = pending.replace("<td>150</td>", "<td></td>")
    monkeypatch.setattr(
        screener,
        "_rate_limited_get",
        Mock(side_effect=[
            response(company_page(("Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"))),
            response(pending, standalone=True),
        ]),
    )
    assert screener.scrape_fundamentals("ACME")["reporting_basis"] == "consolidated"


def test_fallback_uses_one_basis_for_all_quarters_and_quality_metrics(monkeypatch):
    consolidated = company_page(("Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"))
    consolidated = consolidated.replace("<td>100</td>", "<td>900</td>")
    consolidated += (
        '<section id="balance-sheet"><table><thead>'
        '<tr><th></th><th>Mar 2026</th></tr></thead><tbody>'
        '<tr><td>Borrowings+</td><td>999</td></tr>'
        '<tr><td>Equity Capital</td><td>100</td></tr>'
        '</tbody></table></section>'
    )
    standalone = company_page() + (
        '<section id="balance-sheet"><table><thead>'
        '<tr><th></th><th>Mar 2026</th></tr></thead><tbody>'
        '<tr><td>Borrowings+</td><td>0</td></tr>'
        '<tr><td>Equity Capital</td><td>100</td></tr>'
        '</tbody></table></section>'
    )
    monkeypatch.setattr(
        screener,
        "_rate_limited_get",
        Mock(side_effect=[response(consolidated), response(standalone, standalone=True)]),
    )
    result = analysis.analyze_symbol("ACME")
    assert result.reporting_basis == "standalone"
    assert result.latest_quarter == "Sep 2026"
    assert result.yoy_profit_growth == pytest.approx(50)
    assert result.ttm_eps == 51
    assert result.debt_to_equity == 0
    assert result.to_dict()["source_url"].endswith("/ACME/")
