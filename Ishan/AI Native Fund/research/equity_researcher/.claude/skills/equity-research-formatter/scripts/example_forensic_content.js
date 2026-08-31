const { NAVY, GOLD, GREEN, AMBER, RED } = require("./reportStyle.js");

const masthead = ["Research Dossier", "Full Audit Document \u2014 Internal Use Only"];
const title = [
  "National Aluminium Company Limited",
  "NSE: NATIONALUM  |  Metals & Mining \u2014 Aluminium  |  India  |  Run date 2026-07-16",
  "Forensic Research Dossier (Full Audit Record)",
];

const blocks = [
  { type: "callout", title: "No recommendation in this document", color: NAVY, text:
    "This dossier is the long-form audit record. Every number carries a source reference mapping to the source registry. Tables are rendered from fact records, not retyped. The rating does NOT appear in this document \u2014 it lives only in the sell-side note's rating box. Basis: standalone primary (consolidated vs. standalone diverge <0.3% every year; JV/subsidiary carrying value ~2% of balance sheet)." },

  { type: "heading", text: "Input manifest & run record", number: 0 },
  { type: "text", text:
    "Inputs: 13 documents \u2014 5 audited Annual Reports (FY2021\u2013FY2025) plus 4 FY2026 quarterly earnings-call transcripts and 4 quarterly presentations. Declared intake gaps: no standalone FY2026 quarterly financials (taken from presentations, treated as company-summarised until the FY2026 AR publishes); FY2026 audited AR not yet published; no transcripts pre-FY2026 (pre-FY2026 management signalling is limited to AR MD&A)." },
  { type: "text", size: 19, text:
    "Pipeline: INTAKE \u2192 CONVERT \u2192 TRIAGE (sector pack: commodities/metals-mining) \u2192 parallel EXTRACT \u2192 COMPUTE (ratio/statement/EPS-bridge builders) \u2192 parallel ANALYZE (fundamental / forensic / guidance / governance) \u2192 RESEARCH (company + sector/peer deep-research waves) \u2192 LOOP (external facts marked governance stale; governance module re-run, downgraded Green\u2192Amber) \u2192 SYNTHESIZE (peer-valuation + estimates \u2192 thesis) \u2192 VERIFY \u2192 RENDER. Convergence: all 23 red-flag ledger entries adjudicated (2 confirmed, 7 disclosed, 14 dismissed, 0 candidate); 3 high-severity open questions remain unanswered and are carried as disclosed gaps rather than blocking." },

  { type: "heading", text: "Executive summary", number: 1 },
  { type: "text", text:
    "NALCO is an operationally sound, input-cost-advantaged, near-debt-free integrated aluminium producer whose earnings are an unsmoothed, leveraged function of two spot-linked commodity prices (LME aluminium and alumina). The FY2025 profit surge was a cyclical realization peak, not a structural efficiency step-up; FY2026 already shows the reversal beginning at the exit quarter (Q4 FY2026 PAT \u221217.4% YoY). The base-case earnings path through FY2028E is roughly flat-to-down. Set against this, the market price sits materially above every multiple the stock has traded at in its own five-year history, with no confirmed re-rating catalyst identified. Two governance/execution overhangs are live: a fined SEBI LODR board-composition breach and a repeatedly cut/deferred commissioning timeline on the single largest near-term capacity lever." },
  { type: "text", text:
    "Core financial health: the balance sheet is a genuine strength \u2014 near-zero leverage (standalone D/E 0.0016x, FY2022), interest coverage 152x\u2013172x in FY2022\u2013FY2023, captive bauxite and a captive-coal ramp toward ~4 MTpa. Earnings quality is above-median for an Indian commodity CPSE (forensic composite 75/100): unqualified audits five straight years, CAG supplementary comment \u201cNil\u201d in both covered years, a single non-recurring exceptional item (FY2024). Cash conversion is volatile but tracks the commodity cycle rather than manipulation." },
  { type: "text", text:
    "Valuation synopsis: CMP \u20b9361.65 (2026-07-15) is 12.5x FY2025 EPS and ~11.4x the FY2026 cross-check EPS, against a five-year PE-on-average-price band of 4.1x\u20138.4x (median ~6.3x) that never reached double digits even in the FY2025 cyclical-peak year. P/B at CMP is 3.73x versus a five-year band high of 1.78x. Base-case forward P/E is 11.0x (FY27E) / 11.7x (FY28E) \u2014 still above the historical band on forward earnings." },
  { type: "sub", text: "Top four principal risks" },
  { type: "bullets", items: [
    "Valuation reversion \u2014 CMP prices in either a ~2x sustained EPS step-up versus a peak-cycle base, or an unevidenced permanent re-rating.",
    "Execution/guidance credibility on the 5th-stream refinery \u2014 the FY26 volume contribution was cut ~40% in-year then deferred to FY27; commissioning remains unconfirmed as of Jul-2026.",
    "Governance \u2014 a fined, disclosed SEBI LODR independent-director-composition breach (\u20b910.86 lakh, waiver pending) plus an open CBI recruitment-fraud probe.",
    "Commodity price cycle \u2014 structural alumina oversupply (Indonesian ramp) with management guiding no near-term recovery.",
  ]},

  { type: "heading", text: "Industry & market analysis", number: 2 },
  { type: "text", size: 19, text:
    "The aluminium value chain runs bauxite \u2192 alumina \u2192 primary aluminium (LME-priced) \u2192 semis/downstream. NALCO is fully integrated across the first three stages with captive power but has effectively no downstream/specialty business. The structural bottleneck is the alumina-to-LME price premium, which compressed from 15\u201317% to 11\u201311.5% as Indonesian refinery capacity ramped toward 7 MTpa by CY2026 \u2014 the confirmed driver behind the FY2026 alumina realization collapse (US$580\u2192US$370, FY25\u2192FY26)." },
  { type: "sub", text: "Porter's five forces (0\u201310; higher = more pressure on NALCO)" },
  { type: "table", headers: ["Force", "Score", "Trajectory"], opts: { colAligns: ["left","center","left"], colWeights: [2.4,0.7,1.6] }, rows: [
    ["Threat of new entrants", "6", "Worsening in alumina, CY2025\u20132027 (Indonesian ramp)"],
    ["Bargaining power of suppliers", "3", "Improving \u2014 captive bauxite/coal ~57% of fuel need"],
    ["Bargaining power of buyers", "7", "Structurally stable at a high level (spot/LME pricing, no long-term contracts)"],
    ["Threat of substitutes", "2", "Stable \u2014 no evidenced substitution threat"],
    ["Competitive rivalry", "6", "Intensifying \u2014 Hindalco and Vedanta both expanding and cutting costs"],
  ]},
  { type: "text", size: 19, text:
    "Composite read: an industry structure that is moderately-to-highly unfavourable for pricing power (buyer power and rivalry dominant at 6\u20137/10), partially offset by input-cost self-sufficiency (supplier power and substitution both low at 2\u20133/10) \u2014 corroborating the independent finding that NALCO is a \u201ccommodity price taker with near-zero hedging.\u201d" },
  { type: "text", size: 19, text:
    "Demand: India aluminium demand ~6.27% CAGR CY2024\u20132030 (paid research, confidence low \u2014 no official-statistics source located). Price context (CY2027): World Bank US$3,000/t central; SMM US$2,900\u20133,200/t; Goldman bear US$2,400/t; LME spot already US$3,538/t on 28-Apr-2026. Policy: EU CBAM's definitive phase began 1-Jan-2026 (first certificate price \u20ac75.36/tCO\u2082e); Indian unwrought-aluminium exports to the EU fell 41.7% YoY \u2014 NALCO's own EU exposure was not sized in this pass, a disclosed gap. US Section 232 restructured 6-Apr-2026 (50% on wholly-metal articles); NALCO is not a significant direct US exporter." },

  { type: "heading", text: "Company deep-dive", number: 3 },
  { type: "text", size: 19, text:
    "NALCO is a Navratna CPSE (GoI 51.28% via the President of India / Ministry of Mines), fully integrated bauxite\u2013alumina\u2013aluminium with captive thermal, wind and rooftop-solar power. Two reportable segments \u2014 Chemicals (alumina) and Aluminium (metal) \u2014 inside one vertically integrated chain, so the segment split reflects relative price cycles as much as deliberate tonnage reallocation. FY2026 revenue mix shifted ~70/30 \u2192 73/27 (metal/alumina), framed by management as margin-supportive; the segment-EBIT picture is more nuanced \u2014 Aluminium's EBIT share was 61.2% (FY24) and 55.5% (FY25), i.e. Chemicals' EBIT share rose even as revenue mix moved toward metal. This tension is carried as an open question, not over-claimed as a clean margin driver." },
  { type: "text", size: 19, text:
    "Unit economics (FY2026): alumina cost of production \u20b920,000\u201322,000/t; metal cost of production \u20b9155,000\u2013160,000/t. Delivered cost levers: caustic soda consumption improved 121\u219299 kg/t (~\u20b9129cr savings); captive coal +41.84% YoY toward ~4 MT, displacing costlier e-auction coal and grid power; employee cost declining mechanically as ~250 high-paid retirements are replaced by lower-paid recruits." },
  { type: "sub", text: "Moat matrix (weighted, 0\u201310)" },
  { type: "table", headers: ["Dimension", "Score", "Weight", "Trajectory"], opts: { colAligns: ["left","center","center","left"], colWeights: [1.7,0.6,0.6,1.7] }, rows: [
    ["Scale", "4", "0.15", "Improving modestly, off a small base"],
    ["Brand", "1", "0.05", "N/A \u2014 bulk commodity, no premium"],
    ["Distribution", "3", "0.10", "Eroding on contract-stickiness"],
    ["Switching costs", "1", "0.10", "Stable-low \u2014 near-zero for LME-linked commodity"],
    ["Supply-chain integration", "7", "0.25", "Widening \u2014 captive bauxite, coal ramp to ~4 MTpa"],
    ["Regulatory / access barriers", "6", "0.20", "Stable-to-uncertain \u2014 scarce leases, but a lease-date discrepancy is open"],
    ["Specialty vs. bulk mix", "2", "0.15", "Potentially improving, not yet realized"],
  ]},
  { type: "text", size: 19, text:
    "Weighted moat composite = 4.3/10. The two dimensions where NALCO genuinely differentiates \u2014 supply-chain integration (7) and regulatory/access barriers (6) \u2014 are a cost-structure moat, which supports margin resilience in a downturn more than earnings growth or multiple expansion in an upturn. It is not a pricing-power moat. On margin comparability, NALCO's FY2025 EBITDA margin (44.6%) is closely in line with Hindalco's India-upstream 45.6% \u2014 no operating-quality edge over its largest domestic peer this cycle. NALCO's own \u201cworld's lowest-cost producer\u201d claim could not be re-verified against a current third-party ranking (most recent independently-citable instance is FY2019-vintage) \u2014 a moat-relevant gap, not a confirmed premium." },

  { type: "heading", text: "Historical financial performance", number: 4 },
  { type: "sub", text: "Income statement summary (standalone, \u20b9cr unless noted)" },
  { type: "table", headers: ["Metric", "FY21", "FY22", "FY23", "FY24", "FY25"], opts: { colAligns: ["left","center","center","center","center","center"] }, rows: [
    ["Revenue from operations", "8,955.8", "14,214.6", "14,254.9", "13,149.1", "16,787.6"],
    ["Revenue growth YoY %", "N/A", "58.7", "0.3", "\u22127.8", "27.7"],
    ["Finance costs", "7.1", "23.1", "12.9", "17.2", "59.0"],
    ["Other income", "146.6", "264.1", "235.6", "250.7", "357.0"],
    ["PBT (standalone)", "1,316.5", "3,954.9", "1,955.0", "2,712.1", "7,135.1"],
    ["PAT (standalone)", "1,299.4", "2,952.0", "1,544.5", "1,988.5", "5,324.7"],
    ["PAT margin %", "14.5", "20.8", "10.8", "15.1", "31.7"],
    ["EPS diluted (\u20b9, standalone)", "7.0", "16.1", "8.4", "11.2", "28.99"],
  ]},
  { type: "text", size: 17, opts: { italics: true, size: 17 }, text:
    "Note: FY2025 standalone PAT (\u20b95,324.67cr) differs from the consolidated PAT (\u20b95,267.94cr) used in the estimates base \u2014 the two are on different bases and are not interchangeable; standalone EPS is 28.99 on both a basic and diluted basis. EBITDA is not separately disclosed on a standalone basis pre-FY2024; company-reported consolidated EBITDA is preferred in deliverables per reported-over-computed precedence (FY2025 \u20b97,922cr)." },
  { type: "sub", text: "Balance sheet & cash flow highlights (standalone)" },
  { type: "table", headers: ["Metric", "FY21", "FY22", "FY23", "FY24", "FY25"], opts: { colAligns: ["left","center","center","center","center","center"] }, rows: [
    ["Total assets (\u20b9cr)", "14,710.6", "17,488.8", "17,738.7", "19,418.6", "23,122.5"],
    ["Inventories (\u20b9cr)", "1,476.3", "1,645.6", "1,840.2", "1,831.3", "1,908.8"],
    ["CWIP (\u20b9cr)", "1,431.1", "1,763.4", "2,744.9", "3,961.5", "4,934.7"],
    ["CFO (\u20b9cr)", "2,199.4", "4,049.6", "908.2", "2,727.1", "5,806.1"],
    ["Receivable days", "N/A", "1.9", "2.3", "4.3", "4.1"],
    ["ROE % (cons. from FY24)", "N/A", "25.4", "12.0", "13.8", "32.7"],
  ]},

  { type: "heading", text: "Management & governance", number: 5 },
  { type: "text", size: 18, opts: { italics: true, size: 18 }, text:
    "Governance verdict: Amber (composite 73.3/100, provisional on the legal/regulatory sub-score), downgraded from Green this cycle. The rating is not stated in this document." },
  { type: "sub", text: "Leadership" },
  { type: "table", headers: ["Role", "Since", "Prior"], opts: { colAligns: ["left","center","left"], colWeights: [1.7,1,2] }, rows: [
    ["Chairman-cum-Managing Director", "8-Jan-2025 (PESB-selected 17-Sep-2024)", "35+ yrs SAIL (ex Director-in-Charge, Burnpur/Durgapur); primary spokesperson on all 4 FY26 calls"],
    ["Director (Finance)", "11-Jun-2025", "ED Finance, Rourkela Steel Plant (SAIL)"],
    ["Director (Production & Technical)", "Not extracted", "Handled operational/technical Q&A, Q2 FY26"],
    ["Director (Commercial)", "7-Jan-2026", "Ex-Hindustan Copper / RINL"],
    ["Director (Production)", "1-Feb-2023", "Ex-NMDC"],
    ["Three independent directors", "Ceased 31-Mar-2026, not replaced", "Cessation triggered the LODR breach below"],
  ]},
  { type: "sub", text: "Governance composite (weighted)" },
  { type: "table", headers: ["Component", "Weight", "Score", "Note"], opts: { colAligns: ["left","center","center","left"], colWeights: [1.1,0.6,0.6,2.6] }, rows: [
    ["Accounting", "35%", "90", "Unqualified opinions FY2021\u2013FY2025; CAG \u201cNil\u201d FY2024/FY2025; held below high-90s only for a payroll audit-trail control gap"],
    ["Governance", "30%", "58", "Downgraded from 80 on the fined LODR breach + open CBI probe"],
    ["Legal / regulatory", "20%", "62 (provisional)", "Downgraded from 70; SEBI/NCLT/NCLAT docket sweep unresolved \u2014 \u201cunverified-clean, disclosed gap\u201d"],
    ["Concall behaviour", "15%", "80", "2 evasive-candidate records of ~350+ across 4 calls; both self-flagged uncertainty, not refusal"],
  ]},
  { type: "text", size: 18, opts: { italics: true, size: 18 }, text: "Weighted: 0.35\u00d790 + 0.30\u00d758 + 0.20\u00d762 + 0.15\u00d780 = 73.3." },
  { type: "sub", text: "Guidance ledger + credibility" },
  { type: "table", headers: ["Metric family", "One-line history", "Credibility"], opts: { colAligns: ["left","left","center"], colWeights: [1.3,2.6,1], colorizeCol: 2 }, rows: [
    ["Alumina volume production/sales", "Beat 3/3 verifiable full-year guides, though the guide moved down mid-year first", "Medium"],
    ["Metal volume production", "Met 1/1 almost exactly (470K guided vs 471K actual, <0.3%)", "High"],
    ["5th-stream refinery commissioning timeline", "One material slip (implied Sept-2025 \u2192 June-2026), then held 3 quarters", "Low"],
    ["5th-stream FY26 volume contribution", "Cut ~40% in-year (500KT\u2192300KT), then deferred to FY27 (200KT)", "Low"],
    ["0.5 MTPA smelter capex & timeline", "Date stated three ways across docs (self-contradictory Q4 PPT); capex \u20b930,000cr \u2192 \u20b923,000\u201324,000cr", "Low"],
    ["Pottangi bauxite commissioning", "Transcript-vs-PPT date mismatch same quarter; MDO awarded Dec-2025", "Low"],
    ["FY capex total", "FY26 \u20b91,700cr guided vs ~\u20b92,000\u20132,100cr actual (+18\u201324%)", "Medium"],
    ["Alumina price realization", "Ratcheted down each quarter ($400\u2013450\u2192$320\u2013340\u2192$310\u2013320)", "Low"],
    ["Aluminium LME price", "Q4 guide missed low; CY2026 guide swung +17% in one quarter", "Low"],
    ["Coal captive production", "4 MTpa held all 4 quarters, delivered (+41.84% YoY)", "Medium-High"],
  ]},
  { type: "text", size: 19, text:
    "Guidance families most relevant to FY27\u201328 estimates (5th-stream volume, price) are precisely the lowest-credibility families. The cost-efficiency and metal-volume families are the cleanest." },
  { type: "sub", text: "Claims vs. reality (concall record)" },
  { type: "bullets", items: [
    "CMD, Q4 FY26 call: best-ever physical performance across bauxite, alumina and metal production. Reality: accurate at the volume level, but glosses the sharply negative Q4 YoY profit trend (revenue \u22124.8%, PAT \u221217.4%) \u2014 headline narrative and quarterly cadence diverge.",
    "Management, Q3 FY26 call: the 5th-stream FY26 contribution reset to \u201ca more realistic 3 lakh KT.\u201d Reality: a company-labelled ~40% in-year revision on the single largest near-term growth lever.",
    "CMD, Q2 FY26 call, on bauxite mine lease renewal dates: self-flagged uncertainty (\u201cwe will have to check up the data\u201d) \u2014 routed as an open question, treated as transparency-positive rather than evasive.",
  ]},
  { type: "text", size: 19, text:
    "Forensic scorecard (weighted, standalone FY2021\u2013FY2025): composite 75/100. Components: cash conversion 62, accrual-ratio trend 78, one-off frequency 92, provisioning adequacy 72, audit cleanliness 92, disclosure quality 68 \u2014 above-median for an Indian commodity CPSE." },
  { type: "sub", text: "Governance chronology" },
  { type: "table", headers: ["Date", "Event"], opts: { colAligns: ["left","left"], colWeights: [1,3.2] }, rows: [
    ["FY2023", "Unqualified opinion; other income 25.9% of CFO (RF-001); DSO +21% (RF-002)"],
    ["FY2024", "Unqualified; CAG \u201cNil\u201d; contingent liabilities \u20b91,920.03cr; DSO +82% (RF-003)"],
    ["FY2025 (AR 2-Sep-2025)", "Unqualified; CAG \u201cNil\u201d; contingent liabilities \u20b92,050.43cr; dividend to GoI \u20b9941.80cr; payroll audit-trail feature not enabled"],
    ["2026-02-27", "BSE & NSE each fine NALCO \u20b95,42,800 (total \u20b910,85,600 incl. 18% GST) for LODR Reg. 17(1) breach, quarter ended 31-Dec-2025"],
    ["2026-03-17", "NALCO requests fine waiver, citing GoI's exclusive control over ID appointments; outcome not yet reported"],
    ["2026-03-31", "Three independent directors cease on tenure expiry, not replaced \u2014 degrades board and Audit/NRC/Stakeholders committees"],
    ["2026", "CBI opens a recruitment-fraud probe at the Haradghana site (~20 people allegedly given jobs without advertisement); NALCO disputes the \u201craid\u201d framing"],
  ]},
  { type: "text", size: 19, text:
    "Shareholding: promoter (President of India / Ministry of Mines) 51.28%, unchanged vs. Dec-2025, no encumbrance \u2014 pledge concept does not apply to a sovereign promoter. Related-party trade is structurally CPSE-to-CPSE under a common owner: FY2025 CPSE purchases \u20b93,264.17cr (19.4% of revenue), CPSE sales \u20b92,436.35cr (14.5%), dividend to GoI \u20b9941.80cr. The 51.28% holding leaves OFS headroom above the 51% control floor; no OFS/DIPAM target was found \u2014 a structural overhang to monitor, not a red flag." },

  { type: "heading", text: "Earnings quality & red-flag ledger", number: 6 },
  { type: "text", size: 19, text:
    "All 23 adjudicated entries: 2 confirmed, 7 disclosed, 14 dismissed, 0 candidate. Dismissed flags stay visible with their dismissal reasons for auditability. The two confirmed flags below are both guidance-credibility issues, not accounting-integrity issues \u2014 no section-4 manipulation screen confirms gross-up, cash-flow reclassification, capitalization anomaly, or related-party round-tripping." },
  { type: "sub", text: "Confirmed and disclosed flags (9 of 23)" },
  { type: "table", headers: ["ID", "Status", "Sev.", "Why-chain (compressed)"], opts: { colAligns: ["left","center","center","left"], colWeights: [1,1,0.7,3], colorizeCol: 1 }, rows: [
    ["RF-GUI-01", "Confirmed", "Medium", "5th-stream FY26 volume cut ~40% in-year (500KT\u2192300KT), then deferred to FY27 \u2014 no reconciling explanation"],
    ["RF-GUI-02", "Confirmed", "Low", "Alumina contract-mix target stated three ways in one FY (80/20 spot \u2192 50/50 \u2192 spot-only)"],
    ["RF-001", "Disclosed", "Medium", "Other income 25.9% of CFO FY2023 \u2014 CFO collapsed \u221277.6% in the commodity trough while other income stayed flat; specific WC leg unconfirmed"],
    ["RF-MERGE-02", "Disclosed", "Medium", "Other income FY2022 \u221211.2% between AR comparatives \u2014 largest relative P&L delta, no captured footnote"],
    ["RF-MERGE-08", "Disclosed", "Medium", "Total assets FY2022 +1.22% (\u20b9211.04cr) between AR comparatives \u2014 no footnote"],
    ["RF-MERGE-09", "Disclosed", "Medium", "Total liabilities FY2022 +4.47% \u2014 same reclassification as RF-MERGE-08 (balance-sheet-identity preserving)"],
    ["RF-MERGE-12", "Disclosed", "Medium", "Total assets FY2022 consolidated +1.22% \u2014 the same regrouping flows through consolidation"],
    ["RF-GUI-03", "Disclosed", "Low", "0.5 MT smelter commissioning date inconsistent across/within docs (Aug-2030 / Dec-2030 / Jun-2031) \u2014 documentation hygiene, pre-DPR"],
    ["RF-GUI-04", "Disclosed", "Low", "Pottangi date mismatch same-quarter (June call vs. May PPT) \u2014 a one-month transcription slip"],
  ]},
  { type: "sub", text: "Dismissed, low-severity (14 of 23) \u2014 condensed" },
  { type: "text", size: 19, text:
    "RF-002/RF-003: DSO rose from 1.93 to 4.26 days across FY2023\u2013FY2024 (+21%, then +82%) \u2014 percentage noise on a sub-week base with no channel-stuffing signature (inventory rose too); stabilized at 4.05 days by FY2025. RF-MERGE-01, 03\u201307, 10\u201311, 13\u201316 (10 entries): routine AR-to-AR comparative regroupings and PPT-vs-AR rounding deltas, each under 1.1% and each resolved by taking the latest/audited figure \u2014 individually immaterial (rounding on revenue, other income, expenses, inventories; a ~1% PPT-vs-AR gap on FY2025 PBT/PAT, a known and disclosed precedent for FY2026's PPT-sourced figures)." },
  { type: "text", size: 19, text:
    "Composite interpretation: principal soft spots are the unexplained FY2023 CFO/working-capital swing (RF-001) and four comparative-period deltas above 1% without footnote traceability (RF-MERGE-02/08/09/12). Capitalization and related-party screens return no-data rather than a clean pass \u2014 an extraction-scope gap, disclosed, not a negative finding." },

  { type: "heading", text: "Valuation & peers", number: 7 },
  { type: "sub", text: "Historical multiple bands (standalone EPS, 5y)" },
  { type: "table", headers: ["FY", "Avg price", "End price", "EPS", "P/E on avg", "P/E on end"], opts: { colAligns: ["left","center","center","center","center","center"] }, rows: [
    ["FY2021", "28.67", "42.32", "6.97", "4.11", "6.07"],
    ["FY2022", "74.16", "100.92", "16.07", "4.61", "6.28"],
    ["FY2023", "68.98", "69.13", "8.41", "8.20", "8.22"],
    ["FY2024", "93.75", "139.07", "11.22", "8.36", "12.39"],
    ["FY2025", "183.26", "167.94", "28.99", "6.32", "5.79"],
    ["FY2026 (cross-check)", "239.99", "384.19", "31.67", "7.58", "12.13"],
    ["CMP 361.65 vs. FY2025 EPS", "\u2014", "\u2014", "28.99", "12.47", "\u2014"],
    ["CMP 361.65 vs. FY2026 EPS", "\u2014", "\u2014", "31.67", "11.42", "\u2014"],
  ]},
  { type: "text", size: 19, text:
    "The band's own extremes are cycle artifacts, not re-ratings: FY2021's 4.1x is a COVID-trough EPS against a forward-looking price; FY2024's 8.36x is a depressed EPS against a price already re-rating on the anticipated FY2025 recovery; FY2025's drop to 6.32x despite EPS quadrupling shows the market discounting the ~45% margin as unsustainable in real time. The subsequent 12.5x/11.4x at CMP is therefore a genuine expansion beyond anything in the last five years. EV/EBITDA: ~7.8x (FY2024, depressed EBITDA) \u2192 ~3.9x (FY2025 end) \u2192 7.7\u20138.4x at CMP \u2014 a trough-cycle-era multiple now applied to peak-cycle earnings. P/B: 0.73x (FY2021) \u2192 1.78x (band high) \u2192 3.73x at CMP \u2014 more than double the five-year band high." },
  { type: "sub", text: "Peer comparison" },
  { type: "table", headers: ["Peer", "Scale / margin", "Multiple", "Delta vs. NALCO"], opts: { colAligns: ["left","left","center","left"], colWeights: [1.1,1.8,0.9,2] }, rows: [
    ["Hindalco (consol., incl. Novelis)", "\u20b9275,000cr rev; India-upstream EBITDA/t $1,572, 45.56% margin", "Not pulled", "No operating-quality edge for NALCO over Hindalco's comparable segment"],
    ["Vedanta Aluminium", "2.88 MTpa capacity, 2.46mt produced FY26; CoP $1,752/t \u2192 target $1,550\u20131,600/t", "Not pulled", "~6x NALCO's metal scale; common-basis premium/discount not scoreable"],
    ["Alcoa", "Rev $3.2bn, adj. EBITDA $595mn Q1 CY2026", "Fwd P/E 10.04x, EV/EBITDA 8.33x", "NALCO trades at essentially no discount to a larger, longer-track-record peer despite concentrated single-country risk \u2014 unexplained parity"],
  ]},
  { type: "text", size: 19, text:
    "Premium/discount analysis: at CMP and FY2025 EPS, the stock trades at ~2x the five-year average P/E (~6.3x). To re-justify the price at that average multiple, FY2027+ EPS would need to roughly double the FY2025 print (~EPS 57\u201358) \u2014 unsupported by any fact in the pack. The reverse read: CMP prices in either a sustained ~2x EPS step-up versus a peak-cycle base, or a permanent multiple re-rating. Peer-valuation checked explicitly for a re-rating catalyst (credit-rating upgrade, index inclusion, DPR-approved capacity) and found none. The near-debt-free balance sheet is real and supportive but is a pre-existing multi-year condition that does not explain a re-rating specifically over the last 12\u201318 months." },
  { type: "text", size: 19, text:
    "Weighted business-quality score: 6.05/10 \u2014 industry structure 4, cost position 7, balance sheet 9, moat 4.3, earnings quality 7.5, governance 7.3, valuation 2. Ex-valuation the business would score ~6.9/10: it is valuation, not operations, that is the standout outlier." },

  { type: "heading", text: "Estimates (full build)", number: 8 },
  { type: "text", size: 19, text: "Basis: consolidated (FY2026 base is company-summarised PPT)." },
  { type: "table", headers: ["Metric", "FY25A", "FY26A (PPT)", "FY27E (base)", "FY28E (base)"], opts: { colAligns: ["left","center","center","center","center"] }, rows: [
    ["Revenue (\u20b9cr)", "16,787.6", "17,843.0", "19,399.4", "19,156.4"],
    ["Revenue growth %", "27.7", "6.3", "8.7", "\u22121.3"],
    ["EBITDA (\u20b9cr)", "7,922", "8,613", "8,632.7", "8,237.2"],
    ["EBITDA margin %", "47.2", "48.3", "44.5", "43.0"],
    ["PAT (\u20b9cr, cons.)", "5,267.9", "5,815.8", "6,015.9", "5,702.8"],
    ["EPS diluted (\u20b9, cons.)", "28.68", "31.67", "32.76", "31.05"],
    ["Capex (\u20b9cr)", "1,175.6", "N/A", "2,280.0", "2,250.0"],
    ["P/E @ CMP (x)", "\u2014", "11.42", "11.04", "11.65"],
  ]},
  { type: "text", size: 19, text: "Base-case 2yr EPS CAGR FY26\u2192FY28E = \u22120.98%. Revenue is essentially flat FY27E\u2192FY28E as external price normalization outweighs volume/ramp gains \u2014 a sequential decline, not a modeling error." },
  { type: "sub", text: "The 5 assumptions that matter" },
  { type: "bullets", items: [
    "Segment split ~73% metal / ~27% alumina.",
    "5th-stream incremental alumina volume probability-weighted 0.40 (FY27E) / 0.55 (FY28E), not nameplate \u2014 the single largest swing factor, reflecting low guidance credibility.",
    "Price paths anchored to World Bank / Platts, not management guidance.",
    "EBITDA margin faded from FY26's 48.3% to 44.5%/43.0%, within the 5-year band (24.9%\u201348.3%).",
    "Normalized ETR ~25.1\u201325.6% (3y median); no dilution. Capex-overrun pattern (~20% historical) built as an upward bias to capex/D&A/finance cost.",
  ]},
  { type: "table", headers: ["Scenario", "FY27E EPS", "FY28E EPS", "2yr EPS CAGR", "Rationale"], opts: { colAligns: ["left","center","center","center","left"], colWeights: [0.8,0.8,0.8,1,2.6] }, rows: [
    ["Base", "32.76", "31.05", "\u22120.98%", "Probability-weighted 5th-stream; World Bank/Platts price normalization"],
    ["Bull", "38.11", "42.42", "+15.74%", "5th-stream at 100% nameplate; metal $3,200/t, alumina $340/t; margin 48\u201349%"],
    ["Bear", "24.04", "21.26", "\u221218.05%", "Zero incremental 5th-stream/Pottangi; metal ~$2,400/t, alumina $260\u2013280/t; margin 37\u201339%"],
  ]},
  { type: "text", size: 19, text:
    "A naive 100%-guidance-flow-through model would sit near the bull case (+15.7%); the base case sits at \u22120.98% because low-credibility guidance is not allowed to become the base case. Management's own FY27 price guidance is broadly in line with independent anchors \u2014 the divergence is on volume (the 5th-stream ramp), not price." },

  { type: "heading", text: "Future outlook, risk factors & concluding synthesis", number: 9 },
  { type: "sub", text: "Catalyst calendar" },
  { type: "table", headers: ["Date / trigger", "Event"], opts: { colAligns: ["left","left"], colWeights: [1.1,2.9] }, rows: [
    ["~Aug-2026 (Q1 FY27 call)", "First confirmation of whether the 5th-stream refinery commissioned within one quarter of the June-2026 guide"],
    ["Aug\u2013Sept 2026", "0.5 MT smelter DPR targeted"],
    ["On publication", "FY2026 audited AR \u2014 confirms/disputes the Q4 PPT full-year figures used throughout"],
    ["Pending", "BSE/NSE ID-composition fine waiver outcome; board restoration to LODR-compliant composition"],
    ["Pending", "CBI recruitment-fraud probe resolution"],
  ]},
  { type: "sub", text: "Risk factors" },
  { type: "table", headers: ["Risk", "Type", "Prob. \u00d7 Impact"], opts: { colAligns: ["left","center","center"], colWeights: [2.6,1,1] }, rows: [
    ["Valuation reversion toward the 5y band", "Financial/market", "High \u00d7 High"],
    ["5th-stream slips again / ramps below weight", "Operational", "Medium-High \u00d7 High"],
    ["Governance \u2014 LODR breach + CBI probe unresolved", "Governance", "Medium \u00d7 Medium"],
    ["Alumina structural oversupply (Indonesia)", "Industry", "High \u00d7 Medium"],
    ["Commodity price cycle turns down", "Financial", "Medium \u00d7 High"],
    ["Capex overrun continues / debt-funds the smelter", "Financial", "Medium \u00d7 Medium"],
    ["CBAM / EU export exposure", "Industry/policy", "Low-Medium \u00d7 Medium (unsized)"],
    ["FY2026 figures unaudited (PPT-sourced)", "Data quality", "Medium \u00d7 Low-Medium"],
  ]},
  { type: "text", text:
    "Strengths: a clean, near-debt-free balance sheet; a genuine and widening cost-structure moat (the cleanest-delivered lever in the guidance ledger); above-median earnings quality with five straight unqualified audits and CAG \u201cNil\u201d comments; the best delivery record on the levers management actually controls (metal volume, cost efficiency)." },
  { type: "text", text:
    "Vulnerabilities: no pricing power (buyer power 7/10, near-zero switching costs, no hedging); a cost-structure moat that supports margins in a downturn but does not drive earnings growth or justify multiple expansion; two live overhangs \u2014 a fined governance-compliance breach and a repeatedly cut/deferred timeline on the single largest near-term growth lever; and, most acutely, a price that has run to roughly twice the multiple the stock has ever earned in its own five-year history against a base-case earnings path that is flat-to-down." },
  { type: "callout", title: "Concluding synthesis", color: GOLD, text:
    "NALCO is a well-built ship with a sound hull and cheap fuel, sailing a sea whose swells it cannot control \u2014 the current price is set as if the sea had been tamed, when the evidence says only the hull has been strengthened." },

  { type: "heading", text: "Open questions & gaps register (high-severity, condensed)", number: 10 },
  { type: "table", headers: ["ID", "Question", "Status"], opts: { colAligns: ["left","left","center"], colWeights: [1,2.6,1] }, rows: [
    ["OQ-FUND-03", "0.5 MT smelter incremental ROCE/payback?", "Open \u2014 pre-DPR, excluded from horizon"],
    ["OQ-GUI-03", "5th-stream commissioned June-2026, or slipped again?", "Open \u2014 unconfirmed as of Jul-2026"],
    ["OQ-GOV-01", "SEBI/ED/SFIO/CBI/NCLT/IBBI/MCA registry sweep?", "Open \u2014 portals not indexable; \u201cno adverse finding located,\u201d not certified-clean"],
    ["OQ-GOV-05", "Board / independent-director composition?", "Answered (adverse) \u2014 active penalized LODR breach"],
    ["OQ-FUND-01", "FY2026 audited AR vs. Q4 PPT figures?", "Open \u2014 AR not published; re-run on publication"],
  ]},
  { type: "text", size: 18, opts: { italics: true, size: 18 }, text:
    "Full register: 20 entries (5 answered/answered-partial, 15 open or mixed), spanning fundamentals, guidance, and governance. None are treated as blocking \u2014 each is a disclosed gap with a stated resolution trigger." },

  { type: "spacer", h: 100 },
  { type: "callout", title: "Disclaimer", color: NAVY, text:
    "This report is for educational analysis only and is not investment advice or a research report under SEBI (Research Analysts) Regulations, 2014. It has not been prepared by a SEBI-registered Research Analyst. Treat it as business analysis, not investment research. Always do your own due diligence before investing." },
  { type: "callout", title: "AI disclosure", color: GOLD, text:
    "Artificial intelligence was used to prepare substantially all of the analysis in this report (in line with the disclosure expectation SEBI introduced for AI use in research preparation). AI systems can make mistakes: figures are extracted and cross-verified against cited source pages, but errors may remain. Every number carries a source reference \u2014 verify load-bearing figures against the cited page before relying on them." },
  { type: "text", size: 17, opts: { italics: true, size: 17 }, text:
    "Validity: prepared 2026-07-16. Company information changes with news flow and results; treat this analysis as decaying in reliability beyond ~12 months, and market data as of its pull timestamp only (2026-07-15T11:47:58; CMP 361.65, mcap \u20b966,421.8cr, shares 183.6632cr). Sources: company documents supplied by the user (annual reports, quarterly filings, transcripts, presentations); exchange/regulator websites; market data via yfinance; external research as cited with URL and access date. The preparer holds no position information and expresses no view on suitability for any investor. Full source registry (140+ citations, page-level for every Annual Report line item) is retained in the source markdown and omitted here for length." },
];

module.exports = { masthead, title, blocks, footer: "NALCO \u2014 Forensic Dossier (Internal)" };
