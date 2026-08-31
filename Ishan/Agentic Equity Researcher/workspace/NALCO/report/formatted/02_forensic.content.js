const { NAVY, GOLD, GREEN, AMBER, RED } = require("../../../../tools/report_formatter/reportStyle.js");

const masthead = ["Research Dossier", "Full Audit Document — Internal Use Only"];
const title = [
  "National Aluminium Company Limited",
  "NSE: NATIONALUM  |  Metals & Mining — Aluminium  |  India  |  Run date 2026-07-16",
  "Forensic Research Dossier (Full Audit Record)",
];

const blocks = [
  { type: "callout", title: "No recommendation in this document", color: NAVY, text:
    "This dossier is the long-form audit record. Every number carries a source reference [S###] mapping to state/source_registry.json. Tables are rendered from fact records, not retyped. The rating does NOT appear in this document — it lives only in the final note's rating box (report/final_note.md). Basis: standalone primary (consolidated vs standalone diverge <0.3% every year, F-FUND-09; JV/subsidiary carrying value ~2% of balance sheet; FY2026 full-year figures available only on a consolidated Q4-PPT basis and cited as such)." },

  { type: "heading", text: "Input manifest & run record", number: 0 },
  { type: "text", text:
    "Inputs: 13 documents — 5 audited Annual Reports (FY2021–FY2025) plus 4 FY2026 quarterly earnings-call transcripts and 4 quarterly presentations. Declared intake gaps (state/manifest.json): no standalone quarterly results filings (FY2026 quarterly financials taken from presentations, treated as company-summarised until the FY2026 AR publishes); FY2026 audited AR not yet published; no prior deep-research documents (both waves run fresh, DR1 + DR2); no supplied peer/KPI material; no transcripts pre-FY2026 (pre-FY2026 management signalling is limited to AR MD&A)." },
  { type: "text", opts: { size: 19 }, text:
    "Pipeline: INTAKE → CONVERT → TRIAGE (sector pack: commodities/metals-mining) → parallel EXTRACT → COMPUTE (ratio/statement/EPS-bridge/xlsx builders) → parallel ANALYZE (fundamental / forensic / guidance / governance) → RESEARCH (DR1 company + DR1-B follow-up; DR2 sector/peers) → LOOP (external facts F-EXT-1155/1156 marked the governance and legal_regulatory sub-scores stale; governance re-run, downgraded Green→Amber, stale-rerun-only) → SYNTHESIZE (peer-valuation + estimates → thesis) → VERIFY → RENDER. Convergence: all five thesis pillars meet the two-independent-reference minimum; all 23 red-flag ledger entries adjudicated (2 confirmed, 7 disclosed, 14 dismissed, 0 candidate); three high-severity open questions (OQ-FUND-03, OQ-GUI-03, OQ-GOV-01) remain unanswered and are carried as disclosed gaps rather than blocking." },

  { type: "heading", text: "Executive summary", number: 1 },
  { type: "text", text:
    "NALCO is an operationally sound, input-cost-advantaged, near-debt-free integrated aluminium producer whose earnings are an unsmoothed, leveraged function of two spot-linked commodity prices (LME aluminium and alumina). The FY2025 profit surge was a cyclical realization peak, not a structural efficiency step-up; FY2026 already shows the reversal beginning at the exit quarter (Q4 FY2026 PAT −17.4% YoY [S693]). The base-case earnings path through FY2028E is roughly flat-to-down. Set against this, the market price sits materially above every multiple the stock has traded at in its own five-year history, with no confirmed re-rating catalyst identified. Two governance/execution overhangs are live: a fined SEBI LODR board-composition breach and a repeatedly cut/deferred commissioning timeline on the single largest near-term capacity lever." },
  { type: "text", text:
    "Core financial health: the balance sheet is a genuine strength — near-zero leverage (standalone D/E 0.0016x, FY2022 [S1022-context]), interest coverage 152x–172x in FY2022–FY2023 [ratio_summary], captive bauxite and a captive-coal ramp toward ~4 MTpa. Earnings quality is above-median for an Indian commodity CPSE (forensic composite 75/100): unqualified audits five straight years, CAG supplementary comment “Nil” in both covered years, a single non-recurring exceptional item (FY2024). Cash conversion is volatile but tracks the commodity cycle rather than manipulation." },
  { type: "text", text:
    "Valuation synopsis: CMP ₹361.65 (2026-07-15) is 12.5x FY2025 EPS [S1306] and ~11.4x the FY2026 cross-check EPS [S1307], against a five-year PE-on-average-price band of 4.1x–8.4x (median ~6.3x) [S1300–S1304] that never reached double digits even in the FY2025 cyclical-peak year. P/B at CMP is 3.73x [S1317] versus a five-year band high of 1.78x. Base-case forward P/E is 11.0x (FY27E) / 11.7x (FY28E) [S1396/S1397] — still above the historical band on forward earnings." },
  { type: "sub", text: "Top four principal risks" },
  { type: "bullets", items: [
    "Valuation reversion — CMP prices in either a ~2x sustained EPS step-up versus a peak-cycle base, or an unevidenced permanent re-rating [F-VAL-05].",
    "Execution/guidance credibility on the 5th-stream refinery — the FY26 volume contribution was cut ~40% in-year then deferred to FY27; commissioning remains unconfirmed as of Jul-2026 [RF-GUI-01, F-EXT-1150].",
    "Governance — a fined, disclosed SEBI LODR independent-director-composition breach (₹10.86 lakh, waiver pending) plus an open CBI recruitment-fraud probe [F-EXT-1155, F-EXT-1156].",
    "Commodity price cycle — structural alumina oversupply (Indonesian ramp) with management guiding no near-term recovery (FY2027 alumina US$300–310/t vs FY2025 US$580/t) [F-FUND-02].",
  ]},

  { type: "heading", text: "Industry & market analysis", number: 2 },
  { type: "text", opts: { size: 19 }, text:
    "The aluminium value chain runs bauxite → alumina → primary aluminium (LME-priced) → semis/downstream. NALCO is fully integrated across the first three stages with captive power but has effectively no downstream/specialty business. The structural bottleneck is the alumina-to-LME price premium, which compressed from 15–17% to 11–11.5% [GD-Q4-035] as Indonesian refinery capacity ramped toward 7 MTpa by CY2026 (primary aluminium capacity 0.87→2.51→3.56mt 2025→2027) [F-EXT-1211, F-EXT-1212] — the confirmed driver behind the FY2026 alumina realization collapse (US$580→US$370, FY25→FY26) [F-FUND-02]." },
  { type: "sub", text: "Porter's five forces (0–10; higher = more pressure on NALCO)" },
  { type: "table", headers: ["Force", "Score", "Trajectory"], opts: { colAligns: ["left","center","left"], colWeights: [2.4,0.7,1.6] }, rows: [
    ["Threat of new entrants", "6", "Worsening in alumina, CY2025–2027 (Indonesian ramp) [F-EXT-1211/1212]"],
    ["Bargaining power of suppliers", "3", "Improving — captive bauxite/coal ~57% of fuel need [F-EXT-1208]"],
    ["Bargaining power of buyers", "7", "Structurally stable at a high level (spot/LME pricing, no long-term contracts) [F-FUND-01]"],
    ["Threat of substitutes", "2", "Stable — no evidenced substitution threat [F-EXT-1214]"],
    ["Competitive rivalry", "6", "Intensifying — Hindalco and Vedanta both expanding and cutting costs [F-EXT-1216/1219]"],
  ]},
  { type: "text", opts: { size: 19 }, text:
    "Composite read: an industry structure moderately-to-highly unfavourable for pricing power (buyer power and rivalry dominant at 6–7/10), partially offset by input-cost self-sufficiency (supplier power and substitution both low at 2–3/10) — corroborating the independent finding that NALCO is a “commodity price taker with near-zero hedging” (F-FUND-01)." },
  { type: "text", opts: { size: 19 }, text:
    "Demand: India aluminium demand ~6.27% CAGR CY2024–2030 (TechSci, paid research, confidence low — no official-statistics source located) [F-EXT-1213]. Price context (CY2027): World Bank US$3,000/t central; SMM US$2,900–3,200/t; Goldman bear US$2,400/t; LME spot already US$3,538/t on 28-Apr-2026 [F-EXT-1200/1203/1204/1202]. Policy: EU CBAM's definitive phase began 1-Jan-2026 (first certificate price €75.36/tCO₂e); Indian unwrought-aluminium exports to the EU fell 41.7% YoY — NALCO's own EU exposure was not sized in this pass, a disclosed gap [F-EXT-1227]. US Section 232 restructured 6-Apr-2026 (50% on wholly-metal articles); NALCO is not a significant direct US exporter [S1225]." },

  { type: "heading", text: "Company deep-dive", number: 3 },
  { type: "text", opts: { size: 19 }, text:
    "NALCO is a Navratna CPSE (GoI 51.28% via the President of India / Ministry of Mines), fully integrated bauxite–alumina–aluminium with captive thermal, wind and rooftop-solar power. Two reportable segments — Chemicals (alumina) and Aluminium (metal) — inside one vertically integrated chain, so the segment split reflects relative price cycles as much as deliberate tonnage reallocation (F-FUND-08). FY2026 revenue mix shifted ~70/30 → 73/27 (metal/alumina), framed by management as margin-supportive [QT-Q4-075/076]; the segment-EBIT picture is more nuanced — Aluminium's EBIT share was 61.2% (FY24) and 55.5% (FY25) [F-DER-FUN-07/08], i.e. Chemicals' EBIT share rose even as revenue mix moved toward metal. Carried as OQ-FUND-08, not over-claimed as a clean margin driver." },
  { type: "text", opts: { size: 19 }, text:
    "Unit economics (FY2026): alumina cost of production ₹20,000–22,000/t [GD-Q4-024]; metal cost of production ₹155,000–160,000/t [GD-Q4-025]. Delivered cost levers: caustic soda consumption improved 121→99 kg/t (~₹129cr savings) [GD-Q3-014]; captive coal +41.84% YoY toward ~4 MT, displacing costlier e-auction coal and grid power; employee cost declining mechanically as ~250 high-paid retirements are replaced by lower-paid recruits [QT-Q4-028]." },
  { type: "sub", text: "Moat matrix (weighted, 0–10)" },
  { type: "table", headers: ["Dimension", "Score", "Weight", "Trajectory"], opts: { colAligns: ["left","center","center","left"], colWeights: [1.7,0.6,0.6,1.7] }, rows: [
    ["Scale", "4", "0.15", "Improving modestly, off a small base [F-EXT-1220]"],
    ["Brand", "1", "0.05", "N/A — bulk commodity, no premium [F-FUND-01]"],
    ["Distribution", "3", "0.10", "Eroding on contract-stickiness [F-GUI-02]"],
    ["Switching costs", "1", "0.10", "Stable-low — near-zero for LME-linked commodity"],
    ["Supply-chain integration", "7", "0.25", "Widening — captive bauxite, coal ramp to ~4 MTpa [F-EXT-1208]"],
    ["Regulatory / access barriers", "6", "0.20", "Stable-to-uncertain — scarce leases, lease-date discrepancy open [OQ-DR1-1]"],
    ["Specialty vs bulk mix", "2", "0.15", "Potentially improving, not yet realized"],
  ]},
  { type: "text", opts: { size: 19 }, text:
    "Weighted moat composite = 4.3/10 [S1322]. The two dimensions where NALCO genuinely differentiates — supply-chain integration (7) and regulatory/access barriers (6) — are a cost-structure moat, which supports margin resilience in a downturn more than earnings growth or multiple expansion in an upturn. It is not a pricing-power moat. On margin comparability, NALCO's FY2025 EBITDA margin (44.6%, F-DER-FUN-04) is closely in line with Hindalco's India-upstream 45.6% [F-EXT-1216] — no operating-quality edge over its largest domestic peer this cycle. NALCO's own “world's lowest-cost producer” claim could not be re-verified against a current third-party ranking (most recent independently-citable instance is FY2019-vintage) [F-VAL-08, F-EXT-1215] — a moat-relevant gap, not a confirmed premium." },

  { type: "heading", text: "Historical financial performance", number: 4 },
  { type: "sub", text: "Income statement summary (standalone, ₹cr unless noted)" },
  { type: "table", headers: ["Metric", "FY2021", "FY2022", "FY2023", "FY2024", "FY2025"], opts: { colAligns: ["left","center","center","center","center","center"] }, rows: [
    ["Revenue from operations", "8,955.8 [S100]", "14,214.6 [S301]", "14,254.9 [S300]", "13,149.1 [S400]", "16,787.6 [S500]"],
    ["Revenue growth YoY %", "N/A", "58.7", "0.3", "−7.8", "27.7"],
    ["Finance costs", "7.1 [S103]", "23.1 [S315]", "12.9 [S314]", "17.2 [S515]", "59.0 [S514]"],
    ["Other income", "146.6 [S101]", "264.1 [S303]", "235.6 [S302]", "250.7 [S503]", "357.0 [S502]"],
    ["PBT (standalone)", "1,316.5 [S107]", "3,954.9 [S200]", "1,955.0 [S330]", "2,712.1 [S400]", "7,135.1 [S500]"],
    ["PAT (standalone)", "1,299.4 [S107]", "2,952.0 [S200]", "1,544.5 [S338]", "1,988.5 [S400]", "5,324.7 [S538]"],
    ["PAT margin %", "14.5", "20.8", "10.8", "15.1", "31.7"],
    ["EPS diluted (₹, standalone)", "7.0 [S107]", "16.1 [S200]", "8.4 [S350]", "11.2 [S551]", "28.99 [S550]"],
  ]},
  { type: "text", opts: { italics: true, size: 17 }, text:
    "Note: FY2025 standalone PAT (₹5,324.67cr [S538]) differs from the consolidated PAT (₹5,267.94cr) used in the estimates base and Exhibit 4 of the final note — the two are on different bases and are not interchangeable; standalone EPS is 28.99 [S550] on both a basic and diluted basis. Standalone EBITDA is not separately disclosed pre-FY2024; company-reported consolidated EBITDA is preferred in deliverables per reported-over-computed precedence (FY2025 ₹7,922cr)." },
  { type: "sub", text: "Balance sheet & cash flow highlights (standalone)" },
  { type: "table", headers: ["Metric", "FY2021", "FY2022", "FY2023", "FY2024", "FY2025"], opts: { colAligns: ["left","center","center","center","center","center"] }, rows: [
    ["Total assets (₹cr)", "14,710.6 [S108]", "17,488.8 [S397]", "17,738.7 [S396]", "19,418.6 [S595]", "23,122.5 [S594]"],
    ["Inventories (₹cr)", "1,476.3 [S110]", "1,645.6 [S375]", "1,840.2 [S374]", "1,831.3 [S575]", "1,908.8 [S574]"],
    ["Net PPE (₹cr)", "7,317.3", "7,001.9", "6,916.4", "7,020.2", "6,799.0"],
    ["CWIP (₹cr)", "1,431.1", "1,763.4", "2,744.9", "3,961.5", "4,934.7"],
    ["CFO (₹cr)", "2,199.4", "4,049.6 [S3454]", "908.2 [S3453]", "2,727.1", "5,806.1"],
    ["Receivable days", "N/A", "1.9", "2.3", "4.3", "4.1"],
    ["ROE % (cons. from FY24)", "N/A", "25.4", "12.0", "13.8", "32.7"],
  ]},
  { type: "text", opts: { size: 19 }, text:
    "The FY2025 margin move (why-why): standalone EBITDA rose ₹3,278.8cr→₹7,487.1cr [F-DER-FUN-01/02], margin 24.9%→44.6% (+1,966 bps) [F-DER-FUN-03/04] — revenue +27.7% while total expenses fell 11,043.1→10,009.5 (employee cost 2,034.7→1,786.5); operationally both price and volume; structurally a price-taker with near-zero hedging, so FY2025's ~45% margin is a cyclical LME/realization tailwind, directly reversible — Q4 FY2026 PAT −17.4% YoY already shows the reversal. CWIP/net-PPE nearly quadrupled 19.6%→72.6% [F-DER-FUN-05/06]: a build phase, not a harvest phase; three-year incremental ROCE cannot be computed pre-DPR (OQ-FUND-03). DSO rose 1.93→4.26 days on a ~1.1%-of-sales base — tripped RF-002/003, dismissed on materiality (F-FUND-06)." },

  { type: "heading", text: "Management & governance", number: 5 },
  { type: "text", opts: { italics: true, size: 18 }, text:
    "Governance verdict: Amber (composite 73.3/100, provisional on the legal/regulatory sub-score), downgraded from Green this cycle. The rating is not stated in this document." },
  { type: "sub", text: "Leadership" },
  { type: "table", headers: ["Name", "Role", "Since", "Prior / notable"], opts: { colAligns: ["left","left","center","left"], colWeights: [1.4,1.4,1.1,2.2] }, rows: [
    ["Brijendra Pratap Singh", "Chairman-cum-Managing Director", "Charge 8-Jan-2025 (PESB 17-Sep-2024)", "35+ yrs SAIL (ex Director-in-Charge, Burnpur/Durgapur); primary spokesperson on all 4 FY26 calls"],
    ["Abhay Kumar Behuria", "Director (Finance)", "11-Jun-2025", "ED Finance, Rourkela Steel Plant (SAIL)"],
    ["Jagdish Arora", "Director (Production & Technical)", "Not extracted", "Handled operational/technical Q&A, Q2 FY26"],
    ["Anil Kumar Singh", "Director (Commercial)", "7-Jan-2026", "Ex-Hindustan Copper / RINL"],
    ["Pankaj Kumar Sharma", "Director (Production)", "1-Feb-2023", "Ex-NMDC"],
    ["Three independent directors", "Independent", "Ceased 31-Mar-2026, not replaced [F-EXT-1155]", "Cessation triggered the LODR breach below"],
  ]},
  { type: "sub", text: "Governance composite (weighted)" },
  { type: "table", headers: ["Component", "Weight", "Score", "Note"], opts: { colAligns: ["left","center","center","left"], colWeights: [1.1,0.6,0.7,2.6] }, rows: [
    ["Accounting", "35%", "90", "Unqualified opinions FY2021–FY2025; CAG “Nil” FY2024/FY2025 [F-AUD-04/25]; held below high-90s only for a payroll audit-trail control gap [F-AUD-26]"],
    ["Governance", "30%", "58", "Downgraded from 80 on the fined LODR breach (F-EXT-1155) + open CBI probe (F-EXT-1156)"],
    ["Legal / regulatory", "20%", "62 (prov.)", "Downgraded from 70; SEBI/NCLT/NCLAT docket sweep unresolved (portals not indexable) — “unverified-clean, disclosed gap”"],
    ["Concall behaviour", "15%", "80", "2 evasive-candidate records of ~350+ across 4 calls; both self-flagged uncertainty on mine-lease dates, not refusal"],
  ]},
  { type: "text", opts: { italics: true, size: 18 }, text: "Weighted: 0.35×90 + 0.30×58 + 0.20×62 + 0.15×80 = 73.3." },
  { type: "sub", text: "Guidance ledger + credibility" },
  { type: "table", headers: ["Metric family", "One-line history", "Credibility"], opts: { colAligns: ["left","left","center"], colWeights: [1.3,2.6,1], colorizeCol: 2 }, rows: [
    ["Alumina volume production/sales", "Beat 3/3 verifiable full-year guides (FY26 14.46 lakh t vs successive guides), though the guide moved down mid-year first", "Medium"],
    ["Metal volume production", "Met 1/1 almost exactly (470K guided vs 471K actual, <0.3%)", "High"],
    ["5th-stream refinery commissioning timeline", "One material slip (implied Sept-2025 → June-2026), then held 3 quarters", "Low"],
    ["5th-stream FY26 volume contribution", "Cut ~40% in-year (500KT→300KT), then deferred to FY27 (200KT)", "Low"],
    ["0.5 MTPA smelter capex & timeline", "Date stated Aug-2030 / Dec-2030 / Jun-2031 (self-contradictory Q4 PPT); capex ₹30,000cr → ₹23,000–24,000cr", "Low"],
    ["Pottangi bauxite commissioning", "Transcript-vs-PPT date mismatch same quarter; MDO awarded Dilip Buildcon Dec-2025", "Low"],
    ["FY capex total", "FY26 ₹1,700cr guided vs ~₹2,000–2,100cr actual (+18–24%)", "Medium"],
    ["Alumina price realization", "Ratcheted down each quarter ($400–450→$320–340→$310–320)", "Low"],
    ["Aluminium LME price", "Q4 guide missed low; CY2026 guide swung +17% in one quarter", "Low"],
    ["Coal captive production", "4 MTpa held all 4 quarters, delivered (+41.84% YoY)", "Medium-High"],
  ]},
  { type: "text", opts: { size: 19 }, text:
    "Guidance families most relevant to FY27–28 estimates (5th-stream volume, price) are precisely the lowest-credibility families. The cost-efficiency and metal-volume families are the cleanest." },
  { type: "sub", text: "Direct-quotes bank (claims vs reality; attributed by role)" },
  { type: "bullets", items: [
    "CMD, Q4 FY26 call [QT-Q4-001]: best-ever physical performance across bauxite, alumina and metal production. Reality: accurate at the volume level, but glosses the sharply negative Q4 YoY profit trend (revenue −4.8%, PAT −17.4% [S693]) — headline narrative and quarterly cadence diverge (F-FUND-10).",
    "Management, Q3 FY26 call [GD-Q3-037]: the 5th-stream FY26 contribution reset to “a more realistic 3 lakh KT.” Reality: a company-labelled ~40% in-year revision on the single largest near-term growth lever (RF-GUI-01).",
    "CMD, Q2 FY26 call [QT-Q2-041], on bauxite mine-lease renewal dates: self-flagged uncertainty (“we will have to check up the data”) — routed as OQ-DR1-1, treated as transparency-positive rather than evasive.",
  ]},
  { type: "text", opts: { size: 19 }, text:
    "Forensic scorecard (weighted, standalone FY2021–FY2025): composite 75/100. Components: cash_conversion 62, accrual_ratio_trend 78, one_off_frequency 92, provisioning_adequacy 72, audit_cleanliness 92, disclosure_quality 68 (weights 25/20/15/15/15/10) — above-median for an Indian commodity CPSE." },
  { type: "sub", text: "Governance chronology" },
  { type: "table", headers: ["Date", "Event"], opts: { colAligns: ["left","left"], colWeights: [1,3.2] }, rows: [
    ["FY2021", "Unqualified opinion; buyback 2.9cr shares ₹170.12cr; contingent liabilities ₹2,153.48cr"],
    ["FY2022", "Unqualified; dividend payout 37.33%; contingent liabilities ₹2,378.4cr"],
    ["FY2023", "Unqualified; other income 25.9% of CFO (RF-001); DSO +21% (RF-002)"],
    ["FY2024", "Unqualified (A.K. Sabat & Co. / P.A. & Associates); CAG “Nil”; contingent liabilities ₹1,920.03cr; DSO +82% (RF-003)"],
    ["FY2025 (AR 02-Sep-2025)", "Unqualified (B M Chatrath & Co. LLP / SRB & Associates); CAG “Nil”; contingent liabilities ₹2,050.43cr; dividend to GoI ₹941.80cr; payroll audit-trail feature not enabled"],
    ["2026-02-27", "BSE & NSE each fine NALCO ₹5,42,800 (total ₹10,85,600 incl. 18% GST) for LODR Reg. 17(1) breach, quarter ended 31-Dec-2025 [F-EXT-1155]"],
    ["2026-03-17", "NALCO requests fine waiver, citing GoI's exclusive control over ID appointments; outcome not yet reported"],
    ["2026-03-31", "Three IDs cease on tenure expiry, not replaced — degrades board + Audit/NRC/Stakeholders committees"],
    ["2026", "CBI opens a recruitment-fraud probe at the Haradghana site (~20 people allegedly given jobs without advertisement); NALCO disputes the “raid” framing [F-EXT-1156]"],
  ]},
  { type: "text", opts: { size: 19 }, text:
    "Shareholding: promoter (President of India / Ministry of Mines) 51.28%, unchanged vs Dec-2025, no encumbrance [S1450] — pledge concept does not apply to a sovereign promoter. Related-party trade is structurally CPSE-to-CPSE under a common owner: FY2025 CPSE purchases ₹3,264.17cr (19.4% of revenue), CPSE sales ₹2,436.35cr (14.5%), dividend to GoI ₹941.80cr [F-GOV-01/02]. The 51.28% holding leaves OFS headroom above the 51% control floor; no OFS/DIPAM target found — a structural overhang to monitor, not a red flag." },

  { type: "heading", text: "Earnings quality & red-flag ledger", number: 6 },
  { type: "text", opts: { size: 19 }, text:
    "All 23 adjudicated entries: 2 confirmed, 7 disclosed, 14 dismissed, 0 candidate. Dismissed flags stay visible with their dismissal reasons for auditability. The two confirmed flags below are both guidance-credibility issues (RF-GUI-01/02), not accounting-integrity issues — no section-4 manipulation screen confirms gross-up, cash-flow reclassification, capitalization anomaly, or RPT round-tripping." },
  { type: "sub", text: "Confirmed and disclosed flags (9 of 23) — rendered individually" },
  { type: "table", headers: ["ID", "Status", "Sev.", "Why-chain (compressed)"], opts: { colAligns: ["left","center","center","left"], colWeights: [1,1,0.7,3], colorizeCol: 1 }, rows: [
    ["RF-GUI-01", "Confirmed", "Medium", "5th-stream FY26 volume cut ~40% in-year (500KT→300KT), then deferred to FY27 — no reconciling explanation"],
    ["RF-GUI-02", "Confirmed", "Low", "Alumina contract-mix target stated three ways in one FY (80/20 spot → 50/50 → spot-only); Q2 quote extraction-tagged evasive"],
    ["RF-001", "Disclosed", "Medium", "Other income 25.9% of CFO FY2023 — CFO collapsed −77.6% (4,049.6→908.2cr) in the commodity trough while other income stayed flat; specific WC leg unconfirmed (FQ-NALCO-01)"],
    ["RF-MERGE-02", "Disclosed", "Medium", "Other income FY2022 −11.2% (297.4→264.1) between AR comparatives — largest relative P&L delta, no captured footnote (FQ-NALCO-02)"],
    ["RF-MERGE-08", "Disclosed", "Medium", "Total assets FY2022 +1.22% (₹211.04cr) between AR comparatives — matched by identical liabilities move; no footnote (FQ-NALCO-02)"],
    ["RF-MERGE-09", "Disclosed", "Medium", "Total liabilities FY2022 +4.47% (₹211.04cr) — same balance-sheet-identity-preserving reclassification as RF-MERGE-08"],
    ["RF-MERGE-12", "Disclosed", "Medium", "Total assets FY2022 consolidated +1.22% (₹211.04cr) — the same regrouping flows through consolidation (FQ-NALCO-02)"],
    ["RF-GUI-03", "Disclosed", "Low", "0.5 MT smelter commissioning date inconsistent across/within docs (Aug-2030 / Dec-2030 / Jun-2031) — documentation hygiene, pre-DPR"],
    ["RF-GUI-04", "Disclosed", "Low", "Pottangi date mismatch same-quarter (June call vs May PPT) — a one-month transcription slip (OQ-GUI-02)"],
  ]},
  { type: "sub", text: "Dismissed, low-severity (14 of 23) — condensed" },
  { type: "text", opts: { size: 19 }, text:
    "The 14 dismissed entries are condensed here rather than listed row-by-row (each stays in the source ledger with its dismissal reason). RF-002/RF-003: DSO rose 1.93→2.34→4.26 days across FY2023–FY2024 (+21%, then +82%) — percentage noise on a sub-week base with no channel-stuffing signature (inventory rose too); stabilized at 4.05 days by FY2025. RF-MERGE-01, 03–07, 10–11, 13–16 (12 entries): routine AR-to-AR comparative regroupings and PPT-vs-AR rounding deltas, each under ~1.1% and each resolved by taking the latest/audited figure — individually immaterial (rounding on revenue, total income, finance costs, other/total expenses, inventories, segment revenue; and the ~1% PPT-vs-AR gap on FY2025 PBT/PAT, a known and disclosed precedent for FY2026's PPT-sourced figures)." },
  { type: "text", opts: { size: 19 }, text:
    "Composite interpretation: principal soft spots are the unexplained FY2023 CFO/working-capital swing (RF-001) and four comparative-period deltas above 1% without footnote traceability (RF-MERGE-02/08/09/12). Capitalization and RPT screens (F-FOR-06) return no-data rather than a clean pass — an extraction-scope gap, disclosed, not a negative finding." },

  { type: "heading", text: "Valuation & peers", number: 7 },
  { type: "sub", text: "Historical P/E band (standalone EPS, 5y + FY2026 cross-check)" },
  { type: "table", headers: ["FY", "Avg price", "End price", "EPS", "P/E on avg", "P/E on end", "Src"], opts: { colAligns: ["left","center","center","center","center","center","center"] }, rows: [
    ["FY2021", "28.67", "42.32", "6.97", "4.11", "6.07", "S1300"],
    ["FY2022", "74.16", "100.92", "16.07", "4.61", "6.28", "S1301"],
    ["FY2023", "68.98", "69.13", "8.41", "8.20", "8.22", "S1302"],
    ["FY2024", "93.75", "139.07", "11.22", "8.36", "12.39", "S1303"],
    ["FY2025", "183.26", "167.94", "28.99", "6.32", "5.79", "S1304"],
    ["FY2026 (cross-check)", "239.99", "384.19", "31.67", "7.58", "12.13", "S1305"],
    ["CMP 361.65 vs FY2025 EPS", "—", "—", "28.99", "12.47", "—", "S1306"],
    ["CMP 361.65 vs FY2026 EPS", "—", "—", "31.67", "11.42", "—", "S1307"],
  ]},
  { type: "text", opts: { italics: true, size: 17 }, text:
    "Footnote: this dossier's own five-year P/E-on-average-price band is 4.1x–8.4x, median ~6.3x, on the strictly-audited FY2021–FY2025 window. The 7.6x median (band 4.6x–8.7x) cited in the final note's estimates section and the buy-side note is the pe_bands set, which rolls the FY2026 unaudited cross-check year (P/E-on-avg 7.58x) forward. Both are reproduced from source and differ by window, not by error." },
  { type: "text", opts: { size: 19 }, text:
    "The band's own extremes are cycle artifacts, not re-ratings: FY2021's 4.1x is a COVID-trough EPS against a forward-looking price; FY2024's 8.36x is a depressed EPS against a price already re-rating on the anticipated FY2025 recovery; FY2025's drop to 6.32x despite EPS quadrupling shows the market discounting the ~45% margin as unsustainable in real time. The subsequent 12.5x/11.4x at CMP is therefore a genuine expansion beyond anything in the last five years. EV/EBITDA: ~7.8x (FY2024) → ~3.9x (FY2025 end) → 7.7–8.4x at CMP [S1308–S1312]. P/B: 0.73x (FY2021) → 1.78x (band high) → 3.73x at CMP [S1313–S1317] — more than double the five-year band high." },
  { type: "sub", text: "Peer comparison (domestic multiples not located — margin proxies only)" },
  { type: "table", headers: ["Peer", "Scale / margin", "Multiple", "Delta vs NALCO"], opts: { colAligns: ["left","left","center","left"], colWeights: [1.1,1.8,0.9,2] }, rows: [
    ["Hindalco (consol., incl. Novelis)", "₹275,000cr rev; India-upstream EBITDA/t $1,572, 45.56% margin", "Not pulled", "No operating-quality edge for NALCO over Hindalco's comparable segment [F-VAL-06]"],
    ["Vedanta Aluminium", "2.88 MTpa capacity, 2.46mt produced FY26; CoP $1,752/t → target $1,550–1,600/t", "Not pulled", "~6x NALCO's metal scale; common-basis premium/discount not scoreable"],
    ["Alcoa", "Rev $3.2bn, adj. EBITDA $595mn Q1 CY2026", "Fwd P/E 10.04x, EV/EBITDA 8.33x", "NALCO trades at essentially no discount to a larger, longer-track-record peer despite concentrated single-country risk — unexplained parity [F-VAL-07]"],
  ]},
  { type: "text", opts: { size: 19 }, text:
    "Premium/discount analysis: at CMP and FY2025 EPS, the stock trades at ~2x the five-year average P/E (~6.3x). To re-justify the price at that average multiple, FY2027+ EPS would need to roughly double the FY2025 print (~EPS 57–58) — unsupported by any fact in the pack. Reverse read (S1319): CMP prices in either a sustained ~2x EPS step-up versus a peak-cycle base, or a permanent multiple re-rating. Peer-valuation checked explicitly for a re-rating catalyst (credit-rating upgrade, index inclusion, DPR-approved capacity) and found none (F-VAL-05). The near-debt-free balance sheet is real and supportive but is a pre-existing multi-year condition (F-FUND-07, F-VAL-09) that does not explain a re-rating specifically over the last 12–18 months." },
  { type: "text", opts: { size: 19 }, text:
    "Weighted business-quality score: 6.05/10 [S1323] — industry structure 4, cost position 7, balance sheet 9, moat 4.3, earnings quality 7.5, governance 7.3, valuation 2. Ex-valuation the business would score ~6.9/10: it is valuation, not operations, that is the standout outlier." },

  { type: "heading", text: "Estimates (full build)", number: 8 },
  { type: "text", opts: { size: 19 }, text: "Basis: consolidated (FY2026 base is company-summarised PPT). FY2025A PAT/EPS here are consolidated — 5,267.94cr / 28.68 — distinct from the standalone FY2025 figures in §4.1." },
  { type: "table", headers: ["Metric", "FY2025A", "FY2026A (PPT)", "FY2027E (base)", "FY2028E (base)"], opts: { colAligns: ["left","center","center","center","center"] }, rows: [
    ["Revenue (₹cr)", "16,787.6 [S500]", "17,843.0 [F-PQ4-001]", "19,399.4 [S1384]", "19,156.4 [S1385]"],
    ["Revenue growth %", "27.7", "6.3", "8.7", "−1.3"],
    ["EBITDA (₹cr)", "7,922 [F-PQ4-018]", "8,613 [F-PQ4-018]", "8,632.7 [S1386]", "8,237.2 [S1387]"],
    ["EBITDA margin %", "47.2", "48.3", "44.5", "43.0"],
    ["PAT (₹cr, cons)", "5,267.9 [F-AR25B-013]", "5,815.8 [F-PQ4-029]", "6,015.9 [S1388]", "5,702.8 [S1389]"],
    ["EPS diluted (₹, cons)", "28.68", "31.67", "32.76 [S1390]", "31.05 [S1391]"],
    ["Capex (₹cr)", "1,175.6", "N/A (AR pending)", "2,280.0", "2,250.0"],
    ["P/E @ CMP (x)", "—", "11.42", "11.04 [S1396]", "11.65 [S1397]"],
  ]},
  { type: "text", opts: { size: 19 }, text: "Base-case 2yr EPS CAGR FY26→FY28E = −0.98% (F-EST-01). Revenue essentially flat FY27E→FY28E as external price normalization (metal/alumina −3.23% vs FY27E, World-Bank-anchored) outweighs volume/ramp gains — a sequential decline, not a modeling error (EST-002)." },
  { type: "sub", text: "Assumption ledger (the ones that matter)" },
  { type: "bullets", items: [
    "Segment split ~73% metal / ~27% alumina (F-FUND-02/08).",
    "5th-stream incremental alumina volume probability-weighted 0.40 (FY27E) / 0.55 (FY28E), not nameplate — the single largest swing factor, reflecting low guidance credibility (A-1352, F-EST-02).",
    "Price paths anchored to World Bank / Platts, not management guidance (A-1350/1355/1356).",
    "EBITDA margin faded from FY26's 48.3% to 44.5%/43.0%, within the 5-year band (24.9%–48.3%) — Gate 3 PASS.",
    "Normalized ETR ~25.1–25.6% (3y median); no dilution. Capex-overrun pattern (~20% historical, F-FUND-04) built as an upward bias to capex/D&A/finance cost (F-EST-04).",
  ]},
  { type: "sub", text: "Scenarios (seeds for the downstream PT engine — not price targets)" },
  { type: "table", headers: ["Scenario", "FY27E EPS", "FY28E EPS", "2yr EPS CAGR", "Rationale"], opts: { colAligns: ["left","center","center","center","left"], colWeights: [0.8,0.8,0.8,1,2.8] }, rows: [
    ["Base", "32.76 [S1390]", "31.05 [S1391]", "−0.98%", "Probability-weighted 5th-stream; World Bank/Platts price normalization"],
    ["Bull", "38.11 [S1392]", "42.42 [S1393]", "+15.74%", "5th-stream at 100% nameplate; metal $3,200/t, alumina $340/t; margin 48–49%"],
    ["Bear", "24.04 [S1394]", "21.26 [S1395]", "−18.05%", "Zero incremental 5th-stream/Pottangi; metal ~$2,400/t, alumina $260–280/t; margin 37–39%; finance cost +30–50%"],
  ]},
  { type: "text", opts: { size: 19 }, text:
    "A naive 100%-guidance-flow-through model would sit near the bull case (+15.7%); the base case sits at −0.98% because low-credibility guidance is not allowed to become the base case (F-EST-03). Management's own FY27 price guidance is broadly in line with independent anchors — the divergence is on volume (the 5th-stream ramp), not price." },

  { type: "heading", text: "Future outlook, risk factors & concluding synthesis", number: 9 },
  { type: "sub", text: "Catalyst calendar" },
  { type: "table", headers: ["Date / trigger", "Event"], opts: { colAligns: ["left","left"], colWeights: [1.1,2.9] }, rows: [
    ["~Aug-2026 (Q1 FY27 call)", "First confirmation of whether the 5th-stream refinery commissioned within one quarter of the June-2026 guide (OQ-GUI-03)"],
    ["Aug–Sept 2026", "0.5 MT smelter DPR targeted (OQ-FUND-03 becomes answerable)"],
    ["On publication", "FY2026 audited AR — confirms/disputes the Q4 PPT full-year figures used throughout (~1% PPT-vs-AR precedent)"],
    ["Pending", "BSE/NSE ID-composition fine waiver outcome; board restoration to LODR-compliant composition"],
    ["Pending", "CBI recruitment-fraud probe resolution"],
  ]},
  { type: "sub", text: "Risk factors" },
  { type: "table", headers: ["Risk", "Type", "Prob. × Impact"], opts: { colAligns: ["left","center","center"], colWeights: [2.6,1,1] }, rows: [
    ["Valuation reversion toward the 5y band", "Financial / market", "High × High"],
    ["5th-stream slips again / ramps below weight", "Operational", "Medium-High × High"],
    ["Governance — LODR breach + CBI probe unresolved", "Governance", "Medium × Medium"],
    ["Alumina structural oversupply (Indonesia)", "Industry", "High × Medium"],
    ["Commodity price cycle turns down", "Financial", "Medium × High"],
    ["Capex overrun continues / debt-funds the smelter", "Financial", "Medium × Medium"],
    ["CBAM / EU export exposure", "Industry / policy", "Low-Medium × Medium (unsized)"],
    ["FY2026 figures unaudited (PPT-sourced)", "Data quality", "Medium × Low-Medium"],
  ]},
  { type: "text", text:
    "Strengths: a clean, near-debt-free balance sheet; a genuine and widening cost-structure moat (the cleanest-delivered lever in the guidance ledger); above-median earnings quality with five straight unqualified audits and CAG “Nil” comments; the best delivery record on the levers management actually controls (metal volume, cost efficiency)." },
  { type: "text", text:
    "Vulnerabilities: no pricing power (buyer power 7/10, near-zero switching costs, no hedging); a cost-structure moat that supports margins in a downturn but does not drive earnings growth or justify multiple expansion; two live overhangs — a fined governance-compliance breach and a repeatedly cut/deferred timeline on the single largest near-term growth lever; and, most acutely, a price that has run to roughly twice the multiple the stock has ever earned in its own five-year history against a base-case earnings path that is flat-to-down." },
  { type: "callout", title: "Concluding synthesis", color: GOLD, text:
    "NALCO is a well-built ship with a sound hull and cheap fuel, sailing a sea whose swells it cannot control — the current price is set as if the sea had been tamed, when the evidence says only the hull has been strengthened." },

  { type: "heading", text: "Open questions & gaps register (high-severity, condensed)", number: 14 },
  { type: "table", headers: ["ID", "Question", "Severity", "Status"], opts: { colAligns: ["left","left","center","center"], colWeights: [1,2.4,0.7,1.1], colorizeCol: 3 }, rows: [
    ["OQ-FUND-03", "0.5 MT smelter incremental ROCE/payback?", "High", "Open"],
    ["OQ-GUI-03", "5th-stream commissioned June-2026, or slipped again?", "High", "Open"],
    ["OQ-GOV-01", "SEBI/ED/SFIO/CBI/NCLT/IBBI/MCA registry sweep?", "High", "Open"],
    ["OQ-GOV-02", "CAG Sec 143(6) FY2021–FY2025?", "High", "Answered (partial)"],
    ["OQ-GOV-03", "FY2024/FY2025 auditor opinion + contingent liabilities?", "High", "Answered"],
    ["OQ-GOV-05", "Board / independent-director composition?", "Medium", "Answered (adverse)"],
    ["OQ-FUND-01", "FY2026 audited AR vs Q4 PPT figures?", "Medium", "Open"],
  ]},
  { type: "text", opts: { italics: true, size: 18 }, text:
    "Full register: ~22 entries spanning fundamentals, guidance and governance; three high-severity items (OQ-FUND-03, OQ-GUI-03, OQ-GOV-01) remain open, OQ-FUND-07 and OQ-GUI-01 were answered by DR2. None are treated as blocking — each is a disclosed gap with a stated resolution trigger." },

  { type: "spacer", h: 100 },
  { type: "callout", title: "Disclaimer", color: NAVY, text:
    "This report is for educational analysis only and is not investment advice or a research report under SEBI (Research Analysts) Regulations, 2014. It has not been prepared by a SEBI-registered Research Analyst. Treat it as business analysis, not investment research. Always do your own due diligence before investing." },
  { type: "callout", title: "AI disclosure", color: GOLD, text:
    "Artificial intelligence was used to prepare substantially all of the analysis in this report (in line with the disclosure expectation SEBI introduced for AI use in research preparation). AI systems can make mistakes: figures are extracted and cross-verified against cited source pages, but errors may remain. Every number carries a source reference — verify load-bearing figures against the cited page before relying on them." },
  { type: "text", opts: { italics: true, size: 17 }, text:
    "Validity: prepared on 2026-07-16 (the later of: dates in supplied research documents; run date). Company information changes with news flow and results; treat the analysis as decaying in reliability beyond ~12 months, and the market data as of its pull timestamp only. Sources: company documents supplied by the user (annual reports, quarterly filings, transcripts, presentations); exchange/regulator websites; market data via yfinance (timestamped); external research as cited with URL and access date. The preparer holds no position information and expresses no view on suitability for any investor. Full source registry (946+ entries, page-level for every Annual Report line item) is retained in the source markdown (§13) and omitted here for length." },
];

module.exports = { masthead, title, blocks, footer: "NALCO — Forensic Dossier (Internal)", outfile: "NALCO_Forensic.docx" };
