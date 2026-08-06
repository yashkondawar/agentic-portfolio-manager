"""
portfolio_copilot_analysis.py
=============================

Standalone script that performs a holistic portfolio analysis using the
**GitHub Copilot CLI / Agent SDK** (the `copilot` command).

It shells out to the locally-installed `copilot` CLI, which reuses the
VS Code GitHub Copilot session for authentication — so no API keys,
tokens, or env vars are required as long as you can run `copilot` in
a terminal.

Inputs
------
1. A portfolio of stocks. Each holding has:
     - symbol       (e.g. "RELIANCE")
     - quantity     (int)
     - buy_price    (avg cost per share)
     - last_price   (optional, current LTP — auto-filled if Zerodha is used)

   Three ways to supply it:
     a) --source zerodha           → pulls live holdings via ZerodhaClient
     b) --portfolio-file my.json   → loads a JSON file (see schema below)
     c) Inline JSON via --portfolio '<json string>'

2. A single analysis prompt describing what you want
   (e.g. "Identify overweight positions and suggest a rebalance toward
   long-term defensive growth.").

Output
------
Structured, model-generated analysis containing:
  • Per-stock thesis (fundamentals, momentum, risk)
  • Concentration / sector / risk diagnostics on the whole book
  • Concrete restructuring instructions (BUY MORE / TRIM / EXIT / HOLD)
    with target weights and rationale.

Prerequisites
-------------
- GitHub Copilot CLI installed and signed in.
  Verify with:    copilot --version
  If missing:     npm install -g @github/copilot   (then run `copilot` once to auth)
- Optional: set COPILOT_BIN to the absolute path of the CLI if it isn't on PATH.
- Optional: set COPILOT_MODEL to choose a model (e.g. claude-sonnet-4.5).

Portfolio JSON schema
---------------------
    [
        {"symbol": "RELIANCE", "quantity": 10, "buy_price": 2450.5},
        {"symbol": "TCS",      "quantity":  5, "buy_price": 3800.0, "last_price": 4100.2}
    ]

Examples
--------
    # Use live Zerodha holdings
    python portfolio_copilot_analysis.py \
        --source zerodha \
        --prompt "Restructure for the next 12 months favouring quality compounders."

    # Use a JSON file
    python portfolio_copilot_analysis.py \
        --portfolio-file sample_portfolio.json \
        --prompt "Reduce IT-sector concentration and add defensive names." \
        --save analysis.md
"""

# NOTE: intentionally NOT using `from __future__ import annotations`. The
# dataclasses below only reference concrete, already-imported types, and
# stringized annotations force dataclasses into a code path
# (`sys.modules[cls.__module__].__dict__`) that raises AttributeError when this
# module is loaded by a loader that doesn't register it in sys.modules (e.g.
# the Copilot agent runtime imports it as a bare top-level module). Using real
# annotations keeps class creation independent of sys.modules state.
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TextIO

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("portfolio_copilot_analysis")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ─── Data model ────────────────────────────────────────────────────────────

@dataclass
class Holding:
    symbol: str
    quantity: float
    buy_price: float
    last_price: Optional[float] = None  # LTP — optional, used for P&L context

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
        if self.invested and self.last_price:
            return ((self.last_price - self.buy_price) / self.buy_price) * 100
        return None


# ─── Portfolio loaders ─────────────────────────────────────────────────────

def load_portfolio_from_json(data: List[dict]) -> List[Holding]:
    holdings: List[Holding] = []
    for row in data:
        if "symbol" not in row or "quantity" not in row or "buy_price" not in row:
            raise ValueError(
                f"Each holding must contain 'symbol', 'quantity', and 'buy_price'. Got: {row}"
            )
        holdings.append(
            Holding(
                symbol=str(row["symbol"]).strip().upper(),
                quantity=float(row["quantity"]),
                buy_price=float(row["buy_price"]),
                last_price=float(row["last_price"]) if row.get("last_price") is not None else None,
            )
        )
    return holdings


def load_portfolio_from_file(path: Path) -> List[Holding]:
    if not path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Portfolio JSON must be a list of holdings.")
    return load_portfolio_from_json(data)


def load_portfolio_from_zerodha() -> tuple[List[Holding], Optional[float]]:
    """Pull live holdings + available cash from Zerodha Kite Connect."""
    try:
        from zerodha.client import ZerodhaClient
    except ImportError as e:
        raise RuntimeError(
            "Zerodha client unavailable. Ensure 'kiteconnect' is installed."
        ) from e

    client = ZerodhaClient()
    if not client.is_authenticated:
        raise RuntimeError(
            "Zerodha session not authenticated. Run `python -m zerodha.check_portfolio <request_token>` first."
        )

    raw = client.get_holdings()
    holdings: List[Holding] = []
    for h in raw:
        qty = float(h.get("quantity", 0))
        if qty <= 0:
            continue
        holdings.append(
            Holding(
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

    return holdings, cash


# ─── Prompt building ───────────────────────────────────────────────────────
#
# Two named prompt templates ship with this script. Pick one via the
# `--template` flag, or via the `PROMPT_TEMPLATE` env var, or fall back to
# the default ("forensic").
#
#   forensic  → exhaustive 10-part institutional review (new)
#   concise   → focused 5-section restructuring brief (original)
#

# ─── Template: concise restructuring (original prompt) ────────────────────

CONCISE_SYSTEM_PROMPT = """You are a senior equity portfolio analyst
specialising in Indian NSE-listed stocks. You produce rigorous,
evidence-based assessments and concrete restructuring instructions.

Your response MUST follow this exact structure (use Markdown):

## 1. Portfolio Snapshot
- Total invested capital, current value, absolute and % P&L
- Concentration metrics (top 3 positions as % of book)
- Inferred sector mix (best-effort, label any uncertainty)

## 2. Per-Stock Analysis
For EACH holding, produce a compact block:
**<SYMBOL>** — Verdict: BUY MORE | HOLD | TRIM | EXIT
- Thesis (2-4 lines): business quality, growth drivers, key risks
- Valuation stance (rich / fair / cheap with reasoning)
- Position-level risk flags

## 3. Portfolio-Level Diagnostics
- Concentration risk
- Sector / style / factor tilts
- Correlation or thematic overlaps
- Liquidity & event risks

## 4. Restructuring Plan
A clear, ordered action list. For every action specify:
- Symbol, Action (BUY / SELL), Quantity (or % of position), Rationale
- Suggested new target weight (%) for each holding kept
- Any new names to add (max 3) with justification and target weight

## 5. Caveats
Briefly list assumptions, data gaps, and that this is NOT investment advice.

Rules:
- Be specific and numeric where possible.
- If you lack data, state the assumption rather than fabricating numbers.
- Keep tone professional, terse, and actionable.
- Do not ask follow-up questions. Produce the full report in one response.
"""

CONCISE_USER_DIRECTIVE = (
    "Perform a detailed analysis of every holding in this portfolio and "
    "produce concrete restructuring instructions. For each stock cover the "
    "business, recent operational/financial trajectory, valuation, technical "
    "setup, and key risks. Then assess the portfolio holistically "
    "(concentration, sector tilts, correlations, drawdown risk) and give an "
    "ordered, executable rebalancing plan with target weights, suggested "
    "BUY/SELL quantities, and rationale. Conclude with risk-management "
    "actions (stop levels, hedges if relevant) and key monitoring triggers."
)


# ─── Template: forensic 10-part review (new) ──────────────────────────────

FORENSIC_SYSTEM_PROMPT = """You are an institutional equity analyst, forensic
accountant, portfolio manager, and capital allocator.

Analyse the supplied portfolio as if you are managing a concentrated fund
whose objective is to maximise long-term risk-adjusted returns.

You MUST produce the complete 10-part report described below, in order,
using Markdown. Do not skip sections. Do not ask follow-up questions —
where you lack data, state your assumption explicitly and proceed.

═══════════════════════════════════════════════════════════════════════
PART 1 — Portfolio Overview
═══════════════════════════════════════════════════════════════════════
1. Portfolio Summary
   - Number of stocks
   - Sector allocation
   - Market-cap allocation (large / mid / small / micro)
   - Growth vs Value mix
   - Cyclical vs Non-cyclical exposure
   - Domestic vs Export exposure
2. Portfolio Strength Score        (/10)
3. Portfolio Risk Score            (/10)
4. Portfolio Quality Score         (/10)
5. Portfolio Diversification Score (/10)
6. Expected CAGR ranges:
   - Bear Case
   - Base Case
   - Bull Case

═══════════════════════════════════════════════════════════════════════
PART 2 — Individual Stock Deep Dive
═══════════════════════════════════════════════════════════════════════
For EVERY stock in the portfolio, produce:

**Business Quality** (score /10)
- Competitive advantage, industry structure, market opportunity,
  scalability, capital intensity, pricing power, entry barriers.

**Financial Forensics (last 5 years)**
- P&L: revenue / EBITDA / PAT growth, margin trend, segment trend,
  red flags, earnings quality.
- Balance sheet: debt trend, working capital, inventory, receivables,
  payables, asset turns, capital allocation.
- Cash flow: CFO vs PAT, FCF, reinvestment needs, cash conversion.
- Ratios over time: ROE, ROCE, asset turnover, D/E, interest coverage,
  FCF yield, reinvestment ratio, inventory turns.
- List **positives** and **negatives**.

═══════════════════════════════════════════════════════════════════════
PART 3 — Management Assessment
═══════════════════════════════════════════════════════════════════════
Based on the last ~12 quarters of concalls, presentations and annual
reports, evaluate:
guidance vs delivery · capital allocation · acquisitions · capex
execution · margin promises · revenue promises · transparency.

Produce a **Management Integrity Matrix** per stock:

| Parameter              | Score (/10) |
|------------------------|------------:|
| Transparency           |             |
| Capital Allocation     |             |
| Execution              |             |
| Shareholder Friendly   |             |
| Guidance Reliability   |             |

Conclude with an **Overall Integrity Score /10** per stock.

═══════════════════════════════════════════════════════════════════════
PART 4 — Portfolio Risk Analysis
═══════════════════════════════════════════════════════════════════════
Identify and RANK (highest → lowest):
1. Single biggest risk
2. Sector-concentration risk
3. Valuation risk
4. Earnings risk
5. Regulatory risk
6. Balance-sheet risk
7. Management risk

═══════════════════════════════════════════════════════════════════════
PART 5 — Growth Trigger Analysis
═══════════════════════════════════════════════════════════════════════
For each stock, list operating leverage, capacity expansion, capex
utilisation, new product launches, industry tailwinds, export
opportunities, margin-expansion triggers, acquisitions.
Rate impact: **Low / Medium / High**.

═══════════════════════════════════════════════════════════════════════
PART 6 — Valuation Analysis
═══════════════════════════════════════════════════════════════════════
For each stock analyse PE, EV/EBITDA, P/S, P/B, PEG, historical
valuation bands. Tag as **Overvalued / Fairly valued / Undervalued**.
Provide Fair Value, Optimistic Value, and Conservative Value.

═══════════════════════════════════════════════════════════════════════
PART 7 — Portfolio Optimisation
═══════════════════════════════════════════════════════════════════════
Produce three explicit lists:
- **SELL candidates** — weak management / cash flows / capital
  allocation / overvaluation.
- **HOLD candidates** — good execution, reasonable valuation, long
  runway.
- **ADD MORE candidates** — highest-conviction ideas within the
  existing book.

═══════════════════════════════════════════════════════════════════════
PART 8 — Capital Allocation Strategy
═══════════════════════════════════════════════════════════════════════
Given the supplied cash, horizon, SIP, target CAGR and risk appetite:
- SIP allocation per stock (₹ per month)
- Ideal portfolio weights
- Rebalancing suggestions
- **Current vs Ideal Allocation** table:

| Stock | Current % | Ideal % |
|-------|----------:|--------:|

═══════════════════════════════════════════════════════════════════════
PART 9 — Portfolio Stress Test
═══════════════════════════════════════════════════════════════════════
Show estimated impact per holding under:
- Scenario 1: India enters recession
- Scenario 2: Interest rates rise 2%
- Scenario 3: China dumping impacts the industry
- Scenario 4: Global slowdown
- Scenario 5: Bull market continues

═══════════════════════════════════════════════════════════════════════
PART 10 — Final Verdict
═══════════════════════════════════════════════════════════════════════
**Portfolio Report Card** (each /10, then total /100):

| Parameter           | Score |
|---------------------|------:|
| Business Quality    |       |
| Growth Potential    |       |
| Valuation Comfort   |       |
| Management Quality  |       |
| Cash Flow Quality   |       |
| Risk Management     |       |
| Diversification     |       |

**Overall Score: __ /70 (scaled to /100)**

Then answer, explicitly:
1. Which stock can become a 5x in the next decade?
2. Which stock is most likely to disappoint?
3. Which stock deserves the highest allocation?
4. Which stock should be trimmed first?
5. What are the top 5 actions to take immediately?
6. Is this portfolio capable of generating 20%+ CAGR over 5–10 years?

═══════════════════════════════════════════════════════════════════════
Evidence base & rules
═══════════════════════════════════════════════════════════════════════
- Draw on the latest annual reports, last ~12 quarterly concalls,
  investor presentations, Screener.in data, ValuePickr threads from
  the last 90 days, recent industry news and competitor analysis.
- Be brutally objective and evidence-based. Do not simply summarise;
  give actionable conclusions and capital-allocation recommendations.
- Where you lack data, state the assumption explicitly — never
  fabricate numbers.
- Output is for analytical/educational purposes only — include a
  short disclaimer that this is NOT investment advice.
"""

FORENSIC_USER_DIRECTIVE = (
    "Run the FULL 10-part forensic portfolio review defined in the system "
    "instructions, end to end, without skipping any section. Be brutally "
    "objective and evidence-based; produce actionable, capital-allocation-"
    "level conclusions."
)


# ─── Template registry ────────────────────────────────────────────────────

@dataclass(frozen=True)
class PromptTemplate:
    name: str
    description: str
    system_prompt: str
    default_directive: str


PROMPT_TEMPLATES: dict[str, PromptTemplate] = {
    "concise": PromptTemplate(
        name="concise",
        description="5-section restructuring brief (original prompt).",
        system_prompt=CONCISE_SYSTEM_PROMPT,
        default_directive=CONCISE_USER_DIRECTIVE,
    ),
    "forensic": PromptTemplate(
        name="forensic",
        description="10-part institutional forensic review (new prompt).",
        system_prompt=FORENSIC_SYSTEM_PROMPT,
        default_directive=FORENSIC_USER_DIRECTIVE,
    ),
}

DEFAULT_TEMPLATE_NAME = "forensic"


# ─── Web grounding directive ──────────────────────────────────────────────
#
# Injected into the system prompt when web grounding is enabled. Forces the
# model to use its built-in `web-fetch` tool (and any configured web/search
# MCP servers) to ground claims in live data BEFORE writing the report.

WEB_GROUNDING_DIRECTIVE = """
═══════════════════════════════════════════════════════════════════════
MANDATORY EVIDENCE GROUNDING — read carefully
═══════════════════════════════════════════════════════════════════════
Before producing ANY part of the report you MUST use your available
web tools (`web-fetch`, any configured search MCP servers, etc.) to
ground your findings in current, real-world data. Do not rely on
training-data recall for prices, news, or numbers.

For every stock in the portfolio you must, at minimum, attempt to:

1. **Live price & 1-year chart context** — fetch the current LTP, 52-week
   range, and recent % moves. Suggested sources:
     - https://www.nseindia.com/get-quotes/equity?symbol=<SYMBOL>
     - https://www.google.com/finance/quote/<SYMBOL>:NSE
     - https://finance.yahoo.com/quote/<SYMBOL>.NS

2. **Latest fundamentals & ratio history** — Screener.in is the canonical
   source for Indian listed companies:
     - https://www.screener.in/company/<SYMBOL>/consolidated/
     - https://www.screener.in/company/<SYMBOL>/

3. **Recent news (last 30–90 days)** — earnings, regulatory events,
   guidance changes, large orders, management changes. Suggested:
     - https://www.moneycontrol.com/india/stockpricequote/<sector>/<company>/<symbol>
     - https://economictimes.indiatimes.com/markets/stocks
     - https://www.business-standard.com/topic/<symbol>

4. **Latest concall / investor presentation** — most recent earnings
   commentary. Use BSE/NSE filings or company IR pages:
     - https://www.bseindia.com/stock-share-price-<symbol>/
     - https://nsearchives.nseindia.com/

5. **Forum colour & sell-side commentary (optional but valued)** — recent
   ValuePickr threads on the name (last 90 days) and any analyst reports
   that surface through your search tool.

Operating rules while grounding:
- Issue web-fetches in parallel where possible to keep latency down.
- Use a small number of high-signal sources per stock (≈3–5 fetches);
  do not try to crawl exhaustively.
- Cite the URL inline (in parentheses) when stating a specific number,
  date, headline, or quote. Format: `(src: <short-domain>)`.
- If a fetch fails or returns no usable data, STATE that explicitly —
  e.g. "screener.in fetch failed; using last-known FY25 estimate".
  Never silently fabricate a number.
- The portfolio table contains LTPs supplied by the user — use those
  for arithmetic, but **cross-check** at least the top 5 holdings'
  LTPs against a live source and call out any meaningful drift.
- Where you cannot find a current data point, label your output with
  "(assumed)" or "(no live data — directional only)".

Failure to perform live grounding is a failure of this task. Report
gracefully but proceed; do not block on a single missing source.
"""


# ─── Scraper MCP server (custom tool injection) ───────────────────────────
#
# The repo already ships an stdio MCP server (`mcp_server.py`) that wraps
# screener.in / yfinance / TA scrapers as tools. We pass it to the Copilot
# CLI via `--additional-mcp-config @<file>` so the model can call those
# tools directly — typically faster and more structured than raw
# `web-fetch` for Indian equities.
#
# When scraper-tools mode is enabled, we also append a directive to the
# system prompt telling the model to prefer these tools over web-fetch
# wherever applicable.

SCRAPER_MCP_SERVER_NAME = "indian-stock-data"

SCRAPER_MCP_TOOLS = [
    "fetch_stock_price",
    "fetch_fundamentals",
    "fetch_technical_indicators",
    "fetch_stock_news",
    "fetch_financial_statements",
    "fetch_screener_fundamentals",
    "search_nse_stocks",
    "scrape_url",
]

SCRAPER_TOOLS_DIRECTIVE = f"""
═══════════════════════════════════════════════════════════════════════
PREFERRED RESEARCH TOOLS — Indian-equity scrapers (`{SCRAPER_MCP_SERVER_NAME}` MCP)
═══════════════════════════════════════════════════════════════════════
A dedicated MCP server named `{SCRAPER_MCP_SERVER_NAME}` is attached to
this session. It wraps screener.in + yfinance + TA libraries and is
optimised for NSE/BSE-listed names. **Use these tools FIRST**, before
falling back to `web-fetch`:

- `fetch_stock_price(symbol)`            — live LTP, day/52-week range,
                                            mkt cap, P/E, % change.
- `fetch_fundamentals(symbol)`           — yfinance ratios (P/E, PEG, P/B,
                                            EV/EBITDA, margins, ROE, ROA,
                                            D/E, growth, analyst targets).
- `fetch_screener_fundamentals(symbol)`  — DEEP screener.in data: 10-year
                                            P&L, balance sheet, cash flow,
                                            12 quarters, shareholding,
                                            ROCE/ROE trend. **Best single
                                            source for fundamentals.**
- `fetch_technical_indicators(symbol)`   — RSI, MACD, SMA 20/50/200,
                                            Bollinger, ADX, ATR, S/R.
- `fetch_financial_statements(symbol)`   — annual + quarterly IS/BS/CF.
- `fetch_stock_news(symbol)`             — up to 10 recent headlines.
- `search_nse_stocks(query)`             — resolve company name → symbol.
- `scrape_url(url)`                      — generic page text fallback for
                                            moneycontrol / livemint / ET /
                                            BSE filings when the dedicated
                                            tools don't cover what you need.

Symbol convention: pass the **plain NSE ticker** (e.g. `RELIANCE`, `TCS`,
`HDFCBANK`) — NOT `RELIANCE.NS` or `NSE:RELIANCE`. The tools handle that.

Tool-use protocol:
1. For each holding, call `fetch_stock_price` + `fetch_screener_fundamentals`
   in parallel as your first move. That gives you ~80% of what you need.
2. Add `fetch_technical_indicators` only when the report calls for
   momentum / trend / entry-zone commentary.
3. Add `fetch_stock_news` (or `scrape_url` on a moneycontrol/ET page)
   for any name where recent news materially affects the thesis.
4. Use `web-fetch` only for things the scrapers don't cover: concall
   transcripts, sector reports, ValuePickr threads, regulatory filings.
5. Cite which tool surfaced a fact — e.g. `(src: screener.in)` or
   `(src: web-fetch moneycontrol)`. If a tool fails, say so and try a
   different one; do not silently fabricate.
"""


def _augment_with_grounding(
    system_prompt: str,
    web_grounding: bool,
    scraper_tools: bool = False,
) -> str:
    """Append the grounding + scraper-tools directives if enabled."""
    out = system_prompt.rstrip()
    if web_grounding:
        out += "\n\n" + WEB_GROUNDING_DIRECTIVE.strip()
    if scraper_tools:
        out += "\n\n" + SCRAPER_TOOLS_DIRECTIVE.strip()
    return out + "\n"


def _write_scraper_mcp_config(tmp_dir: Path) -> Path:
    """Write a Copilot CLI MCP config file pointing at the local scraper
    MCP server (`mcp_server.py`). Returns the path so the caller can pass
    it via `--additional-mcp-config @<path>`.

    We use absolute paths and `sys.executable` so the spawn works
    regardless of where `copilot` is launched from.
    """
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


def resolve_template(name: Optional[str]) -> PromptTemplate:
    """Resolve a template by name, falling back to env var, then default."""
    chosen = (name or os.getenv("PROMPT_TEMPLATE") or DEFAULT_TEMPLATE_NAME).strip().lower()
    if chosen not in PROMPT_TEMPLATES:
        raise SystemExit(
            f"Unknown prompt template: {chosen!r}. "
            f"Available: {', '.join(sorted(PROMPT_TEMPLATES))}"
        )
    return PROMPT_TEMPLATES[chosen]


def _portfolio_table(holdings: List[Holding]) -> str:
    rows = [
        "| Stock | Qty | Avg Cost ₹ | Current Price ₹ | Invested ₹ | Current Value ₹ | Allocation % | P&L ₹ | P&L % |",
        "|-------|----:|-----------:|----------------:|-----------:|----------------:|-------------:|------:|------:|",
    ]
    total_invested = 0.0
    total_value = 0.0
    has_ltp = True

    for h in holdings:
        total_invested += h.invested
        if h.last_price is None:
            has_ltp = False
        else:
            total_value += h.current_value or 0.0

    denom = total_value if (has_ltp and total_value > 0) else total_invested

    for h in holdings:
        ltp = f"{h.last_price:,.2f}" if h.last_price is not None else "—"
        cur = f"{h.current_value:,.2f}" if h.current_value is not None else "—"
        pnl = f"{h.pnl:,.2f}" if h.pnl is not None else "—"
        pnl_pct = f"{h.pnl_pct:+.2f}%" if h.pnl_pct is not None else "—"
        weight_basis = (h.current_value if h.current_value is not None else h.invested)
        alloc_pct = (weight_basis / denom * 100) if denom else 0
        rows.append(
            f"| {h.symbol} | {h.quantity:g} | {h.buy_price:,.2f} | {ltp} "
            f"| {h.invested:,.2f} | {cur} | {alloc_pct:.2f}% | {pnl} | {pnl_pct} |"
        )

    totals = f"\n**Totals** — Invested: ₹{total_invested:,.2f}"
    if has_ltp:
        pnl_total = total_value - total_invested
        pnl_pct_total = (pnl_total / total_invested * 100) if total_invested else 0
        totals += (
            f" · Current: ₹{total_value:,.2f} · "
            f"P&L: ₹{pnl_total:,.2f} ({pnl_pct_total:+.2f}%)"
        )
    else:
        totals += " · LTP unavailable for some holdings; estimate where needed."

    return "\n".join(rows) + totals


@dataclass
class PortfolioContext:
    """Optional metadata the forensic prompt expects: cash, horizon, SIP, etc."""
    cash_available: Optional[float] = None
    horizon_years: Optional[float] = None
    monthly_sip: Optional[float] = None
    target_cagr_pct: Optional[float] = None
    risk_appetite: Optional[str] = None  # Low / Moderate / High

    def render(self, total_value: float) -> str:
        def fmt_money(v: Optional[float]) -> str:
            return f"₹{v:,.2f}" if v is not None else "_not provided_"

        return (
            f"- **Total Portfolio Value**: ₹{total_value:,.2f}\n"
            f"- **Cash Available**: {fmt_money(self.cash_available)}\n"
            f"- **Investment Horizon**: "
            f"{self.horizon_years if self.horizon_years is not None else '_not provided_'} years\n"
            f"- **Additional Monthly Investment (SIP)**: {fmt_money(self.monthly_sip)}\n"
            f"- **Target CAGR**: "
            f"{(str(self.target_cagr_pct) + '%') if self.target_cagr_pct is not None else '_not provided_'}\n"
            f"- **Risk Appetite**: {self.risk_appetite or '_not provided_'}"
        )


def build_full_prompt(
    holdings: List[Holding],
    user_prompt: str,
    context: Optional[PortfolioContext] = None,
    template: Optional[PromptTemplate] = None,
    web_grounding: bool = True,
    scraper_tools: bool = True,
) -> str:
    """Combine the template's system instructions, portfolio table, investor
    context, and the free-form user prompt into a single message for the
    Copilot CLI.

    Directives are appended to the system prompt based on flags:
      - `web_grounding`  → require use of web-fetch / search tools.
      - `scraper_tools`  → require preferential use of the scraper MCP
                           tools (fetch_stock_price, fetch_screener_*, …).
    """
    total_value = sum(
        (h.current_value if h.current_value is not None else h.invested) for h in holdings
    )
    ctx = context or PortfolioContext()
    tmpl = template or PROMPT_TEMPLATES[DEFAULT_TEMPLATE_NAME]
    system_prompt = _augment_with_grounding(
        tmpl.system_prompt,
        web_grounding=web_grounding,
        scraper_tools=scraper_tools,
    )
    return (
        f"{system_prompt}\n\n"
        f"# Portfolio\n\n{_portfolio_table(holdings)}\n\n"
        f"# Investor Context\n\n{ctx.render(total_value)}\n\n"
        f"# User Analysis Request\n\n{user_prompt.strip()}\n"
    )


# ─── GitHub Copilot CLI invocation ─────────────────────────────────────────

def _resolve_copilot_bin() -> str:
    """Locate the `copilot` executable."""
    explicit = os.getenv("COPILOT_BIN")
    if explicit:
        if not Path(explicit).exists():
            raise RuntimeError(f"COPILOT_BIN points to non-existent path: {explicit}")
        return explicit

    # On Windows the global npm bin is usually `copilot.cmd`
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
    holdings: List[Holding],
    user_prompt: str,
    model: Optional[str] = None,
    extra_cli_args: Optional[List[str]] = None,
    context: Optional[PortfolioContext] = None,
    template: Optional[PromptTemplate] = None,
    web_grounding: bool = True,
    scraper_tools: bool = True,
    copilot_log: Optional[Path] = None,
    log_level: str = "debug",
) -> str:
    """Invoke the Copilot CLI in non-interactive mode and return its stdout.

    The full prompt (system instructions + portfolio table + investor
    context + user request) is written to a temp file inside the current
    working directory, and we ask Copilot to read it. This avoids the
    Windows cmd.exe ~8191-char command line limit when the portfolio is
    large.

    When `web_grounding` is True, the prompt instructs the model to use
    web tools to back its findings, and `--allow-all-urls` is passed so
    URL approval prompts don't block the headless run.

    When `scraper_tools` is True, the local scraper MCP server
    (`mcp_server.py`) is attached via `--additional-mcp-config`, exposing
    Indian-equity scraper tools (screener.in, yfinance, TA) directly to
    the model.

    When `copilot_log` is provided, the Copilot CLI is started with
    `--log-level=<log_level>` (default `debug`) and its stderr is
    tee'd live to both that file AND the parent console (prefixed
    `[copilot]`), giving you visibility into MCP tool invocations.
    """
    copilot_bin = _resolve_copilot_bin()
    full_prompt = build_full_prompt(
        holdings,
        user_prompt,
        context=context,
        template=template,
        web_grounding=web_grounding,
        scraper_tools=scraper_tools,
    )

    # Temp file MUST live inside the workspace so Copilot can read it
    # without extra --add-dir grants.
    tmp_dir = Path.cwd() / ".copilot_tmp"
    tmp_dir.mkdir(exist_ok=True)
    prompt_file = tmp_dir / f"prompt-{uuid.uuid4().hex[:8]}.md"
    prompt_file.write_text(full_prompt, encoding="utf-8")

    short_prompt = (
        f"Read the file `{prompt_file.as_posix()}` in its entirety using your "
        "file-read tool. It contains a system role description, a portfolio "
        "table, and a user analysis request. Follow the instructions in that "
        "file exactly and respond with ONLY the final Markdown report — do "
        "not echo the prompt or describe what you are doing."
    )

    # `-p / --prompt` runs the CLI in programmatic (non-interactive) mode.
    # `--allow-all-tools` skips the tool-permission prompts that would otherwise
    # block a fully-headless run. `-s` strips stats noise so we get just the
    # agent response.
    cmd: List[str] = [
        copilot_bin,
        "-p", short_prompt,
        "--allow-all-tools",
        "--add-dir", str(tmp_dir),
        "-s",
    ]

    # When web grounding is enabled, allow all URLs so web-fetch / search
    # tools don't trigger an interactive approval prompt mid-run.
    if web_grounding:
        cmd.append("--allow-all-urls")

    # Attach the local scraper MCP server so the model can call the
    # screener.in / yfinance / TA tools directly. Written to a temp config
    # file and passed via `--additional-mcp-config @<path>`.
    scraper_cfg_file: Optional[Path] = None
    if scraper_tools:
        try:
            scraper_cfg_file = _write_scraper_mcp_config(tmp_dir)
            cmd.extend(["--additional-mcp-config", f"@{scraper_cfg_file}"])
            logger.info("Scraper MCP server attached via %s", scraper_cfg_file.name)
        except FileNotFoundError as e:
            logger.warning("Skipping scraper tools: %s", e)
            scraper_tools = False

    # When a log file is requested, ask the CLI to emit debug-level info to
    # stderr so we can capture tool calls, MCP boot messages, etc.
    if copilot_log is not None:
        cmd.extend(["--log-level", log_level])
        copilot_log.parent.mkdir(parents=True, exist_ok=True)

    chosen_model = model or os.getenv("COPILOT_MODEL")
    if chosen_model:
        cmd.extend(["--model", chosen_model])

    if extra_cli_args:
        cmd.extend(extra_cli_args)

    logger.info(
        "Invoking Copilot CLI (%s) with %d holdings%s "
        "(prompt file: %s, %d bytes, web_grounding=%s, scraper_tools=%s, log=%s)",
        copilot_bin,
        len(holdings),
        f", model={chosen_model}" if chosen_model else "",
        prompt_file.name,
        prompt_file.stat().st_size,
        web_grounding,
        scraper_tools,
        copilot_log if copilot_log else "—",
    )

    # Open the log file in append mode so multiple runs in one session
    # don't overwrite each other.
    log_handle: Optional[TextIO] = None
    if copilot_log is not None:
        log_handle = open(copilot_log, "a", encoding="utf-8", errors="replace")
        log_handle.write(
            f"\n{'='*72}\n"
            f"Copilot CLI run @ {datetime.now().isoformat(timespec='seconds')}\n"
            f"cmd: {cmd}\n"
            f"web_grounding={web_grounding}  scraper_tools={scraper_tools}  model={chosen_model}\n"
            f"{'='*72}\n"
        )
        log_handle.flush()

    def _pump_stderr(pipe, sink: Optional[TextIO]) -> None:
        """Tee Copilot stderr to console (prefixed) and optional log file."""
        try:
            for raw in iter(pipe.readline, ""):
                if not raw:
                    break
                # Live console echo so tool calls are visible during the run.
                # Use sys.stderr so it stays distinct from the streamed report.
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
        # Stream stdout live so the user sees the analysis as it's generated.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        # Spin up a background thread to consume stderr live; otherwise a
        # chatty MCP/log stream can fill the pipe buffer and deadlock.
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
        # Best-effort cleanup of per-run temp files (prompt + MCP config).
        try:
            prompt_file.unlink(missing_ok=True)
        except OSError:
            pass
        if scraper_cfg_file is not None:
            try:
                scraper_cfg_file.unlink(missing_ok=True)
            except OSError:
                pass


# ─── CLI ───────────────────────────────────────────────────────────────────

def _env_float(name: str) -> Optional[float]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        logger.warning("Env var %s=%r is not a number; ignoring.", name, raw)
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Portfolio analysis using the GitHub Copilot CLI. "
            "Choose a prompt template with --template "
            "(forensic = 10-part deep review, concise = 5-section brief)."
        ),
    )
    parser.add_argument(
        "--template",
        choices=sorted(PROMPT_TEMPLATES),
        default=None,
        help=(
            "Which prompt template to use. Overrides PROMPT_TEMPLATE env var. "
            f"Default: {DEFAULT_TEMPLATE_NAME}. "
            + " · ".join(f"{t.name}: {t.description}" for t in PROMPT_TEMPLATES.values())
        ),
    )
    parser.add_argument(
        "--source",
        choices=["zerodha", "file", "inline"],
        help="Where to load the portfolio from. If omitted, inferred from other flags.",
    )
    parser.add_argument(
        "--portfolio-file",
        type=Path,
        help="Path to a JSON file with the portfolio (list of holdings).",
    )
    parser.add_argument(
        "--portfolio",
        type=str,
        help="Inline JSON list of holdings.",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help=(
            "Free-form analysis directive appended after the chosen template's "
            "system prompt. If omitted, the template's default directive is used."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Copilot model name (overrides COPILOT_MODEL env var).",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Optional path to save the model's response as a Markdown file.",
    )
    parser.add_argument(
        "--copilot-arg",
        action="append",
        default=[],
        help="Extra arg to pass through to `copilot` (can be repeated).",
    )
    parser.add_argument(
        "--web-grounding",
        action=argparse.BooleanOptionalAction,
        default=(os.getenv("WEB_GROUNDING", "true").strip().lower() not in {"0", "false", "no", "off"}),
        help=(
            "Force the model to use web tools (web-fetch / search MCPs) to "
            "ground findings in live data. Adds --allow-all-urls so URL "
            "approval doesn't block the run. Default: on. "
            "Disable with --no-web-grounding or WEB_GROUNDING=false."
        ),
    )
    parser.add_argument(
        "--scraper-tools",
        action=argparse.BooleanOptionalAction,
        default=(os.getenv("SCRAPER_TOOLS", "true").strip().lower() not in {"0", "false", "no", "off"}),
        help=(
            "Attach the local scraper MCP server (mcp_server.py) so the model "
            "can call screener.in / yfinance / TA tools directly. Default: on. "
            "Disable with --no-scraper-tools or SCRAPER_TOOLS=false."
        ),
    )
    parser.add_argument(
        "--copilot-log",
        type=Path,
        default=None,
        help=(
            "Save Copilot CLI stderr (incl. tool-call debug logs) to this file "
            "AND tee it live to the parent stderr (prefixed [copilot]). "
            "Pass 'auto' to use logs/copilot-<timestamp>.log."
        ),
    )
    parser.add_argument(
        "--copilot-log-level",
        choices=["error", "warn", "info", "debug"],
        default="debug",
        help="Copilot CLI --log-level passed when --copilot-log is set. Default: debug.",
    )

    # ─── Investor context (Part 8 inputs) ───
    parser.add_argument(
        "--cash",
        type=float,
        default=_env_float("PORTFOLIO_CASH"),
        help="Cash available to deploy (₹). Auto-filled from Zerodha if --source=zerodha.",
    )
    parser.add_argument(
        "--horizon-years",
        type=float,
        default=_env_float("PORTFOLIO_HORIZON_YEARS"),
        help="Investment horizon in years.",
    )
    parser.add_argument(
        "--monthly-sip",
        type=float,
        default=_env_float("PORTFOLIO_MONTHLY_SIP"),
        help="Additional monthly SIP investment (₹).",
    )
    parser.add_argument(
        "--target-cagr",
        type=float,
        default=_env_float("PORTFOLIO_TARGET_CAGR"),
        help="Target CAGR (%%) over the horizon.",
    )
    parser.add_argument(
        "--risk-appetite",
        type=str,
        default=os.getenv("PORTFOLIO_RISK_APPETITE") or None,
        choices=["Low", "Moderate", "High", "low", "moderate", "high"],
        help="Risk appetite (Low / Moderate / High).",
    )
    return parser.parse_args()


def _resolve_portfolio(args: argparse.Namespace) -> tuple[List[Holding], Optional[float]]:
    """Load holdings + (optionally) cash, depending on the chosen source."""
    source = args.source
    if not source:
        if args.portfolio_file:
            source = "file"
        elif args.portfolio:
            source = "inline"
        else:
            source = "zerodha"

    if source == "zerodha":
        return load_portfolio_from_zerodha()
    if source == "file":
        if not args.portfolio_file:
            raise SystemExit("--portfolio-file is required when --source=file")
        return load_portfolio_from_file(args.portfolio_file), None
    if source == "inline":
        if not args.portfolio:
            raise SystemExit("--portfolio is required when --source=inline")
        try:
            data = json.loads(args.portfolio)
        except json.JSONDecodeError as e:
            raise SystemExit(f"Invalid --portfolio JSON: {e}") from e
        return load_portfolio_from_json(data), None
    raise SystemExit(f"Unknown source: {source}")


def main() -> int:
    args = _parse_args()
    try:
        holdings, auto_cash = _resolve_portfolio(args)
    except Exception as e:
        logger.error("Failed to load portfolio: %s", e)
        return 2

    if not holdings:
        logger.error("Portfolio is empty — nothing to analyze.")
        return 2

    template = resolve_template(args.template)
    user_directive = args.prompt if args.prompt is not None else template.default_directive

    # CLI / env cash overrides Zerodha-auto cash.
    cash_available = args.cash if args.cash is not None else auto_cash

    context = PortfolioContext(
        cash_available=cash_available,
        horizon_years=args.horizon_years,
        monthly_sip=args.monthly_sip,
        target_cagr_pct=args.target_cagr,
        risk_appetite=(args.risk_appetite.capitalize() if args.risk_appetite else None),
    )

    print(f"\n=== Loaded {len(holdings)} holdings ===")
    for h in holdings:
        print(f"  {h.symbol:<15} qty={h.quantity:<6g} avg=₹{h.buy_price:,.2f}")
    print("=" * 40)
    print(f"Template:       {template.name} — {template.description}")
    print(f"Web grounding:  {'ON  (fetching live data)' if args.web_grounding else 'OFF (cached knowledge only)'}")
    print(f"Scraper tools:  {'ON  (screener.in + yfinance MCP attached)' if args.scraper_tools else 'OFF'}")
    # Resolve --copilot-log: 'auto' → logs/copilot-<timestamp>.log
    copilot_log_path: Optional[Path] = args.copilot_log
    if copilot_log_path is not None and str(copilot_log_path).lower() == "auto":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        copilot_log_path = Path("logs") / f"copilot-{stamp}.log"
    if copilot_log_path is not None:
        print(f"Copilot log:    {copilot_log_path} (level={args.copilot_log_level})")
    if cash_available is not None:
        print(f"Cash available: ₹{cash_available:,.2f}")
    if args.horizon_years is not None:
        print(f"Horizon:        {args.horizon_years} years")
    if args.monthly_sip is not None:
        print(f"Monthly SIP:    ₹{args.monthly_sip:,.2f}")
    if args.target_cagr is not None:
        print(f"Target CAGR:    {args.target_cagr}%")
    if args.risk_appetite is not None:
        print(f"Risk appetite:  {args.risk_appetite.capitalize()}")
    print("=" * 40 + "\n")

    try:
        result = run_analysis(
            holdings=holdings,
            user_prompt=user_directive,
            model=args.model,
            extra_cli_args=args.copilot_arg,
            context=context,
            template=template,
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
        logger.info("Saved analysis to %s", args.save)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
