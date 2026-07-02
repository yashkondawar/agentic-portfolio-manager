I'll ground this in live data. Starting with the watchlist and a first wave of open positions.

Watchlist captured. BSE LTP confirmed live. Now fetching technicals for all open positions in waves.

Wave 1 done. Continuing with wave 2.

Final wave of positions.

Positions complete. Now grounding market regime and the failed TATAMOTORS price.

Data complete. Surfacing a couple fresh momentum candidates to round out the screen.

# 📊 Daily Swing Review — 2026-06-22

> Live data via `indian-stock-data` (RSI/MACD/MA/ATR/vol/S-R = `src: technicals`), market regime `src: web`. User-supplied LTPs cross-checked: BSE ₹4,032.70 ✓, BAJAJ-AUTO ₹10,191 ✓, MCX ₹2,870.40 ✓ — no material drift. `fetch_technical_indicators` for TATAMOTORS failed (no data on both attempts) — flagged, not fabricated.

---

## 1. Desk Snapshot

- **Stated swing capital:** ₹200,000 · **Deployed (current mkt value):** ₹1,890,900.65 · **Cash:** ₹6,922.30 · **Open positions:** 49.
- **🚨 Structural flag (assumption):** Deployed capital is **~9.5× the stated ₹200k**. The "2% rule = ₹4,000/trade" is mathematically meaningless against a ₹1.9M book. I assume the ₹200k figure is a stale/mislabeled config and treat the **real working book as ₹1.9M**, with **only ₹6,922 cash** to deploy. New buys therefore MUST be funded by exits (see §4).
- **Book P&L:** Invested ₹1,524,526 → Current ₹1,890,901 → **Unrealized +₹366,374 (+24.03%)** (src: supplied). No book-level profit goal set; per-trade goal +20%. The book is already net-green — job now is to **lock extended winners and amputate dead losers**, not chase.
- **Open risk:** Stops were **not supplied** (assumption: none active = uncontrolled). Using my proposed stops below, defined portfolio open risk ≈ **₹95k–110k (~5–6% of book)** — acceptable once stops are actually placed; today it is effectively unbounded. **Place the stops.**
- **Market regime (src: web):** Nifty 50 **24,102.9 (+0.37%)**, Bank Nifty **57,935.6 (+0.43%)**, breadth positive (Nifty A/D ~1.5), India VIX **12.84** (low). FIIs −₹636 Cr, DIIs +₹1,036 Cr. Gravestone-doji on Nifty near 24,200 resistance = **mildly risk-on but capped**. Tape supports *selective* swing longs, not aggressive adds.

---

## 2. Open Position Triage

*(Holding-days / days-left not supplied — I flag time-stop risk where price action shows a stalled or broken position regardless.)*

### 🟢 Strong winners — HOLD / TRAIL

**BEL** — **TRAIL-STOP** · Entry 284.78 / LTP 431.45 / **+51.5%** / past target (₹341.74).
- Above all MAs, RSI 61, MACD bull, ADX 27 strong (src: technicals). Trend intact.
- Trail stop **₹409** (S1/20-DMA zone); next target **₹443→460**. Let it run, protect gains.

**MAZDOCK** — **HOLD** · 1,014.84 / 2,541.70 / **+150.5%**.
- RSI 58, fresh MACD bull cross, coiling at 50/200-DMA, vol normal. Re-accelerating.
- Trail **₹2,380**; target **₹2,635** then ₹2,800.

**GRSE** — **HOLD/TRAIL** · 1,733.69 / 2,860.60 / **+65.0%**.
- RSI 61, MACD strong-bull, vol **2.9×**, above MAs. Breakout healthy.
- Trail **₹2,615**; target **₹3,020**.

**MAHABANK** — **TRAIL-STOP** · 54.28 / 89.47 / **+64.8%**.
- RSI 69.7 (hot), +38% vs 200-DMA, MACD bull. Extended — protect.
- Trail **₹84 (20-EMA)**; target **₹95**. Book partial 200/500 if RSI tags 75.

**GRAVITA** — **HOLD** · 1,172.75 / 1,743.90 / **+48.7%**. RSI 64, breakout on vol 1.6×, above all MAs. Trail **₹1,592**; target **₹1,836**.

**HBLENGINE** — **HOLD** · 541.11 / 817.65 / **+51.5%**. RSI 58, strong-bull, near 20d high. Stop **₹741**; target **₹884**.

**VOLTAMP** — **BOOK-PARTIAL** · 8,567.67 / 10,509 / **+22.7%** (past target ₹10,281).
- RSI 64, MACD strong-bull (hist 104), +25% vs 200-DMA — extended. Sell **3 of 6**, trail rest **₹9,840 (20-EMA)**; target ₹11,076.

**CDSL** — **BOOK-PARTIAL** · 1,089.44 / 1,371.80 / **+25.9%** (past target).
- **RSI 73 overbought**, MACD bull, +14% in 30d. Lock 20/45 shares, trail rest **₹1,267**; target ₹1,451.

**BHARTIARTL** — **HOLD** · 1,470 / 1,916.60 / **+30.4%**. RSI 65, MACD bull breakout. Stop **₹1,815**; target **₹1,971**.

**LT** — **HOLD** · 3,342.62 / 4,200.60 / **+25.7%**. RSI 65, above all MAs, MACD bull. Trail **₹3,955**; target **₹4,346**.

**BDL** — **HOLD** · 1,282.12 / 1,406.70 / **+9.7%**. RSI 69, vol 1.6×, 7d +16% — momentum surge. Stop **₹1,237**; target **₹1,538**.

**CAMS** — **HOLD** · 795.48 / 819.10 / **+2.9%**. RSI 62, strong-bull above all MAs. Stop **₹747**; target **₹954**.

**ETERNAL** — **HOLD** · 236.67 / 263.65 / **+11.4%**. RSI 61, strong-bull, MACD+. Stop **₹243**; target **₹284**.

**HDFCBANK** — **HOLD** · 773 / 786.40 / **+1.7%**. RSI 63, MACD bull, breaking 20-DMA. Stop **₹741**; target **₹927**.

**HAL** — **HOLD** · 4,632 / 4,515.20 / **−2.5%**. RSI 62, above MAs, MACD bull cross — recovering. Stop **₹4,266**; target **₹4,646→5,558**.

**NBCC** — **HOLD/ADD-watch** · 111 / 109.98 / **−0.9%**. RSI 62, ADX 33 strong, +12% vs 50-DMA. Clean. Stop **₹98**; target **₹118→133**.

**BALAMINES** — **HOLD** · 2,525.39 / 2,123.60 / **−15.9%**. RSI 60, ADX 40 strong-up, +27% vs 50-DMA, +16.5% in 30d — strong recovery. Stop **₹1,950**; target **₹2,374**.

**RECLTD** — **HOLD** · 485.55 / 369.85 / **−23.8%**. RSI 65, strong-bull, vol 1.7×, above MAs — best of the laggards. Stop **₹337**; target **₹387**.

### 🟡 Extended/fading winners — BOOK / TIGHT TRAIL

**BSE** — **BOOK-PARTIAL + TRAIL** · 673.72 / 4,032.70 / **+498.6%**.
- Monster gain but **MACD bearish**, RSI 52, below 20-DMA, 30d −3.8%, vol 0.65× (src: technicals). Momentum rolling over.
- **Book 22 of 45** (locks ~₹74k profit), trail remaining 23 at **₹3,729 (S1)**; invalidation = close <3,729.

**MCX** — **EXIT (book the spike)** · 977.58 / 2,870.40 / **+193.6%**.
- **MACD bearish, RSI 46, below 20/50-DMA, 30d −12.2%** — peak is in. ADX 28 now pointing down.
- **Sell full 65** into strength ≈ ₹186,576. Don't give back a triple. PEAK/EXHAUSTION confirmed.

**RVNL** — **TRAIL-TIGHT / BOOK** · 128.50 / 246.15 / **+91.6%**.
- Below 50-DMA (−9%) & 200-DMA (−20%), RSI 46, 30d −9%. Uptrend broken though MACD ticking up.
- Trail **₹222 (S1)**; if it loses 222, exit. Consider booking 100/200 now.

**SILVERBEES (silver ETF)** — **BOOK / TRAIL-TIGHT** · 164 / 225.14 / **+37.3%**.
- **Strong Bearish momentum**, RSI 41, below 20/50-DMA, 30d −10.9%. Trend rolled over.
- Trail **₹216**; lock at least half (100/200) now — commodity ETF, no catalyst to defend.

**BAJAJ-AUTO** — **TRAIL** · 7,054.90 / 10,191 / **+44.5%**.
- **MACD bearish**, RSI 52, sideways at 20-DMA, but vol 2.3×. Trail **₹9,812 (S1)**; target ₹10,660. Already past book-target — protect.

**GESHIP** — **BOOK at target** · 1,223.70 / 1,473.15 / **+20.4%** (≈target ₹1,468).
- Target hit. RSI 51, below 50-DMA, 30d −11.6% — momentum gone. **Book 50–100%** here; trail any remainder ₹1,360.

**JSL** — **HOLD/watch** · 640.51 / 708.80 / **+10.7%**. RSI 50, below 50/200-DMA but MACD recovering, ADX 28. Stop **₹662**; target **₹745**.

**WAAREEENER** — **HOLD/watch** · 2,432 / 3,061.70 / **+25.9%**. RSI 47, below 50-DMA, flat. Stop **₹2,955**; target **₹3,173**. Stalling — watch for break.

**TATAPOWER** — **HOLD/watch** · 324.36 / 405.95 / **+25.2%**. RSI 47, below 50-DMA, sideways. Stop **₹385**; target **₹430**.

**MOSCHIP** — **HOLD/watch** · 207 / 213.23 / **+3.0%**. RSI 52, MACD just turned bearish, flat. Stop **₹198**; target **₹229**.

### 🔴 Dead money / broken — EXIT or recovery-bounce only

**HAPPSTMNDS** — **EXIT** · 933.39 / 348.40 / **−62.7%**. Below all MAs, RSI 39, MACD bearish, 30d −5.7%. Broken swing turned bag. **Cut full 33.** Time-stop long breached.

**TCS** — **EXIT** · 3,482.50 / 2,127.80 / **−38.9%**. RSI 37, MACD bearish, −22.5% vs 200-DMA, downtrend. **Cut full 10.** No swing thesis left.

**WIPRO** — **EXIT** · 230 / 180.18 / **−21.7%**. RSI 35, MACD bearish, below all MAs, vol collapsing. **Cut full 80.** IT laggard.

**PRAJIND** — **EXIT** · 497.34 / 341.55 / **−31.3%**. RSI 41, MACD bearish, below 50-DMA, 30d −12.5%. **Cut full 40.**

**NAHARINDUS** — **EXIT (illiquid)** · 169.05 / 119.11 / **−29.5%**. **Avg vol ~26k, today 9.8k shares** — illiquid, gap risk. RSI 59 but untradeable for swing. **Exit 150 on strength**, mind slippage.

**CLEAN** — **TRAIL-bounce / EXIT-on-fail** · 1,729.10 / 821.10 / **−52.5%**. RSI 61 + **vol 11×** bounce but below 200-DMA. Dead-cat risk. Stop **₹753**; only hold the technical bounce, no averaging.

**KNRCON** — **bounce only** · 257.77 / 139.25 / **−46.0%**. RSI 63, +8.6% vs 50-DMA recovering, but −8% vs 200-DMA. Stop **₹123**; trim into ₹149.

**PRINCEPIPE** — **HOLD-tight / was a stop-out** · 722 / 287 / **−60.0%**. Ironically now RSI 62, ADX 33, above 50-DMA — bouncing. Stop **₹263**; target **₹302**. This should have been cut at −1R long ago; manage the bounce, don't add.

**POLYPLEX** — **bounce** · 1,483.19 / 952.90 / **−35.8%**. RSI 61, MACD bull, above MAs. Stop **₹901**; target **₹988**.

**BAJAJHFL** — **HOLD-bounce** · 126.69 / 88.98 / **−29.8%**. RSI 65, vol 2.3×, MACD bull, 30d +7.1% — strong rebound but below 200-DMA. Stop **₹83.7**; target **₹92.8**.

**IONEXCHANG** — **HOLD-bounce** · 566.15 / 397 / **−29.9%**. RSI 60, vol 4.4×, MACD bull recovering. Stop **₹340**; target **₹428**.

**IGPL** — **HOLD** · 647 / 452.65 / **−30.0%**. RSI 57, +12.8% vs 200-DMA, MACD bull. Stop **₹418**; target **₹477**.

**JIOFIN** — **HOLD/watch** · 307.90 / 243.38 / **−21.0%**. RSI 56, MACD bull, below 200-DMA. Stop **₹231**; target **₹251**.

**IEX** — **HOLD/watch** · 154.50 / 125.68 / **−18.7%**. RSI 55, vol 2.4×, sideways below 200-DMA. Stop **₹118**; target **₹131**.

**IRCON** — **EXIT/weak** · 171 / 139.10 / **−18.7%**. RSI 50, below all MAs, sideways, no momentum. Redeploy candidate — **trim/exit 100.**

**IRCTC** — **EXIT/weak** · 704.45 / 521.75 / **−25.9%**. RSI 47, −16% vs 200-DMA, ADX 10 (no trend). Dead capital — **exit 50.**

**ITC** — **HOLD (defensive)** · 362.84 / 291.20 / **−19.7%**. RSI 53, below 200-DMA, low ATR. Not a swing — slow bag. Stop **₹279**; consider rotating out.

**IRB** — **EXIT/weak** · 30.84 / 21.70 / **−29.6%**. Penny-ish ₹21, flat, no trend (RSI 57, ADX 17). **Exit 700**, free ₹15k.

**JWL** — **HOLD/watch** · 320.12 / 279.70 / **−12.6%**. RSI 50, flat at MAs. Stop **₹259**; target **₹304**.

**NHPC** — **HOLD/watch** · 85.90 / 78.22 / **−8.9%**. RSI 56, flat, vol normal. Stop **₹72.7**; target **₹82.7**.

**BEML** — **EXIT/weak** · 1,824 / 1,762.90 / **−3.4%**. RSI 48, below all MAs, ADX 11, 30d −3.6%. No edge — **rotate out.**

---

## 3. New Opportunities (Rotation Candidates)

Sizing note: with only **₹6,922 cash**, no candidate is buyable until exits clear. Sizes below assume freed capital from §4; risk-per-trade capped at **₹4,000 (2% of stated ₹200k)** per the config — kept tiny deliberately.

**Watchlist screen:**

**1. COFORGE** *(fresh, not on watchlist — best idea)* — **Setup: Momentum/Pullback** · **WAIT-FOR-TRIGGER**
- Fits profile: RSI 61, MACD bull, **+10.5% vs 50-DMA**, 30d +7%, strong-bull momentum (src: technicals). IT bounce leader.
- Entry trigger: close **>₹1,554** (20d high). Entry zone **1,490–1,510**, **Stop ₹1,375** (50-DMA/S1), **Target ₹1,700**, **R:R ≈ 2.0:1**, window ~3–4 wks.
- Size (2% / risk ₹110-sh): **36 shares ≈ ₹53,500 deployed**, open-risk add **₹4,000**. **Verdict: WAIT-FOR-TRIGGER >1,554.**

**2. DIXON** — **Setup: Pullback** · **WAIT**
- RSI 60.5, MACD bull, +8.3% vs 50-DMA, momentum strong-bull, but **below 200-DMA (−4.7%)** and at upper Bollinger (src: technicals).
- Entry on pullback to **₹11,800 (20-DMA)** w/ reversal candle, **Stop ₹11,150**, **Target ₹13,126 (R1)**, R:R ≈ 2.0:1. Near-term resistance caps it.
- Size (risk ₹650-sh): **6 shares ≈ ₹74,000**, open-risk **₹3,900**. **Verdict: WAIT for 11,800 pullback or >13,126 breakout.**

**3. HUDCO** — **Setup: Breakout-pending** · **WATCH**
- RSI 55, MACD bull but **ADX 12 (no trend)**, hugging flat 50/200-DMA, vol 1.5× (src: technicals). Choppy, no clean trend.
- Trigger: close **>₹220** on volume; Stop ₹201, Target ₹240, R:R ~2:1. **Verdict: WATCH — no setup yet.**

**KAYNES** — **SKIP.** RSI 49, **below 50-DMA (−9.6%) & 200-DMA (−30%)**, vol 0.5×, sideways (src: technicals). Fails trend + volume filters.

**BSE (as new add)** — **SKIP/WATCH.** Already a held monster; MACD bearish now — not a fresh long.

*Other fresh names screened & rejected:* **TRENT** (RSI 72.6 overbought, below 200-DMA — WATCH), **SOLARINDS** (MACD hist negative, extended — WATCH), **MFSL** (RSI 58, ADX 14 weak — WAIT >1,748), **PERSISTENT** (RSI 44, bearish — skip).

**Ranking:** ① COFORGE (trigger-ready) ② DIXON (needs pullback) ③ HUDCO (watch). **Nothing is a "TAKE NOW" today** — all need a trigger. No forced trades.

---

## 4. Capital Rotation Plan

Max-concurrent and concentration caps **not set** → assumption: trim the 49-name sprawl toward fewer, higher-quality names. **Process, not revenge.**

**Step 1 — Exit dead money / amputate losers (frees ~₹104k):**
| Exit | Qty | ≈ Proceeds |
|---|--:|--:|
| TCS | 10 | ₹21,278 |
| WIPRO | 80 | ₹14,414 |
| HAPPSTMNDS | 33 | ₹11,497 |
| PRAJIND | 40 | ₹13,662 |
| NAHARINDUS | 150 | ₹17,867 |
| IRB | 700 | ₹15,190 |
| IRCTC | 50 | ₹26,088 |

**Step 2 — Lock extended/peaked winners (frees ~₹350k):**
- **MCX full 65 → ₹186,576** (peak confirmed). **BSE 22/45 → ₹88,719.** **SILVERBEES 100/200 → ₹22,514.** **VOLTAMP 3/6, CDSL 20/45, MAHABANK 200/500** (partials).

**Step 3 — Redeploy (only on triggers):**
1. **COFORGE 36 sh ≈ ₹53.5k** — *only* on close >₹1,554.
2. **DIXON 6 sh ≈ ₹74k** — *only* on pullback to 11,800 or breakout >13,126.
3. Hold remainder as **cash buffer** (book is over-deployed; rebuilding dry powder is itself the highest-value "trade").

**Loss-offset framing:** Realized losers (TCS/WIPRO/HAPPSTMNDS/PRAJIND ≈ **−₹55k–60k realized** vs entries) are **already more than covered** by booking MCX/BSE/CDSL/VOLTAMP partials (**+₹250k+ realized gains available**). The book stays net **+₹300k**. Offset comes from **harvesting winners + 2:1 R:R redeploys**, **NOT** from upsizing risk. No averaging down on any red name.

---

## 5. Risk & Watch Triggers

- **Portfolio open risk:** uncontrolled until stops are entered; with proposed stops ≈ **₹95k–110k (~5–6% of the ₹1.9M book)**. **Action: place every stop listed in §2 today.**
- **Over-deployment** is the #1 risk: ₹6.9k cash on a ₹1.9M book = zero shock absorber. Rebuild cash via §4.
- **Concentration:** BSE, MCX, MAZDOCK gains dominate P&L — trim to de-risk single-name blow-back.
- **Liquidity/gap risk:** **NAHARINDUS** (~26k avg vol), **IGPL** (~30k), **POLYPLEX** (~55k) — exit/trim with limit orders, expect slippage.
- **Event risk:** Nifty pinned under **24,200** with a gravestone doji + FII selling — a rejection there pressures high-beta PSU/defence/rail names (RVNL, IRCON, BDL, GRSE). Monsoon/RBI and Q1 results season approaching — check earnings dates before any new entry.
- **Exact triggers before next session:**
  - **COFORGE** close **>₹1,554** → enter. **DIXON** tag **₹11,800** w/ reversal → enter; **>₹13,126** breakout → enter.
  - **BSE** close **<₹3,729** → exit balance. **MCX** any strength → exit (already flagged). **RVNL** **<₹222** → exit. **SILVERBEES <₹216** → exit rest.
  - **Nifty <23,950** → freeze all new longs, tighten trails. **Nifty >24,250** → release COFORGE/DIXON entries.

---

## 6. Caveats

- **Assumptions:** Stated ₹200k capital treated as mislabeled vs the ₹1.9M deployed book; **holding-days/days-left not supplied**, so time-stops were inferred from price action; **no stops were on file** (treated as none active); per-trade risk capped at the config's ₹4,000.
- **Data gaps:** `TATAMOTORS` technicals + price failed on both attempts (no data returned) — **not evaluated**, not fabricated. All other prices/indicators are live (src: technicals); regime is `src: web` (intraday levels may shift).
- All ₹ levels/share counts are explicit and derived from live data; none invented.
- **This is NOT investment advice** — it is a disciplined process review for educational purposes; verify live quotes and your own risk tolerance before acting.

