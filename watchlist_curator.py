"""
watchlist_curator.py
====================

Monthly **swing-trading watchlist curator** for the Indian market (NSE).

It scans a large universe (Nifty 500 by default — or any NSE index / custom
list), mechanically screens for swing-suitable momentum + trend + liquidity,
then uses the **GitHub Copilot CLI + scraper MCP** to deeply vet the shortlist
on fundamentals / financials / technicals and emit a final, ranked, high-quality
watchlist.

The output `swing_watchlist.txt` is directly consumable by the daily runner:

    python swing_trading_copilot.py --source zerodha \
        --watchlist-file swing_watchlist.txt

Workflow
--------
Run this ONCE a MONTH to refresh the watchlist, then feed that same file into
your DAILY `swing_trading_copilot.py` runs (which pick entries, rotate capital,
and manage exits against your open book).

Two-stage funnel (why it's both fast and accurate)
--------------------------------------------------
  Stage 1 — Mechanical screen (Python / yfinance, fast, free)
    Universe (e.g. 500 names) → compute SMA stack, RSI, ATR%, 1m/3m/6m returns,
    relative strength vs Nifty, volume surge, traded value, distance from 52w
    high → apply hard filters → composite rank → industry-diversified SHORTLIST
    (~40 names). This avoids running an LLM over 500 stocks.

  Stage 2 — LLM curation (Copilot CLI + scraper MCP, deep, accurate)
    The shortlist (with its metrics) is handed to the agent, which uses
    screener.in / yfinance / TA / news tools to vet business quality, financial
    trend, balance-sheet risk and the technical setup, rejecting weak or
    manipulated names, and produces the FINAL ranked watchlist (~20) plus a
    machine-readable block this script parses into `swing_watchlist.txt`.

Use `--no-llm` to stop after Stage 1 (instant, free, purely mechanical).

Prerequisites
-------------
- Python deps already in this repo: yfinance, pandas (see requirements.txt).
- For Stage 2: GitHub Copilot CLI installed + signed in (`copilot --version`).

Examples
--------
    # Full monthly curation over the Nifty 500
    python watchlist_curator.py --index nifty500 \
        --final-size 20 --out-watchlist swing_watchlist.txt

    # Fast mechanical-only shortlist (no LLM), broader midcap universe
    python watchlist_curator.py --index niftymidcap150 --no-llm \
        --shortlist-size 30

    # Curate from a custom universe file (one NSE symbol per line)
    python watchlist_curator.py --universe-file my_universe.txt

DISCLAIMER: For educational/analytical use only — NOT investment advice.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import math
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

from core.agent import AgentRequest, Capability, run_agent, scraper_mcp
from core.storage import runtime_dir, save_artifacts, set_document
from dotenv import load_dotenv

# Prompt directives are shared with the swing runner; the harness plumbing now
# lives in core.agent.
from swing_trading_copilot import (
    SCRAPER_TOOLS_DIRECTIVE,
    WEB_GROUNDING_DIRECTIVE,
)

load_dotenv()

logger = logging.getLogger("watchlist_curator")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ─── Universe sources (NSE published index constituents) ──────────────────────

NSE_INDEX_URLS: Dict[str, str] = {
    "nifty50": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "niftynext50": "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv",
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
    "nifty500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "niftymidcap150": "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "niftysmallcap250": "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    "niftymidcap100": "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap100list.csv",
}

_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

NIFTY_BENCHMARK = "^NSEI"  # Nifty 50 index, for relative-strength


@dataclass
class UniverseStock:
    symbol: str
    industry: str = "Unknown"
    company: str = ""


def load_universe_from_index(index_name: str) -> List[UniverseStock]:
    key = index_name.strip().lower()
    if key not in NSE_INDEX_URLS:
        raise SystemExit(
            f"Unknown index {index_name!r}. Available: {', '.join(sorted(NSE_INDEX_URLS))}"
        )
    url = NSE_INDEX_URLS[key]
    logger.info("Fetching universe '%s' from NSE: %s", key, url)
    req = urllib.request.Request(url, headers=_HTTP_HEADERS)
    data = urllib.request.urlopen(req, timeout=45).read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(data)))
    out: List[UniverseStock] = []
    for r in rows:
        sym = (r.get("Symbol") or "").strip().upper()
        if not sym:
            continue
        out.append(
            UniverseStock(
                symbol=sym,
                industry=(r.get("Industry") or "Unknown").strip(),
                company=(r.get("Company Name") or "").strip(),
            )
        )
    logger.info("Loaded %d symbols from %s", len(out), key)
    return out


def load_universe_from_file(path: Path) -> List[UniverseStock]:
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")
    out: List[UniverseStock] = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        for tok in line.replace("\t", ",").split(","):
            sym = tok.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                out.append(UniverseStock(symbol=sym))
    if not out:
        raise SystemExit(f"No symbols found in universe file: {path}")
    logger.info("Loaded %d symbols from %s", len(out), path)
    return out


# ─── Stage 1: mechanical metrics (yfinance + pandas) ──────────────────────────

def _yf_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s.endswith(".NS") and not s.endswith(".BO"):
        s = f"{s}.NS"
    return s


def _rsi(close, period: int = 14):
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


def _atr_pct(high, low, close, period: int = 14):
    prev_close = close.shift()
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    import pandas as pd  # noqa: F401
    tr = tr1.combine(tr2, max).combine(tr3, max)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return (atr / close) * 100


def _ret(close, lookback: int) -> Optional[float]:
    if len(close) <= lookback:
        return None
    a = close.iloc[-1]
    b = close.iloc[-1 - lookback]
    if b and not math.isnan(b):
        return (a / b - 1.0) * 100
    return None


@dataclass
class StockMetrics:
    symbol: str
    industry: str
    close: float
    sma20: float
    sma50: float
    sma200: float
    rsi: float
    atr_pct: float
    ret_1m: Optional[float]
    ret_3m: Optional[float]
    ret_6m: Optional[float]
    rel_strength_3m: Optional[float]  # ret_3m - nifty_ret_3m
    vol_surge: float                  # avg_vol_20 / avg_vol_50
    traded_value_cr: float            # avg(close*volume) over 20d, in ₹ crore
    dist_from_high_pct: float         # how far below 52w high (positive number)
    sma50_rising: bool
    score: float = 0.0

    @property
    def sma_stack(self) -> bool:
        return self.close > self.sma50 > self.sma200

    @property
    def above_200(self) -> bool:
        return self.close > self.sma200


def _compute_metrics_for(symbol: str, industry: str, df, nifty_ret_3m: Optional[float]) -> Optional[StockMetrics]:
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["Close"])
    if len(df) < 60:  # need a reasonable history
        return None
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"].fillna(0)

    try:
        last = float(close.iloc[-1])
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200_series = close.rolling(200).mean()
        sma200 = float(sma200_series.iloc[-1]) if len(close) >= 200 else float("nan")
        rsi = float(_rsi(close).iloc[-1])
        atrp = float(_atr_pct(high, low, close).iloc[-1])
        avg_vol_20 = float(vol.rolling(20).mean().iloc[-1])
        avg_vol_50 = float(vol.rolling(50).mean().iloc[-1]) if len(vol) >= 50 else avg_vol_20
        vol_surge = (avg_vol_20 / avg_vol_50) if avg_vol_50 else 1.0
        traded_value_cr = float((close * vol).rolling(20).mean().iloc[-1]) / 1e7  # ₹ crore
        high_52w = float(close.tail(252).max())
        dist_from_high = (high_52w - last) / high_52w * 100 if high_52w else float("nan")
        sma50_rising = bool(close.rolling(50).mean().iloc[-1] > close.rolling(50).mean().iloc[-6]) if len(close) >= 56 else False
    except Exception as e:  # noqa: BLE001
        logger.debug("metric calc failed for %s: %s", symbol, e)
        return None

    if any(math.isnan(x) for x in (last, sma20, sma50, rsi, atrp)):
        return None

    r1 = _ret(close, 21)
    r3 = _ret(close, 63)
    r6 = _ret(close, 126)
    rel3 = (r3 - nifty_ret_3m) if (r3 is not None and nifty_ret_3m is not None) else None

    return StockMetrics(
        symbol=symbol,
        industry=industry,
        close=last,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200 if not math.isnan(sma200) else sma50,
        rsi=rsi,
        atr_pct=atrp,
        ret_1m=r1,
        ret_3m=r3,
        ret_6m=r6,
        rel_strength_3m=rel3,
        vol_surge=vol_surge,
        traded_value_cr=traded_value_cr,
        dist_from_high_pct=dist_from_high,
        sma50_rising=sma50_rising,
    )


def download_and_compute(
    universe: List[UniverseStock],
    period: str = "1y",
    chunk_size: int = 50,
) -> List[StockMetrics]:
    """Batch-download history via yfinance and compute swing metrics."""
    import yfinance as yf

    industry_by_sym = {u.symbol: u.industry for u in universe}
    yf_to_plain = {_yf_symbol(u.symbol): u.symbol for u in universe}
    all_yf = list(yf_to_plain.keys())

    # Benchmark return for relative strength.
    nifty_ret_3m: Optional[float] = None
    try:
        import pandas as pd
        bench = yf.download(NIFTY_BENCHMARK, period=period, interval="1d",
                            auto_adjust=True, progress=False, threads=True)
        if bench is not None and not bench.empty:
            bclose = bench["Close"]
            # Newer yfinance returns MultiIndex columns even for a single ticker.
            if isinstance(bclose, pd.DataFrame):
                bclose = bclose.iloc[:, 0]
            bclose = bclose.dropna()
            nifty_ret_3m = _ret(bclose, 63)
            logger.info("Nifty 3m return: %s", f"{nifty_ret_3m:.2f}%" if nifty_ret_3m is not None else "n/a")
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not fetch Nifty benchmark: %s", e)

    results: List[StockMetrics] = []
    total = len(all_yf)
    for i in range(0, total, chunk_size):
        chunk = all_yf[i:i + chunk_size]
        logger.info("Downloading %d-%d of %d ...", i + 1, min(i + chunk_size, total), total)
        try:
            data = yf.download(chunk, period=period, interval="1d", auto_adjust=True,
                               progress=False, group_by="ticker", threads=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("Chunk download failed (%s); skipping.", e)
            continue

        for yfs in chunk:
            plain = yf_to_plain[yfs]
            try:
                sub = data[yfs] if len(chunk) > 1 else data
            except (KeyError, TypeError):
                continue
            m = _compute_metrics_for(plain, industry_by_sym.get(plain, "Unknown"), sub, nifty_ret_3m)
            if m is not None:
                results.append(m)

    logger.info("Computed metrics for %d / %d symbols", len(results), total)
    return results


# ─── Stage 1: filter + score + rank ───────────────────────────────────────────

@dataclass
class ScreenConfig:
    min_price: float = 50.0
    min_liquidity_cr: float = 5.0     # avg daily traded value, ₹ crore
    rsi_min: float = 45.0
    rsi_max: float = 80.0
    max_atr_pct: float = 9.0          # avoid hyper-volatile names
    require_above_200: bool = True
    require_sma_stack: bool = True
    require_positive_rel_strength: bool = False
    shortlist_size: int = 40
    max_per_industry: int = 3


def _passes_filters(m: StockMetrics, c: ScreenConfig) -> bool:
    if m.close < c.min_price:
        return False
    if m.traded_value_cr < c.min_liquidity_cr:
        return False
    if not (c.rsi_min <= m.rsi <= c.rsi_max):
        return False
    if m.atr_pct > c.max_atr_pct:
        return False
    if c.require_above_200 and not m.above_200:
        return False
    if c.require_sma_stack and not m.sma_stack:
        return False
    if c.require_positive_rel_strength and (m.rel_strength_3m is None or m.rel_strength_3m <= 0):
        return False
    return True


def _percentile_ranks(values: List[Optional[float]]) -> List[float]:
    """Return percentile rank (0..1) per value; None → 0."""
    idx = [(v, i) for i, v in enumerate(values) if v is not None]
    out = [0.0] * len(values)
    if not idx:
        return out
    idx.sort(key=lambda t: t[0])
    n = len(idx)
    for rank, (_, i) in enumerate(idx):
        out[i] = rank / (n - 1) if n > 1 else 1.0
    return out


def _rsi_sweetspot(rsi: float) -> float:
    """Score peaks around 60 (strong but not blow-off); 0..1."""
    return max(0.0, 1.0 - abs(rsi - 60.0) / 40.0)


def score_and_rank(metrics: List[StockMetrics], c: ScreenConfig) -> List[StockMetrics]:
    passed = [m for m in metrics if _passes_filters(m, c)]
    logger.info("%d / %d symbols pass hard filters", len(passed), len(metrics))
    if not passed:
        return []

    pr_ret3 = _percentile_ranks([m.ret_3m for m in passed])
    pr_ret1 = _percentile_ranks([m.ret_1m for m in passed])
    pr_rel = _percentile_ranks([m.rel_strength_3m for m in passed])
    pr_vol = _percentile_ranks([m.vol_surge for m in passed])
    pr_liq = _percentile_ranks([m.traded_value_cr for m in passed])
    pr_prox = _percentile_ranks([-m.dist_from_high_pct for m in passed])  # closer to high = higher

    for k, m in enumerate(passed):
        m.score = round(
            0.28 * pr_ret3[k]
            + 0.20 * pr_rel[k]
            + 0.15 * pr_ret1[k]
            + 0.12 * _rsi_sweetspot(m.rsi)
            + 0.10 * pr_prox[k]
            + 0.08 * pr_vol[k]
            + 0.07 * pr_liq[k],
            4,
        )

    passed.sort(key=lambda m: m.score, reverse=True)

    # Industry-diversified shortlist.
    shortlisted: List[StockMetrics] = []
    per_industry: Dict[str, int] = {}
    for m in passed:
        cap = c.max_per_industry
        industry = (m.industry or "").strip()
        is_unknown = not industry or industry.lower() == "unknown"
        if cap > 0 and not is_unknown and per_industry.get(industry, 0) >= cap:
            continue
        shortlisted.append(m)
        if not is_unknown:
            per_industry[industry] = per_industry.get(industry, 0) + 1
        if len(shortlisted) >= c.shortlist_size:
            break

    return shortlisted


def render_shortlist_table(rows: List[StockMetrics]) -> str:
    def f(v: Optional[float], suf: str = "") -> str:
        return f"{v:.1f}{suf}" if v is not None else "—"

    out = [
        "| # | Symbol | Industry | Close ₹ | RSI | ATR% | 1m% | 3m% | RS3m | VolSurge | TradedVal(Cr) | %fromHigh | Score |",
        "|--:|--------|----------|--------:|----:|----:|----:|----:|-----:|---------:|--------------:|----------:|------:|",
    ]
    for i, m in enumerate(rows, 1):
        out.append(
            f"| {i} | {m.symbol} | {m.industry} | {m.close:,.1f} | {m.rsi:.0f} | {m.atr_pct:.1f} "
            f"| {f(m.ret_1m)} | {f(m.ret_3m)} | {f(m.rel_strength_3m)} | {m.vol_surge:.2f} "
            f"| {m.traded_value_cr:,.1f} | {m.dist_from_high_pct:.1f} | {m.score:.3f} |"
        )
    return "\n".join(out)


# ─── Stage 2: LLM curation via Copilot CLI ────────────────────────────────────

CURATION_SYSTEM_PROMPT = """You are an elite equity analyst building a monthly
SWING-TRADING WATCHLIST for the Indian market (NSE). You have been handed a
machine-screened shortlist that already passed mechanical momentum / trend /
liquidity / volatility filters. Your job is to VET each name on quality and
produce the final, high-conviction watchlist that a daily swing system will
trade from over the coming month.

Trading profile this watchlist must serve:
- Target ~{target_profit}% per trade within ≤{max_holding_days} days, then rotate.
- Liquid, clean, tradable names only — NO operators/penny/illiquid/manipulated
  stocks, NO names with serious accounting or balance-sheet red flags.

For EACH shortlisted symbol, use your research tools to check:
1. **Business / fundamentals** — is it a real, quality business? Sales & profit
   growth trend, margins, ROE/ROCE, debt/leverage, promoter pledging,
   shareholding trend, any governance/forensic red flags (screener.in).
2. **Financial trend** — last few quarters: growth accelerating or rolling over?
   Any earnings disappointment or guidance cut? (screener.in / news).
3. **Technical setup** — confirm the swing thesis: trend vs 20/50/200-DMA, RSI,
   MACD, volume, proximity to a breakout level or healthy pullback support, and
   whether a ~{target_profit}% move in the window is realistic from here.
4. **Catalyst / risk** — upcoming results, sector tailwind/headwind, event risk.

Then DECIDE: KEEP (with a swing setup label) or REJECT (with the reason).
Prefer QUALITY over quantity — it is fine to return fewer than {final_size}
names if only that many are genuinely worth trading. Reject anything you cannot
verify or that has a real red flag.

Output a Markdown report with these sections:

## 1. Market & Selection Overview
Brief read on the tape (Nifty/Bank Nifty trend, breadth) and your selection
stance this month (grounded in live data).

## 2. Curated Watchlist (KEEPERS)
A ranked table, best-first:
| Rank | Symbol | Sector | Setup | Quality | Entry Zone ₹ | Stop Hint ₹ | Why it's on the list |
Setup ∈ {{Breakout, Pullback, Momentum, Reversal, Range}}. Quality ∈ {{High, Medium}}.
Keep "Why" to one tight line each, citing the key evidence (src: ...).

## 3. Rejections (with reasons)
A compact table of shortlisted names you dropped and the one-line reason
(e.g. high debt, earnings rollover, overbought/extended, illiquid, red flag).

## 4. How to use this list
One short paragraph: this list feeds the daily swing runner for the next month;
re-run curation monthly; daily entries/stops are decided then, not here.

## 5. MACHINE-READABLE OUTPUT (required)
Finally, output the final keepers as a SINGLE fenced code block tagged json,
EXACTLY in this shape (no extra prose inside the block):

```json
{{"watchlist": [
  {{"symbol": "DIXON", "sector": "Consumer Durables", "setup": "Breakout", "quality": "High", "note": "QoQ growth + breakout on volume"}}
]}}
```
Use plain NSE tickers (e.g. DIXON, not DIXON.NS). Order the array best-first to
match your ranked table. This block is parsed by an automated script, so it MUST
be valid JSON and MUST be the LAST thing in your response.

Rules: be decisive and evidence-based; never fabricate a number — if a tool
fails, say so and judge conservatively. This is research, NOT investment advice.
"""


def build_curation_prompt(
    shortlist: List[StockMetrics],
    final_size: int,
    target_profit: float,
    max_holding_days: int,
    web_grounding: bool,
    scraper_tools: bool,
) -> str:
    system = CURATION_SYSTEM_PROMPT.format(
        target_profit=f"{target_profit:g}",
        max_holding_days=int(max_holding_days),
        final_size=int(final_size),
    )
    system = system.rstrip()
    if web_grounding:
        system += "\n\n" + WEB_GROUNDING_DIRECTIVE.strip()
    if scraper_tools:
        system += "\n\n" + SCRAPER_TOOLS_DIRECTIVE.strip()

    today = date.today().isoformat()
    return (
        f"{system}\n\n"
        f"# Today's Date\n\n{today}\n\n"
        f"# Target\n\nCurate up to {int(final_size)} high-quality swing names "
        f"(profile: ~{target_profit:g}% in ≤{int(max_holding_days)} days).\n\n"
        f"# Machine-Screened Shortlist ({len(shortlist)} names)\n\n"
        f"{render_shortlist_table(shortlist)}\n\n"
        f"# Request\n\nVet every shortlisted name with your tools and produce the "
        f"final curated watchlist exactly as specified, ending with the required "
        f"json block.\n"
    )


_CURATE_HANDOFF = (
    "Read the file `{path}` in its entirety using your "
    "file-read tool. It contains your system role, a machine-screened "
    "shortlist of stocks, and a request. Follow it exactly and respond with "
    "ONLY the final Markdown report (which MUST end with the required json "
    "block). Do not echo the prompt or describe what you are doing."
)


def invoke_copilot(
    prompt_text: str,
    *,
    model: Optional[str],
    web_grounding: bool,
    scraper_tools: bool,
    copilot_log: Optional[Path],
    log_level: str,
    extra_cli_args: Optional[List[str]] = None,
) -> str:
    """Run the curation prompt on the configured agent backend."""
    mcp_servers: dict = {}
    if scraper_tools:
        try:
            mcp_servers = scraper_mcp()
        except FileNotFoundError as e:
            logger.warning("Skipping scraper tools: %s", e)

    request = AgentRequest(
        prompt=prompt_text,
        label="curate",
        handoff_instruction=_CURATE_HANDOFF,
        mcp_servers=mcp_servers,
        requires=frozenset({Capability.WEB_SEARCH}) if web_grounding else frozenset(),
        model=model,
        log_file=copilot_log,
        log_level=log_level,
        extra_cli_args=tuple(extra_cli_args or ()),
    )
    logger.info("Watchlist curation — %d prompt bytes", len(prompt_text))
    return run_agent(request).text


# ─── Parse LLM output → watchlist file ────────────────────────────────────────

_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def parse_curated_watchlist(llm_output: str) -> List[dict]:
    """Extract the final json watchlist block. Returns list of picks (best-first)."""
    matches = _JSON_BLOCK_RE.findall(llm_output)
    for raw in reversed(matches):  # the spec says it's the LAST block
        try:
            obj = json.loads(raw)
            wl = obj.get("watchlist")
            if isinstance(wl, list) and wl:
                cleaned = []
                for item in wl:
                    if isinstance(item, dict) and item.get("symbol"):
                        cleaned.append(item)
                    elif isinstance(item, str):
                        cleaned.append({"symbol": item})
                if cleaned:
                    return cleaned
        except json.JSONDecodeError:
            continue
    return []


def write_watchlist_file(picks: List[dict], path: Path, *, index: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_watchlist(picks, index=index), encoding="utf-8")
    logger.info("Wrote %d symbols to watchlist file: %s", len(picks), path)


def render_watchlist(picks: List[dict], *, index: str) -> str:
    lines = [
        f"# Swing-trading watchlist — curated {date.today().isoformat()} "
        f"from {index} universe by watchlist_curator.py",
        "# Format: SYMBOL  # sector | setup | quality | note",
        "# Consume with: swing_trading_copilot.py --watchlist-file <this file>",
        "",
    ]
    for p in picks:
        sym = str(p.get("symbol", "")).strip().upper()
        if not sym:
            continue
        meta = " | ".join(
            str(p.get(k, "")).strip() for k in ("sector", "setup", "quality", "note")
            if str(p.get(k, "")).strip()
        )
        lines.append(f"{sym}  # {meta}" if meta else sym)
    return "\n".join(lines) + "\n"


def write_mechanical_watchlist(rows: List[StockMetrics], path: Path, *, index: str) -> None:
    """Stage-1-only watchlist (no LLM) — used with --no-llm."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_mechanical_watchlist(rows, index=index), encoding="utf-8")
    logger.info("Wrote %d symbols to mechanical watchlist file: %s", len(rows), path)


def render_mechanical_watchlist(rows: List[StockMetrics], *, index: str) -> str:
    lines = [
        f"# Swing-trading watchlist (MECHANICAL, no LLM vetting) — "
        f"{date.today().isoformat()} from {index} universe",
        "# Format: SYMBOL  # industry | score",
        "# Consume with: swing_trading_copilot.py --watchlist-file <this file>",
        "",
    ]
    for m in rows:
        lines.append(f"{m.symbol}  # {m.industry} | score {m.score:.3f}")
    return "\n".join(lines) + "\n"


def persist_watchlist(
    picks: List[dict],
    *,
    index: str,
    report: Optional[str] = None,
    shortlist: Optional[str] = None,
    copilot_log: Optional[Path] = None,
) -> str:
    set_document(
        "watchlists",
        "swing_current",
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "index": index,
            "picks": picks,
        },
    )
    artifacts = {"watchlist.txt": render_watchlist(picks, index=index)}
    if report is not None:
        artifacts["report.md"] = report
    if shortlist is not None:
        artifacts["shortlist.md"] = shortlist
    if copilot_log is not None and copilot_log.exists():
        artifacts["copilot.log"] = copilot_log.read_text(
            encoding="utf-8", errors="replace"
        )
    group_id, _ = save_artifacts(
        "watchlist_curation",
        f"{index}-{datetime.now():%Y%m%dT%H%M%S}",
        artifacts,
        metadata={"index": index, "symbols": [pick.get("symbol") for pick in picks]},
        content_types={
            "watchlist.txt": "text/plain",
            "report.md": "text/markdown",
            "shortlist.md": "text/markdown",
            "copilot.log": "text/plain",
        },
    )
    return group_id


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _env_float(name: str) -> Optional[float]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Monthly swing-trading watchlist curator for Indian equities. "
            "Stage 1 mechanically screens a universe (Nifty 500 etc.); Stage 2 "
            "uses the Copilot CLI + scraper MCP to vet fundamentals/financials/"
            "technicals and emit a final ranked watchlist file."
        ),
    )
    # Universe
    p.add_argument("--index", default=os.getenv("CURATOR_INDEX", "nifty500"),
                   choices=sorted(NSE_INDEX_URLS),
                   help="NSE index universe to scan. Default: nifty500.")
    p.add_argument("--universe-file", type=Path, default=None,
                   help="Custom universe file (NSE symbols, CSV or one-per-line). Overrides --index.")
    p.add_argument("--period", default="1y",
                   help="History period for yfinance (e.g. 6mo, 1y, 2y). Default: 1y.")
    p.add_argument("--chunk-size", type=int, default=50,
                   help="yfinance batch size. Default: 50.")

    # Stage-1 screen config
    p.add_argument("--min-price", type=float, default=_env_float("CURATOR_MIN_PRICE") or 50.0,
                   help="Minimum share price ₹. Default: 50.")
    p.add_argument("--min-liquidity-cr", type=float,
                   default=_env_float("CURATOR_MIN_LIQ_CR") or 5.0,
                   help="Min avg daily traded value in ₹ crore. Default: 5.")
    p.add_argument("--rsi-min", type=float, default=45.0, help="Min RSI(14). Default: 45.")
    p.add_argument("--rsi-max", type=float, default=80.0, help="Max RSI(14). Default: 80.")
    p.add_argument("--max-atr-pct", type=float, default=9.0,
                   help="Max ATR%% (volatility cap). Default: 9.")
    p.add_argument("--no-require-stack", action="store_true",
                   help="Don't require close>SMA50>SMA200 (looser trend filter).")
    p.add_argument("--require-positive-rs", action="store_true",
                   help="Require positive 3m relative strength vs Nifty.")
    p.add_argument("--shortlist-size", type=int, default=40,
                   help="Stage-1 shortlist size handed to the LLM. Default: 40.")
    p.add_argument("--max-per-industry", type=int, default=3,
                   help="Max names per industry in the shortlist (0 = no cap). Default: 3.")

    # Stage-2 / output
    p.add_argument("--final-size", type=int, default=20,
                   help="Target size of the final curated watchlist. Default: 20.")
    p.add_argument("--target-profit", type=float, default=20.0,
                   help="Swing target %% the watchlist must serve. Default: 20.")
    p.add_argument("--max-holding-days", type=int, default=30,
                   help="Swing holding window (days) the watchlist must serve. Default: 30.")
    p.add_argument("--llm", action=argparse.BooleanOptionalAction, default=True,
                   help="Run Stage-2 LLM curation. --no-llm stops after the mechanical screen.")
    p.add_argument("--out-watchlist", type=Path, default=None,
                   help="Optional file export. The active watchlist is always stored in SQLite.")
    p.add_argument("--out-report", type=Path, default=None,
                   help="Optional Markdown export for the full curation report.")

    # Copilot passthrough
    p.add_argument("--model", default=None, help="Copilot model (overrides COPILOT_MODEL).")
    p.add_argument("--web-grounding", action=argparse.BooleanOptionalAction,
                   default=(os.getenv("WEB_GROUNDING", "true").strip().lower() not in {"0", "false", "no", "off"}),
                   help="Force live web grounding in Stage 2. Default: on.")
    p.add_argument("--scraper-tools", action=argparse.BooleanOptionalAction,
                   default=(os.getenv("SCRAPER_TOOLS", "true").strip().lower() not in {"0", "false", "no", "off"}),
                   help="Attach the scraper MCP server in Stage 2. Default: on.")
    p.add_argument("--copilot-arg", action="append", default=[],
                   help="Extra arg passed through to `copilot` (repeatable).")
    p.add_argument("--copilot-log", type=Path, default=None,
                   help="Save Copilot stderr to file + tee live. 'auto' → logs/curate-<ts>.log.")
    p.add_argument("--copilot-log-level", choices=["error", "warn", "info", "debug"],
                   default="debug", help="Copilot --log-level when --copilot-log is set.")

    # Misc
    p.add_argument("--save-shortlist", type=Path, default=None,
                   help="Optional path to save the Stage-1 shortlist table (Markdown).")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    # 1) Universe
    try:
        if args.universe_file:
            universe = load_universe_from_file(args.universe_file)
            universe_label = str(args.universe_file)
        else:
            universe = load_universe_from_index(args.index)
            universe_label = args.index
    except Exception as e:
        logger.error("Failed to load universe: %s", e)
        return 2

    print(f"\n=== Watchlist Curator — {date.today().isoformat()} ===")
    print(f"Universe:        {universe_label} ({len(universe)} symbols)")
    print(f"Period:          {args.period}")
    print(f"Stage 2 (LLM):   {'ON' if args.llm else 'OFF (mechanical only)'}")
    print("=" * 52 + "\n")

    # 2) Stage 1 — mechanical metrics + screen
    logger.info("Stage 1: downloading data and computing metrics ...")
    metrics = download_and_compute(universe, period=args.period, chunk_size=args.chunk_size)
    if not metrics:
        logger.error("No metrics computed — aborting (check connectivity / symbols).")
        return 1

    screen_cfg = ScreenConfig(
        min_price=args.min_price,
        min_liquidity_cr=args.min_liquidity_cr,
        rsi_min=args.rsi_min,
        rsi_max=args.rsi_max,
        max_atr_pct=args.max_atr_pct,
        require_sma_stack=not args.no_require_stack,
        require_above_200=not args.no_require_stack,
        require_positive_rel_strength=args.require_positive_rs,
        shortlist_size=args.shortlist_size,
        max_per_industry=args.max_per_industry,
    )
    shortlist = score_and_rank(metrics, screen_cfg)
    if not shortlist:
        logger.error("No symbols passed the Stage-1 filters. Loosen --rsi-min/--min-liquidity-cr "
                     "or pass --no-require-stack.")
        return 1

    table = render_shortlist_table(shortlist)
    print("\n──── Stage-1 Shortlist (top momentum/quality candidates) ────\n")
    print(table)
    print()

    if args.save_shortlist:
        args.save_shortlist.parent.mkdir(parents=True, exist_ok=True)
        args.save_shortlist.write_text(
            f"# Stage-1 shortlist — {universe_label} — {date.today().isoformat()}\n\n{table}\n",
            encoding="utf-8",
        )
        logger.info("Saved shortlist to %s", args.save_shortlist)

    # 3) Mechanical-only mode → write and exit.
    if not args.llm:
        picks = [{"symbol": row.symbol, "industry": row.industry} for row in shortlist]
        group_id = persist_watchlist(
            picks,
            index=universe_label,
            shortlist=(
                f"# Stage-1 shortlist — {universe_label} — "
                f"{date.today().isoformat()}\n\n{table}\n"
            ),
        )
        if args.out_watchlist:
            write_mechanical_watchlist(shortlist, args.out_watchlist, index=universe_label)
        print(f"\nMechanical watchlist stored → sqlite://artifacts/{group_id}")
        print("Re-run without --no-llm for fundamental/financial vetting.\n")
        return 0

    # 4) Stage 2 — LLM curation.
    copilot_log_path: Optional[Path] = args.copilot_log
    if copilot_log_path is not None and str(copilot_log_path).lower() == "auto":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        copilot_log_path = runtime_dir() / "logs" / f"curate-{stamp}.log"

    prompt = build_curation_prompt(
        shortlist,
        final_size=args.final_size,
        target_profit=args.target_profit,
        max_holding_days=args.max_holding_days,
        web_grounding=args.web_grounding,
        scraper_tools=args.scraper_tools,
    )

    print("\n──── Stage 2: LLM curation (fundamentals + financials + technicals) ────\n")
    try:
        llm_output = invoke_copilot(
            prompt,
            model=args.model,
            web_grounding=args.web_grounding,
            scraper_tools=args.scraper_tools,
            copilot_log=copilot_log_path,
            log_level=args.copilot_log_level,
            extra_cli_args=args.copilot_arg,
        )
    except Exception as e:
        logger.exception("Stage-2 curation failed: %s", e)
        logger.warning("Falling back to the mechanical shortlist.")
        picks = [{"symbol": row.symbol, "industry": row.industry} for row in shortlist]
        persist_watchlist(
            picks,
            index=universe_label,
            shortlist=table,
            copilot_log=copilot_log_path,
        )
        if args.out_watchlist:
            write_mechanical_watchlist(shortlist, args.out_watchlist, index=universe_label)
        return 1

    # 5) Persist report + active watchlist; optional paths are exports.
    if args.out_report:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(llm_output, encoding="utf-8")
        logger.info("Exported curation report to %s", args.out_report)

    picks = parse_curated_watchlist(llm_output)
    if picks:
        group_id = persist_watchlist(
            picks,
            index=universe_label,
            report=llm_output,
            shortlist=table,
            copilot_log=copilot_log_path,
        )
        if args.out_watchlist:
            write_watchlist_file(picks, args.out_watchlist, index=universe_label)
        print(
            f"\nCurated watchlist ({len(picks)} names) stored "
            f"→ sqlite://artifacts/{group_id}"
        )
    else:
        logger.warning(
            "Could not parse a json watchlist block from the model output. "
            "Storing the mechanical shortlist as fallback.",
        )
        fallback = [{"symbol": row.symbol, "industry": row.industry} for row in shortlist]
        persist_watchlist(
            fallback,
            index=universe_label,
            report=llm_output,
            shortlist=table,
            copilot_log=copilot_log_path,
        )
        if args.out_watchlist:
            write_mechanical_watchlist(shortlist, args.out_watchlist, index=universe_label)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
