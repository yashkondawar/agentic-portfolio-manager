import pandas as pd

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
