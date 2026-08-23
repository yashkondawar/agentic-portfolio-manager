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
