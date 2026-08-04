"""Unit tests for the sector-relative debt gate (option 2).

Pure — no network / yfinance / screener — so they run in the normal suite. They
lock in the LIVE cap formula (``qtr_results.config.sector_debt_cap``) and the
flipped backtest default, i.e. the exact behaviour that lets a capital-intensive
winner like GESHIP (Industrials, D/E ~0.064) clear the gate that the flat 0.05
cap wrongly rejected.
"""

from qtr_results import config as live_cfg
from backtesting.qtr_results.config import BacktestConfig


# ── live cap formula ─────────────────────────────────────────────────────────

def test_unknown_sector_falls_back_to_flat_floor():
    assert live_cfg.sector_debt_cap(None) == live_cfg.MAX_DEBT_TO_EQUITY
    assert live_cfg.sector_debt_cap("UNKNOWN") == live_cfg.MAX_DEBT_TO_EQUITY
    assert live_cfg.sector_debt_cap("Not A Sector") == live_cfg.MAX_DEBT_TO_EQUITY


def test_known_sector_cap_is_factor_times_median_floored():
    med = live_cfg.SECTOR_MEDIAN_DE["Industrials"]
    expected = max(live_cfg.MAX_DEBT_TO_EQUITY, live_cfg.SECTOR_DEBT_FACTOR * med)
    assert live_cfg.sector_debt_cap("Industrials") == expected
    # Industrials is capital-intensive enough that the cap clears the floor.
    assert live_cfg.sector_debt_cap("Industrials") > live_cfg.MAX_DEBT_TO_EQUITY


def test_geship_scenario_admitted_but_over_levered_rejected():
    # GESHIP: Industrials, point-in-time D/E ~0.064 -> must now clear the gate.
    cap = live_cfg.sector_debt_cap("Industrials")
    assert 0.064 <= cap
    # A genuinely over-levered Industrials name is still rejected.
    assert 0.90 > cap


def test_asset_light_sector_stays_disciplined():
    # An asset-light sector must NOT be handed a loose gate: its scaled cap stays
    # near the tight floor, so a debt-carrying tech/telecom name is still cut.
    for sector in ("Technology", "Communication Services"):
        assert live_cfg.sector_debt_cap(sector) < 0.30


# ── backtest default flip ────────────────────────────────────────────────────

def test_backtest_defaults_to_sector_relative():
    cfg = BacktestConfig()
    assert cfg.debt_gate_mode == "sector_relative"
    assert cfg.sector_debt_factor == 2.0
