I'll ground this in live data. Let me fetch technicals and prices for the watchlist in parallel, starting with the first batch.

Let me fetch the next batch of watchlist symbols.

Now the final batch of watchlist symbols plus market regime data.

Now let me ground the market regime (Nifty/Bank Nifty) with a live source.

## Swing Screener — NSE/BSE | 2026‑06‑25

> **Data note:** `fetch_technical_indicators` returned valid RSI/MACD/EMA20/volume but **NaN for SMA‑50/200, ADX and ATR** for every symbol (src: technicals) — a data gap. I therefore judged trend via EMA20, 52‑week positioning and 20‑day high/low instead of the 50/200‑DMA stack, and built stops off swing structure rather than ATR. All prices are live intraday (src: yfinance via indian-stock-data).

---

## 1. Market Regime

The tape is **risk‑on and supportive of swing longs**. Nifty 50 closed **+0.83% at 24,021.65** and Bank Nifty **+1.69% (~58,256)**, led by banks and IT, with healthy breadth — Nifty advance/decline **29:21** and Bank Nifty **12:2** (src: web/thehindubusinessline, ET, moneycontrol). Crude easing and improved sentiment underpin the move, though analysts flag ongoing consolidation, so be **selective**. Net: a green light for *quality* breakouts/pullbacks, not a "buy anything" tape. Notably, several watchlist names are already **extended well above their 20‑EMA** after this rally — chase‑risk is the main hazard today.

---

## 2. Screened Candidates

Max risk/trade = **₹4,000** (2% of ₹200,000). Min R:R 2:1, window ≤30 days.

**KPRMILL** — Setup: Momentum / fresh Breakout
- Trend ✅ (price ₹1,218 >> EMA20 1,065) · RSI 64 ✅ band · MACD bullish ✅ · **Volume 10.4× avg ✅✅** (huge) · 52w‑high ₹1,334 = today's high · Liquidity ✅. **Fail/caution:** closed +7.72% but with a **massive upper wick** (high 1,334 → close 1,218) = intraday distribution; price **+14% above EMA20** = extended (src: technicals/price).
- Entry ₹1,255–1,265 (on a *reclaim/close >1,260*), Stop ₹1,170 (risk ₹95/sh), Target ₹1,518 (+20%). **R:R ≈ 2.7**. Window 2–4 wks.
- Size: 42 sh ≈ ₹53,130; open risk ₹3,990.
- **Verdict: WAIT‑FOR‑TRIGGER** — daily close above ₹1,260 holding above ₹1,180; don't chase the wick.

**JSWINFRA** — Setup: Breakout / Momentum
- Trend ✅ (₹338 > EMA20 290) · **RSI 72.6 ❌ overbought** · MACD bullish ✅ · **Volume 6.8× ✅** · near 52w‑high 349 · Liquidity ✅. **Fail:** **+16.6% above EMA20** — far too extended to enter (src: technicals).
- Entry (only on pullback) ₹315–320, Stop ₹296, Target ₹384 (+20%). R:R ≈ 2.8.
- Size: ~16 sh ≈ ₹5,100/risk… (defer).
- **Verdict: WAIT‑FOR‑TRIGGER** — buy a pullback to ₹315–320 that holds; no chasing at ₹338.

**DEEPAKFERT** — Setup: Breakout (cleanest fit)
- Trend ✅ (₹1,602 > EMA20 1,494, +7.3% — sane) · **RSI 66.8 ✅** in band · MACD bullish ✅ · Volume 0.42× ⚠️ (light) · 20d‑high ₹1,617 just overhead · 52w‑high 1,778 · PE 27 / fwd 14.7 ✅ no landmine (src: price/technicals).
- Entry ₹1,595–1,620, Stop ₹1,525 (risk ₹85/sh), Target ₹1,925 (+20%); first resistance 1,778. **R:R ≈ 2.0 to 1,778 / 3.8 to target.** Window 3–4 wks.
- Size: 47 sh ≈ ₹75,670; open risk ₹3,995 (⚠️ position value ~38% of capital — see caveats).
- **Verdict: TAKE NOW (small) / add on close >₹1,617 with ≥1.5× volume.**

**NUVAMA** — Setup: Breakout
- Trend ✅ (₹1,736 > EMA20 1,620) · RSI 69.5 ⚠️ upper band · MACD bullish ✅ · Volume 0.73× ⚠️ · just below 52w‑high 1,779 · Liquidity ✅ (src: technicals).
- Entry ₹1,780–1,800 (on breakout), Stop ₹1,655 (risk ₹130), Target ₹2,090 (+20%). **R:R ≈ 2.4.** Window 3–4 wks.
- Size: 30 sh ≈ ₹53,550; open risk ₹3,900.
- **Verdict: WAIT‑FOR‑TRIGGER** — daily close above ₹1,779.

**NETWEB** — Setup: Breakout
- Trend ✅ (₹5,074 > EMA20 4,643, +9.3%) · RSI 60.6 ✅ · MACD bullish ✅ · **Volume 0.38× ❌** (breakout needs volume) · at 52w‑high 5,244 (src: technicals).
- Entry ₹5,250–5,300, Stop ₹4,930 (risk ₹320), Target ₹6,300 (+20%). **R:R ≈ 3.3.** Window 3–4 wks.
- Size: 12 sh ≈ ₹63,000; open risk ₹3,840.
- **Verdict: WAIT‑FOR‑TRIGGER** — close above ₹5,244 on ≥1.5× volume.

**GABRIEL** — Setup: Breakout
- Trend ✅ (₹1,241 > EMA20 1,116) · RSI 65.3 ✅ · MACD bullish ✅ · Volume 0.61× ⚠️ · 20d‑high 1,254 overhead · 52w‑high 1,388 (src: technicals).
- Entry ₹1,255–1,270, Stop ₹1,175 (risk ₹80), Target ₹1,506 (+20%); first resistance 1,388. **R:R ≈ 1.9 to 1,388 / 3.1 to target.** Window 3–4 wks.
- Size: 50 sh ≈ ₹62,750; open risk ₹4,000.
- **Verdict: WAIT‑FOR‑TRIGGER** — close above ₹1,254.

**CAPLIPOINT** — Setup: Momentum (extended)
- Trend ✅ but **RSI 74.5 ❌ overbought**, **+11% above EMA20 ❌**, at 52w‑high 2,590. MACD bullish ✅. **Verdict: WATCH** — only on a pullback to ~₹2,300.

**APARINDS** — **RSI 75.6 ❌ overbought**, **+12% above EMA20 ❌**, at 52w‑high 17,157. Too extended. **Verdict: WATCH** (pullback to ~15,000).

**OLECTRA** — ₹1,492, RSI 69.9, MACD bullish (strong histogram), +10.8% above EMA20, below 20d‑high 1,553, 52w‑high 1,714 gives room. Red day. **Verdict: WAIT‑FOR‑TRIGGER** — close above ₹1,553.

**TEJASNET** — ₹624, RSI 67.3, MACD bullish, below 20d‑high 645. **Fail:** **negative EPS (‑51.36), no PE** = fundamental landmine for a swing long; volume 0.29×. **Verdict: WATCH** only above ₹645.

**DATAPATTNS** — ₹4,620 **‑4.37% today**, bearish reversal candle off 4,907; RSI 65.7. Momentum broke intraday. **Verdict: WATCH** — needs a green reclaim of ₹4,800.

**ENGINERSIN** — ₹254 **‑2.52%**, RSI 63.9, near EMA20 242; thin MACD histogram. Controlled pullback but no reversal candle yet. **Verdict: WATCH/WAIT** — reclaim ₹258.

**NIACL** — ₹188 **‑3.38% today**, sharp red candle; PE/PB cheap but momentum rolling over. **Verdict: WATCH.**

**WOCKPHARMA** — ₹1,968 **‑2.09%**, **MACD turned bearish (histogram ‑6.2) ❌**, off 52w‑high 2,422, PE 150. **Verdict: FAIL / skip.**

---

## 3. Ranked Shortlist (qualifiers only)

| # | Symbol | Setup | Entry (₹) | Stop (₹) | Target (₹) | R:R | Verdict |
|---|--------|-------|-----------|----------|------------|-----|---------|
| 1 | **DEEPAKFERT** | Breakout | 1,595–1,620 | 1,525 | 1,925 | 3.8 | **TAKE NOW / add >1,617** |
| 2 | **NUVAMA** | Breakout | 1,780–1,800 | 1,655 | 2,090 | 2.4 | WAIT‑FOR‑TRIGGER >1,779 |
| 3 | **KPRMILL** | Momentum | 1,255–1,265 | 1,170 | 1,518 | 2.7 | WAIT‑FOR‑TRIGGER >1,260 |
| 4 | **NETWEB** | Breakout | 5,250–5,300 | 4,930 | 6,300 | 3.3 | WAIT (needs volume) >5,244 |
| 5 | **GABRIEL** | Breakout | 1,255–1,270 | 1,175 | 1,506 | 3.1 | WAIT‑FOR‑TRIGGER >1,254 |

JSWINFRA, OLECTRA, CAPLIPOINT, APARINDS, TEJASNET, DATAPATTNS, ENGINERSIN, NIACL = WATCH (extended/red/landmine). WOCKPHARMA = fail.

**Honest read:** only **DEEPAKFERT** is buyable at current levels today; the other strong charts are either **sitting just under a breakout trigger** or **over‑extended after today's rally**. I'm not forcing market entries into extended names.

---

## 4. Deployment Plan

Capital ₹200,000 · 2% rule · max 6 positions. Note: 2%‑risk sizing on these **high‑priced, low‑intraday‑vol names produces large position values** (e.g. DEEPAKFERT full size ≈ ₹76k ≈ 38% of book) — so **capital, not risk, is the binding constraint**; cap any single name at ~₹50k (≈25%) for diversification.

**Recommended staging (target 3 names):**
1. **TAKE NOW — DEEPAKFERT:** capped to **31 sh ≈ ₹49,650**, stop 1,525 → open risk **₹2,635**.
2. **On trigger — NUVAMA** (>1,779): **28 sh ≈ ₹49,980**, risk **₹3,640**.
3. **On trigger — KPRMILL** (>1,260): **40 sh ≈ ₹50,200**, risk **₹3,800**.

- **Capital deployed:** ~₹1,49,800 (≈75%) · **Cash buffer:** ~₹50,200.
- **Total open risk if all 3 fill:** ~**₹10,075 ≈ 5.0% of capital** — within sane limits.
- Keep 2–3 slots free for NETWEB/GABRIEL/OLECTRA if they trigger; do **not** exceed ~₹16k (≈8%) total open risk across the book. Add only on confirmed daily closes with ≥1.5× volume; book 50% at +20% and trail the rest below the 20‑EMA.

---

## 5. Caveats

- **Data gaps (src: technicals):** SMA‑50/200, ADX and ATR returned **NaN** for all symbols — the 50/200‑DMA uptrend filter and ATR‑based stops could **not** be directly verified; I substituted EMA20, 52‑week position and 20‑day swing levels. Stops are structure‑based, not ATR‑based. Confirm the 50/200‑DMA stack on a chart before executing.
- Indicator values (RSI/MACD/EMA) are as returned by the scraper and may lag the live tick by a session; **re‑check at the open** before acting on any trigger.
- KPRMILL/JSWINFRA posted explosive volume — verify there's **no news/bulk‑deal/one‑off** distorting the move (KPRMILL news feed returned empty; src: technicals) and watch for gap risk.
- TEJASNET is **loss‑making** (negative EPS); WOCKPHARMA PE ~150 — excluded/flagged on fundamentals.
- Mind event risk: results season, F&O expiry, RBI policy.
- **Not investment advice** — a screening framework only. Verify live prices and place hard stops; the setup is invalid if the stop is hit.

