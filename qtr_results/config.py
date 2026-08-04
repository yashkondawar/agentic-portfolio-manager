"""Configuration and shared defaults for the quarterly-results strategy.

All tunables (selection thresholds, target band, trailing-stop ratio, holding
window) and state-file locations live here so the rest of the package stays
free of magic numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

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

# ── B8b: sector-relative debt gate (validated in backtesting, now live) ─────
# The flat MAX_DEBT_TO_EQUITY judges every business against the same near-zero
# bar, so structurally capital-intensive winners (shippers, cement, capital
# goods, utilities) are rejected on leverage that is normal — even exemplary —
# FOR THEIR SECTOR. Live miss that motivated this: GESHIP posted +155% YoY
# profit (strength 92/100) but the daily run dropped it purely because its
# D/E 0.064 > the 0.05 cap. In "sector_relative" mode the cap becomes
#     max(MAX_DEBT_TO_EQUITY, SECTOR_DEBT_FACTOR × sector-median D/E)
# so an asset-light sector collapses to the tight floor while a capital-
# intensive one earns a proportional allowance. A name is judged against its
# OWN sector's balance-sheet norm, not an IT company's. The backtest (nifty500,
# 2023-2026) lifted hedged alpha +6.9% → +63.4% (Sharpe 0.24 → 1.40, PF 1.24 →
# 2.11) and rescued the H2 correction regime from a LOSING book to +36% — the
# improvement concentrated in the HARD regime, not a bull. Set
# DEBT_GATE_MODE = "absolute" to restore the flat-cap behaviour.
DEBT_GATE_MODE = "sector_relative"   # "sector_relative" | "absolute"
SECTOR_DEBT_FACTOR = 2.0             # cap = factor × sector-median D/E (floor'd)

# Structural per-sector median point-in-time debt/equity, precomputed ONCE from
# the Nifty-500 backtest universe (financials excluded; sectors with < 4 peers
# omitted → they fall back to the flat floor). Sector capital-intensity is
# structurally stable, so a single baked median per sector is a fair, low-
# variance threshold that needs no per-run computation. yfinance sector labels.
SECTOR_MEDIAN_DE = {
    "Basic Materials": 0.2911,
    "Communication Services": 0.0252,
    "Consumer Cyclical": 0.3106,
    "Consumer Defensive": 0.1412,
    "Energy": 0.5719,
    "Healthcare": 0.2579,
    "Industrials": 0.1258,
    "Real Estate": 0.4844,
    "Technology": 0.0988,
    "Utilities": 1.3148,
}


def sector_debt_cap(sector: Optional[str]) -> float:
    """Leverage cap for ``sector`` = max(floor, factor × sector-median D/E).

    An unknown sector, or one absent from the baked baseline (too few peers),
    falls back to the flat ``MAX_DEBT_TO_EQUITY`` floor — a data-thin sector is
    never handed a looser gate by accident.
    """
    floor = MAX_DEBT_TO_EQUITY if MAX_DEBT_TO_EQUITY is not None else float("inf")
    med = SECTOR_MEDIAN_DE.get(sector) if sector else None
    if med is None:
        return floor
    return max(floor, SECTOR_DEBT_FACTOR * med)


# ── Tier-2 LLM qualitative conviction layer ────────────────────────────────
# After the cheap mechanical gates (`is_strong` + debt) have selected a shortlist,
# a point-in-time LLM read of the actual filing (results PDF / investor
# presentation / concall) plus recent news / order-book / sector sentiment scores
# each candidate's *conviction* (0-1). The LLM can only REMOVE or SIZE picks that
# already passed the mechanical filters — it never adds un-vetted names. This is
# the qualitative judgement a skilled manual trader applies and that the purely
# mechanical numbers (largely priced-in) cannot capture.
#   * Gate:  drop verdict == "skip" or conviction < MIN_CONVICTION.
#   * Rank:  order the shortlist by conviction × strength.
#   * Shape exit: high-conviction names ride toward TARGET_MAX with a longer hold;
#                 low-conviction names use the tighter TARGET_MIN with a shorter hold.
# Disable the whole layer with USE_CONVICTION_LLM = False (falls back to the
# mechanical-only behaviour, unchanged). Any LLM/parse failure degrades gracefully
# to a neutral verdict so a run is never broken by the qualitative step.
USE_CONVICTION_LLM = True
MIN_CONVICTION = 0.45          # gate: drop shortlisted names scoring below this
MAX_CONVICTION_EVALS = 15      # cap LLM calls per run (cost / latency guard)
CONVICTION_MODEL = None        # None → Copilot CLI default model
CONVICTION_SHAPES_EXIT = True  # map conviction → target band + holding window
# Holding-window multipliers applied to MAX_HOLDING_DAYS across the conviction
# range [0,1] (linear): a low-conviction pick is cut sooner, a high-conviction one
# is allowed to ride the move longer.
HOLD_DAYS_MIN_FACTOR = 0.7
HOLD_DAYS_MAX_FACTOR = 1.6

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
