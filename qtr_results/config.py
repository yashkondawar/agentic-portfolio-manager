"""Configuration and shared defaults for the quarterly-results strategy.

All tunables (selection thresholds, target band, trailing-stop ratio, holding
window) and state-file locations live here so the rest of the package stays
free of magic numbers.
"""

from __future__ import annotations

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PACKAGE_DIR = Path(__file__).resolve().parent
STATE_DIR = PACKAGE_DIR / "state"
LEDGER_PATH = STATE_DIR / "ledger.json"
MEMORY_JSON_PATH = STATE_DIR / "memory.json"
MEMORY_MD_PATH = STATE_DIR / "memory.md"
# Persistent seen-cache for NSE filed-results delta detection.
NSE_SEEN_PATH = STATE_DIR / "nse_seen.json"

# ── "Strong result" selection thresholds (percent) ─────────────────────────
MIN_YOY_PROFIT_GROWTH = 20.0
MIN_QOQ_PROFIT_GROWTH = 5.0
MIN_YOY_EPS_GROWTH = 15.0
MIN_YOY_SALES_GROWTH = 10.0

# ── Balance-sheet quality gate (B8, validated in backtesting) ──────────────
# A "strong result" in a debt-heavy business whipsaws out of the trailing stop
# far more often than the same beat in a clean-balance-sheet compounder. Gating
# on point-in-time debt/equity ≤ 0.05 (Borrowings ÷ (Equity Capital + Reserves)
# from the latest annual balance sheet) lifted the 1-year Nifty-200 backtest from
# +2.3% → +11.7% (PF 1.13 → 2.17) and validated out-of-sample on Nifty-500/3yr
# (+4.2% → +12.5%). Banks/NBFCs are structurally levered, so they are exempt
# unless APPLY_QUALITY_TO_FINANCIALS is enabled. Set MAX_DEBT_TO_EQUITY = None
# to disable the gate; a missing value never rejects (data-gap safe).
MAX_DEBT_TO_EQUITY = 0.05
APPLY_QUALITY_TO_FINANCIALS = False

# ── Target band (percent) ──────────────────────────────────────────────────
# PE-rerating upside is floored/capped into this band; static fallback tiers
# also live inside it.
TARGET_MIN_PCT = 10.0
TARGET_MAX_PCT = 20.0

# Trailing stop distance = target_pct * TRAILING_STOP_RATIO  (user: goal / 2).
TRAILING_STOP_RATIO = 0.5

# ── Holding window ─────────────────────────────────────────────────────────
MAX_HOLDING_WEEKS = 3
MAX_HOLDING_DAYS = MAX_HOLDING_WEEKS * 7

# ── Static target tiers (strength_score threshold -> target_pct) ───────────
# Used when PE / EPS data is missing so a re-rating target can't be computed.
STATIC_TARGET_TIERS = [
    (75.0, TARGET_MAX_PCT),   # very strong
    (55.0, 15.0),             # strong
    (0.0, TARGET_MIN_PCT),    # qualifying
]

# ── Discovery ──────────────────────────────────────────────────────────────
DEFAULT_LOOKBACK_DAYS = 1  # how many days back (incl. today) to treat as "just declared"


def ensure_state_dir() -> None:
    """Create the state directory if it does not yet exist."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
