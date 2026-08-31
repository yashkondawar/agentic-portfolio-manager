# National Aluminium Company Limited (NALCO) — Research Dossier (full audit document)
*Run date: 2026-07-16 · Inputs: 13 documents (manifest below) · Basis: standalone primary (reason: consolidated vs standalone diverge <0.3% every year, F-FUND-09; JV/subsidiary carrying value ~2% of balance sheet; FY2026 full-year figures available only on a consolidated Q4-PPT basis and cited as such)*

> This dossier is the long-form audit record. Every number carries a source reference `[S###]` mapping to `state/source_registry.json`. Tables are rendered from fact records, not retyped. The rating does **not** appear in this document — it lives only in the final note's rating box (`report/final_note.md`). Where a figure is company-summarised (FY2026 Q4 PPT) or externally sourced, it is labelled at point of use.

---

## 0. Input manifest & run record

### 0.1 Input document manifest

| File | Classification | Period | Pages | Notes |
|---|---|---|---|---|
| AR_FY2021.pdf | annual_report | FY2021 | 265 | 40th AR 2020-21, BSE filing 06.09.2021 |
| AR_FY2022.pdf | annual_report | FY2022 | 262 | 41st AR 2021-22, BSE filing 25.08.2022 |
| AR_FY2023.pdf | annual_report | FY2023 | 264 | 42nd AR 2022-23 |
| AR_FY2024.pdf | annual_report | FY2024 | 284 | 43rd AR 2023-24 |
| AR_FY2025.pdf | annual_report | FY2025 | 307 | 44th AR 2024-25, BSE filing 02.09.2025 |
| TR_2025-08-08.pdf | transcript | FY2026Q1 | 21 | Q1 FY26 earnings call 08.08.2025 |
| TR_2025-11-07.pdf | transcript | FY2026Q2 | 28 | Q2/H1 FY26 earnings call 07.11.2025 |
| TR_2026-01-30.pdf | transcript | FY2026Q3 | 22 | Q3/9M FY26 earnings call 30.01.2026 |
| TR_2026-04-30.pdf | transcript | FY2026Q4 | 28 | Q4/FY26 earnings call 30.04.2026 |
| PPT_FY2026Q1.pdf | presentation | FY2026Q1 | 16 | Q1 FY26 earnings-call presentation |
| PPT_FY2026Q2.pdf | presentation | FY2026Q2 | 18 | Q2/H1 FY26 earnings-call presentation |
| PPT_FY2026Q3.pdf | presentation | FY2026Q3 | 16 | Q3 FY26 earnings-call presentation |
| PPT_FY2026Q4.pdf | presentation | FY2026Q4 | 19 | Q4/FY26 earnings-call presentation |

Documents supplied cover five audited fiscal years (FY2021–FY2025) plus the four FY2026 quarterly call/presentation sets. **Declared intake gaps** (`state/manifest.json`): no standalone quarterly results filings (FY2026 quarterly financials are taken from the four presentations and treated as company-summarised until the FY2026 AR publishes); the FY2026 audited AR was not published as of intake; no prior deep-research documents (both research waves run fresh, DR1 + DR2); no supplied peer/KPI material; no transcripts for FY2021–FY2025 (pre-FY2026 management signalling is limited to AR MD&A).

### 0.2 Run record

Waves dispatched: INTAKE → CONVERT → TRIAGE (sector pack: commodities/metals-mining) → parallel EXTRACT (per-document) → COMPUTE (`compute_ratios.py`, `build_comprehensive_statement.py`, `eps_bridge_check.py`, `export_financials_xlsx.py`) → parallel ANALYZE (fundamental / forensic / guidance / governance) → RESEARCH (DR1 company + DR1-B follow-up; DR2 sector/peers) → LOOP (external facts marked the governance and legal_regulatory sub-scores stale; governance re-run downgraded Green→Amber) → SYNTHESIZE (peer-valuation + estimates-builder → thesis) → VERIFY → RENDER.

Order variation and reason: the governance module was re-run after the DR1-B follow-up surfaced the BSE/NSE independent-director fine and the CBI probe — new load-bearing external facts (F-EXT-1155, F-EXT-1156) marked the governance and legal_regulatory sub-scores stale, so only those re-ran (stale-rerun-only). The estimates and peer-valuation modules ran last so they could consume the answered commodity-price open questions (OQ-FUND-07, OQ-GUI-01) from DR2. Convergence status: all five thesis pillars meet the two-independent-reference minimum; all 23 red-flag ledger entries adjudicated (2 confirmed, 7 disclosed, 14 dismissed), zero remaining `candidate`; three high-severity open questions (OQ-FUND-03, OQ-GUI-03, OQ-GOV-01) remain unanswered and are carried as disclosed gaps rather than blocking.

---

## 1. Executive summary

**Thesis.** NALCO is an operationally sound, input-cost-advantaged, near-debt-free integrated aluminium producer whose earnings are an unsmoothed, leveraged function of two spot-linked commodity prices (LME aluminium and alumina). The FY2025 profit surge was a cyclical realization peak, not a structural efficiency step-up; FY2026 already shows the reversal beginning at the exit quarter (Q4 FY2026 PAT −17.4% YoY [S693]). The base-case earnings path through FY2028E is roughly flat-to-down. Set against this, the market price sits materially above every multiple the stock has traded at in its own five-year history, with no confirmed re-rating catalyst identified. Two governance/execution overhangs are live: a fined SEBI LODR board-composition breach and a repeatedly cut/deferred commissioning timeline on the single largest near-term capacity lever.

**Core financial health.** Balance sheet is a genuine strength: near-zero leverage (standalone D/E 0.0016x FY2022 [S1022-context]), interest coverage of 152x–172x in FY2022–FY2023 [ratio_summary], captive bauxite and a captive-coal ramp toward ~4 MTpa. Earnings quality is above-median for an Indian commodity CPSE (forensic composite 75/100): unqualified audits five straight years (FY2021–FY2025), CAG supplementary comment "Nil" in both covered years, a single non-recurring exceptional item (FY2024). Cash conversion is volatile but tracks the commodity cycle rather than manipulation.

**Valuation synopsis.** CMP ₹361.65 (2026-07-15) is 12.5x FY2025 EPS [S1306] and ~11.4x the FY2026 cross-check EPS [S1307], against a five-year PE-on-average-price band of 4.1x–8.4x (median ~6.3x) [S1300–S1304] that never reached double digits even in the FY2025 cyclical-peak year. P/B at CMP is 3.73x [S1317] versus a five-year band high of 1.78x. Base-case forward P/E is 11.0x (FY27E) / 11.7x (FY28E) [S1396/S1397] — still above the historical band on forward earnings.

**Top four principal risks.** (1) Valuation reversion — CMP prices in either a ~2x sustained EPS step-up versus a peak-cycle base, or an unevidenced permanent re-rating [F-VAL-05]. (2) Execution/guidance credibility on the 5th-stream refinery — the FY26 volume contribution was cut ~40% in-year then deferred to FY27, and commissioning remains unconfirmed as of Jul-2026 [RF-GUI-01, F-EXT-1150]. (3) Governance — a fined, disclosed SEBI LODR independent-director-composition breach (₹10.86 lakh, waiver pending) plus an open CBI recruitment-fraud probe [F-EXT-1155, F-EXT-1156]. (4) Commodity price cycle — structural alumina oversupply (Indonesian ramp) with management guiding no near-term recovery (FY2027 alumina US$300–310/t vs FY2025 US$580/t) [F-FUND-02].

---

## 2. Industry & market analysis

*(DR2 material in full; external sources access-dated 2026-07-16, facts F-EXT-1200..1230 / SRC-1200..1228. Forecast figures are attributed opinions, not settled facts.)*

### 2.1 Value chain & bottleneck

The aluminium value chain runs bauxite (ore) → alumina (refined intermediate) → primary aluminium (smelted metal, LME-priced) → semis/downstream (rolled, extruded, wire rod, foil). NALCO is fully integrated across the first three stages with captive power, but has effectively **no downstream/specialty business** — its output is bulk primary metal and calcined alumina/alumina hydrate sold on spot/LME terms. The structural bottleneck and margin-setter in the current cycle is the **alumina-to-LME price premium**: management reports it compressed from 15–17% to 11–11.5% [GD-Q4-035] as Indonesian refinery capacity ramped. The independently confirmed driver — Indonesian metallurgical alumina capacity reaching 7 MTpa by CY2026, and Indonesian primary aluminium operating capacity projected from 0.87mt (2025) to 2.51mt (2026) to 3.56mt (2027) [F-EXT-1211, F-EXT-1212] — sits upstream of NALCO's realized price and is the force behind the FY2026 alumina realization collapse (US$580 → US$370 FY25→FY26) [F-FUND-02].

### 2.2 Porter's five forces (0–10; higher score = higher pressure on NALCO)

| Force | Score /10 | Justification | Trajectory |
|---|---|---|---|
| Threat of new entrants | 6 | Large, fast-ramping Indonesian alumina/aluminium capacity directly pressures NALCO's realized alumina price [F-EXT-1211, F-EXT-1212]; management attributes the FY2026 realization collapse substantially to this supply [F-FUND-02, GD-Q4-035]. | Worsening in the alumina segment over CY2025–2027. |
| Bargaining power of suppliers | 3 | NALCO is largely captive on its two key inputs — own Panchpatmali bauxite and captive coal ramped to ~4 MTpa (~57% of fuel need) [F-EXT-1208]; residual exposure via e-auction coal premiums (FY26 avg 38%, Mar-2026 45%) and external caustic soda/CP coke [F-EXT-1229]. | Improving on captive coal/bauxite. |
| Bargaining power of buyers | 7 | Alumina sold almost entirely on spot tenders (4 shipments/month, no long-term contracts as of Q4 FY26) and metal at LME-linked prices repriced every 3 days with near-zero hedging [F-FUND-01 why-chain, QT-Q4-054/055/056]; buyers/the market set price. | Structurally stable at a high level. |
| Threat of substitutes | 2 | No evidenced substitution threat at the primary-metal level; India wire-rod demand projected +5.93% CAGR to 2030 [F-EXT-1214]. | Stable. |
| Competitive rivalry | 6 | Hindalco (India upstream, first-decile cost claim) and Vedanta Aluminium (targeting US$1,550–1,600/t cost of production from ~US$1,752/t via 100% captive bauxite+coal) both expanding and cutting costs [F-EXT-1216, F-EXT-1219]; NALCO shows no clear operating-quality edge over either this cycle. | Intensifying. |

Composite read: an industry structure that is **moderately-to-highly unfavourable for pricing power** (buyer power and new-entrant/rivalry pressure dominant at 6–7/10), partially offset by NALCO's input-cost self-sufficiency (supplier power and substitution both low at 2–3/10). This corroborates the independent fundamental-analyst finding that NALCO is a "commodity price taker with near-zero hedging" (F-FUND-01).

### 2.3 TAM / demand build (with the build shown)

India aluminium demand is estimated at a **6.27% CAGR CY2024–2030** by TechSci (a paid research house, methodology not independently auditable) [F-EXT-1213], the low end of a 5.9–7.8% spread across multiple paid-research estimates; the wire-rod sub-segment specifically is estimated at +5.93% CAGR to 2030 [F-EXT-1214]. Confidence: **low** — no official-statistics (CRISIL/ICRA/government industry-association) source was located; the company's own claimed range (6.3–7.2%) sits inside this plausible band, supporting rather than confirming it.

### 2.4 Cycle-overlap checks (commodity-price context)

- **LME aluminium (CY2027 forecast spread):** World Bank (primary, regulator-grade) US$3,000/t central; SMM (PRA) three-scenario US$2,900–3,200/t; Goldman Sachs conditional bear case US$2,400/t [F-EXT-1200, F-EXT-1203, F-EXT-1204]. LME spot already US$3,538/t on 28-Apr-2026, above the World Bank full-year CY2026 average call [F-EXT-1202] — genuine two-sided uncertainty, not a consensus. Management's FY2027 metal guide (US$3,000–3,100/t) sits on the World Bank central case, **base-case-to-slightly-conservative** against the external spread (answers OQ-FUND-07).
- **Alumina:** Platts FOB-Australia averaged US$306.91/t in Q1 CY2026 [F-EXT-1206], inside NALCO's guided US$310–320/t band and matching the CMD's public quote of US$320–340/t (answers OQ-GUI-01: management's price narrative tracks the independent index, no systematic lag/lead).

### 2.5 Policy architecture

- **EU CBAM (material, new):** definitive phase began 1-Jan-2026; first quarterly certificate price €75.36/tCO₂e (7-Apr-2026). Indian unwrought-aluminium exports to the EU fell 41.7% YoY (YTD Jan) [F-EXT-1227]. NALCO's captive power is coal-based (highest emission intensity, least CBAM-favourable). **NALCO's own EU export volume/% of sales was not sized in this pass** — a company-specific exposure gap, not a null finding.
- **US Section 232:** restructured 6-Apr-2026 to 50% on wholly-metal articles / 25% on derivatives [S1225]; NALCO not a significant direct US exporter — relevant mainly as a global trade-flow-diversion/glut risk.
- **India anti-dumping:** aluminium foil duties extended to 15-Dec-2026 [S1223] — downstream, limited direct read-through.
- **Coal cost trend:** India e-auction premiums rose to 45% (Mar-2026) from 35% (Feb-2026); Indonesian thermal coal +33% from start of CY2026 [F-EXT-1229, F-EXT-1230] — a cost-tailwind risk for NALCO's non-captive coal share.

---

## 3. Company deep-dive

### 3.1 Business & segments

NALCO is a Navratna CPSE (Government of India promoter, 51.28% via the President of India / Ministry of Mines) and a fully integrated bauxite–alumina–aluminium producer with captive thermal, wind and rooftop-solar power. Two reportable segments: **Chemicals** (alumina/hydrate) and **Aluminium** (primary metal). Both sit inside one vertically integrated value chain — NALCO consumes a large share of its own alumina captively in smelting — so the segment split reflects relative price cycles as much as deliberate tonnage reallocation (F-FUND-08).

### 3.2 Segment mix & evolution

Management quantifies the FY2026 revenue mix as shifting from ~70/30 to **73/27 (metal/alumina)** and frames it as margin-supportive ("we are getting better margins on aluminium") [QT-Q4-075/076]. The segment-EBIT picture is more nuanced and non-monotonic: Aluminium's share of combined standalone segment EBIT was **61.2% in FY2024 and 55.5% in FY2025** [F-DER-FUN-07/08] — i.e. Chemicals' EBIT share *rose* FY24→FY25 even as revenue mix moved toward metal, because alumina segment EBIT grew faster off a smaller base in the FY2025 price upswing. This tension is carried as OQ-FUND-08 and flagged so the segment-mix narrative is not over-claimed as a clean, one-directional margin driver.

Alumina sales are heavily export-tilted: Q4 FY2026 ~90.5%/9.5% export/domestic (13.09 lakh ton export vs 1.37 lakh ton domestic) [guidance.json sales_demand topic] — exposing distribution to trade-policy risk (CBAM) rather than a defensible domestic network.

### 3.3 Unit economics & cost buckets

Disclosed unit costs (FY2026): alumina cost of production ₹20,000–22,000/t [GD-Q4-024]; metal cost of production ₹155,000–160,000/t [GD-Q4-025]. Cost levers delivered in FY2026: caustic soda consumption improved from 121 kg/t (prior year) to 99 kg/t (9M FY26 actual), ~₹129cr savings [GD-Q3-014]; captive coal production +41.84% YoY toward ~4 MT, displacing costlier e-auction/linkage coal and grid power [coal_captive_production ledger]; employee cost declining mechanically as ~250 high-paid retirements are replaced by lower-paid recruits [QT-Q4-028]. A full per-tonne cost-bucket percentage breakdown at a level comparable to Vedanta/Hindalco was not extractable at segment granularity in this pass — flagged as a gap, not estimated.

### 3.4 Moat matrix (with evidence)

| Dimension | Score /10 | Weight | Evidence | Trajectory |
|---|---|---|---|---|
| Scale | 4 | 0.15 | FY2026 metal production ~471KT ≈ 1/6th of Vedanta's 2.46mt [F-EXT-1220]; smallest of the three India-listed upstream producers by metal volume. | Improving modestly but off a small base, years away. |
| Brand | 1 | 0.05 | Bulk commodity sold on spot/LME terms; no brand premium [F-FUND-01]. | N/A. |
| Distribution | 3 | 0.10 | Export-tilted (90.5%), no long-term offtake contracts currently [F-GUI-02]. | Eroding on contract-stickiness. |
| Switching costs | 1 | 0.10 | Near-zero for LME-linked commodity; no lock-in. | Stable-low. |
| Supply-chain integration | 7 | 0.25 | Captive bauxite, captive coal ramping to ~4 MTpa (~57% of fuel), pending Pottangi mine [F-EXT-1208]. | Widening. |
| Regulatory / access barriers | 6 | 0.20 | Scarce, government-allocated Panchpatmali leases; GoI ownership eases clearances — but lease-expiry dates carry an unresolved management/external discrepancy [QT-Q2-041, OQ-DR1-1]. | Stable-to-uncertain. |
| Specialty vs bulk mix | 2 | 0.15 | Overwhelmingly bulk/commodity-grade; wire rod/rolled products in the pipeline but not yet contributing. | Potentially improving, not realized. |

**Weighted moat composite = 4.3/10** [S1322]. The two dimensions where NALCO genuinely differentiates — supply-chain integration (7) and regulatory/access barriers (6) — are a **cost-structure moat**, which supports margin resilience in a downturn more than earnings growth or multiple expansion in an upturn. It is not a pricing-power moat.

### 3.5 Competitive positioning narrative

On margin comparability, NALCO's FY2025 standalone EBITDA margin (44.6%, F-DER-FUN-04) is closely in line with Hindalco's India-upstream 45.6% [F-EXT-1216] — i.e. **no operating-quality edge** over its largest domestic peer's comparable segment this cycle, undercutting a "quality premium" justification. NALCO's own "world's lowest-cost producer" claim could not be re-verified against a current (2025/2026) third-party ranking — the most recent independently-citable Wood Mackenzie instance located is FY2019-vintage [F-VAL-08, F-EXT-1215]; a moat-relevant gap, not a confirmed premium.

---

## 4. Historical financial performance

*(All rendered tables in this section are generated from the facts store via `tools/render_tables.py`; sectional legend follows each. Cells marked N/A carry the explanation given — FY2021–FY2025 are the audited-AR window; FY2026 full-year is company-summarised PPT and appears in §12 annexure and §8 estimates, not re-typed here.)*

### 4.1 Income statement summary (standalone)

*All PAT/EPS cells below are the standalone P&L figures. Note the FY2025 standalone PAT (5,324.67cr [S538]) differs from the consolidated PAT (5,267.94cr) used in the estimates base and Exhibit 4 of the final note — the two are on different bases and are not interchangeable; standalone EPS is 28.99 [S550] on both a basic and diluted basis.*

| Metric | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 |
|---|---|---|---|---|---|
| Revenue from operations | 8,955.8 [S100] | 14,214.6 [S301] | 14,254.9 [S300] | 13,149.1 [S400] | 16,787.6 [S500] |
| Revenue growth YoY % | N/A (FY2020 not in AR set) | 58.7 | 0.3 | -7.8 | 27.7 |
| Finance costs | 7.1 [S103] | 23.1 [S315] | 12.9 [S314] | 17.2 [S515] | 59.0 [S514] |
| Other income | 146.6 [S101] | 264.1 [S303] | 235.6 [S302] | 250.7 [S503] | 357.0 [S502] |
| PBT (standalone) | 1,316.5 [S107] | 3,954.9 [S200] | 1,955.0 [S330] | 2,712.1 [S400] | 7,135.1 [S500] |
| PAT (standalone) | 1,299.4 [S107] | 2,952.0 [S200] | 1,544.5 [S338] | 1,988.5 [S400] | 5,324.7 [S538] |
| EPS diluted (standalone) | 7.0 [S107] | 16.1 [S200] | 8.4 [S350] | 11.2 [S551] | 28.99 [S550] |

*Legend:* [S100] AR_FY2021 p.151 Note 27; [S101] AR_FY2021 p.152 Note 28; [S103] AR_FY2021 p.152 Notes 31–33; [S107] AR_FY2021 p.152 Note 36 EPS; [S200] AR_FY2022 p.147 P&L; [S300]/[S301] AR_FY2023 p.131 Note 29; [S302]/[S303] AR_FY2023 p.131 Note 30; [S314]/[S315] AR_FY2023 p.131 Note 34; [S330] AR_FY2023 p.131 PBT; [S338] AR_FY2023 p.131 profit for year; [S350] AR_FY2023 p.131 Note 38 EPS; [S400] AR_FY2024 p.147 P&L; [S500] AR_FY2025 p.155 Note 28; [S502]/[S503] AR_FY2025 p.155 Note 29; [S514]/[S515] AR_FY2025 p.155 Note 33; [S538] AR_FY2025 standalone profit for the year FY2025 (5,324.67cr); [S550]/[S551] AR_FY2025 p.155 Note 38 EPS.

### 4.2 Adjusted margins and the FY2025 margin move (why-why)

Standalone EBITDA (computed via PBT+Dep+Fin−OtherIncome route, medium confidence) rose from **₹3,278.8cr (FY2024) to ₹7,487.1cr (FY2025)** [F-DER-FUN-01/02]; margin from **24.9% to 44.6%, a +1,966 bps move** [F-DER-FUN-03/04] — the single largest margin move in the five-year set, well above the 200bps why-why threshold (F-FUND-01). Company-reported consolidated EBITDA (excl. exceptional) is ₹7,922cr FY2025 and ₹8,613cr FY2026 [F-PQ4-018] and is used in deliverables per reported-over-computed precedence.

- **Numeric layer:** revenue +27.7% (13,149.1→16,787.6) while total expenses *fell* from 11,043.1 to 10,009.5 — operating leverage compounded by an absolute cost decline; employee cost fell 2,034.7→1,786.5 [S400/S500].
- **Operational layer:** both price and volume. Metal realization rose ~US$2,550→US$2,700/t (metal ~70–73% of mix); alumina volumes pushed higher to partly offset a ~US$200/t alumina price decline; retirements lowered employee cost [QT-Q4-007/075, QT-Q4-028].
- **Structural layer:** NALCO is a price-taker with near-zero hedging (metal repriced every 3 days, alumina spot-tendered) [QT-Q4-054/055/056]. FY2025's ~45% margin is therefore a cyclical LME/realization tailwind, **directly reversible** — and the FY2026 data already shows the reversal (Q4 FY2026 PAT −17.4% YoY). Implication: FY2025 is a cyclical peak, not a run-rate; estimates should fade the margin toward mid-cycle, which management itself guides (FY2027 alumina US$300–310/t) [QT-Q4-052].

### 4.3 ROCE / ROE trajectory deep-dive

Reported ratio_summary: ROE 25.4% (FY2022) → 12.0% (FY2023); ROCE 34.1% (FY2022) → 15.2% (FY2023) [ratio_summary]. FY2025 consolidated ROE ~32.7% [S1320] is largely a function of the cyclical margin peak (numerator), not a structural capital-efficiency gain (F-FUND-01 caution). The ratio series has gaps for FY2024/FY2025 in the standalone ratio render (missing consistent equity/capital-employed line-item pairs at extraction), so the ROE/ROCE trajectory is read off the two computed years plus the FY2025 consolidated cross-check rather than a clean five-year standalone series — a disclosed limitation, not a bare blank.

### 4.4 Capex & incremental-returns analysis

Standalone CWIP rose **1,431.1cr (FY2021) → 4,934.7cr (FY2025), +245%** [S-AR series], while net PPE was broadly flat-to-down (7,317.3 → 6,799.0cr) [S-AR series]; the CWIP/net-PPE ratio **nearly quadrupled, 19.6% → 72.6%** [F-DER-FUN-05/06]. This is a multi-year build phase, not a harvest phase: the 5th-stream refinery (+1 MT, taking the refinery from 2.1 to 3.1 MT) was 80% complete at Q2 FY26 [QT-Q2-007]; the 0.5 MT greenfield smelter (~₹18,000cr) is only at DPR stage (F-FUND-03). **Three-year incremental ROCE cannot be computed** for NALCO's largest reinvestment program because that program has not started — carried as OQ-FUND-03 (high severity, disclosed gap). FY2026 capex overshot its ₹1,700cr budget by ~24% (~₹400cr) with no disclosed root cause (F-FUND-04, OQ-FUND-05).

### 4.5 Working capital

DSO rose from 1.93 days (FY2022) to a peak of 4.26 days (FY2024), stabilising at 4.05 days (FY2025) [D-DSO series] — more than doubling on a percentage basis but off a near-zero base (receivables ₹186.4cr on ₹16,788cr revenue, ~1.1% of sales FY2025). Inventory days 41.5–50.8 across the window [ratio_summary]. The DSO moves tripped the forensic threshold (RF-002/RF-003) but were dismissed on materiality; ageing composition shows the bulk is current or legacy-disputed >3-year balances, not broadening customer credit (F-FUND-06). Consistent with NALCO's spot/tender sales model.

### 4.6 Comprehensive statement note

The full 3-level line-item tree across all fiscal years and quarters is in `state/comprehensive_statement.json` (and `.md`). It is not reproduced verbatim here because the rendered matrix is extremely wide and sparse (single-year/single-quarter values scattered across ~29 period columns); the level-1/level-2 income, balance and cash-flow summaries rendered in §4.1 and the annexure (§12) are the readable projection of that same state. Where a specific FY2026 quarterly figure is used (e.g., Q4 revenue 5,013cr, PAT 1,718cr), it is cited to the Q4 PPT.

---

## 5. Management & governance

*Governance verdict: **Amber** (composite 73.3/100, provisional on the legal_regulatory sub-score); downgraded from Green this cycle. Sub-scores below. The rating is not stated here.*

### 5.1 Leadership table

| Name | Role | Tenure / appointment | Prior | Notable |
|---|---|---|---|---|
| Brijendra Pratap Singh | Chairman-cum-Managing Director | PESB-selected 17-Sep-2024, charge 8-Jan-2025 [DR1] | 35+ yrs SAIL (ex Director-in-Charge Burnpur/Durgapur) | Primary spokesperson all 4 FY26 calls; one self-flagged uncertain answer on mine-lease dates. |
| Abhay Kumar Behuria | Director (Finance) | Charge 11-Jun-2025 [DR1] | ED Finance, Rourkela Steel Plant (SAIL) | Handled finance/cost/dividend Q&A. |
| Jagdish Arora | Director (Production & Technical) | N/A — not extracted | N/A | Answered operational/technical Q&A (Q2 FY26). |
| Anil Kumar Singh | Director (Commercial) | Effective 7-Jan-2026 [DR1, secondary] | ex-Hindustan Copper/RINL | — |
| Pankaj Kumar Sharma | Director (Production) | Since 1-Feb-2023 [DR1] | ex-NMDC | — |
| Three independent directors (Trupti Kamlesh Patel, Ajay Narang, Patel Sanjaykumar) | Independent | Ceased 31-Mar-2026 on tenure expiry; **not replaced** [F-EXT-1155] | — | Cessation triggered the LODR breach below. |

LinkedIn-vs-stated discrepancy check: not performed (no discrepancy identified, but also not directly queried) — remains open (OQ-GOV-05 partially answered).

### 5.2 Governance composite (0–100, config weights)

| Component | Weight | Score | Note |
|---|---|---|---|
| Accounting | 35% | 90 | RESOLVED clean: unqualified opinions FY2021–FY2025; CAG Sec 143(6) "Nil" FY2024/FY2025 [F-AUD-04/25]; contingent liabilities within range; held below high-90s only for the payroll audit-trail control gap [F-AUD-26]. |
| Governance | 30% | 58 | DOWNGRADED from 80 on the fined LODR board-composition breach (F-EXT-1155) + open CBI probe (F-EXT-1156). |
| Legal / regulatory | 20% | 62 (provisional) | DOWNGRADED from 70; SEBI/NCLT/NCLAT docket sweep methodologically unresolved (portals not indexable), carried as "unverified-clean, disclosed gap." |
| Concall behaviour | 15% | 80 | 2 evasive-candidate records of ~350+ across 4 calls; both self-flagged uncertainty on mine-lease dates, not refusal. |

**Weighted: 0.35×90 + 0.30×58 + 0.20×62 + 0.15×80 = 73.3.**

### 5.3 Guidance ledger + credibility

| Metric family | One-line history | Credibility |
|---|---|---|
| Alumina volume production/sales | Beat 3/3 verifiable full-year guides (FY26 actual 14.46 lakh t vs successive 12.5-12.8 / 12-12.5 / 12.5-13.0 guides) — conservative | medium (single-year, guide moved down mid-year first) |
| Metal volume production | Met 1/1 almost exactly (470K guided vs 471K actual, <0.3%) | high, capped medium for depth |
| 5th-stream refinery commissioning timeline | One material slip (implied Sept-2025 → June-2026), then held 3 quarters | low (pre-reset) / medium (post-reset) |
| 5th-stream FY26 volume contribution | Cut ~40% in-year (500KT→300KT), then deferred to FY27 (200KT) | **low** |
| 0.5 MTPA smelter capex & timeline | Date stated Aug-2030 / Dec-2030 / Jun-2031 across docs (self-contradictory Q4 PPT); capex ₹30,000cr→₹23,000-24,000cr | **low** (pre-DPR) |
| Pottangi bauxite commissioning | Transcript-vs-PPT date mismatch same quarter (May vs June 2026); MDO awarded Dilip Buildcon Dec-2025 | low |
| FY capex total | FY26 ₹1,700cr guided vs ~₹2,000-2,100cr actual (miss, +18-24%) | medium |
| Alumina price realization | Ratcheted down each quarter ($400-450→$320-340→$310-320), beat only the latest reset | low (commodity call) |
| Aluminium LME price | Q4 guide missed low; CY2026 guide swung +17% in one quarter | low (commodity call) |
| Coal captive production | 4 MTpa held all 4 quarters, delivered (+41.84% YoY) | medium-high |

Guidance families most relevant to FY27–28 estimates (5th-stream volume, price) are precisely the lowest-credibility families. The cost-efficiency and metal-volume families are the cleanest.

### 5.4 Direct-quotes bank (claims vs reality)

- *"This year, we have done best ever physical performance in all the areas… bauxite excavation, alumina hydrate production, calcined alumina production, metal production."* — CMD, TR_2026-04-30, [QT-Q4-001]. **Reality:** accurate at the production/volume level, but glosses the sharply negative Q4 YoY profit trend (Q4 revenue −4.8%, PAT −17.4% [S693]) — headline narrative and quarterly cadence diverge (F-FUND-10).
- *"…now more realistic 3 lakh KT"* (FY26 5th-stream contribution, down from ~5 lakh KT) — management, TR_2026-01-30, [GD-Q3-037]. **Reality:** a company-labelled ~40% in-year revision on the single largest near-term growth lever (RF-GUI-01).
- *"Existing bauxite mine renewal, I think it is up to '29… We will have to check up the data."* — CMD, TR_2025-11-07 p.19, [QT-Q2-041]. **Reality:** no AR lease-date fact was extracted to corroborate; treated as transparency-positive self-flagging, routed as OQ-DR1-1.
- *"Around 10% to 15% increase in the employee cost… it can be around 12% to 13% also."* — management, TR_2026-04-30. **Reality:** FY2026 audited employee-cost actual not yet available; not checkable until the FY2026 AR.

### 5.5 Forensic scorecard (0–100 weighted) — see §6 for full ledger

Composite **75/100** (standalone, FY2021–FY2025 window). Components: cash_conversion 62, accrual_ratio_trend 78, one_off_frequency 92, provisioning_adequacy 72, audit_cleanliness 92, disclosure_quality 68 (weights 25/20/15/15/15/10). Above-median for an Indian commodity CPSE.

### 5.6 Governance chronology

| Date | Event |
|---|---|
| FY2021 | Unqualified opinion; buyback 2.9cr shares ₹170.12cr; contingent liabilities ₹2,153.48cr |
| FY2022 | Unqualified; dividend payout 37.33%; contingent liabilities ₹2,378.4cr |
| FY2023 | Unqualified; other income 25.9% of CFO (RF-001); DSO +21% (RF-002) |
| FY2024 | Unqualified (A.K. Sabat & Co. / P.A. & Associates); CAG "Nil"; contingent liabilities ₹1,920.03cr; DSO +82% (RF-003) |
| FY2025 (AR 02-Sep-2025) | Unqualified (B M Chatrath & Co. LLP / SRB & Associates); CAG "Nil"; contingent liabilities ₹2,050.43cr; dividend to GoI ₹941.80cr; KMP remuneration ₹8.12cr; payroll audit-trail feature not enabled |
| 2026-02-27 | BSE & NSE each fine NALCO ₹5,42,800 (total ₹10,85,600 incl. 18% GST) for LODR Reg. 17(1) breach, quarter ended 31-Dec-2025 [F-EXT-1155] |
| 2026-03-17 | NALCO requests fine waiver, citing GoI's exclusive control over ID appointments; outcome not yet reported |
| 2026-03-31 | Three IDs cease on tenure expiry, not replaced — degrades board + Audit/NRC/Stakeholders committees |
| 2026 | CBI opens recruitment-fraud probe at Haradghana site (~20 people allegedly given jobs without advertisement); NALCO disputes "raid" framing [F-EXT-1156] |

### 5.7 Shareholding & pledge trend

Promoter: President of India / Ministry of Mines, **51.28%** — primary-verified against the Q4 FY2026 shareholding-pattern disclosure (President of India, unchanged vs Dec-2025, no encumbrance) [S1450]. Pledge: **N/A — sovereign promoter, pledge concept does not apply**. RPTs are structurally CPSE-to-CPSE trade under a common owner: FY2025 CPSE purchases ₹3,264.17cr (19.4% of revenue), CPSE sales ₹2,436.35cr (14.5%), dividend to GoI ₹941.80cr [F-GOV-01/02]. Disinvestment overlay: 51.28% leaves OFS headroom above the 51% control floor; no OFS/DIPAM target found (a structural overhang to monitor, not a red flag).

---

## 6. Earnings quality & red-flag ledger (complete)

All 23 adjudicated entries below (2 confirmed, 7 disclosed, 14 dismissed; 0 candidate). Dismissed flags stay visible with their dismissal reasons for auditability.

| ID | Category | Status | Sev. | Why-chain (compressed) | Confidence |
|---|---|---|---|---|---|
| RF-001 | earnings_quality | disclosed | medium | Other income 25.9% of CFO FY2023 is a denominator effect — CFO collapsed −77.6% (4,049.6→908.2cr) in the commodity trough while other income stayed flat; specific WC leg unconfirmed (extraction gap, FQ-NALCO-01). | medium |
| RF-002 | working_capital | dismissed | low | DSO +21% (1.93→2.34d) FY2023 — percentage noise on a ~2-day base; immaterial. | high |
| RF-003 | working_capital | dismissed | low | DSO +82% (2.34→4.26d) FY2024 — still <1 week; no channel-stuffing signature (inventory rose too); stabilized FY2025 (4.05d). | high |
| RF-MERGE-01 | data_quality | dismissed | low | Revenue FY2022 +0.24% (14,180.8→14,214.6) between AR_FY2022 and AR_FY2023 comparative — routine regrouping; latest wins. | high |
| RF-MERGE-02 | data_quality | disclosed | medium | Other income FY2022 −11.2% (297.4→264.1), largest relative P&L delta; no captured footnote naming the line (FQ-NALCO-02). | medium |
| RF-MERGE-03 | data_quality | dismissed | low | Total income FY2022 +0.003% (₹0.44cr) — rounding; revenue & other-income regroupings offset. | high |
| RF-MERGE-04 | data_quality | dismissed | low | Finance costs FY2022 +₹0.01cr — rounding. | high |
| RF-MERGE-05 | data_quality | dismissed | low | Other expenses FY2022 +₹0.43cr — rounding. | high |
| RF-MERGE-06 | data_quality | dismissed | low | Total expenses FY2022 +₹0.44cr — rounding, nets the above. | high |
| RF-MERGE-07 | data_quality | dismissed | low | Inventories FY2022 −₹0.57cr — minor valuation adjustment. | high |
| RF-MERGE-08 | data_quality | disclosed | medium | Total assets FY2022 +1.22% (₹211.04cr) — matched by identical liabilities move (RF-MERGE-09), i.e. a balance-sheet-identity-preserving reclassification; no footnote (FQ-NALCO-02). | medium |
| RF-MERGE-09 | data_quality | disclosed | medium | Total liabilities FY2022 +4.47% (₹211.04cr) — same reclassification as RF-MERGE-08. | medium |
| RF-MERGE-10 | data_quality | dismissed | low | Segment revenue (aluminium) FY2022 +0.26% — flows from the revenue regrouping. | high |
| RF-MERGE-11 | data_quality | dismissed | low | Revenue FY2022 consolidated +0.24% — same as standalone (immaterial subsidiary contribution). | high |
| RF-MERGE-12 | data_quality | disclosed | medium | Total assets FY2022 consolidated +1.22% (₹211.04cr) — regrouping flows through consolidation (FQ-NALCO-02). | medium |
| RF-MERGE-13 | data_quality | dismissed | low | Revenue FY2025 PPT-vs-AR +0.002% — deck rounding; audited AR kept. | high |
| RF-MERGE-14 | data_quality | dismissed | low | Total income FY2025 PPT-vs-AR +0.002% — deck rounding. | high |
| RF-MERGE-15 | data_quality | dismissed | low | PBT FY2025 PPT-vs-AR +0.80% (7,135 vs 7,078.37) — PPT quotes a rounded/pre-exceptional figure; audited AR kept. | medium |
| RF-MERGE-16 | data_quality | dismissed | low | PAT FY2025 PPT-vs-AR +1.08% (5,325 vs 5,267.94) — same PPT convention; audited AR kept. | medium |
| RF-GUI-01 | disclosure | **confirmed** | medium | 5th-stream FY26 volume cut ~40% in-year (500KT→300KT), then deferred to FY27 — original figure implied FY26 delivery, did not arrive; no reconciling explanation. | high |
| RF-GUI-02 | disclosure | **confirmed** | low | Alumina contract-mix target stated three ways in one FY (80/20 spot → 50/50 → spot-only); Q2 quote extraction-tagged evasive. | medium |
| RF-GUI-03 | disclosure | disclosed | low | 0.5 MT smelter commissioning date inconsistent across/within docs (Aug-2030 / Dec-2030 / Jun-2031; self-contradictory Q4 PPT) — pre-DPR planning estimates, documentation-hygiene issue. | high |
| RF-GUI-04 | disclosure | disclosed | low | Pottangi date mismatch same-quarter (June call vs May PPT) — one-month transcription slip; MDO tender tight (OQ-GUI-02). | medium |

**Composite interpretation.** No section-4 manipulation screen confirms gross-up, cash-flow reclassification, capitalization anomaly, or RPT round-tripping. Principal soft spots are the unexplained FY2023 CFO/WC swing (RF-001) and four comparative-period deltas >1% without footnote traceability (RF-MERGE-02/08/09/12). Capitalization/RPT screens (F-FOR-06) return no-data rather than a clean pass — an extraction-scope gap, disclosed. The two confirmed flags are both guidance-credibility issues (RF-GUI-01/02), not accounting-integrity issues.

---

## 7. Valuation & peers

### 7.1 Historical multiple bands

**P/E band (standalone EPS, 5y):**

| FY | Avg price | End price | EPS (basic std) | P/E on avg | P/E on end | Src |
|---|---|---|---|---|---|---|
| FY2021 | 28.67 | 42.32 | 6.97 | 4.11 | 6.07 | S1300 |
| FY2022 | 74.16 | 100.92 | 16.07 | 4.61 | 6.28 | S1301 |
| FY2023 | 68.98 | 69.13 | 8.41 | 8.20 | 8.22 | S1302 |
| FY2024 | 93.75 | 139.07 | 11.22 | 8.36 | 12.39 | S1303 |
| FY2025 | 183.26 | 167.94 | 28.99 | 6.32 | 5.79 | S1304 |
| FY2026 (cross-check, cons EPS 31.67) | 239.99 | 384.19 | 31.67 | 7.58 | 12.13 | S1305 |
| **CMP 361.65** vs FY2025 EPS | — | — | 28.99 | **12.47** | — | S1306 |
| **CMP 361.65** vs FY2026 EPS | — | — | 31.67 | **11.42** | — | S1307 |

*Legend:* S1300–S1307 are derived pe_band facts (formula: price/EPS), each traceable in `state/source_registry.json`.

The band's own extremes are cycle artifacts, not re-ratings (F-VAL, "why_band_moved"): FY2021's 4.1x is a COVID-trough EPS against a forward-looking price; FY2024's 8.36x is a depressed EPS against a price already re-rating on the anticipated FY2025 recovery; FY2025's drop to 6.32x despite EPS quadrupling shows the market discounting the ~45% margin as unsustainable in real time. The subsequent 12.5x/11.4x at CMP is therefore a genuine expansion beyond anything in the last five years.

**EV/EBITDA band:** ~7.8x (FY2024, depressed EBITDA) → ~3.9x (FY2025 end, company-reported EBITDA basis) → **7.7–8.4x at CMP** [S1308–S1312] — a trough-cycle-era multiple now applied to peak-cycle earnings.

**P/B band:** 0.73x (FY2021) → 1.48x → 1.78x → 1.73x → **3.73x at CMP** [S1313–S1317] — more than double the five-year band high.

**FCF yield:** N/A — a clean multi-year FCF series could not be built on a comparable basis during an accelerating capex phase; not approximated (S1318).

### 7.2 Peer tables (comparability deltas)

**Domestic (multiples not located in DR2 — margin proxies only):**

| Peer | Scale / production | Integration | Margin / unit econ | Multiple | Delta vs NALCO |
|---|---|---|---|---|---|
| Hindalco (consol incl. Novelis) | ₹275,000cr rev, ₹38,097cr EBITDA (13.85% consol margin); India upstream EBITDA/t US$1,572, 45.56% margin | Upstream (India) integrated; Novelis downstream | India-upstream 45.6% margin ≈ NALCO FY2025 44.6% | **Not pulled (gap)** | No operating-quality edge for NALCO over Hindalco's comparable segment [F-VAL-06] |
| Vedanta Aluminium | 2.88 MTpa capacity, 2.46mt produced FY26 | Integrating to 100% captive bauxite+coal | OPBDITA/t US$1,158–1,188; CoP US$1,752/t → target US$1,550–1,600/t | Not pulled (gap) | ~6x NALCO's metal scale; common-basis premium/discount not scoreable |

**International:**

| Peer | Multiples | Operating | Delta vs NALCO |
|---|---|---|---|
| Alcoa | trailing P/E 12.60x, fwd P/E 10.04x, EV/EBITDA 8.33x, mcap US$14.28bn (26-Jun-2026) | Rev US$3.2bn, adj EBITDA US$595mn Q1 CY2026 | NALCO trades at **essentially no discount** to a larger, multi-country, longer-track-record peer despite concentrated single-country risk and peak-cycle earnings — unexplained parity [F-VAL-07] |
| Norsk Hydro | Not scored (downstream-heavy, ~13.9% margin) | Rev NOK207,971mn FY2025 | Not like-for-like |
| Chalco | Not scored | ~5.3% net margin, 17.35mt alumina | Largest by volume, far lower margin |

### 7.3 Premium/discount analysis & what's priced in

At CMP and FY2025 EPS, the stock trades at ~2x the five-year average P/E (~6.3x). To re-justify the price at that average multiple, FY2027+ EPS would need to roughly double the FY2025 print (~EPS 57–58) — unsupported by any fact in the pack; management's own read is that FY2025 was a margin peak and FY2026 already shows Q4 PAT −17.4%. The reverse read (S1319): CMP prices in **either** a sustained ~2x EPS step-up versus a peak-cycle base, **or** a permanent multiple re-rating. Peer-valuation checked explicitly for a re-rating catalyst (credit-rating upgrade, index inclusion, DPR-approved capacity) and found **none** (F-VAL-05). The near-debt-free balance sheet is real and supportive but is a pre-existing multi-year condition (F-FUND-07, F-VAL-09) that does not explain a re-rating specifically over the last 12–18 months.

### 7.4 Valuation insights table (F-VAL-01…09)

| ID | Insight |
|---|---|
| F-VAL-01 | CMP 12.5x FY2025 / ~11.4x FY2026 EPS, ~2x the 5y average and above the 5y single-year high (8.36x). |
| F-VAL-02 | FY2025 P/E (6.32x) was the second-lowest in the band despite the highest EPS/margin — market discounted the surge in real time. |
| F-VAL-03 | EV/EBITDA halved FY24→FY25 then back to 7.7–8.4x at CMP — trough-era multiple on peak-era earnings. |
| F-VAL-04 | P/B 3.73x vs band high 1.78x — unprecedented for a stock below 1x book as recently as FY2021. |
| F-VAL-05 | Reverse read requires ~2x EPS step-up or an unevidenced re-rating; no confirmed catalyst. |
| F-VAL-06 | NALCO shows no operating-quality edge vs Hindalco's India-upstream segment this cycle. |
| F-VAL-07 | Multiples converged with Alcoa despite smaller scale, single-country risk, peak-cycle earnings. |
| F-VAL-08 | "Lowest-cost producer" claim not re-verifiable with a current third-party ranking (FY2019-vintage only). |
| F-VAL-09 | Near-debt-free balance sheet is supportive but static — does not explain the recent re-rating. |

### 7.5 Summary rating matrix (business quality)

Weighted business-quality score **6.05/10** [S1323]: industry structure 4 (−), cost position 7 (+), balance sheet 9 (neutral), moat 4.3 (neutral-to-+), earnings quality 7.5 (neutral), governance 7.3 (−), valuation 2 (−). Ex-valuation the business would score ~6.9/10 — it is valuation, not operations, that is the standout outlier.

---

## 8. Estimates (full build)

Basis: consolidated (FY2026 base is company-summarised PPT). All estimate facts EST-001…014; assumptions A-13xx in `state/assumptions.json`.

### 8.1 Driver tree & estimates table

*(Consolidated basis. FY2025A PAT/EPS here are consolidated — 5,267.94cr / 28.68 — distinct from the standalone FY2025 figures in §4.1 (5,324.67cr / 28.99).)*

| Metric | FY2025A | FY2026A (PPT) | FY2027E (base) | FY2028E (base) |
|---|---|---|---|---|
| Revenue (₹cr) | 16,787.6 [S500] | 17,843.0 [F-PQ4-001] | 19,399.4 [S1384] | 19,156.4 [S1385] |
| Revenue growth % | 27.7 | 6.3 | 8.7 | −1.3 |
| EBITDA (₹cr) | 7,922 [F-PQ4-018] | 8,613 [F-PQ4-018] | 8,632.7 [S1386] | 8,237.2 [S1387] |
| EBITDA margin % | 47.2 | 48.3 | 44.5 | 43.0 |
| PAT (₹cr, cons) | 5,267.9 [F-AR25B-013] | 5,815.8 [F-PQ4-029] | 6,015.9 [S1388] | 5,702.8 [S1389] |
| EPS diluted (₹, cons) | 28.68 | 31.67 | 32.76 [S1390] | 31.05 [S1391] |
| Capex (₹cr) | 1,175.6 | N/A (AR pending) | 2,280.0 | 2,250.0 |
| P/E @ CMP (x) | — | 11.42 | 11.04 [S1396] | 11.65 [S1397] |

Base-case **2yr EPS CAGR FY26→FY28E = −0.98%** (F-EST-01). Revenue essentially flat FY27E→FY28E as external price normalization (metal −3.23%, alumina −3.23% vs FY27E, World-Bank-anchored) outweighs volume/ramp gains — a sequential decline, not a modeling error (EST-002 note).

### 8.2 Assumption ledger (the ones that matter)

- Segment split ~73% metal / ~27% alumina (F-FUND-02/08).
- 5th-stream incremental alumina volume **probability-weighted 0.40 (FY27E) / 0.55 (FY28E)**, not nameplate — reflecting low guidance credibility and DR1b's unconfirmed-commissioning finding (A-1352; the single largest swing factor, F-EST-02).
- Price paths anchored to World Bank / Platts, not management guidance (A-1350/1355/1356).
- EBITDA margin faded from FY26's 48.3% to 44.5%/43.0%, within the 5-year band (24.9%–48.3%) — Gate 3 PASS.
- Normalized ETR ~25.1–25.6% (3y median); no dilution (GoI-majority, no ESOP/QIP).
- Capex-overrun pattern (~20% historical, F-FUND-04) built as an **upward bias** to capex/D&A/finance-cost, standing in for the (absent) working-capital drag (F-EST-04).

### 8.3 Sanity gates (all six)

Capex→gross-block→asset-turns PASS (expected capitalization-ahead-of-ramp divergence, disclosed); EPS vs PAT growth PASS (no dilution); margin vs bridge vs band PASS (within 24.9–48.3%); CFO/EBITDA quality PASS (73.3% FY25 conversion held); estimates-vs-guidance variant view PASS (stated); capacity-constrained revenue PASS (metal at rated capacity, alumina probability-capped below nameplate) — F-EST-05.

### 8.4 Scenarios (seeds for the downstream PT engine — not price targets)

| Scenario | FY27E EPS | FY28E EPS | 2yr EPS CAGR | Rationale |
|---|---|---|---|---|
| Base | 32.76 [S1390] | 31.05 [S1391] | **−0.98%** | Probability-weighted 5th-stream; World Bank/Platts price normalization. |
| Bull | 38.11 [S1392] | 42.42 [S1393] | **+15.74%** | 5th-stream at 100% nameplate; metal US$3,200/t, alumina US$340/t; margin 48–49%. |
| Bear | 24.04 [S1394] | 21.26 [S1395] | **−18.05%** | Zero incremental 5th-stream/Pottangi; metal ~US$2,400/t (Goldman bear), alumina US$260–280/t; margin 37–39%; finance cost +30–50%. |

The base/bull/bear spread is driven primarily by the probability weight on the one capacity lever, not by price assumptions alone (F-EST-02).

### 8.5 Variant view vs guidance/consensus

A naive 100%-guidance-flow-through model would sit near the bull case (+15.7%); the base case sits at −0.98% because low-credibility guidance is not allowed to become the base case (F-EST-03). Management's own FY27 *price* guidance is broadly in line with the independent anchors — the divergence is on *volume* (the 5th-stream ramp), not price.

---

## 9. Future outlook & monitorables

### 9.1 Sector-pack checkpoints (commodities/metals-mining)

- Quarterly alumina realization vs Platts FOB-Australia and the alumina-to-LME premium (currently 11–11.5%, was 15–17%).
- LME aluminium realization vs the World Bank CY2027 central case (US$3,000/t) and the Goldman bear track (US$2,400/t).
- Captive coal tonnage progress toward the FY27 4.8 MTpa guide (subject to EC clearance for Utkal D&E).
- Metal production vs the FY27 4.73 lakh ton guide (highest-credibility family).

### 9.2 Catalyst calendar

| Date / trigger | Event |
|---|---|
| ~Aug-2026 (Q1 FY27 call) | First confirmation of whether the 5th-stream refinery commissioned within one quarter of the June-2026 guide (OQ-GUI-03). |
| Aug–Sept 2026 | 0.5 MT smelter DPR targeted (OQ-FUND-03 becomes answerable). |
| On publication | FY2026 audited AR — confirms/disputes the Q4 PPT full-year figures used throughout (RF-MERGE precedent: ~1% PPT-vs-AR gap for FY2025). |
| Pending | BSE/NSE ID-composition fine waiver outcome; board restoration to LODR-compliant composition. |
| Pending | CBI recruitment-fraud probe resolution. |

### 9.3 What would change the view

Upgrade-supportive: 5th-stream confirmed commissioned/ramping within a quarter of guide; fine waiver granted AND board restored; CBI probe closes with no adverse finding; FY2027 prices sustained materially above guidance without a war premium; a confirmed re-rating catalyst (rating upgrade / index-weight increase / DPR-approved smelter with credible payback). Downgrade-supportive: a second consecutive capex overshoot (>15–20%) or a second commissioning slip; FY2026 AR materially diverging from PPT figures. (from `state/thesis.json` what_would_change_our_mind.)

---

## 10. Risk factors

| Risk | Type | Probability × Impact | Named mitigant |
|---|---|---|---|
| Valuation reversion toward the 5y band | Financial / market | High × High | None intrinsic — depends on either an EPS step-up or an evidenced re-rating, neither present (F-VAL-05). |
| 5th-stream slips again / ramps below probability weight | Operational | Medium-High × High | Metal-volume and cost families are delivering; base case already probability-discounts the lever (A-1352). |
| Governance — LODR breach + CBI probe unresolved | Governance | Medium × Medium | Company self-disclosed and appealing; breach is a CPSE appointment-control issue (GoI names IDs), not misconduct; accounting sub-score clean (90/100). |
| Alumina structural oversupply (Indonesia) | Industry | High × Medium | Segment mix shift toward metal; captive-cost moat cushions margin; management guides no near-term recovery (already in base case). |
| Commodity price cycle turns down (metal + alumina) | Financial | Medium × High | Near-debt-free balance sheet absorbs downturns; captive input costs support margin resilience. |
| Capex overrun continues / debt-funds the smelter | Financial | Medium × Medium | Balance-sheet capacity to gear from near-zero base; bear case already embeds finance-cost inflation (F-EST-04). |
| CBAM / EU export exposure | Industry / policy | Low-Medium × Medium (unsized) | NALCO's specific EU export mix not quantified — a disclosed gap (F-EXT-1227). |
| FY2026 figures unaudited (PPT-sourced) | Data quality | Medium × Low-Medium | Precedent gap ~1% (FY2025 PPT vs AR); flagged, re-run on AR publication (OQ-FUND-01). |

---

## 11. Concluding synthesis

**Strengths.** A clean, near-debt-free balance sheet; a genuine and widening cost-structure moat (captive bauxite, captive-coal ramp — the cleanest-delivered lever in the guidance ledger); above-median earnings quality with five straight unqualified audits and CAG "Nil" comments; the best delivery record in the ledger on the levers management actually controls (metal volume, cost efficiency).

**Vulnerabilities.** No pricing power (buyer power 7/10, near-zero switching costs, no hedging); a cost-structure moat that supports margins in a downturn but does not drive earnings growth or justify multiple expansion; two live overhangs — a fined governance-compliance breach and a repeatedly cut/deferred timeline on the single largest near-term growth lever; and, most acutely, a price that has run to roughly twice the multiple the stock has ever earned in its own five-year history against a base-case earnings path that is flat-to-down.

The structural metaphor that fits: NALCO is a well-built ship with a sound hull and cheap fuel, sailing a sea whose swells it cannot control — the current price is set as if the sea had been tamed, when the evidence says only the hull has been strengthened.

---

## 12. Annexure (verbatim, unabridged)

*Rendered from the facts store via `tools/render_tables.py` (standalone basis). N/A cells reflect line items not extracted at fact-record level for that year; the FY2021–FY2025 audited window is the populated span. FY2026 full-year figures are company-summarised (Q4 PPT) and appear in §8 / valuation_handoff.json rather than the audited-AR annexure.*

### 12.1 Income statement summary (standalone, verbatim)

| Metric | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 |
|---|---|---|---|---|---|
| Revenue from operations | 8,955.8 [S100] | 14,214.6 [S301] | 14,254.9 [S300] | 13,149.1 [S400] | 16,787.6 [S500] |
| Revenue growth YoY % | N/A (FY2020 outside AR set) | 58.7 | 0.3 | -7.8 | 27.7 |
| EBITDA | N/A (no extracted standalone EBITDA line; computed route F-DER-FUN-01/02 for FY2024/FY2025 only) | N/A | N/A | 3,278.8 (computed) | 7,487.1 (computed) |
| Finance costs | 7.1 [S103] | 23.1 [S315] | 12.9 [S314] | 17.2 [S515] | 59.0 [S514] |
| Other income | 146.6 [S101] | 264.1 [S303] | 235.6 [S302] | 250.7 [S503] | 357.0 [S502] |
| PBT (standalone) | 1,316.5 [S107] | 3,954.9 [S200] | 1,955.0 [S330] | 2,712.1 [S400] | 7,135.1 [S500] |
| PAT (standalone) | 1,299.4 [S107] | 2,952.0 [S200] | 1,544.5 [S338] | 1,988.5 [S400] | 5,324.7 [S538] |
| PAT margin % (standalone) | 14.5 | 20.8 | 10.8 | 15.1 | 31.7 |
| EPS diluted (standalone) | 7.0 [S107] | 16.1 [S200] | 8.4 [S350] | 11.2 [S551] | 28.99 [S550] |

*Legend as §4.1 (FY2025 standalone PAT 5,324.67cr [S538]; consolidated PAT 5,267.94cr is used in §8 estimates).* EBITDA computed rows carry medium confidence (F-DER-FUN-01/02, PBT+Dep+Fin−OtherIncome route); company-reported consolidated EBITDA (₹7,922cr FY2025) is preferred in deliverables per reported-over-computed precedence.

### 12.2 Balance sheet summary (standalone, verbatim)

| Metric | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 |
|---|---|---|---|---|---|
| Total assets | 14,710.6 [S108] | 17,488.8 [S397] | 17,738.7 [S396] | 19,418.6 [S595] | 23,122.5 [S594] |
| Total equity | 10,680.7 [S111] | 12,554.6 [S203] | 13,238.5 [S3402] | N/A (not extracted at line level) | N/A (not extracted at line level) |
| Borrowings (current) | 46.1 [S113] | 20.7 [S203] | N/A | N/A | N/A (consol current borrowings 124.22cr per F-FUND-07) |
| Inventories | 1,476.3 [S110] | 1,645.6 [S375] | 1,840.2 [S374] | 1,831.3 [S575] | 1,908.8 [S574] |
| Trade receivables | N/A | 75.2 [S203] | 91.3 [S378] | 153.5 [S579] | 186.4 [S578] |
| Net PPE | 7,317.3 [AR21] | 7,001.9 [AR22] | 6,916.4 [AR23] | 7,020.2 [AR24] | 6,799.0 [AR25] |
| CWIP | 1,431.1 [AR21] | 1,763.4 [AR22] | 2,744.9 [AR23] | 3,961.5 [AR24] | 4,934.7 [AR25] |

*Legend:* [S108] AR_FY2021 p.151 Notes 5–7; [S110] AR_FY2021 p.151 Notes 15–16; [S111] AR_FY2021 p.151 Notes 17–18; [S113] AR_FY2021 p.151 Note 19; [S203] AR_FY2022 p.146 BS; [S3402] AR_FY2023 p.130 total equity; [S374]/[S375] AR_FY2023 p.130 Note 15; [S378] AR_FY2023 p.130 Note 10; [S396]/[S397] AR_FY2023 p.130 total assets; [S574]/[S575] AR_FY2025 p.154 Note 15; [S578]/[S579] AR_FY2025 p.154 Note 10; [S594]/[S595] AR_FY2025 p.154 total assets. Net PPE/CWIP series per F-FUND-03 evidence (F-AR21-151/153 … F-AR25-053/055).

### 12.3 Cash flow & FCF (standalone, verbatim)

| Metric | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 |
|---|---|---|---|---|---|
| CFO | 2,199.4 (F-FOR context) | 4,049.6 [S3454] | 908.2 [S3453] | 2,727.1 (F-FOR context) | 5,806.1 (F-FOR context) |
| Net capex | N/A (not a comparable standalone series across all 5y; see §7.1 FCF-yield gap) | — | — | — | — |
| Free cash flow | N/A | — | — | — | — |

*Legend:* [S3453]/[S3454] AR_FY2023 p.135 standalone CFS. FY2021/FY2024/FY2025 CFO figures per forensic-auditor cash-conversion component (₹2,199.4 / ₹2,727.1 / ₹5,806.1cr). Consolidated handoff records FY2024 CFO 2,727.08 / capex 1,559.7 / FCF 1,167.38; FY2025 CFO 5,806.11 / capex 1,175.58 / FCF 4,630.53 (valuation_handoff.json).

### 12.4 Key ratios (standalone, verbatim)

| Metric | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 |
|---|---|---|---|---|---|
| PAT margin % (standalone) | 14.5 | 20.8 | 10.8 | 15.1 | 31.7 |
| ROE % | N/A | 25.4 | 12.0 | 13.8 (cons) | 32.7 (cons) |
| ROCE % | N/A | 34.1 | 15.2 | N/A | N/A |
| Asset turnover (x) | 0.6 | 0.9 | 0.8 | 0.7 | 0.8 |
| Receivable days | N/A | 1.9 | 2.3 | 4.3 | 4.1 |
| Inventory days | 60.2 | 42.3 | 47.1 | 50.8 | 41.5 |
| Debt/Equity (x) | 0.0 | 0.0 | N/A | N/A | N/A |
| Interest coverage (x) | N/A | 172.0 | 152.3 | N/A | N/A |

*Legend:* ratio_summary render (`compute_ratios.py`); FY2024/FY2025 ROE per D-ROE-FY2024-CONS-018 / D-ROE-FY2025-CONS-026 (consolidated). N/A cells reflect missing consistent standalone equity/capital-employed pairs at extraction, not zero values.

### 12.5 Valuation multiple annexure (derived)

P/E band, EV/EBITDA band and P/B band tables reproduced in full at §7.1 with S1300–S1317 derived-fact references; reverse-read at S1319; ROE S1320; alumina revenue sensitivity ~₹13.3cr per US$1/t (S1321); moat composite S1322; business-quality composite S1323.

---

## 13. Global source legend

*Every distinct source referenced, deduplicated, traced to the original document (never to an intermediate module). Full registry: `state/source_registry.json` (946+ entries). Legends after each table above list the subset used there.*

**Internal — Annual Reports (audited):**
- **AR_FY2021.pdf** — S100 (p.151 Note 27 revenue), S101 (p.152 Note 28 other income), S103 (p.152 Notes 31–33), S107 (p.152 Note 36 EPS/PBT/PAT), S108 (p.151 Notes 5–7 PPE/CWIP), S110 (p.151 Notes 15–16), S111 (p.151 Notes 17–18 equity/buyback), S113 (p.151 Note 19 borrowings), SRC-119 (audit opinion).
- **AR_FY2022.pdf** — S200 (p.147 P&L / p.146 BS), S203 (p.146 BS assets & liabilities), S205 (segment revenue), SRC-210 (audit opinion).
- **AR_FY2023.pdf** — S300/S301 (p.131 Note 29 revenue), S302/S303 (p.131 Note 30 other income), S314/S315 (p.131 Note 34 finance costs), S323/S325 (other/total expenses), S330 (p.131 PBT), S338 (profit for year), S350 (p.131 Note 38 EPS), S374/S375 (p.130 Note 15 inventories), S378 (p.130 Note 10 receivables), S396/S397 (p.130 total assets), S3402 (total equity), S3443 (total liabilities), S3453/S3454 (p.135 standalone CFS), S3466/S3473/S3477 (consolidated), SRC-3469 (audit opinion).
- **AR_FY2024.pdf** — S400 (p.147 standalone P&L), F-AUD-01/02/03 (joint auditors A.K. Sabat & Co. / P.A. & Associates; unqualified), F-AUD-04 (CAG Sec 143(6) "Nil"), F-AUD-05 (contingent liabilities ₹1,920.03cr), SRC-422/423/529 (FY2024 exceptional gain ₹426.81cr), SRC-2702.
- **AR_FY2025.pdf** — S500 (p.155 Note 28 revenue), S502/S503 (p.155 Note 29 other income), S514/S515 (p.155 Note 33 finance costs), S538 (standalone Statement of P&L — profit for the year FY2025, ₹5,324.67cr), S548 (Note 38 EPS basic 28.99), S550/S551 (p.155 Note 38 EPS diluted), S574/S575 (p.154 Note 15 inventories), S578/S579 (p.154 Note 10 receivables), S594/S595 (p.154 total assets), F-AUD-22/23/24 (joint auditors B M Chatrath & Co. LLP / SRB & Associates; unqualified), F-AUD-25 (CAG "Nil"), F-AUD-26 (payroll audit-trail gap), F-AUD-27 (contingent liabilities ₹2,050.43cr), SRC-2500/2504/2508/2512 (pass-2 comparatives), SRC-2586 (standalone CF profit 5,324.67cr), SRC-2617/2619/2621/2623 (RPT/dividend/KMP), SRC-2752.

**Internal — Transcripts (FY2026 calls):** TR_2025-08-08 (Q1: QT-Q1-007, GD-Q1-xxx), TR_2025-11-07 (Q2: QT-Q2-041, GD-Q2-xxx), TR_2026-01-30 (Q3: GD-Q3-014/037), TR_2026-04-30 (Q4: QT-Q4-001…088, GD-Q4-xxx). Quote/guidance derived-fact IDs (QT-, GD-, GD-PQ-) map to `facts/quotes/*` and `facts/quotes` guidance records.

**Internal — Presentations (FY2026):** PPT_FY2026Q1–Q4 — S693 (Q4 PPT FY2025 comparatives), F-PQ1-038 (FY2025 EBITDA 7,922cr), F-PQ4-001 (FY2026 revenue 17,843cr), F-PQ4-017/018 (EBITDA/margin), F-PQ4-020 (D&A), F-PQ4-023 (finance cost), F-PQ4-026/029 (PBT/PAT), GD-PQ2/PQ3/PQ4 (smelter/Pottangi dates).

**Market data (yfinance):** SRC-MKT-001 / F-MKT-* — CMP 361.65 (2026-07-15), mcap 66,421.8cr, shares 183.6632cr, 52-wk 445.15/179.93, FY average/end prices FY2015–FY2027, returns/CAGR series. Pulled 2026-07-15T11:47:58.

**Derived (this run):** S1000–S1007 (fundamental EBITDA/margin/CWIP/segment); S1020–S1028 (forensic screens); S1040–S1059 (guidance credibility/delivery); F-GOV-01…06 (governance RPT %); S1300–S1323 (valuation derived facts, each carrying its own formula per citation standard §2): S1300–S1305 (P/E band FY2021–FY2026), S1306/S1307 (CMP P/E on FY2025/FY2026 EPS), S1308–S1312 (EV/EBITDA band), S1313–S1317 (P/B band incl. S1317 CMP P/B 3.73x), S1318 (FCF-yield gap note), S1319 (reverse read), S1320 (FY2025 ROE 32.73%), S1321 (alumina revenue sensitivity), S1322 (moat composite 4.3/10), S1323 (business-quality composite 6.05/10).

**Estimates (estimates-builder derived facts, EST-001…014 → SRC-1384…1397):** S1384 (revenue FY27E 19,399.4cr), S1385 (revenue FY28E 19,156.4cr), S1386 (EBITDA FY27E 8,632.7cr), S1387 (EBITDA FY28E 8,237.2cr), S1388 (PAT FY27E 6,015.9cr), S1389 (PAT FY28E 5,702.8cr), S1390 (EPS FY27E base 32.76), S1391 (EPS FY28E base 31.05), S1392 (EPS FY27E bull 38.11), S1393 (EPS FY28E bull 42.42), S1394 (EPS FY27E bear 24.04), S1395 (EPS FY28E bear 21.26), S1396 (fwd P/E FY27E 11.04x), S1397 (fwd P/E FY28E 11.65x). Assumption ledger A-13xx in `state/assumptions.json`.

**External (web/research, access-dated 2026-07-16):**
- DR1 (F-EXT-1100…1112 / SRC-1100–1121): management bios (nalcoindia.com press releases, primary), regulatory/lease/OFS sweep.
- DR1-B (F-EXT-1150…1159 / SRC-1150–1170): F-EXT-1150/1151 (5th-stream commissioning-support tender pre-bid 01-Jul-2026), F-EXT-1152 (Pottangi MDO to Dilip Buildcon 9-Dec-2025), F-EXT-1155 (SRC-1160/1161/1162/1163 BSE/NSE fine, 4 trade-press sources), F-EXT-1156 (SRC-1164/1165 CBI probe), F-EXT-1157 (SEBI/NCLT docket unresolved), F-EXT-1158 (CAG report unresolved), F-EXT-1159 (FY26 cash unresolved).
- Shareholding — **S1450** (NALCO Q4 FY2026 shareholding-pattern disclosure: President of India 51.28%, unchanged vs Dec-2025, no encumbrance; nalcoindia.com investor-services, accessed 2026-07-16, **primary**).
- DR2 (F-EXT-1200…1230 / SRC-1200–1228): World Bank CMO (F-EXT-1200/1201, primary), LME spot (F-EXT-1202), SMM (F-EXT-1203), Goldman bear (F-EXT-1204), Platts FOB-Australia (F-EXT-1206, primary), Indonesian capacity (F-EXT-1211/1212), India demand (F-EXT-1213/1214), Wood Mackenzie FY2019 (F-EXT-1215), Hindalco (F-EXT-1216/1217), Vedanta (F-EXT-1218/1219/1220), Alcoa (F-EXT-1221/1222), Norsk Hydro (F-EXT-1223/1224), Chalco (F-EXT-1225), CBAM (F-EXT-1227), coal (F-EXT-1229/1230); **S1223** (India anti-dumping duty on aluminium foil imports — China/Indonesia/Malaysia/Thailand, extended to 15-Dec-2026), **S1225** (US Section 232 restructured 6-Apr-2026 — 50% wholly-metal / 25% derivatives). Corroboration tiers labelled per record (primary = regulator/PRA filing; secondary = trade press; forecasts = attributed opinion).

---

## 14. Open questions & gaps register

| ID | Question (short) | Severity | Status | Answer / disclosure |
|---|---|---|---|---|
| OQ-FUND-01 | FY2026 audited AR vs Q4 PPT figures? | medium | open | AR not published; FY2026 full-year figures are PPT-sourced; re-run on publication. |
| OQ-FUND-02 | FY2026 standalone vs consolidated identity holds? | low | open | Only consolidated PPT available for FY2026. |
| OQ-FUND-03 | 0.5 MT smelter incremental ROCE/payback? | high | open | Pre-DPR; not computable; excluded from FY27–29 horizon. Disclosed gap. |
| OQ-FUND-04 | Smelter capex funding mix (debt vs equity)? | medium | open | Not disclosed; bear case models finance-cost inflation. |
| OQ-FUND-05 | Root cause of FY26 capex ~24% overshoot? | low | open | Disclosed qualitatively only. |
| OQ-FUND-06 | FY25/26 current-borrowings composition? | low | open | Not isolated. |
| OQ-FUND-07 | External FY2027 price decks vs guidance? | medium | **answered** | Management guide base-to-conservative vs World Bank/SMM/Goldman spread (DR2). |
| OQ-FUND-08 | Why did alumina-segment EBIT grow faster than metal FY25? | low | open | Reconciliation pending; segment-mix narrative not over-claimed. |
| FQ-NALCO-01 | FY2023 CFO collapse — which WC leg? | medium | open | CFO reconciliation schedule not extracted; benign read supported but leg unconfirmed. |
| FQ-NALCO-02 | FY2022 reclassification footnote (RF-MERGE-02/08/09/12)? | medium | open | No footnote captured; disclosed. |
| OQ-GUI-01 | Price guidance vs independent index? | medium | **answered** | Consistent (Platts $306.91/t inside guided band). |
| OQ-GUI-02 | Pottangi commissioning — May or June, actual? | medium | open | MDO awarded Dec-2025; actual mining start unconfirmed. |
| OQ-GUI-03 | 5th-stream commissioned June-2026 or slipped again? | high | open | Unconfirmed as of Jul-2026 (tender pre-bid 01-Jul-2026). Disclosed monitorable. |
| OQ-GUI-04 | FY26 year-end cash vs ₹20,000cr guide? | low | open | Only H1 cash (~₹7,900cr) found; year-end pending AR. |
| OQ-GUI-05 | Pre-FY2026 capacity-timeline track record? | medium | open | No pre-FY2026 transcripts; credibility built on one FY. |
| OQ-GOV-01 | SEBI/ED/SFIO/CBI/NCLT/IBBI/MCA registry sweep? | high | open | Docket portals not indexable; "no adverse finding located," not certified-clean. Disclosed gate. |
| OQ-GOV-02 | CAG Sec 143(6) FY2021–FY2025? | high | answered (partial) | Company-disclosed "Nil" FY2024/FY2025; external CAG PDF not fetched. |
| OQ-GOV-03 | FY2024/FY2025 auditor opinion + contingent liabilities? | high | answered | Both unqualified; ₹1,920.03cr / ₹2,050.43cr (re-extraction). |
| OQ-GOV-04 | GoI shareholding trend / OFS? | medium | answered (partial) | No OFS found; 51.28% secondary-tier. |
| OQ-GOV-05 | Board/ID composition? | medium | **answered (adverse)** | Active penalized LODR breach, not routine vacancy (F-EXT-1155). |
| OQ-GOV-06 | Media/reputation? | medium | answered (partial) | CBI probe + fine press coverage surfaced. |
| OQ-DR1-1..6 | Lease dates, GoI % primary, dividend policy, reputation sweep, SEBI/NCLT docket, Director-HR | low-medium | mixed | See DR1/DR1-B; lease-date discrepancy and docket screen remain open. |

---

**Disclaimer.** This report is for educational analysis only and is not investment advice or a research report under SEBI (Research Analysts) Regulations, 2014. It has not been prepared by a SEBI-registered Research Analyst. Treat it as business analysis, not investment research. Always do your own due diligence before investing.

**AI disclosure.** Artificial intelligence was used to prepare substantially all of the analysis in this report (in line with the disclosure expectation SEBI introduced for AI use in research preparation). AI systems can make mistakes: figures are extracted and cross-verified against cited source pages, but errors may remain. Every number carries a source reference — verify load-bearing figures against the cited page before relying on them.

**Validity.** Prepared on 2026-07-16 (the later of: dates in supplied research documents; run date). Company information changes with news flow and results; treat the analysis as decaying in reliability beyond ~12 months, and the market data as of its pull timestamp only.

**Sources.** Company documents supplied by the user (annual reports, quarterly filings, transcripts, presentations); exchange/regulator websites; market data via yfinance (timestamped); external research as cited with URL and access date. The preparer holds no position information and expresses no view on suitability for any investor.
