"""
swing_trading_copilot.py
========================

Daily swing-trading copilot for the **Indian stock market (NSE/BSE)**, built on
top of the **GitHub Copilot CLI / Agent SDK** (the `copilot` command).

It is a sibling of `portfolio_copilot_analysis.py` but purpose-built for
**short-term swing trading** rather than long-term portfolio construction.

The mental model
----------------
You allocate a fixed pool of capital to swing trading. For every position you
enter you expect a target return (default **+20%**) within a maximum holding
window (default **30 days**). When a stock hits its target / peaks you rotate
out and recycle the capital into a fresh opportunity. Losers are cut at a
pre-defined stop loss, and realized losses are deliberately offset by the rest
of the book (see the "loss-offset" rules baked into the prompts).

Run it once a day on your swing book. It will:
  • Review every OPEN position → EXIT (target/peak/time-stop), TRIM/BOOK-PARTIAL,
    HOLD, TRAIL-STOP, or ADD, each with concrete price levels.
  • Screen your watchlist (and surface fresh ideas) for NEW entries that fit the
    20%-in-a-month profile, with entry zone, stop loss, target and position size.
  • Give portfolio-level risk, capital-rotation and loss-offset guidance.

Authentication
--------------
Shells out to the locally-installed `copilot` CLI, which reuses your VS Code
GitHub Copilot session — no API keys or tokens required.

Inputs
------
1. Open swing positions. Each has:
     - symbol       (e.g. "TATAMOTORS")
     - quantity     (int)
     - buy_price    (avg entry per share)
     - entry_date   (optional, "YYYY-MM-DD" — enables time-stop logic)
     - last_price   (optional LTP — auto-filled if Zerodha is used)
     - target_pct   (optional per-trade target override, else global default)
     - stop_loss    (optional per-trade stop price)

   Three ways to supply positions:
     a) --source zerodha           → pulls live holdings via ZerodhaClient
     b) --portfolio-file my.json   → loads a JSON file (schema below)
     c) Inline JSON via --portfolio '<json string>'

2. (Optional) A watchlist of candidate symbols to evaluate for NEW entries:
     --watchlist "TATAMOTORS,DIXON,KAYNES"   (or --watchlist-file watch.txt)

3. (Optional) A free-form directive via --prompt, else the template default.

Templates
---------
  daily     → full daily review: manage open positions + screen for new entries
              + portfolio risk / capital rotation (DEFAULT)
  manage    → only review/triage existing open positions
  discover  → only screen the watchlist + market for NEW swing entries

Position JSON schema
--------------------
    [
      {"symbol": "TATAMOTORS", "quantity": 20, "buy_price": 920.0,
       "entry_date": "2026-06-02", "stop_loss": 880.0, "target_pct": 18},
      {"symbol": "DIXON", "quantity": 3, "buy_price": 14500.0,
       "entry_date": "2026-06-10"}
    ]

Examples
--------
    # Full daily review of live Zerodha swing book + a watchlist
    python swing_trading_copilot.py \
        --source zerodha \
        --watchlist "TATAMOTORS,DIXON,KAYNES,BSE,HUDCO" \
        --target-profit 20 --max-holding-days 30 --risk-per-trade 2 \
        --save swing_today.md

    # Only hunt for fresh ideas from a watchlist file
    python swing_trading_copilot.py \
        --template discover \
        --portfolio '[]' \
        --watchlist-file watchlist.txt

    # Only manage existing positions from a JSON file
    python swing_trading_copilot.py \
        --template manage \
        --portfolio-file sample_swing_portfolio.json

Prerequisites
-------------
- GitHub Copilot CLI installed and signed in:  copilot --version
  If missing:  npm install -g @github/copilot   (then run `copilot` once to auth)
- Optional: COPILOT_BIN  → absolute path to the CLI if not on PATH.
- Optional: COPILOT_MODEL → model name (e.g. claude-sonnet-4.5).

DISCLAIMER: Output is for educational/analytical purposes only and is NOT
investment advice. Swing trading carries real risk of capital loss. A target
of +20% in a month is aggressive and will NOT hit on every trade — disciplined
stop losses and position sizing are what keep you in the game.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, TextIO

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("swing_trading_copilot")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ─── Defaults (all overridable via CLI / env) ─────────────────────────────────

DEFAULT_TARGET_PROFIT_PCT = 20.0   # expected gain per trade
DEFAULT_MAX_HOLDING_DAYS = 30      # rotate out by this many days
DEFAULT_RISK_PER_TRADE_PCT = 2.0   # 2% rule — max capital risked per trade
DEFAULT_MIN_RR = 2.0               # minimum reward:risk ratio


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class SwingPosition:
    symbol: str
    quantity: float
    buy_price: float
    last_price: Optional[float] = None     # LTP — optional, used for live P&L
    entry_date: Optional[date] = None      # enables time-stop / holding-age logic
    target_pct: Optional[float] = None     # per-trade target override
    stop_loss: Optional[float] = None      # per-trade stop price

    @property
    def invested(self) -> float:
        return self.quantity * self.buy_price

    @property
    def current_value(self) -> Optional[float]:
        return self.quantity * self.last_price if self.last_price else None

    @property
    def pnl(self) -> Optional[float]:
        cv = self.current_value
        return (cv - self.invested) if cv is not None else None

    @property
    def pnl_pct(self) -> Optional[float]:
        if self.buy_price and self.last_price:
            return ((self.last_price - self.buy_price) / self.buy_price) * 100
        return None

    @property
    def holding_days(self) -> Optional[int]:
        if self.entry_date is None:
            return None
        return (date.today() - self.entry_date).days

    def target_price(self, default_target_pct: float) -> float:
        tgt = self.target_pct if self.target_pct is not None else default_target_pct
        return self.buy_price * (1 + tgt / 100.0)

    def days_left(self, max_holding_days: int) -> Optional[int]:
        hd = self.holding_days
        return (max_holding_days - hd) if hd is not None else None

    def progress_to_target_pct(self, default_target_pct: float) -> Optional[float]:
        """How far P&L% has travelled toward the target (e.g. 50 = halfway)."""
        if self.pnl_pct is None:
            return None
        tgt = self.target_pct if self.target_pct is not None else default_target_pct
        if tgt == 0:
            return None
        return (self.pnl_pct / tgt) * 100


def _parse_entry_date(raw) -> Optional[date]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date):
        return raw
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    logger.warning("Could not parse entry_date %r; ignoring (time-stop disabled for it).", raw)
    return None


# ─── Position loaders ─────────────────────────────────────────────────────────

def load_positions_from_json(data: List[dict]) -> List[SwingPosition]:
    positions: List[SwingPosition] = []
    for row in data:
        if "symbol" not in row or "quantity" not in row or "buy_price" not in row:
            raise ValueError(
                f"Each position must contain 'symbol', 'quantity', and 'buy_price'. Got: {row}"
            )
        positions.append(
            SwingPosition(
                symbol=str(row["symbol"]).strip().upper(),
                quantity=float(row["quantity"]),
                buy_price=float(row["buy_price"]),
                last_price=float(row["last_price"]) if row.get("last_price") is not None else None,
                entry_date=_parse_entry_date(row.get("entry_date")),
                target_pct=float(row["target_pct"]) if row.get("target_pct") is not None else None,
                stop_loss=float(row["stop_loss"]) if row.get("stop_loss") is not None else None,
            )
        )
    return positions


def load_positions_from_file(path: Path) -> List[SwingPosition]:
    if not path.exists():
        raise FileNotFoundError(f"Position file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Position JSON must be a list of positions.")
    return load_positions_from_json(data)


def load_positions_from_zerodha() -> tuple[List[SwingPosition], Optional[float]]:
    """Pull live holdings + available cash from Zerodha Kite Connect.

    Note: Kite holdings do not carry the swing entry-date, so time-stop logic is
    disabled for Zerodha-sourced positions unless you also pass a JSON file. The
    model still gets full price/P&L context.
    """
    try:
        from zerodha.client import ZerodhaClient
    except ImportError as e:
        raise RuntimeError(
            "Zerodha client unavailable. Ensure 'kiteconnect' is installed."
        ) from e

    client = ZerodhaClient()
    if not client.is_authenticated:
        raise RuntimeError(
            "Zerodha session not authenticated. Run "
            "`python -m zerodha.check_portfolio <request_token>` first."
        )

    raw = client.get_holdings()
    positions: List[SwingPosition] = []
    for h in raw:
        qty = float(h.get("quantity", 0))
        if qty <= 0:
            continue
        positions.append(
            SwingPosition(
                symbol=str(h.get("tradingsymbol", "")).strip().upper(),
                quantity=qty,
                buy_price=float(h.get("average_price", 0)),
                last_price=float(h.get("last_price", 0)) or None,
            )
        )

    cash: Optional[float] = None
    try:
        cash = float(client.get_available_cash())
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not fetch Zerodha available cash: %s", e)

    return positions, cash


def load_watchlist(symbols_csv: Optional[str], watchlist_file: Optional[Path]) -> List[str]:
    """Combine --watchlist CSV and --watchlist-file (one symbol per line or CSV)."""
    out: List[str] = []
    if symbols_csv:
        out.extend(s.strip().upper() for s in symbols_csv.replace("\n", ",").split(",") if s.strip())
    if watchlist_file:
        if not watchlist_file.exists():
            raise FileNotFoundError(f"Watchlist file not found: {watchlist_file}")
        text = watchlist_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.split("#", 1)[0]  # allow trailing comments
            out.extend(s.strip().upper() for s in line.replace("\t", ",").split(",") if s.strip())
    # De-dup, preserve order
    seen = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


# ─── Shared swing-trading playbook (web-researched rules) ──────────────────────
#
# This block encodes the strategy distilled from established swing-trading
# methodology for the Indian market. It is injected into every template so the
# model reasons with a consistent, disciplined framework.

SWING_PLAYBOOK = """
═══════════════════════════════════════════════════════════════════════
SWING-TRADING PLAYBOOK — the framework you MUST reason within
═══════════════════════════════════════════════════════════════════════
Objective: capture a defined move (target return) within a defined holding
window, then ROTATE capital into the next setup. This is momentum/positional
trading on liquid NSE names — NOT long-term investing and NOT intraday.

── A. STOCK-SELECTION / SCREENING FILTERS (a candidate should pass MOST) ──
1. Liquidity: price > ₹50–100, avoid illiquid micro/penny stocks; prefer
   large- and quality mid-caps with high delivery volume. Daily traded value
   comfortably above the size you intend to deploy (mind slippage).
2. Trend: price ABOVE rising 50-DMA and 200-DMA (uptrend); 20-EMA > 50-EMA.
3. Momentum: RSI(14) in the 55–70 band (strong but not extremely overbought
   >75). Fresh MACD bullish crossover / positive histogram is a plus.
4. Structure: clean breakout above a prior swing-high/consolidation/resistance
   OR a controlled pullback to support (20/50-EMA) holding with a bullish
   reversal candle.
5. Volume confirmation: breakout/up-move on volume ≥ 1.5–2× the 20-day average.
   Breakouts WITHOUT volume are suspect.
6. Relative strength: stock and its SECTOR are outperforming Nifty/sector index.
7. Catalyst (edge, not mandatory): earnings momentum, guidance upgrade, order
   wins, sector tailwind, news flow.
8. Volatility fit: enough ATR to reach the target inside the window, but not so
   wild that a sane stop gets whipsawed.

── B. ENTRY ──
- Breakout entry: enter on a confirmed close above resistance with volume; avoid
  chasing if price is already extended >5–7% above the breakout level.
- Pullback entry: enter near 20/50-EMA support with a bullish confirmation candle
  and RSI holding > 50.
- Define entry ZONE (not a single tick) and never average DOWN a losing swing.

── C. STOP LOSS (non-negotiable) ──
- Place stop just below the breakout level / recent swing-low / key EMA, OR
  1–1.5× ATR below entry — whichever gives a sensible invalidation level.
- The setup is INVALID if the stop is hit. Exit. No exceptions, no widening.
- Risk-per-share = entry − stop. The trade must offer reward:risk ≥ {min_rr}:1
  to the target; if not, SKIP it.

── D. POSITION SIZING (the 2% rule) ──
- Risk at most {risk_per_trade}% of TOTAL swing capital on any single trade.
- Shares = (capital × {risk_per_trade}%) / (entry − stop). Round DOWN.
- This caps damage and lets you survive losing streaks. Also respect a sensible
  max number of concurrent positions and per-name concentration cap.

── E. EXIT / PROFIT-BOOKING ──
- Primary target: +{target_profit}% (or the per-trade target / next major
  resistance, whichever is the disciplined choice).
- Book PARTIAL (e.g. 50%) at target and TRAIL the rest (below 20-EMA, last
  swing-low, or 1.5–2× ATR) to ride extended momentum — but protect gains.
- TIME STOP: if a position is near/over the max holding window
  ({max_holding_days} days) and has NOT made meaningful progress, exit and
  redeploy — dead capital is an opportunity cost.
- Reversal exit: exit on a clear bearish signal (close below 20-EMA, bearish
  engulfing at resistance, MACD/RSI bearish divergence, volume distribution).
- Peak detection: if a name is extended far above its moving averages with RSI
  >75 and momentum stalling, lock profits rather than getting greedy.

── F. CAPITAL ROTATION & LOSS-OFFSET DISCIPLINE ──
- Freed capital from exits goes to the BEST available fresh setup — do not force
  it into an existing winner unless a genuinely new entry trigger appears.
- After a STOP-OUT / realized loss: do NOT revenge-trade and do NOT increase
  size to "win it back" fast. Recover through PROCESS — the next high-quality
  setup, correct sizing, and a favourable reward:risk. You may rationally lift
  the target only where the chart/strength genuinely supports a larger move;
  never invent extra risk to manufacture a recovery.
- Track the book's net realized + unrealized P&L vs the target so you know how
  much the winners must carry to offset any losers.

── G. RISK HYGIENE ──
- Mind event risk (earnings dates, RBI policy, results season, F&O expiry).
- Beware gap-down risk on illiquid names; size for slippage.
- Keep a portfolio-level cap on total open risk (sum of per-trade risks).
- Never let a planned swing trade silently turn into a long-term "investment"
  bag just because it went against you.
"""


def _render_playbook(cfg: "SwingConfig") -> str:
    return SWING_PLAYBOOK.format(
        min_rr=_fmt_num(cfg.min_rr),
        risk_per_trade=_fmt_num(cfg.risk_per_trade_pct),
        target_profit=_fmt_num(cfg.target_profit_pct),
        max_holding_days=int(cfg.max_holding_days),
    )


def _fmt_num(v: float) -> str:
    return f"{v:g}"


# ─── Prompt templates ─────────────────────────────────────────────────────────

DAILY_SYSTEM_PROMPT = """You are an elite swing-trading desk analyst for Indian
NSE/BSE equities. You run a disciplined, momentum-based swing book whose single
job is to turn over capital quickly for defined gains while ruthlessly cutting
losers. You are decisive, numeric, and risk-first.

Produce a complete DAILY SWING REVIEW in Markdown with EXACTLY these sections.
Do not ask follow-up questions; where data is missing, state your assumption and
proceed.

## 1. Desk Snapshot
- Total swing capital, deployed vs cash, # open positions, open risk (sum of
  per-trade risk to stops as % of capital).
- Net P&L of the book (realized context if provided + unrealized), and how far
  it is from the stated profit goal.
- One-line market regime read (Nifty/Bank Nifty trend, breadth, risk-on/off) —
  ground this in live data.

## 2. Open Position Triage
For EVERY open position output a compact block:
**<SYMBOL>** — Action: EXIT | BOOK-PARTIAL | HOLD | TRAIL-STOP | ADD
- Entry / LTP / P&L% / holding-days / days-left-in-window / progress-to-target.
- Technical read: trend vs 20/50/200, RSI, MACD, volume, key support/resistance.
- The reason for the action in 1–2 lines.
- Concrete levels: new stop (₹), trail level (₹), target (₹), and qty to
  sell/add if any.
- Flag TIME-STOP breaches (near/over the holding window with no progress) and
  PEAK/exhaustion signals explicitly.

## 3. New Opportunities (Rotation Candidates)
Screen the supplied watchlist FIRST (evaluate each against the playbook), then
add up to 3 fresh high-conviction ideas you surface. For each candidate:
**<SYMBOL>** — Setup: Breakout | Pullback | Momentum
- Why it fits the {target_profit}%-in-{max_holding_days}-days profile (trend,
  RSI, MACD, volume, relative strength, catalyst).
- Entry zone (₹), Stop (₹), Target (₹), Reward:Risk, expected holding window.
- Position size using the {risk_per_trade}% rule against available capital
  (shares + ₹ deployed), and the resulting open-risk add.
- A short verdict: TAKE NOW / WAIT-FOR-TRIGGER / WATCH.
Rank candidates best-first. If nothing qualifies, say so — do not force trades.

## 4. Capital Rotation Plan
- Ordered action list mapping exits → freed capital → best new entries.
- Respect max concurrent positions and concentration caps.
- If there are realized/unrealized losses, state explicitly how the proposed
  book is expected to offset them (through process and reward:risk, NOT by
  inflating risk). No revenge trades.

## 5. Risk & Watch Triggers
- Portfolio-level open risk, event risk (earnings/expiry/policy), liquidity/gap
  risk on any name.
- The exact price/indicator triggers to watch before the next session.

## 6. Caveats
Assumptions, data gaps, and a one-line reminder this is NOT investment advice.

Rules: be specific and numeric (give actual ₹ levels and share counts). Use the
playbook filters as your decision backbone. Prefer FEWER, higher-quality actions
over churn. Never fabricate a price or number — if a live fetch fails, say so.
"""

MANAGE_SYSTEM_PROMPT = """You are an elite swing-trading desk analyst for Indian
NSE/BSE equities, focused TODAY only on triaging the EXISTING open swing book.
You are decisive, numeric, and risk-first. Do not ask follow-up questions.

Produce a Markdown report:

## 1. Book Snapshot
Total deployed, # positions, net unrealized P&L%, open risk to stops, distance
from the profit goal, one-line market-regime read (ground in live data).

## 2. Position-by-Position Triage
For EVERY open position:
**<SYMBOL>** — Action: EXIT | BOOK-PARTIAL | HOLD | TRAIL-STOP | ADD
- Entry / LTP / P&L% / holding-days / days-left / progress-to-target.
- Technicals: trend vs 20/50/200-DMA, RSI(14), MACD, volume, S/R levels.
- Decision rationale (2 lines max).
- Exact levels: revised stop (₹), trailing level (₹), target (₹), qty to
  sell/add.
- Explicitly flag: TARGET HIT / PEAK-exhaustion / TIME-STOP breach / STOP
  threatened / thesis broken.

## 3. Prioritised Action List
Ordered EXIT/BOOK/TRAIL/ADD actions with the capital each frees or commits.
Note how freed capital should be earmarked for rotation. Apply loss-offset
discipline (recover via process, never via inflated risk; no revenge trading).

## 4. Risk & Triggers
Open risk, event risk, and the precise price/indicator triggers to watch next
session.

## 5. Caveats
Assumptions, data gaps, NOT investment advice.

Rules: numeric and specific (real ₹ levels, share counts). Reason strictly
within the supplied swing playbook. Never fabricate numbers — if a fetch fails,
say so.
"""

DISCOVER_SYSTEM_PROMPT = """You are an elite swing-trading screener for Indian
NSE/BSE equities. Your ONLY job today is to surface NEW swing entries that fit
the stated target-return-within-window profile. You are selective and risk-first
— quality over quantity. Do not ask follow-up questions.

Produce a Markdown report:

## 1. Market Regime
One short paragraph on Nifty/Bank Nifty trend, breadth and risk-on/off, grounded
in live data — swing longs work best with a supportive tape; say so if it is not.

## 2. Screened Candidates
Evaluate EVERY symbol in the supplied watchlist against the playbook filters
FIRST, then add up to 5 additional fresh ideas you surface from current market
strength. For EACH candidate, output:
**<SYMBOL>** — Setup: Breakout | Pullback | Momentum | Reversal
- Checklist pass/fail vs the playbook (trend, RSI, MACD, volume, relative
  strength, liquidity, catalyst) — be explicit about which filters pass.
- Entry zone (₹), Stop (₹), Target (₹) [≈{target_profit}% or next resistance],
  Reward:Risk, expected holding window (≤{max_holding_days} days).
- Position size via the {risk_per_trade}% rule against available capital
  (shares + ₹), and the open-risk it adds.
- Verdict: TAKE NOW / WAIT-FOR-TRIGGER / WATCH, with the exact trigger.

## 3. Ranked Shortlist
A best-first ranked table of the qualifying names with Setup, Entry, Stop,
Target, R:R, and Verdict. Exclude anything that fails the filters — if few or
none qualify, say so plainly rather than forcing trades.

## 4. Deployment Plan
Given available capital and the {risk_per_trade}% rule, suggest how many of the
shortlisted names to take now, the ₹ per position, total capital deployed, and
total open risk — staying within sane diversification.

## 5. Caveats
Assumptions, data gaps, NOT investment advice.

Rules: numeric and specific. Reason strictly within the swing playbook. Never
fabricate a price — if a live fetch fails, state it.
"""


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    description: str
    system_prompt: str
    default_directive: str
    needs_positions: bool  # whether the template centres on the open book


DAILY_DIRECTIVE = (
    "Run the full DAILY SWING REVIEW: triage every open position with concrete "
    "actions and price levels, screen the watchlist (and surface fresh ideas) for "
    "new entries that fit the target profile, and give an ordered capital-rotation "
    "and loss-offset plan. Ground every technical and price claim in live data."
)

MANAGE_DIRECTIVE = (
    "Triage the existing open swing book only. For each position give a decisive "
    "EXIT / BOOK-PARTIAL / HOLD / TRAIL-STOP / ADD call with exact stop, trail and "
    "target levels and share counts. Flag target hits, peaks, time-stop breaches "
    "and broken theses. Ground everything in live data."
)

DISCOVER_DIRECTIVE = (
    "Screen the watchlist and current market for NEW swing entries that fit the "
    "target-return-within-window profile. Apply the playbook filters strictly, "
    "give entry/stop/target/R:R and position sizing per candidate, and a ranked "
    "shortlist with a deployment plan. Ground everything in live data."
)


PROMPT_TEMPLATES: dict[str, PromptTemplate] = {
    "daily": PromptTemplate(
        name="daily",
        description="Full daily review: manage open book + screen new entries + rotation plan.",
        system_prompt=DAILY_SYSTEM_PROMPT,
        default_directive=DAILY_DIRECTIVE,
        needs_positions=False,
    ),
    "manage": PromptTemplate(
        name="manage",
        description="Triage existing open positions only (exit/hold/trail/add).",
        system_prompt=MANAGE_SYSTEM_PROMPT,
        default_directive=MANAGE_DIRECTIVE,
        needs_positions=True,
    ),
    "discover": PromptTemplate(
        name="discover",
        description="Screen watchlist + market for new swing entries only.",
        system_prompt=DISCOVER_SYSTEM_PROMPT,
        default_directive=DISCOVER_DIRECTIVE,
        needs_positions=False,
    ),
}

DEFAULT_TEMPLATE_NAME = "daily"


def resolve_template(name: Optional[str]) -> PromptTemplate:
    chosen = (name or os.getenv("SWING_TEMPLATE") or DEFAULT_TEMPLATE_NAME).strip().lower()
    if chosen not in PROMPT_TEMPLATES:
        raise SystemExit(
            f"Unknown template: {chosen!r}. Available: {', '.join(sorted(PROMPT_TEMPLATES))}"
        )
    return PROMPT_TEMPLATES[chosen]


# ─── Web grounding directive ──────────────────────────────────────────────────

WEB_GROUNDING_DIRECTIVE = """
═══════════════════════════════════════════════════════════════════════
MANDATORY LIVE GROUNDING — swing trading lives and dies on FRESH data
═══════════════════════════════════════════════════════════════════════
Before producing ANY call you MUST use your web tools (`web-fetch`, configured
search MCP servers, etc.) to ground prices, technicals and news in CURRENT data.
Stale recall is unacceptable for swing trading.

For each relevant symbol (open positions AND watchlist candidates) attempt to:

1. **Live price & recent action** — current LTP, day range, 52-week range, and
   the last few weeks of % moves / how it sits vs its 20/50/200-DMA. Sources:
     - https://www.nseindia.com/get-quotes/equity?symbol=<SYMBOL>
     - https://www.google.com/finance/quote/<SYMBOL>:NSE
     - https://finance.yahoo.com/quote/<SYMBOL>.NS
2. **Technical posture** — RSI(14), MACD, moving-average alignment, recent
   volume vs average, nearby support/resistance and swing levels.
3. **Catalyst / news (last 1–4 weeks)** — earnings, orders, guidance, sector
   moves, events. Sources: moneycontrol, economictimes, business-standard.
4. **Market regime** — Nifty 50 / Bank Nifty trend & breadth to judge whether
   the tape supports swing longs.

Operating rules:
- Fetch in parallel; ≈2–4 high-signal sources per symbol — do not over-crawl.
- Cite the source inline when you state a number/level/date, e.g. `(src: nse)`.
- If a fetch fails, SAY so and proceed — never fabricate a price or indicator.
- Cross-check the top open positions' LTPs against a live source and flag drift
  from the user-supplied prices.
"""


# ─── Scraper MCP server (custom tool injection) ───────────────────────────────

SCRAPER_MCP_SERVER_NAME = "indian-stock-data"

SCRAPER_TOOLS_DIRECTIVE = f"""
═══════════════════════════════════════════════════════════════════════
PREFERRED RESEARCH TOOLS — Indian-equity scrapers (`{SCRAPER_MCP_SERVER_NAME}` MCP)
═══════════════════════════════════════════════════════════════════════
A dedicated MCP server named `{SCRAPER_MCP_SERVER_NAME}` is attached. It wraps
screener.in + yfinance + TA libraries for NSE/BSE names. **Use these FIRST**,
before `web-fetch`. For swing trading the technical tool is your workhorse:

- `fetch_technical_indicators(symbol)` — RSI, MACD, SMA 20/50/200, Bollinger,
  ADX, ATR, support/resistance. **Your PRIMARY tool** for every position and
  candidate — it drives entry/stop/target/trail decisions.
- `fetch_stock_price(symbol)`          — live LTP, day & 52-week range, % change,
  mkt cap, P/E.
- `fetch_stock_news(symbol)`           — up to 10 recent headlines (catalysts).
- `fetch_fundamentals(symbol)`         — quick ratios / analyst targets (sanity
  check; swing is technical-led but avoid obvious fundamental landmines).
- `fetch_screener_fundamentals(symbol)`— deeper screener.in data when needed.
- `search_nse_stocks(query)`           — resolve a company name → NSE symbol.
- `scrape_url(url)`                    — generic page fallback (moneycontrol /
  ET / livemint) when the dedicated tools don't cover something.

Symbol convention: pass the **plain NSE ticker** (e.g. `TATAMOTORS`, `DIXON`) —
NOT `TATAMOTORS.NS` or `NSE:TATAMOTORS`.

Tool-use protocol:
1. For EVERY open position and watchlist candidate, call
   `fetch_technical_indicators` + `fetch_stock_price` in parallel first — that
   gives you trend, momentum, volatility (ATR for stops) and live price.
2. Add `fetch_stock_news` for any name where a catalyst affects the call.
3. Use `fetch_fundamentals` / `fetch_screener_fundamentals` only as a guardrail.
4. Use `web-fetch` for market-regime (Nifty/Bank Nifty) and anything the
   scrapers don't cover.
5. Cite the tool that surfaced each fact, e.g. `(src: screener.in)` /
   `(src: technicals)`. If a tool fails, say so and try another — never fabricate.
"""


def _augment_with_grounding(
    system_prompt: str,
    web_grounding: bool,
    scraper_tools: bool,
) -> str:
    out = system_prompt.rstrip()
    if web_grounding:
        out += "\n\n" + WEB_GROUNDING_DIRECTIVE.strip()
    if scraper_tools:
        out += "\n\n" + SCRAPER_TOOLS_DIRECTIVE.strip()
    return out + "\n"


def _write_scraper_mcp_config(tmp_dir: Path) -> Path:
    """Write a Copilot CLI MCP config pointing at the local scraper MCP server."""
    repo_root = Path(__file__).resolve().parent
    server_script = repo_root / "mcp_server.py"
    if not server_script.exists():
        raise FileNotFoundError(
            f"Scraper MCP server not found at {server_script}. "
            "Disable with --no-scraper-tools or fix the path."
        )

    config = {
        "mcpServers": {
            SCRAPER_MCP_SERVER_NAME: {
                "type": "stdio",
                "command": sys.executable,
                "args": [str(server_script)],
                "cwd": str(repo_root),
                "tools": ["*"],
            }
        }
    }

    cfg_path = tmp_dir / f"mcp-{uuid.uuid4().hex[:8]}.json"
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return cfg_path


# ─── Config & rendering ───────────────────────────────────────────────────────

@dataclass
class SwingConfig:
    """Swing-trading parameters — all configurable per the user's goal."""
    total_capital: Optional[float] = None
    cash_available: Optional[float] = None
    target_profit_pct: float = DEFAULT_TARGET_PROFIT_PCT
    max_holding_days: int = DEFAULT_MAX_HOLDING_DAYS
    risk_per_trade_pct: float = DEFAULT_RISK_PER_TRADE_PCT
    min_rr: float = DEFAULT_MIN_RR
    max_positions: Optional[int] = None
    risk_appetite: Optional[str] = None  # Low / Moderate / High

    def render(self, deployed_value: float) -> str:
        def money(v: Optional[float]) -> str:
            return f"₹{v:,.2f}" if v is not None else "_not provided_"

        cap = self.total_capital if self.total_capital is not None else (
            (deployed_value + self.cash_available) if self.cash_available is not None else None
        )
        risk_budget = (
            f"₹{cap * self.risk_per_trade_pct / 100:,.2f}" if cap is not None else "_n/a_"
        )
        return (
            f"- **Total Swing Capital**: {money(cap)}\n"
            f"- **Currently Deployed**: ₹{deployed_value:,.2f}\n"
            f"- **Cash Available to Deploy**: {money(self.cash_available)}\n"
            f"- **Target Profit per Trade**: {_fmt_num(self.target_profit_pct)}%\n"
            f"- **Max Holding Window**: {int(self.max_holding_days)} days\n"
            f"- **Risk per Trade (2% rule)**: {_fmt_num(self.risk_per_trade_pct)}% "
            f"(≈ {risk_budget} max risk/trade)\n"
            f"- **Min Reward:Risk**: {_fmt_num(self.min_rr)}:1\n"
            f"- **Max Concurrent Positions**: "
            f"{self.max_positions if self.max_positions is not None else '_not set_'}\n"
            f"- **Risk Appetite**: {self.risk_appetite or '_not provided_'}"
        )


def _positions_table(positions: List[SwingPosition], cfg: SwingConfig) -> str:
    if not positions:
        return "_No open swing positions._"

    rows = [
        "| Symbol | Qty | Entry ₹ | LTP ₹ | P&L % | Held (d) | Left (d) | Target ₹ | Stop ₹ | →Target % |",
        "|--------|----:|--------:|------:|------:|---------:|---------:|---------:|-------:|----------:|",
    ]
    total_invested = 0.0
    total_value = 0.0
    has_ltp = True

    for p in positions:
        total_invested += p.invested
        if p.last_price is None:
            has_ltp = False
        else:
            total_value += p.current_value or 0.0

    for p in positions:
        ltp = f"{p.last_price:,.2f}" if p.last_price is not None else "—"
        pnl_pct = f"{p.pnl_pct:+.2f}" if p.pnl_pct is not None else "—"
        held = str(p.holding_days) if p.holding_days is not None else "—"
        left = str(p.days_left(cfg.max_holding_days)) if p.days_left(cfg.max_holding_days) is not None else "—"
        tgt = f"{p.target_price(cfg.target_profit_pct):,.2f}"
        stop = f"{p.stop_loss:,.2f}" if p.stop_loss is not None else "—"
        prog = p.progress_to_target_pct(cfg.target_profit_pct)
        prog_s = f"{prog:.0f}%" if prog is not None else "—"
        rows.append(
            f"| {p.symbol} | {p.quantity:g} | {p.buy_price:,.2f} | {ltp} | {pnl_pct} "
            f"| {held} | {left} | {tgt} | {stop} | {prog_s} |"
        )

    totals = f"\n**Deployed** — Invested: ₹{total_invested:,.2f}"
    if has_ltp:
        pnl_total = total_value - total_invested
        pnl_pct_total = (pnl_total / total_invested * 100) if total_invested else 0
        totals += (
            f" · Current: ₹{total_value:,.2f} · "
            f"Unrealized P&L: ₹{pnl_total:,.2f} ({pnl_pct_total:+.2f}%)"
        )
    else:
        totals += " · LTP unavailable for some positions; fetch live where needed."

    return "\n".join(rows) + totals


def _watchlist_block(watchlist: List[str]) -> str:
    if not watchlist:
        return "_No watchlist supplied — surface fresh ideas from current market strength._"
    return ", ".join(watchlist)


def build_full_prompt(
    positions: List[SwingPosition],
    watchlist: List[str],
    user_prompt: str,
    cfg: SwingConfig,
    template: PromptTemplate,
    web_grounding: bool = True,
    scraper_tools: bool = True,
) -> str:
    deployed_value = sum(
        (p.current_value if p.current_value is not None else p.invested) for p in positions
    )
    system_prompt = _augment_with_grounding(
        template.system_prompt, web_grounding=web_grounding, scraper_tools=scraper_tools
    )
    # Fill template placeholders that reference configurable goals.
    system_prompt = system_prompt.format(
        target_profit=_fmt_num(cfg.target_profit_pct),
        max_holding_days=int(cfg.max_holding_days),
        risk_per_trade=_fmt_num(cfg.risk_per_trade_pct),
    )
    playbook = _render_playbook(cfg)

    today = date.today().isoformat()
    return (
        f"{system_prompt}\n\n"
        f"{playbook}\n\n"
        f"# Today's Date\n\n{today}\n\n"
        f"# Swing Configuration\n\n{cfg.render(deployed_value)}\n\n"
        f"# Open Swing Positions\n\n{_positions_table(positions, cfg)}\n\n"
        f"# Watchlist (candidates to evaluate for NEW entries)\n\n"
        f"{_watchlist_block(watchlist)}\n\n"
        f"# Request\n\n{user_prompt.strip()}\n"
    )


# ─── GitHub Copilot CLI invocation ────────────────────────────────────────────

def _resolve_copilot_bin() -> str:
    explicit = os.getenv("COPILOT_BIN")
    if explicit:
        if not Path(explicit).exists():
            raise RuntimeError(f"COPILOT_BIN points to non-existent path: {explicit}")
        return explicit

    for name in ("copilot", "copilot.cmd", "copilot.exe"):
        path = shutil.which(name)
        if path:
            return path

    raise RuntimeError(
        "GitHub Copilot CLI not found on PATH.\n"
        "Install with:  npm install -g @github/copilot\n"
        "Then run `copilot` once to authenticate.\n"
        "Or set COPILOT_BIN to the absolute path of the binary."
    )


def run_analysis(
    positions: List[SwingPosition],
    watchlist: List[str],
    user_prompt: str,
    cfg: SwingConfig,
    template: PromptTemplate,
    model: Optional[str] = None,
    extra_cli_args: Optional[List[str]] = None,
    web_grounding: bool = True,
    scraper_tools: bool = True,
    copilot_log: Optional[Path] = None,
    log_level: str = "debug",
) -> str:
    """Invoke the Copilot CLI in non-interactive mode and return its stdout."""
    copilot_bin = _resolve_copilot_bin()
    full_prompt = build_full_prompt(
        positions,
        watchlist,
        user_prompt,
        cfg=cfg,
        template=template,
        web_grounding=web_grounding,
        scraper_tools=scraper_tools,
    )

    tmp_dir = Path.cwd() / ".copilot_tmp"
    tmp_dir.mkdir(exist_ok=True)
    prompt_file = tmp_dir / f"swing-prompt-{uuid.uuid4().hex[:8]}.md"
    prompt_file.write_text(full_prompt, encoding="utf-8")

    short_prompt = (
        f"Read the file `{prompt_file.as_posix()}` in its entirety using your "
        "file-read tool. It contains your system role, a swing-trading playbook, "
        "the swing configuration, the open positions, a watchlist, and a request. "
        "Follow the instructions in that file exactly and respond with ONLY the "
        "final Markdown report — do not echo the prompt or describe what you are doing."
    )

    cmd: List[str] = [
        copilot_bin,
        "-p", short_prompt,
        "--allow-all-tools",
        "--add-dir", str(tmp_dir),
        "-s",
    ]

    if web_grounding:
        cmd.append("--allow-all-urls")

    scraper_cfg_file: Optional[Path] = None
    if scraper_tools:
        try:
            scraper_cfg_file = _write_scraper_mcp_config(tmp_dir)
            cmd.extend(["--additional-mcp-config", f"@{scraper_cfg_file}"])
            logger.info("Scraper MCP server attached via %s", scraper_cfg_file.name)
        except FileNotFoundError as e:
            logger.warning("Skipping scraper tools: %s", e)
            scraper_tools = False

    if copilot_log is not None:
        cmd.extend(["--log-level", log_level])
        copilot_log.parent.mkdir(parents=True, exist_ok=True)

    chosen_model = model or os.getenv("COPILOT_MODEL")
    if chosen_model:
        cmd.extend(["--model", chosen_model])

    if extra_cli_args:
        cmd.extend(extra_cli_args)

    logger.info(
        "Invoking Copilot CLI (%s) — template=%s, %d positions, %d watchlist%s "
        "(prompt: %s, %d bytes, web_grounding=%s, scraper_tools=%s, log=%s)",
        copilot_bin,
        template.name,
        len(positions),
        len(watchlist),
        f", model={chosen_model}" if chosen_model else "",
        prompt_file.name,
        prompt_file.stat().st_size,
        web_grounding,
        scraper_tools,
        copilot_log if copilot_log else "—",
    )

    log_handle: Optional[TextIO] = None
    if copilot_log is not None:
        log_handle = open(copilot_log, "a", encoding="utf-8", errors="replace")
        log_handle.write(
            f"\n{'='*72}\n"
            f"Swing Copilot run @ {datetime.now().isoformat(timespec='seconds')}\n"
            f"cmd: {cmd}\n"
            f"template={template.name}  web_grounding={web_grounding}  "
            f"scraper_tools={scraper_tools}  model={chosen_model}\n"
            f"{'='*72}\n"
        )
        log_handle.flush()

    def _pump_stderr(pipe, sink: Optional[TextIO]) -> None:
        try:
            for raw in iter(pipe.readline, ""):
                if not raw:
                    break
                sys.stderr.write(f"[copilot] {raw}")
                sys.stderr.flush()
                if sink is not None:
                    sink.write(raw)
                    sink.flush()
        finally:
            try:
                pipe.close()
            except Exception:  # noqa: BLE001
                pass

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        stderr_thread = threading.Thread(
            target=_pump_stderr,
            args=(proc.stderr, log_handle),
            daemon=True,
        )
        stderr_thread.start()

        captured: List[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            captured.append(line)
            print(line, end="", flush=True)

        return_code = proc.wait()
        stderr_thread.join(timeout=5.0)

        if return_code != 0:
            raise RuntimeError(
                f"Copilot CLI exited with code {return_code}. "
                f"See log: {copilot_log}" if copilot_log else
                f"Copilot CLI exited with code {return_code}."
            )

        return "".join(captured)
    finally:
        if log_handle is not None:
            try:
                log_handle.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            prompt_file.unlink(missing_ok=True)
        except OSError:
            pass
        if scraper_cfg_file is not None:
            try:
                scraper_cfg_file.unlink(missing_ok=True)
            except OSError:
                pass


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _env_float(name: str) -> Optional[float]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        logger.warning("Env var %s=%r is not a number; ignoring.", name, raw)
        return None


def _env_int(name: str) -> Optional[int]:
    v = _env_float(name)
    return int(v) if v is not None else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Daily swing-trading copilot for Indian equities using the GitHub "
            "Copilot CLI. Templates: daily (full review), manage (open book only), "
            "discover (new ideas only)."
        ),
    )
    parser.add_argument(
        "--template",
        choices=sorted(PROMPT_TEMPLATES),
        default=None,
        help=(
            "Which template to use. Overrides SWING_TEMPLATE env var. "
            f"Default: {DEFAULT_TEMPLATE_NAME}. "
            + " · ".join(f"{t.name}: {t.description}" for t in PROMPT_TEMPLATES.values())
        ),
    )

    # ─── Position sources ───
    parser.add_argument(
        "--source",
        choices=["zerodha", "file", "inline"],
        help="Where to load open positions from. If omitted, inferred from other flags.",
    )
    parser.add_argument(
        "--portfolio-file",
        type=Path,
        help="Path to a JSON file with open swing positions (list).",
    )
    parser.add_argument(
        "--portfolio",
        type=str,
        help="Inline JSON list of open swing positions. Use '[]' for none.",
    )

    # ─── Watchlist ───
    parser.add_argument(
        "--watchlist",
        type=str,
        default=os.getenv("SWING_WATCHLIST") or None,
        help="Comma-separated NSE symbols to evaluate for NEW entries.",
    )
    parser.add_argument(
        "--watchlist-file",
        type=Path,
        default=None,
        help="Path to a file of candidate symbols (CSV or one-per-line; '#' comments allowed).",
    )

    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Free-form directive appended after the template's system prompt. "
             "If omitted, the template's default directive is used.",
    )
    parser.add_argument("--model", type=str, default=None,
                        help="Copilot model name (overrides COPILOT_MODEL env var).")
    parser.add_argument("--save", type=Path,
                        help="Optional path to save the model's response as Markdown.")
    parser.add_argument("--copilot-arg", action="append", default=[],
                        help="Extra arg to pass through to `copilot` (repeatable).")

    parser.add_argument(
        "--web-grounding",
        action=argparse.BooleanOptionalAction,
        default=(os.getenv("WEB_GROUNDING", "true").strip().lower() not in {"0", "false", "no", "off"}),
        help="Force the model to ground in live data via web tools. Default: on.",
    )
    parser.add_argument(
        "--scraper-tools",
        action=argparse.BooleanOptionalAction,
        default=(os.getenv("SCRAPER_TOOLS", "true").strip().lower() not in {"0", "false", "no", "off"}),
        help="Attach the local scraper MCP server (screener.in / yfinance / TA). Default: on.",
    )
    parser.add_argument(
        "--copilot-log",
        type=Path,
        default=None,
        help="Save Copilot CLI stderr (tool-call debug) to this file AND tee live. "
             "Pass 'auto' to use logs/swing-copilot-<timestamp>.log.",
    )
    parser.add_argument(
        "--copilot-log-level",
        choices=["error", "warn", "info", "debug"],
        default="debug",
        help="Copilot CLI --log-level when --copilot-log is set. Default: debug.",
    )

    # ─── Swing configuration (the user's goal, all configurable) ───
    parser.add_argument("--total-capital", type=float, default=_env_float("SWING_TOTAL_CAPITAL"),
                        help="Total capital allocated to swing trading (₹).")
    parser.add_argument("--cash", type=float, default=_env_float("SWING_CASH"),
                        help="Cash available to deploy (₹). Auto-filled from Zerodha if --source=zerodha.")
    parser.add_argument("--target-profit", type=float,
                        default=_env_float("SWING_TARGET_PROFIT") or DEFAULT_TARGET_PROFIT_PCT,
                        help=f"Target profit %% per trade. Default: {DEFAULT_TARGET_PROFIT_PCT}.")
    parser.add_argument("--max-holding-days", type=int,
                        default=_env_int("SWING_MAX_HOLDING_DAYS") or DEFAULT_MAX_HOLDING_DAYS,
                        help=f"Max holding window in days. Default: {DEFAULT_MAX_HOLDING_DAYS}.")
    parser.add_argument("--risk-per-trade", type=float,
                        default=_env_float("SWING_RISK_PER_TRADE") or DEFAULT_RISK_PER_TRADE_PCT,
                        help=f"Max %% of capital risked per trade (2%% rule). Default: {DEFAULT_RISK_PER_TRADE_PCT}.")
    parser.add_argument("--min-rr", type=float,
                        default=_env_float("SWING_MIN_RR") or DEFAULT_MIN_RR,
                        help=f"Minimum reward:risk ratio to take a trade. Default: {DEFAULT_MIN_RR}.")
    parser.add_argument("--max-positions", type=int, default=_env_int("SWING_MAX_POSITIONS"),
                        help="Max concurrent open positions.")
    parser.add_argument("--risk-appetite", type=str,
                        default=os.getenv("SWING_RISK_APPETITE") or None,
                        choices=["Low", "Moderate", "High", "low", "moderate", "high"],
                        help="Risk appetite (Low / Moderate / High).")
    return parser.parse_args()


def _resolve_positions(args: argparse.Namespace) -> tuple[List[SwingPosition], Optional[float]]:
    source = args.source
    if not source:
        if args.portfolio_file:
            source = "file"
        elif args.portfolio is not None:
            source = "inline"
        else:
            source = "zerodha"

    if source == "zerodha":
        return load_positions_from_zerodha()
    if source == "file":
        if not args.portfolio_file:
            raise SystemExit("--portfolio-file is required when --source=file")
        return load_positions_from_file(args.portfolio_file), None
    if source == "inline":
        if args.portfolio is None:
            raise SystemExit("--portfolio is required when --source=inline")
        try:
            data = json.loads(args.portfolio)
        except json.JSONDecodeError as e:
            raise SystemExit(f"Invalid --portfolio JSON: {e}") from e
        return load_positions_from_json(data), None
    raise SystemExit(f"Unknown source: {source}")


def main() -> int:
    args = _parse_args()
    try:
        positions, auto_cash = _resolve_positions(args)
    except Exception as e:
        logger.error("Failed to load positions: %s", e)
        return 2

    try:
        watchlist = load_watchlist(args.watchlist, args.watchlist_file)
    except Exception as e:
        logger.error("Failed to load watchlist: %s", e)
        return 2

    template = resolve_template(args.template)

    if template.needs_positions and not positions:
        logger.error(
            "Template '%s' requires open positions, but none were loaded. "
            "Use --template discover to hunt for new ideas instead.",
            template.name,
        )
        return 2

    if not positions and not watchlist:
        logger.error(
            "Nothing to analyze: no open positions and no watchlist. "
            "Supply --portfolio/--portfolio-file/--source and/or --watchlist."
        )
        return 2

    user_directive = args.prompt if args.prompt is not None else template.default_directive
    cash_available = args.cash if args.cash is not None else auto_cash

    cfg = SwingConfig(
        total_capital=args.total_capital,
        cash_available=cash_available,
        target_profit_pct=args.target_profit,
        max_holding_days=args.max_holding_days,
        risk_per_trade_pct=args.risk_per_trade,
        min_rr=args.min_rr,
        max_positions=args.max_positions,
        risk_appetite=(args.risk_appetite.capitalize() if args.risk_appetite else None),
    )

    print(f"\n=== Swing Copilot — {date.today().isoformat()} ===")
    print(f"Template:        {template.name} — {template.description}")
    print(f"Open positions:  {len(positions)}")
    for p in positions:
        ed = f" since {p.entry_date.isoformat()}" if p.entry_date else ""
        print(f"  {p.symbol:<15} qty={p.quantity:<6g} entry=₹{p.buy_price:,.2f}{ed}")
    print(f"Watchlist:       {len(watchlist)} symbols" + (f" ({', '.join(watchlist)})" if watchlist else ""))
    print("=" * 50)
    print(f"Target profit:   {_fmt_num(cfg.target_profit_pct)}% per trade")
    print(f"Max holding:     {int(cfg.max_holding_days)} days")
    print(f"Risk/trade:      {_fmt_num(cfg.risk_per_trade_pct)}%  ·  Min R:R {_fmt_num(cfg.min_rr)}:1")
    if cfg.total_capital is not None:
        print(f"Total capital:   ₹{cfg.total_capital:,.2f}")
    if cash_available is not None:
        print(f"Cash available:  ₹{cash_available:,.2f}")
    if cfg.max_positions is not None:
        print(f"Max positions:   {cfg.max_positions}")
    if cfg.risk_appetite is not None:
        print(f"Risk appetite:   {cfg.risk_appetite}")
    print(f"Web grounding:   {'ON' if args.web_grounding else 'OFF'}  ·  "
          f"Scraper tools: {'ON' if args.scraper_tools else 'OFF'}")

    copilot_log_path: Optional[Path] = args.copilot_log
    if copilot_log_path is not None and str(copilot_log_path).lower() == "auto":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        copilot_log_path = Path("logs") / f"swing-copilot-{stamp}.log"
    if copilot_log_path is not None:
        print(f"Copilot log:     {copilot_log_path} (level={args.copilot_log_level})")
    print("=" * 50 + "\n")

    try:
        result = run_analysis(
            positions=positions,
            watchlist=watchlist,
            user_prompt=user_directive,
            cfg=cfg,
            template=template,
            model=args.model,
            extra_cli_args=args.copilot_arg,
            web_grounding=args.web_grounding,
            scraper_tools=args.scraper_tools,
            copilot_log=copilot_log_path,
            log_level=args.copilot_log_level,
        )
    except Exception as e:
        logger.exception("Analysis failed: %s", e)
        return 1

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(result, encoding="utf-8")
        logger.info("Saved swing analysis to %s", args.save)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
