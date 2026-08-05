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
# also live inside it. With ride-the-wave exit (DISABLE_PROFIT_TARGET, below)
# this target is a REFERENCE only — the position is not clipped at it.
TARGET_MIN_PCT = 10.0
TARGET_MAX_PCT = 20.0

# ── Exit mechanics (ported from the winning nifty500 2023-2026 backtest) ────
# "Ride-the-wave": disable the fixed PE-rerating profit target and let a genuine
# earnings-momentum winner run the full swing, closing only on the ATR trailing
# stop or the time-stop. On the Nifty-500/2023-2026 study the +20% cap was
# almost never the binding exit (only 11 of 70 winners exceeded it) and clipped
# the few real runners, so ride-the-wave dominated the capped variant on every
# axis. Set False to restore the fixed-target behaviour.
DISABLE_PROFIT_TARGET = True

# ATR-based trailing stop, DECOUPLED from the target. The legacy stop was
# target_pct/2 (tight 5-10% stops on a 20% target) which whipsawed volatile
# mid/small-caps out on the first normal pullback and, perversely, gave the
# highest-conviction picks the TIGHTEST stops. Instead the stop distance is
# ATR_STOP_MULTIPLIER x ATR(ATR_PERIOD) measured in each stock's own volatility.
# The 6x multiplier was the most REGIME-STABLE setting in a split-half test
# (H1 17.6% / H2 18.6% CAGR — the only value that repeated across both halves).
# When ATR can't be computed (thin history) fall back to FALLBACK_STOP_PCT.
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 6.0
FALLBACK_STOP_PCT = 8.0

# Trailing stop distance = target_pct * TRAILING_STOP_RATIO. LEGACY: only used
# when ATR sizing is unavailable and the older percent-based path is taken.
TRAILING_STOP_RATIO = 0.5

# ── Holding window ─────────────────────────────────────────────────────────
# Post-earnings-announcement drift (PEAD) in Indian equities is strongest over
# 30-90 days after declaration, not 15-21 (Sehgal & Bijoy 2015; NSE working
# papers). The old 21-day (3-week) time-stop killed winners well before the
# fundamental thesis could play out; the wide ATR trail needs room to ride, so
# the horizon is 90 days (matches the backtest). Conviction still shortens or
# extends this per name via HOLD_DAYS_*_FACTOR.
MAX_HOLDING_DAYS = 90

# ── Portfolio sizing (the capital overlay the live tracker previously lacked) ─
# The live strategy was a pure signal/ledger tracker with no position sizing, so
# it emitted no qty / ₹ / risk. It now sizes exactly like the backtest: risk a
# fixed % of equity per trade, where per-share risk is the ATR-based stop
# distance, capped by a per-name concentration limit, a max open-position count
# and available cash. Every value is overridable from the strategy params.
STARTING_CAPITAL = 500_000.0   # ₹5,00,000 sizing base (matches the backtest)
RISK_PER_TRADE_PCT = 4.0       # validated free-lunch sweet spot (2% base → 4%)
MAX_POSITIONS = 10             # max concurrent open positions (portfolio cap)
MAX_POSITION_PCT = 20.0        # per-name concentration cap (% of equity)
COMMISSION_PCT = 0.20          # per-side all-in cost proxy (STT+charges+slippage)
PORTFOLIO_PATH = STATE_DIR / "portfolio.json"

# ── Entry-quality filters (validated in the backtest; data-gap-safe) ────────
# These strip the pathological trades the backtest showed repeatedly stopped
# out. Both DEGRADE SAFELY: if the point-in-time data can't be fetched the name
# is NOT rejected (consistent with the debt-gate philosophy and the GESHIP
# lesson — a data gap must never silently drop a strong result).
#   * Uptrend: require close > SMA(TREND_MA_PERIOD) and a non-declining slope —
#     a clean "not broken" check that removes "great result inside a downtrend".
#   * Liquidity: require median 20-day rupee turnover >= the floor, to avoid
#     micro-cap slippage / effectively-illiquid index survivors.
REQUIRE_UPTREND = True
TREND_MA_PERIOD = 20
MIN_LIQUIDITY_MEDIAN_20D = 5_00_00_000.0  # ₹5 crore
HISTORY_PERIOD = "1y"          # yfinance OHLC window for ATR / SMA / turnover

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
