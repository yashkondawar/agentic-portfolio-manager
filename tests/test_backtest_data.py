from datetime import date

from backtesting.swing_trading.data import _cache_tag


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
