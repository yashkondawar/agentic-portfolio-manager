# NALCO — Buy-Side EPS-Bridge Note

*Independent buy-side rerating call on National Aluminium Company Ltd (NSE: NATIONALUM). CMP ₹361.65 (2026-07-15). Basis: consolidated estimates, standalone historicals where noted. All facts cite the handoff/dossier registry. This note is independent of the sell-side REDUCE and reaches its conclusion from the EPS-bridge doctrine alone.*

## 1. Verdict up front

**Recommendation: AVOID (do not initiate at CMP). Conviction 0.72.** This is not a quality verdict — the business is sound. It is a rerating verdict, and the rerating case fails at the first rung. Under the doctrine, PE re-rates only when EPS growth is **consistent and >20%** while the **starting PE is low relative to that growth**. NALCO offers a base-case 2yr EPS CAGR of **−0.98%** (F-EST-01) at a fwd PE of **11.0x/11.7x** (S1396/S1397) — flat-to-down earnings at a multiple that is ~2x the stock's own five-year band ceiling (4.6x–8.7x, median 7.6x; pe_bands). Every ingredient the doctrine requires for a rerating is inverted: growth is absent, and the starting multiple is already at a record high. This is a de-rating setup, not a re-rating one.

## 2. The EPS = Price × PE frame — the rerating condition fails on both legs

The one PASS in the checker (`eps_growth_20pct`, FY2025 +164.82%) is a **thin, single-year print** and the doctrine explicitly disqualifies it: "a single strong year is not consistency." That +165% was a cyclical LME/alumina realization spike (EBITDA margin 24.9%→44.6%, +1,966bps, F-DER-FUN-03/04), not a structural step-up — and the reversal is already visible (Q4 FY2026 PAT −17.4% YoY, S693). The `revenue_growth_consistency` rule correctly **FAILs** (FY2024 −7.76% breaks the floor; the five-year series is 58.7/0.3/−7.8/27.7/6.3 — the signature of a price-taker, not a compounder). Consistency is the gate, and NALCO does not clear it. Starting PE is not low relative to growth; it is high relative to *no* growth.

## 3. EPS decomposition ladder (volume / price / mix / cost / leverage)

The deterministic checker is **1 PASS / 1 FAIL / 7 NA** — the seven NAs are extraction-sparsity artifacts (no gross-margin, receivables, interest-vs-EBIT, dilution, CFO-expansion, D&A-adjusted or coverage series could be built), not passes. I reconstruct the bridge from the handoff and dossier:

- **Volume:** The only credible growth lever. Metal volumes near rated smelter capacity (~4.6–4.7 lakh MT, guidance credibility **high**, 470K guided vs 471K actual, <0.3% miss; guidance_ledger). But capacity-constrained volume caps upside — it cannot compound.
- **Price:** The dominant and uncontrollable driver. Realization is spot/LME-linked, repriced every 3 days, near-zero hedging (F-FUND-01). Base case anchors to World Bank/Platts normalization off the FY26 peak (metal ~$3,000/t, alumina ~$300–310/t) — a fade, not a tailwind. Alumina structural oversupply (Indonesian ramp to 7 MTpa by CY2026, F-EXT-1211) compressed the alumina-to-LME premium from 15–17% to 11–11.5% (GD-Q4-035).
- **Mix:** Shift to 73/27 metal/alumina is framed as margin-supportive (QT-Q4-075), but segment-EBIT data is non-monotonic (Aluminium EBIT share *fell* 61.2%→55.5% FY24→FY25, F-DER-FUN-07/08) — the mix story is not a clean, durable margin driver (OQ-FUND-08).
- **Cost:** The genuine positive. Caustic soda 121→99 kg/t (~₹129cr, GD-Q3-014); captive coal +41.84% YoY toward ~4 MTpa; Pottangi captive bauxite (MDO awarded Dec-2025, F-EXT-1152) as a medium-term input-cost offset. This is a **cost-structure moat that defends margin in a downturn — it does not drive earnings growth or justify multiple expansion** (moat composite 4.3/10; F-VAL-09).
- **Operating leverage / D&A:** No operating-leverage tailwind ahead (revenue flat FY27E→FY28E, −1.25%). D&A rises 745→857→895 on the capex build, a mechanical drag on EPS as capacity depreciates ahead of the ramp (`dna_adjusted_eps_growth` NA — flagged, not passed).

**Bridge verdict:** volume capped, price fading, mix ambiguous, cost helpful but defensive, leverage negative. The bridge does not build to >20% consistent EPS growth — it builds to roughly flat.

## 4. Funding discipline & working capital (doctrine rungs iii–iv)

These rungs are where NALCO scores *best*, but they are not rerating catalysts:
- **Funding-quality hierarchy: tier 1 (internally funded).** Near-debt-free (D/E ~0.0, interest coverage 152x–172x FY22/23; interest just ₹59–129cr against EBITDA ~₹8,600cr). The 5th-stream capex has been self-funded from operating cash. This is the best rung on the sheet — but a *pre-existing multi-year condition* (F-FUND-07), so it cannot explain a rerating over the last 12–18 months.
- **No dilution risk** (GoI-majority, no ESOP/QIP; `dilution_consecutive` NA but functionally clean).
- **CFO positive through expansion** (FY2025 CFO ₹5,806cr; `cfo_positive_expansion` NA only for lack of ≥3 net-capex periods — not a fail). FY2026 CFO/capex/FCF are a data gap (AR unpublished).
- **Working capital immaterial** — DSO ~4 days on ~1.1% of sales; the DSO flags (RF-002/003) were dismissed on materiality.

A clean, near-debt-free balance sheet with disciplined funding is a floor under the *business*, not a lever under the *multiple*.

## 5. Qualitative gate (doctrine rung v) — split verdict, growth lever fails

The doctrine requires management to be actively delivering the *exact strategies* (positioning, share capture, portfolio expansion) with a delivery-vs-promise track record. NALCO **splits**:
- **Passes** on what it controls: metal volume (high credibility) and cost efficiency (medium-high, captive coal delivered).
- **Fails** on the single largest swing factor. The 5th-stream alumina refinery — the only near-term growth lever — has **low guidance credibility**: contribution cut ~40% in-year (500kt→300kt→200kt, RF-GUI-01 **confirmed**), commissioning slipped from the guided Jun-2026 date and remains **unconfirmed as of Jul-2026** (tender pre-bid, F-EXT-1150), consistent with an ~18-month historical slippage pattern. Capex overruns ~20% recurringly (F-FUND-04). Governance is **Amber (73.3)** with a *confirmed, fined* LODR board-composition breach (F-EXT-1155) and an open CBI probe (F-EXT-1156).

Per the doctrine: "a numerically clean bridge from a management team that fails this gate is not sufficient on its own." Here the bridge is not even clean *and* the growth-lever gate fails. Management's own tone is "Bullish/self-confident" (rating.variant_view) precisely on the lowest-credibility families.

## 6. What entry price/multiple would make this attractive

Under the doctrine, absent consistent >20% growth, the only route to attractiveness is a **low starting PE** — mean-reversion to the cyclically-appropriate band, not a rerating. On base FY27E EPS 32.76 (S1390):
- At the 5y median 7.6x → ~₹249 (fair-cycle value).
- At p75 8.2x → ~₹269 (upper-cycle, still a discount to CMP).
- At the 5y-max 8.66x → ~₹284 — the ceiling the stock has *ever* paid, and still ~21% below CMP.

An accumulate-worthy entry under this doctrine would require CMP near ₹250–270 (median-to-p75 on base EPS), i.e. a **25–30% de-rating from here** — OR a confirmed rerating catalyst (5th-stream commissioned and ramping, credit-rating upgrade, or index-weight change), of which peer-valuation found **none** (F-VAL-05). CMP at 11.0x/11.7x fwd is pricing bull-case optionality the numbers do not support.

## 7. Scenario inputs (traceable) and base target

**EPS scenarios (ascending):** 21.26 / 24.04 / 31.05 / 32.76 / 42.42 — bear FY28E, bear FY27E, base FY28E, base FY27E, bull FY28E (S1394/S1395/S1391/S1390/S1393). **PE scenarios (ascending):** 4.61 / 6.39 / 7.58 / 8.20 / 8.66 — the full 5y historical band (min/p25/median/p75/max, pe_bands). I deliberately anchor the PE scale to *history*, not to the CMP-implied 11.0x, because the doctrine rerates only on earned consistency, which is absent. **Base target: ₹248.32** (base FY27E EPS 32.76 × 5y-median 7.58x) — a grid cell, and the doctrine-consistent fair value. This is ~31% below CMP.

**Invalidation:** 5th-stream refinery confirmed commissioned AND ramping ≥200kt within one quarter of a re-guided date (Q1 FY27 call, ~Aug-2026), OR LME aluminium sustained >$3,300/t with alumina premium re-widening above 15% — either would move base EPS toward the bull path and re-open the rerating case.

## 8. Bridge summary

| Rule | Verdict | Read |
|---|---|---|
| revenue_growth_consistency | **FAIL** | FY24 −7.8% breaks floor; price-taker volatility |
| eps_growth_20pct | PASS (thin) | Single-year cyclical spike, not consistency |
| gross_margin_trend | NA | Sparse cost data — not a pass |
| receivables_pct_revenue_trend | NA | Immaterial (~1.1% of sales) |
| interest_vs_ebit_growth | NA | Near-debt-free; qualitatively clean |
| dilution_consecutive | NA | No dilution (GoI-majority) |
| cfo_positive_expansion | NA | CFO positive; <3 capex periods |
| dna_adjusted_eps_growth | NA | D&A rising — flagged as EPS drag |
| interest_coverage | NA | Coverage 152–172x historically |

**Bottom line:** a well-built, cheap-fuel, near-debt-free ship on a sea it cannot control (dossier §11). Sound hull, no wind. The rerating case fails the consistency gate and the starting-multiple gate simultaneously; the qualitative gate fails on the one growth lever that matters. AVOID at CMP; re-engage near ₹250–270 or on a confirmed 5th-stream/price catalyst.
