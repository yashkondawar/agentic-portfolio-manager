"""
config.py
=========

Central configuration for the swing-trading backtest. Mirrors the parameters of
the live system (``SwingConfig`` in ``swing_trading_copilot.py`` and
``ScreenConfig`` in ``watchlist_curator.py``) so the backtest reasons within the
SAME playbook the live LLM is instructed to follow.

All values are overridable from the CLI (see ``run_backtest.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent
DATA_CACHE_DIR = HERE / "data_cache"
RESULTS_DIR = HERE / "results"


@dataclass
class BacktestConfig:
    # ── Capital / goal ────────────────────────────────────────────────────────
    starting_capital: float = 500_000.0      # ₹5,00,000 to start (all cash)
    goal_return_pct: float = 20.0            # +20% goal → ₹6,00,000

    # ── Backtest window ───────────────────────────────────────────────────────
    # Defaults: trailing ~1 year ending "today". Resolved in run_backtest if None.
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Extra history downloaded BEFORE start_date so indicators (SMA200, 52w high,
    # 3/6-month returns) are warm on day 1 — guarantees no cold-start leak.
    warmup_days: int = 420                    # ~ calendar days (>200 trading days)

    # ── Universe / watchlist (monthly rebalance — mechanical Stage-1 screen) ──
    universe_index: str = "nifty200"          # nifty50/100/200/500/midcap150...
    universe_file: Optional[Path] = None      # optional custom symbol file
    benchmark: str = "^NSEI"                  # Nifty 50 for relative strength
    watchlist_size: int = 20                  # final monthly watchlist size
    shortlist_size: int = 40                  # Stage-1 shortlist before trimming
    max_per_industry: int = 3                 # industry diversification cap

    # ── Daily swing playbook (mirrors SWING_PLAYBOOK / SwingConfig) ───────────
    target_profit_pct: float = 20.0           # per-trade target
    max_holding_days: int = 30                # time-stop window (calendar days)
    risk_per_trade_pct: float = 2.0           # 2% rule
    min_rr: float = 2.0                       # minimum reward:risk
    max_positions: int = 8                    # max concurrent open positions
    max_position_pct: float = 25.0            # per-name concentration cap (% cap)

    # Entry-filter thresholds (deterministic proxy of the playbook checklist).
    rsi_min: float = 55.0
    rsi_max: float = 70.0
    max_atr_pct: float = 9.0                  # skip hyper-volatile names
    min_volume_ratio: float = 1.2             # vol >= 1.2x 20d avg on signal day
    min_liquidity_cr: float = 5.0             # avg daily traded value, ₹ crore
    min_price: float = 50.0
    breakout_lookback: int = 20               # prior N-day high = breakout level
    max_extension_pct: float = 7.0            # don't chase >7% above breakout
    atr_stop_mult: float = 1.5                # stop = entry - 1.5*ATR

    # Exit management.
    partial_book_frac: float = 0.5            # sell 50% at target, trail the rest
    trail_atr_mult: float = 2.0               # trail remainder by 2*ATR below close
    time_stop_progress_pct: float = 2.0       # "no progress" threshold for soft time-stop
    time_stop_soft_frac: float = 0.7          # exit if held >= 70% of window w/o progress

    # ── Costs ─────────────────────────────────────────────────────────────────
    commission_pct: float = 0.05              # round-trip-ish per-side cost proxy (%)

    # ── Misc ──────────────────────────────────────────────────────────────────
    use_cache: bool = True                    # reuse downloaded price cache
    seed_label: str = "swing_backtest"

    def goal_capital(self) -> float:
        return self.starting_capital * (1 + self.goal_return_pct / 100.0)
