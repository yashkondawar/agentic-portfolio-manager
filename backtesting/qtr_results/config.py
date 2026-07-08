"""
config.py
=========

Central configuration for the **quarterly-results** backtest. Mirrors the live
strategy's tunables (``qtr_results.config``: selection thresholds, target band,
trailing-stop ratio, holding window) so the backtest reasons within the SAME
playbook the live strategy follows, and adds the capital/goal/window/universe
knobs a portfolio simulation needs (same shape as the swing-trading backtest).

All values are overridable from the CLI (see ``run_backtest.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

# Reuse the live strategy defaults so the backtest starts from identical numbers.
from qtr_results import config as live_config

HERE = Path(__file__).resolve().parent
PRICE_CACHE_DIR = HERE / "data_cache"
FUND_CACHE_DIR = HERE / "fundamentals_cache"
RESULTS_DIR = HERE / "results"


@dataclass
class BacktestConfig:
    # ── Capital / goal ────────────────────────────────────────────────────────
    starting_capital: float = 500_000.0       # ₹5,00,000 to start (all cash)
    goal_return_pct: float = 20.0             # +20% goal → ₹6,00,000

    # ── Backtest window ───────────────────────────────────────────────────────
    # Defaults: trailing ~1 year ending "today". Resolved in run_backtest if None.
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Extra price history downloaded BEFORE start_date so nothing cold-starts.
    warmup_days: int = 60                      # calendar days of price warmup

    # ── Universe (companies whose result declarations we replay) ──────────────
    universe_index: str = "nifty200"           # nifty50/100/200/500/midcap150...
    universe_file: Optional[Path] = None       # optional custom symbol file
    benchmark: str = "^NSEI"                   # Nifty 50 (defines the calendar)

    # ── Result-event discovery / timing ───────────────────────────────────────
    # A quarter that ends on `quarter_end` is treated as DECLARED `reporting_lag_days`
    # later (Indian companies file Q results ~4-8 weeks after quarter-end). The
    # entry is then priced at the first trading session's OPEN on/after that date,
    # so every pick uses the historical price at that point in time — never today's.
    reporting_lag_days: int = 45
    max_new_per_day: int = 5                    # cap simultaneous fresh buys/day

    # ── Selection thresholds (mirror qtr_results.config) ──────────────────────
    min_yoy_profit_growth: float = live_config.MIN_YOY_PROFIT_GROWTH   # 20%
    min_qoq_profit_growth: float = live_config.MIN_QOQ_PROFIT_GROWTH   # 5%
    min_yoy_eps_growth: float = live_config.MIN_YOY_EPS_GROWTH         # 15%

    # ── Target band + trailing stop + holding window (mirror qtr_results) ─────
    target_min_pct: float = live_config.TARGET_MIN_PCT                 # 10%
    target_max_pct: float = live_config.TARGET_MAX_PCT                 # 20%
    trailing_stop_ratio: float = live_config.TRAILING_STOP_RATIO       # target/2
    max_holding_days: int = live_config.MAX_HOLDING_DAYS               # 21 (3 wks)

    # ── Portfolio sizing (the capital overlay the live signal-tracker lacks) ──
    # The live strategy is a signal/ledger tracker with no position sizing; a
    # backtest needs one. We reuse the swing setup's risk model: risk a fixed %
    # of equity per trade, where the per-share risk is the initial trailing-stop
    # distance (entry * trailing_stop_pct/100). Capped by a per-name concentration
    # limit and available cash.
    risk_per_trade_pct: float = 2.0
    max_positions: int = 10                    # max concurrent open positions
    max_position_pct: float = 20.0             # per-name concentration cap (%)

    # ── Costs ─────────────────────────────────────────────────────────────────
    commission_pct: float = 0.05               # per-side cost proxy (%)

    # ── Misc ──────────────────────────────────────────────────────────────────
    use_cache: bool = True                     # reuse downloaded price/fundamentals
    max_symbols: Optional[int] = None          # cap universe size (for quick runs)

    def goal_capital(self) -> float:
        return self.starting_capital * (1 + self.goal_return_pct / 100.0)
