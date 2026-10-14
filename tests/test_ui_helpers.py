import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ui.components import clean_editor_rows


def test_clean_editor_rows_normalizes_symbols_and_drops_blanks():
    rows = pd.DataFrame(
        [
            {"symbol": " tcs.ns ", "quantity": 2, "buy_price": 100},
            {"symbol": "", "quantity": 0, "buy_price": 0},
        ]
    )
    assert clean_editor_rows(rows, ("quantity", "buy_price")) == [
        {"symbol": "TCS", "quantity": 2, "buy_price": 100}
    ]


@pytest.mark.parametrize("include_source", [False, True])
def test_quarterly_funnel_displays_financial_source_without_breaking_old_runs(
    include_source,
):
    row = {
        "symbol": "ACME",
        "company": "Acme Ltd",
        "result_date": "2026-10-14",
        "strength": 10,
        "stage": "analysed",
        "status": "weak_fundamentals",
        "reason": "below growth threshold",
    }
    if include_source:
        row.update(
            latest_quarter="Sep 2026",
            reporting_basis="standalone",
            source_url="https://www.screener.in/company/ACME/",
        )
    data = {"analysed": [row]}
    app = AppTest.from_string(
        "from ui.components import _render_quarterly_results\n"
        f"_render_quarterly_results({data!r})\n"
    ).run(timeout=30)
    assert not app.exception
    frame = app.dataframe[0].value
    assert frame.iloc[0]["symbol"] == "ACME"
    if include_source:
        assert frame.iloc[0]["reporting_basis"] == "standalone"
        assert frame.iloc[0]["latest_quarter"] == "Sep 2026"
        assert frame.iloc[0]["source_url"] == row["source_url"]
    else:
        assert "reporting_basis" not in frame.columns
