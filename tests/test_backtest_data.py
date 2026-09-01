from datetime import date

import pandas as pd

from backtesting.swing_trading.data import _cache_tag
from core.bars import normalise_frame


def test_cache_tag_includes_symbol_identity_and_benchmark():
    start = date(2025, 1, 1)
    end = date(2026, 1, 1)

    first = _cache_tag(["TCS", "INFY"], "^NSEI", start, end)
    second = _cache_tag(["RELIANCE", "HDFCBANK"], "^NSEI", start, end)
    other_benchmark = _cache_tag(["TCS", "INFY"], "^BSESN", start, end)

    assert first != second
    assert first != other_benchmark
    assert _cache_tag(["TCS.NS"], "^NSEI", start, end) != _cache_tag(
        ["TCS.BO"], "^NSEI", start, end
    )


def test_normalise_accepts_yfinance_ticker_first_multiindex():
    columns = pd.MultiIndex.from_tuples(
        [
            ("TCS.NS", "Open"),
            ("TCS.NS", "High"),
            ("TCS.NS", "Low"),
            ("TCS.NS", "Close"),
            ("TCS.NS", "Volume"),
        ],
        names=["Ticker", "Price"],
    )
    raw = pd.DataFrame(
        [[100.0, 102.0, 99.0, 101.0, 1_000_000]],
        columns=columns,
        index=pd.to_datetime(["2026-07-24"]),
    )

    normalized = normalise_frame(raw)

    assert normalized is not None
    assert list(normalized.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert normalized.iloc[0]["Close"] == 101.0
