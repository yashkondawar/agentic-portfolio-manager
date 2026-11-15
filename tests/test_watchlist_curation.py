import logging
import math

import pandas as pd
import pytest

import swing_trading_copilot
import watchlist_curator

from core.storage import delete_document, get_document, set_document
from strategies.swing_trading import SwingTradingStrategy
from strategies.watchlist_curation import WatchlistCurationStrategy
from watchlist_curator import ScreenConfig, StockMetrics, score_and_rank


def test_unknown_industries_are_not_collectively_capped():
    metrics = [
        StockMetrics(
            symbol=f"STOCK{index}",
            industry="Unknown",
            close=120,
            sma20=110,
            sma50=100,
            sma200=90,
            rsi=60,
            atr_pct=3,
            ret_1m=5 + index,
            ret_3m=10 + index,
            ret_6m=20 + index,
            rel_strength_3m=5,
            vol_surge=1.5,
            traded_value_cr=20,
            dist_from_high_pct=2,
            sma50_rising=True,
        )
        for index in range(5)
    ]

    ranked = score_and_rank(
        metrics,
        ScreenConfig(shortlist_size=5, max_per_industry=3),
    )

    assert len(ranked) == 5


def _metric(symbol: str = "TCS") -> StockMetrics:
    return StockMetrics(
        symbol=symbol,
        industry="Technology",
        close=120,
        sma20=110,
        sma50=100,
        sma200=90,
        rsi=60,
        atr_pct=3,
        ret_1m=5,
        ret_3m=10,
        ret_6m=20,
        rel_strength_3m=5,
        vol_surge=1.5,
        traded_value_cr=20,
        dist_from_high_pct=2,
        sma50_rising=True,
    )


def test_strategy_run_updates_active_watchlist(monkeypatch):
    delete_document("watchlists", "swing_current")
    monkeypatch.setattr(
        watchlist_curator,
        "load_universe_from_index",
        lambda _index: [watchlist_curator.UniverseStock(symbol="TCS")],
    )
    monkeypatch.setattr(
        watchlist_curator,
        "download_and_compute",
        lambda _universe, period: [_metric()],
    )

    result = WatchlistCurationStrategy().run(
        {"index": "nifty500", "period": "1y", "use_llm": False}
    )

    stored = get_document("watchlists", "swing_current")
    assert stored["picks"][0]["symbol"] == "TCS"
    assert result.data["artifact_group_id"]


def test_swing_strategy_uses_stored_watchlist(monkeypatch):
    set_document(
        "watchlists",
        "swing_current",
        {"picks": [{"symbol": "TCS"}, {"symbol": "INFY"}]},
    )
    captured = {}

    def fake_run_analysis(**kwargs):
        captured["watchlist"] = kwargs["watchlist"]
        return "# Swing report"

    monkeypatch.setattr(swing_trading_copilot, "run_analysis", fake_run_analysis)

    result = SwingTradingStrategy().run({"positions": [], "watchlist": []})

    assert result.ok
    assert captured["watchlist"] == ["TCS", "INFY"]


def _price_history(base=100.0):
    close = pd.Series(
        [base + i * 0.2 + 2 * math.sin(i) for i in range(210)],
        index=pd.bdate_range("2025-01-01", periods=210),
    )
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 2,
            "Low": close - 2,
            "Close": close,
            "Volume": 1_000_000.0,
        }
    )


def _download_shape(frames, layout):
    if layout == "flat":
        assert len(frames) == 1
        return next(iter(frames.values()))
    frame = pd.concat(frames, axis=1, names=["Ticker", "Price"])
    return frame.swaplevel(axis=1) if layout == "price_first" else frame


@pytest.mark.parametrize("size", [1, 50, 501])
def test_download_computes_every_symbol_including_single_ticker_tail(monkeypatch, size):
    frame = _price_history()
    chunks = []

    def fake_download(tickers, **kwargs):
        if tickers == watchlist_curator.NIFTY_BENCHMARK:
            return _download_shape({tickers: frame}, "price_first")
        chunks.append(list(tickers))
        return _download_shape({symbol: frame for symbol in tickers}, "ticker_first")

    monkeypatch.setattr("yfinance.download", fake_download)
    universe = [
        watchlist_curator.UniverseStock(f"STOCK{i}", "Technology") for i in range(size)
    ]
    result = watchlist_curator.download_and_compute(universe)

    assert [m.symbol for m in result] == [u.symbol for u in universe]
    assert all(m.industry == "Technology" for m in result)
    assert all(m.close == pytest.approx(frame["Close"].iloc[-1]) for m in result)
    assert all(m.rel_strength_3m == pytest.approx(0) for m in result)
    assert [len(chunk) for chunk in chunks] == [
        min(50, size - i) for i in range(0, size, 50)
    ]


@pytest.mark.parametrize("layout", ["flat", "ticker_first", "price_first"])
def test_single_symbol_and_benchmark_accept_yahoo_column_layouts(monkeypatch, layout):
    stock = _price_history()
    benchmark = _price_history(200.0)

    def fake_download(tickers, **kwargs):
        frames = (
            {tickers: benchmark} if isinstance(tickers, str) else {tickers[0]: stock}
        )
        return _download_shape(frames, layout)

    monkeypatch.setattr("yfinance.download", fake_download)
    result = watchlist_curator.download_and_compute(
        [watchlist_curator.UniverseStock("TCS")]
    )

    assert len(result) == 1
    expected = watchlist_curator._ret(stock["Close"], 63) - watchlist_curator._ret(
        benchmark["Close"], 63
    )
    assert result[0].rel_strength_3m == pytest.approx(expected)


@pytest.mark.parametrize("layout", ["ticker_first", "price_first"])
def test_missing_and_unavailable_symbols_do_not_abort_good_prices(
    monkeypatch, caplog, layout
):
    frame = _price_history()

    def fake_download(tickers, **kwargs):
        if isinstance(tickers, str):
            return _download_shape({tickers: frame}, layout)
        return _download_shape(
            {
                "GOOD.NS": frame,
                "BAGMANE.NS": frame * float("nan"),
                "BADSCHEMA.NS": frame.drop(columns="Close"),
            },
            layout,
        )

    monkeypatch.setattr("yfinance.download", fake_download)
    with caplog.at_level(logging.WARNING, logger="watchlist_curator"):
        result = watchlist_curator.download_and_compute(
            [
                watchlist_curator.UniverseStock(symbol)
                for symbol in ["GOOD", "BAGMANE", "MISSING", "BADSCHEMA"]
            ]
        )
    assert [m.symbol for m in result] == ["GOOD"]
    for symbol in ["BAGMANE", "MISSING", "BADSCHEMA"]:
        assert symbol in caplog.text


def test_missing_ticker_never_receives_another_tickers_history(monkeypatch, caplog):
    def fake_download(tickers, **kwargs):
        ticker = tickers if isinstance(tickers, str) else "SOMEONEELSE.NS"
        return _download_shape({ticker: _price_history()}, "ticker_first")

    monkeypatch.setattr("yfinance.download", fake_download)
    result = watchlist_curator.download_and_compute(
        [watchlist_curator.UniverseStock("MISSING")]
    )
    assert result == []
    assert "MISSING.NS" in caplog.text


@pytest.mark.parametrize("layout", ["ticker_first", "price_first"])
def test_each_symbol_keeps_its_own_prices(monkeypatch, layout):
    histories = {"AAA.NS": _price_history(100), "BBB.NS": _price_history(200)}

    def fake_download(tickers, **kwargs):
        frames = {tickers: _price_history()} if isinstance(tickers, str) else histories
        return _download_shape(frames, layout)

    monkeypatch.setattr("yfinance.download", fake_download)
    result = watchlist_curator.download_and_compute(
        [
            watchlist_curator.UniverseStock("AAA"),
            watchlist_curator.UniverseStock("BBB"),
        ]
    )
    assert {m.symbol: m.close for m in result} == {
        "AAA": histories["AAA.NS"]["Close"].iloc[-1],
        "BBB": histories["BBB.NS"]["Close"].iloc[-1],
    }


@pytest.mark.parametrize("response", [None, pd.DataFrame()])
def test_no_history_is_a_failed_run_not_an_empty_saved_watchlist(monkeypatch, response):
    original = {"picks": [{"symbol": "KEEPME"}]}
    set_document("watchlists", "swing_current", original)
    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="No metrics computed"):
        WatchlistCurationStrategy().run({"universe": ["MISSING"], "use_llm": False})
    assert get_document("watchlists", "swing_current") == original


@pytest.mark.parametrize("missing", ["Close", "High", "Low", "Volume"])
def test_metrics_skip_incomplete_schema_with_warning(missing, caplog):
    result = watchlist_curator._compute_metrics_for(
        "INCOMPLETE",
        "Unknown",
        _price_history().drop(columns=missing),
        None,
    )
    assert result is None
    assert "INCOMPLETE" in caplog.text and missing in caplog.text


def test_flat_multi_symbol_response_is_not_reused_for_every_stock(monkeypatch, caplog):
    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: _price_history())
    result = watchlist_curator.download_and_compute(
        [
            watchlist_curator.UniverseStock("AAA"),
            watchlist_curator.UniverseStock("BBB"),
        ]
    )
    assert result == []
    assert "AAA.NS" in caplog.text and "BBB.NS" in caplog.text


def test_nse_universe_skips_only_confirmed_synthetic_components(monkeypatch, caplog):
    from io import BytesIO

    csv = (
        "Company Name,Industry,Symbol,Series,ISIN Code\n"
        "Ordinary Equity,IT,GOOD,EQ,INE000000001\n"
        "Synthetic Component,Other,DUMMYHEG,EQ,DUM545A01024\n"
        "New REIT,Real Estate,BAGMANE,RR,INE2OVN25015\n"
        "Not Confirmed,Other,DUMMYREAL,EQ,INE000000002\n"
    )
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *args, **kwargs: BytesIO(csv.encode("utf-8"))
    )
    result = watchlist_curator.load_universe_from_index("nifty500")
    assert [stock.symbol for stock in result] == ["GOOD", "BAGMANE", "DUMMYREAL"]
    assert "DUMMYHEG" in caplog.text and "synthetic" in caplog.text.lower()
