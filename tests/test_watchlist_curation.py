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
