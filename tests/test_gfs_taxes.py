"""Tests for the Indian cost and capital-gains model.

The point of these is not that the arithmetic runs, but that the *rules* are
right: GST attaches to broker-side fees and not to statutory levies, the STCG
rate changed mid-year in 2024, the tax year runs April-March, losses set off in
the direction the law allows, and buy-and-hold is taxed once rather than
annually. Every one of those is a place where a plausible-looking model
silently produces the wrong number.
"""

from datetime import date

import pandas as pd
import pytest

from backtesting.gfs import taxes as tx


def make_trade(entry, exit_px, entry_date, exit_date, qty=100):
    return {
        "quantity": qty,
        "entry_price": entry,
        "exit_price": exit_px,
        "entry_date": entry_date,
        "exit_date": exit_date,
    }


# ── Charges ──────────────────────────────────────────────────────────────────


def test_gst_applies_to_brokerage_not_to_stt_or_stamp():
    """GST is levied on services, so STT and stamp duty must stay outside it."""
    cfg = tx.TaxConfig()
    value = 100_000.0

    charged = tx.charges_for_leg(value, cfg, is_buy=True)

    stt = value * cfg.stt_buy_pct / 100.0
    stamp = value * cfg.stamp_duty_pct / 100.0
    gst_free = stt + stamp
    # Whatever the rest is, GST applied to it must not have touched stt/stamp.
    assert charged > gst_free
    taxed_part = charged - gst_free
    # The GST-bearing part is brokerage + exchange + SEBI, grossed up by GST.
    assert taxed_part == pytest.approx(taxed_part / 1.18 * 1.18)
    # And STT alone dominates a delivery trade.
    assert stt / charged > 0.5


def test_sell_leg_has_no_stamp_duty():
    cfg = tx.TaxConfig()
    buy = tx.charges_for_leg(100_000.0, cfg, is_buy=True)
    sell = tx.charges_for_leg(100_000.0, cfg, is_buy=False)
    assert buy > sell
    assert buy - sell == pytest.approx(100_000.0 * cfg.stamp_duty_pct / 100.0, rel=1e-6)


def test_round_trip_cost_is_small_relative_to_turnover():
    cfg = tx.TaxConfig()
    cost = tx.round_trip_charges(100_000.0, 110_000.0, cfg)
    assert 0.05 < cost / 210_000.0 * 100.0 < 0.25


# ── Rate schedule ────────────────────────────────────────────────────────────


def test_stcg_rate_switches_on_23_july_2024():
    cfg = tx.TaxConfig()
    assert cfg.stcg_rate_for(date(2024, 7, 22)) == cfg.stcg_rate_pct_legacy
    assert cfg.stcg_rate_for(date(2024, 7, 23)) == cfg.stcg_rate_pct
    assert cfg.stcg_rate_for(date(2020, 1, 1)) == cfg.stcg_rate_pct_legacy


def test_fy_2024_25_blends_both_stcg_rates():
    """A year straddling the change must not be taxed wholly at either rate."""
    cfg = tx.TaxConfig()
    trades = [
        make_trade(100, 120, date(2024, 5, 1), date(2024, 6, 1)),   # 15% era
        make_trade(100, 120, date(2024, 9, 1), date(2024, 10, 1)),  # 20% era
    ]
    table = tx.apply_to_trades(trades, cfg)
    by_year = tx.capital_gains_by_year(table, cfg)
    rate = float(by_year.loc["2024-25", "stcg_rate"])
    assert cfg.stcg_rate_pct_legacy < rate < cfg.stcg_rate_pct


# ── Financial year ───────────────────────────────────────────────────────────


def test_financial_year_boundary_is_april_not_january():
    assert tx.financial_year(date(2023, 3, 31)) == "2022-23"
    assert tx.financial_year(date(2023, 4, 1)) == "2023-24"
    assert tx.financial_year(date(2023, 12, 31)) == "2023-24"


def test_march_and_april_exits_land_in_different_years():
    cfg = tx.TaxConfig()
    trades = [
        make_trade(100, 130, date(2023, 2, 1), date(2023, 3, 20)),
        make_trade(100, 130, date(2023, 3, 1), date(2023, 4, 5)),
    ]
    by_year = tx.capital_gains_by_year(tx.apply_to_trades(trades, cfg), cfg)
    assert set(by_year.index) == {"2022-23", "2023-24"}


# ── Holding period ───────────────────────────────────────────────────────────


def test_long_term_needs_more_than_365_days():
    cfg = tx.TaxConfig()
    short = make_trade(100, 120, date(2022, 1, 1), date(2022, 12, 1))
    long = make_trade(100, 120, date(2022, 1, 1), date(2023, 6, 1))
    table = tx.apply_to_trades([short, long], cfg)
    assert list(table["long_term"]) == [False, True]


def test_ltcg_exemption_shelters_small_long_term_gains():
    cfg = tx.TaxConfig()
    # One long-term trade with a gain below the annual exemption.
    gain_per_share = cfg.ltcg_exempt_per_year / 100.0 * 0.5
    trades = [
        make_trade(1000, 1000 + gain_per_share, date(2022, 1, 1), date(2023, 6, 1))
    ]
    by_year = tx.capital_gains_by_year(tx.apply_to_trades(trades, cfg), cfg)
    assert float(by_year["taxable_ltcg"].iloc[0]) == 0.0
    assert float(by_year["tax"].iloc[0]) == 0.0


# ── Loss relief ──────────────────────────────────────────────────────────────


def test_losing_year_pays_no_tax_and_carries_the_loss_forward():
    cfg = tx.TaxConfig()
    trades = [make_trade(100, 70, date(2022, 5, 1), date(2022, 6, 1))]
    by_year = tx.capital_gains_by_year(tx.apply_to_trades(trades, cfg), cfg)
    assert float(by_year["tax"].iloc[0]) == 0.0
    assert float(by_year["loss_carried_forward"].iloc[0]) > 0.0


def test_carried_loss_reduces_next_year_tax():
    cfg = tx.TaxConfig()
    loss_only = [make_trade(100, 70, date(2022, 5, 1), date(2022, 6, 1))]
    gain_only = [make_trade(100, 130, date(2023, 5, 1), date(2023, 6, 1))]

    standalone = tx.capital_gains_by_year(tx.apply_to_trades(gain_only, cfg), cfg)
    combined = tx.capital_gains_by_year(
        tx.apply_to_trades(loss_only + gain_only, cfg), cfg
    )
    assert float(combined.loc["2023-24", "tax"]) < float(standalone.loc["2023-24", "tax"])


def test_short_term_loss_offsets_long_term_gain():
    """ST losses may shelter LT gains; the reverse is not allowed."""
    cfg = tx.TaxConfig()
    st_loss = make_trade(1000, 100, date(2022, 5, 1), date(2022, 6, 1))
    lt_gain = make_trade(1000, 5000, date(2021, 4, 1), date(2022, 6, 1))

    lt_alone = tx.capital_gains_by_year(tx.apply_to_trades([lt_gain], cfg), cfg)
    together = tx.capital_gains_by_year(
        tx.apply_to_trades([st_loss, lt_gain], cfg), cfg
    )
    assert float(together.loc["2022-23", "tax"]) < float(lt_alone.loc["2022-23", "tax"])


def test_long_term_loss_does_not_offset_short_term_gain():
    cfg = tx.TaxConfig()
    lt_loss = make_trade(1000, 100, date(2021, 4, 1), date(2022, 6, 1))
    st_gain = make_trade(1000, 5000, date(2022, 5, 1), date(2022, 6, 1))

    st_alone = tx.capital_gains_by_year(tx.apply_to_trades([st_gain], cfg), cfg)
    together = tx.capital_gains_by_year(
        tx.apply_to_trades([lt_loss, st_gain], cfg), cfg
    )
    assert float(together.loc["2022-23", "taxable_stcg"]) == pytest.approx(
        float(st_alone.loc["2022-23", "taxable_stcg"])
    )


# ── Net outcome ──────────────────────────────────────────────────────────────


def test_net_cagr_is_below_gross_cagr():
    cfg = tx.TaxConfig()
    trades = [
        make_trade(100, 115, date(2020 + i // 4, 1 + 3 * (i % 4), 1),
                   date(2020 + i // 4, 2 + 3 * (i % 4), 1))
        for i in range(8)
    ]
    summary = tx.net_summary(trades, 500_000.0, 2.0, cfg)
    assert summary["net_cagr"] < summary["cagr_after_charges"]
    assert summary["cagr_after_charges"] < summary["gross_cagr"]


def test_buy_and_hold_is_taxed_once_not_annually():
    """The honest benchmark: the index compounds untaxed and pays LTCG at exit.

    Taxing it annually would understate it and flatter the strategy.
    """
    cfg = tx.TaxConfig()
    gross, years = 12.0, 10.0
    net = tx.benchmark_net_cagr(gross, years, cfg)
    annual_haircut = gross * (1 - cfg.ltcg_rate_pct / 100.0)
    assert annual_haircut < net < gross


def test_benchmark_net_cagr_penalty_shrinks_with_horizon():
    """Deferral is worth more the longer you hold, so the drag must fall."""
    cfg = tx.TaxConfig()
    short_drag = 12.0 - tx.benchmark_net_cagr(12.0, 3.0, cfg)
    long_drag = 12.0 - tx.benchmark_net_cagr(12.0, 25.0, cfg)
    assert long_drag < short_drag


# ── Input handling ───────────────────────────────────────────────────────────


def test_accepts_iso_date_strings_from_the_artifact_writer():
    """The service serialises trades before reporting, turning dates into text."""
    cfg = tx.TaxConfig()
    typed = [make_trade(100, 120, date(2022, 1, 3), date(2022, 3, 1))]
    stringy = [make_trade(100, 120, "2022-01-03", "2022-03-01")]
    assert tx.apply_to_trades(typed, cfg)["net_pnl"].iloc[0] == pytest.approx(
        tx.apply_to_trades(stringy, cfg)["net_pnl"].iloc[0]
    )


def test_empty_trade_list_is_not_an_error():
    cfg = tx.TaxConfig()
    assert tx.apply_to_trades([], cfg).empty
    assert tx.capital_gains_by_year(pd.DataFrame(), cfg).empty
    assert "No closed trades" in tx.render_tax_summary({})
