const { GREEN, AMBER, RED, NAVY, GOLD } = require("./reportStyle.js");

const masthead = ["Equity Research", "Initiating Coverage \u2014 External Distribution"];
const title = [
  "National Aluminium Company Limited",
  "NSE / BSE: NATIONALUM  |  Metals & Mining \u2014 Aluminium  |  India  |  15 July 2026",
  "Sound Balance Sheet, Priced at ~2x Its Own History \u2014 REDUCE",
];

const blocks = [
  { type: "tombstone", fields: [
    ["Rating", "REDUCE"],
    ["CMP", "\u20b9361.65"],
    ["Fair-value context", "\u20b9190\u2013275"],
    ["Fwd P/E FY27E/FY28E", "11.04x / 11.65x"],
    ["Market Cap", "\u20b966,421.8 cr"],
    ["52-wk H/L", "\u20b9445.15 / 179.93"],
  ]},
  { type: "text", opts: { italics: true, size: 19 }, text:
    "Fair-value context: \u20b9190\u2013275, from the 5-year forward P/E band (~6.3x median, up to ~8.7x) applied to FY28E EPS of \u20b931.05. This band is context, not a formal target price \u2014 the rating (REDUCE) is the only recommendation statement in this note." },

  { type: "heading", text: "Snapshot (as of 2026-07-15)", number: null },
  { type: "table", headers: ["CMP", "Mcap (\u20b9cr)", "52-wk H/L", "Promoter % (pledge)", "FII/DII %", "Free float", "Fwd P/E FY27/28E"],
    rows: [["361.65", "66,421.8", "445.15 / 179.93", "51.28% (nil \u2014 sovereign)", "N/A \u2014 not in filings", "~48.7% (implied)", "11.04x / 11.65x"]],
    opts: { colAligns: ["center","center","center","center","center","center","center"], colWeights: [1,1.2,1.2,1.6,1.3,1.2,1.3] } },
  { type: "text", size: 18, opts: { italics: true, size: 18 }, text:
    "FII/DII split and exact free float were not in the supplied filings; promoter is the President of India / Ministry of Mines, so pledge does not apply." },

  { type: "heading", text: "Investment thesis", number: null },
  { type: "bullets", items: [
    "Operationally sound, input-cost-advantaged \u2014 but a price-taker with zero smoothing. FY2025 standalone EBITDA margin expanded ~1,966bps (24.9%\u219244.6%) on a cyclical realization tailwind, not structural efficiency; metal reprices every 3 days and alumina sells spot-tendered with near-zero hedging. The genuine, widening advantage is cost structure \u2014 captive bauxite and a captive-coal ramp to ~4 MTpa (~57% of fuel) \u2014 which supports margin resilience in a downturn but does not confer pricing power.",
    "Earnings quality is above-median for an Indian commodity CPSE, with disclosed \u2014 not concealed \u2014 soft spots. Forensic composite 75/100: unqualified audits FY2021\u2013FY2025, CAG \u201cNil\u201d in both covered years, a single non-recurring exceptional item (FY2024). The FY2023 CFO/other-income flag is a denominator effect in a commodity trough; the DSO doubling is immaterial off a ~1.1%-of-sales receivables base. This is not a \u201cnumbers are fake\u201d case.",
    "Governance is Amber, not Green \u2014 an active, fined LODR breach plus an open CBI probe. BSE and NSE each fined NALCO \u20b95,42,800 (total \u20b910.86 lakh incl. GST) for breaching SEBI LODR Reg. 17(1)\u2019s independent-director minimum after three IDs ceased 31-Mar-2026 without replacement; a waiver was requested but not yet granted. Separately, a 2026 CBI recruitment-fraud probe at the Haradghana site is open. Governance composite 73.3/100; the accounting sub-score itself is clean (90/100).",
    "Guidance/execution credibility is low on the levers that matter most for FY27\u201328. The 5th-stream refinery \u2014 the single largest near-term capacity catalyst \u2014 had its FY26 volume contribution cut ~40% in-year (500KT\u2192300KT) then deferred to FY27, and commissioning remained unconfirmed as of Jul-2026. FY2026 capex overshot budget ~24% with no disclosed cause, while CWIP/net-PPE nearly quadrupled (19.6%\u219272.6%, FY2021\u2013FY2025) with the largest tranche (\u20b918,000cr smelter) not yet started.",
  ]},

  { type: "heading", text: "Variant view & what's priced in", number: null },
  { type: "text", text:
    "The market may be correctly pricing NALCO's balance-sheet optionality and cost-structure moat rather than mispricing its cyclical earnings. NALCO is near-debt-free and its captive-input position is genuinely widening; if the market now treats it as a structurally lower-risk PSU deserving a permanent re-rating \u2014 on a broader PSU/commodity theme, prospective index-weight changes, or credit re-assessment \u2014 then the historical 4\u20138x band is the wrong anchor and ~11\u201312x could be a fair through-cycle level. This note does not adopt that view: peer-valuation checked explicitly for a re-rating catalyst (rating upgrade, index inclusion, DPR-approved capacity) and found none, and the balance-sheet strength is a multi-year pre-existing condition that does not explain a re-rating specifically over the last 12\u201318 months." },
  { type: "text", text:
    "Reverse-multiple read: at CMP and FY2025 EPS the stock trades at 12.5x versus a 5-year average of ~6.3x. Holding the historical average multiple, the price implies FY2027+ EPS roughly double the FY2025 peak-cycle print (~EPS 57\u201358) \u2014 against a base case of \u22120.98% 2yr EPS CAGR. Equivalently, at a constant ~11x multiple the price already capitalises the bull scenario, not the base." },
  { type: "table", headers: ["Risk", "Probability \u00d7 Impact"], rows: [
      ["Valuation reversion toward the 5-year band", "High \u00d7 High"],
      ["5th-stream slips again / ramps below plan", "Medium-High \u00d7 High"],
      ["LODR breach + CBI probe unresolved", "Medium \u00d7 Medium"],
      ["Alumina structural oversupply (Indonesia) pressures realizations", "High \u00d7 Medium"],
    ], opts: { colAligns: ["left","center"], colWeights: [3,1] } },

  { type: "heading", text: "Company", number: null },
  { type: "text", text:
    "NALCO is a Navratna CPSE (GoI 51.28%) and a fully integrated bauxite\u2192alumina\u2192aluminium producer with captive power. Two reportable segments \u2014 Chemicals (alumina) and Aluminium (metal) \u2014 sit inside one value chain; NALCO has no downstream/specialty business, so output is bulk primary metal and alumina sold on spot/LME terms." },
  { type: "sub", text: "Exhibit 1 \u2014 Segment mix & structural facts" },
  { type: "table", headers: ["Item", "Detail"], rows: [
      ["Revenue mix (FY2026)", "~73% metal / ~27% alumina, shifted from ~70/30; management frames as margin-supportive"],
      ["Segment EBIT nuance", "Aluminium EBIT share 61.2% (FY24) \u2192 55.5% (FY25) \u2014 non-monotonic vs. revenue mix"],
      ["Alumina sales", "~90.5% export / 9.5% domestic (Q4 FY26); spot-only, no long-term contracts currently"],
      ["Integration", "Captive Panchpatmali bauxite; captive coal ~4 MTpa (~57% fuel); pending Pottangi mine (MDO to Dilip Buildcon, Dec-2025)"],
      ["Balance sheet", "Near debt-free (D/E ~0.002x); interest coverage 152\u2013172x FY22\u201323"],
    ], opts: { colAligns: ["left","left"], colWeights: [1, 2.6] } },
  { type: "text", size: 19, text:
    "The 2\u20133 structural facts that matter: (i) a real, widening cost-structure moat (captive inputs) that is margin-defensive, not pricing-power-positive; (ii) scarce government-allocated mining leases, though lease-expiry dates carry an unresolved discrepancy; (iii) a build-phase balance sheet \u2014 CWIP is ~73% of net PPE with the largest tranche not yet started." },

  { type: "heading", text: "Industry & competition", number: null },
  { type: "text", text:
    "Market-size build: India aluminium demand ~6.27% CAGR CY2024\u20132030 (TechSci, paid research, low confidence), the low end of a 5.9\u20137.8% spread; wire-rod +5.93% CAGR to 2030. Pricing: LME aluminium CY2027 spans US$2,400/t (Goldman bear) to US$3,000/t (World Bank central) to US$3,200/t (SMM high); spot was US$3,538/t on 28-Apr-2026. Alumina averaged US$306.91/t (Platts FOB-Australia, Q1 CY2026). Value-chain bottleneck: the alumina-to-LME premium compressed 15\u201317% \u2192 11\u201311.5% as Indonesian metallurgical alumina capacity ramps to 7 MTpa by CY2026 and primary aluminium capacity nearly triples (0.87\u21923.56mt, 2025\u21922027) \u2014 the force behind NALCO's FY2026 alumina realization collapse (US$580\u2192US$370). Cycle position: FY2025 was a realization peak; the FY2026 exit quarter was already negative YoY." },
  { type: "sub", text: "Exhibit 2 \u2014 Peer comparison (decision-relevant cut; domestic multiples not located)" },
  { type: "table", headers: ["Peer", "EBITDA margin", "Scale (metal)", "Integration", "P/E", "EV/EBITDA"], rows: [
      ["NALCO (CMP)", "44.6% (FY25 std, peak)", "~471KT", "Full upstream + captive power", "12.5x", "7.7\u20138.4x"],
      ["Hindalco (India upstream)", "45.6%", "Larger", "Upstream + Novelis downstream", "Not pulled", "Not pulled"],
      ["Vedanta Aluminium", "OPBDITA/t $1,158\u20131,188", "2.46mt (~6x NALCO)", "To 100% captive", "Not pulled", "Not pulled"],
      ["Alcoa", "Adj. EBITDA $595mn Q1", "Larger, multi-country", "Global upstream", "12.60x", "8.33x"],
    ], opts: { colAligns: ["left","center","center","left","center","center"], colWeights: [1.5,1.3,1.2,1.8,0.9,1] } },
  { type: "text", size: 19, text:
    "Premium/discount verdict: NALCO's FY2025 margin is in line with Hindalco's India-upstream segment (no operating-quality edge), and its multiples have converged with the larger, more diversified Alcoa at essentially no discount despite concentrated single-country risk and peak-cycle earnings \u2014 a parity unexplained by any evidenced quality edge." },

  { type: "heading", text: "Financial analysis", number: null },
  { type: "sub", text: "Exhibit 3 \u2014 Financial summary (standalone FY21\u201325; FY26 EBITDA is company-reported consolidated PPT)" },
  { type: "table", headers: ["\u20b9cr", "FY21", "FY22", "FY23", "FY24", "FY25", "FY26 (PPT)"], rows: [
      ["Revenue", "8,955.8", "14,214.6", "14,254.9", "13,149.1", "16,787.6", "17,843.0"],
      ["Revenue growth %", "\u2014", "58.7", "0.3", "\u22127.8", "27.7", "6.3"],
      ["EBITDA (reported, cons.)", "\u2014", "\u2014", "\u2014", "\u2014", "7,922", "8,613"],
      ["PBT (standalone)", "1,316.5", "3,954.9", "1,955.0", "2,712.1", "7,135.1", "7,767 (cons.)"],
      ["PAT (standalone)", "1,299.4", "2,952.0", "1,544.5", "1,988.5", "5,324.7", "5,815.8 (cons.)"],
      ["EPS diluted (\u20b9, standalone)", "7.0", "16.1", "8.4", "11.2", "28.99", "31.67 (cons. calc)"],
    ], opts: { colAligns: ["left","center","center","center","center","center","center"] } },
  { type: "bullets", items: [
    "Margin architecture is cyclical, not structural. The +1,966bps FY2025 margin move traces to price/volume (metal realization ~$2,550\u2192$2,700/t; alumina volumes offsetting a ~$200/t price fall) plus falling employee cost from retirements \u2014 a reversible tailwind, and the reversal has begun: Q4 FY2026 revenue \u22124.8% / PAT \u221217.4% YoY, masked by a positive full-year headline.",
    "Capex\u2192incremental-ROCE is unproven. CWIP/net-PPE nearly quadrupled to 72.6%; the \u20b918,000cr smelter is pre-DPR and excluded from the estimate horizon, so 3-year incremental ROCE cannot yet be computed.",
    "Working capital / cash conversion is clean. DSO peaked at 4.26 days off a ~1.1%-of-sales base; CFO/EBITDA conversion was 73.3% in FY2025 \u2014 no confirmed working-capital drag.",
    "Funding is a future, not current, concern. Finance costs tripled off a near-zero base (17.2\u219259.0cr FY24\u2192FY25) but leverage remains negligible; a debt-funded smelter would be the structural shift to watch.",
  ]},

  { type: "heading", text: "Earnings quality & governance", number: null },
  { type: "text", text:
    "Earnings-quality composite 75/100 \u2014 drivers: one-off frequency 92, audit cleanliness 92, accrual-ratio trend 78 (CFO exceeded PAT in 4 of 5 years), pulled down by cash-conversion 62 (FY2023 CFO volatility) and disclosure quality 68 (four comparative-period deltas >1% without footnote traceability). Governance verdict: Amber, 73.3/100 \u2014 the accounting sub-score is clean at 90/100; the Amber gate is the fined LODR board-composition breach and the open CBI probe. No high-severity confirmed accounting flag exists; the two confirmed flags are guidance-credibility issues, not accounting integrity issues. Checks run and cleared: 14 of 23 red-flag ledger entries dismissed, 7 disclosed, 2 confirmed, 0 candidate. Guidance credibility: high on metal volume and cost efficiency (delivered); low on 5th-stream volume, smelter timeline, and commodity-price calls." },

  { type: "heading", text: "Estimates & valuation", number: null },
  { type: "sub", text: "Exhibit 4 \u2014 Estimates (consolidated, base case)" },
  { type: "table", headers: ["Metric", "FY25A", "FY26A (PPT)", "FY27E", "FY28E"], rows: [
      ["Revenue (\u20b9cr)", "16,787.6", "17,843.0", "19,399.4", "19,156.4"],
      ["Growth %", "27.7", "6.3", "8.7", "\u22121.3"],
      ["EBITDA (\u20b9cr)", "7,922", "8,613", "8,632.7", "8,237.2"],
      ["EBITDA margin %", "47.2", "48.3", "44.5", "43.0"],
      ["PAT (\u20b9cr, cons.)", "5,267.9", "5,815.8", "6,015.9", "5,702.8"],
      ["EPS diluted (\u20b9, cons.)", "28.68", "31.67", "32.76", "31.05"],
      ["Capex (\u20b9cr)", "1,175.6", "N/A (AR pending)", "2,280", "2,250"],
      ["P/E @ CMP (x)", "\u2014", "11.42", "11.04", "11.65"],
    ], opts: { colAligns: ["left","center","center","center","center"] } },
  { type: "text", text:
    "Base-case 2yr EPS CAGR \u22120.98%. The 5 assumptions that matter: (1) 5th-stream volume probability-weighted 0.40/0.55, not nameplate \u2014 the single largest swing factor, given low guidance credibility. (2) Price paths anchored to World Bank/Platts, not management guidance. (3) Margin faded to 44.5%/43.0%, within the 5-year band. (4) Normalized ETR ~25.3%; no dilution. (5) Capex-overrun pattern (~20%) built as an upward bias to capex/D&A/finance cost. Forward P/E 11.0x/11.7x sits above the 5-year band (4.6x\u20138.7x, median 7.6x) even on forward earnings; the only located peer forward multiple (Alcoa, 10.04x) sits below NALCO's implied forward multiples." },
  { type: "sub", text: "Scenarios (inputs to the downstream PT engine \u2014 not price targets)" },
  { type: "table", headers: ["Scenario", "FY27E EPS", "FY28E EPS", "2yr EPS CAGR", "Rationale"], rows: [
      ["Base", "32.76", "31.05", "\u22120.98%", "Probability-weighted 5th-stream; external price normalization off the FY26 peak."],
      ["Bull", "38.11", "42.42", "+15.74%", "5th-stream at nameplate; metal $3,200/t, alumina $340/t; margin 48\u201349%."],
      ["Bear", "24.04", "21.26", "\u221218.05%", "Zero incremental 5th-stream; metal ~$2,400/t, alumina $260\u2013280/t; margin 37\u201339%; finance cost +30\u201350%."],
    ], opts: { colAligns: ["left","center","center","center","left"], colWeights: [0.9,0.9,0.9,1,2.6] } },

  { type: "heading", text: "Risks, catalysts & monitorables", number: null },
  { type: "text", text:
    "Risks with mitigants: valuation reversion (no intrinsic mitigant \u2014 needs an EPS step-up or evidenced re-rating, neither present); 5th-stream slip (base case already probability-discounts it; metal-volume/cost delivery on track); governance overhang (self-disclosed and appealed; a CPSE ID-appointment issue controlled by GoI, not misconduct; accounting clean); commodity downturn (near-debt-free balance sheet plus captive-cost moat cushion margins)." },
  { type: "text", text:
    "Catalyst calendar: ~Aug-2026 Q1 FY27 call \u2014 first read on 5th-stream commissioning. Aug\u2013Sept 2026 \u2014 smelter DPR targeted. On publication \u2014 FY2026 audited AR (tests the PPT figures; ~1% precedent gap). Pending \u2014 LODR fine-waiver outcome and board restoration; CBI probe resolution." },
  { type: "text", text:
    "Monitorables: a second commissioning slip or a second capex overshoot >15\u201320% is downgrade-supportive. A fine waiver granted and board restored to LODR-compliance removes the Amber driver. Alumina sustained above US$310/t and metal above US$3,100/t without a war premium moves the base toward bull. Material FY2026 AR divergence from PPT figures re-opens FY2026-dependent findings." },

  { type: "heading", text: "Data gaps & limitations", number: null },
  { type: "bullets", items: [
    "FY2026 audited AR pending \u2014 all FY2026 full-year figures are company-summarised Q4 PPT figures; FY2025 precedent shows a ~1% PPT-vs-AR gap at PBT/PAT.",
    "SEBI/NCLT/NCLAT docket screens unreachable \u2014 the governance legal/regulatory sub-score (62/100) is \u201cunverified-clean, disclosed gap,\u201d not certified-clean.",
    "Domestic peer multiples missing \u2014 Hindalco/Vedanta P/E, EV/EBITDA, P/B were not located; premium/discount scored on operating-margin proxies only, with Alcoa as an international cross-check.",
    "CBAM exposure unsized \u2014 India's EU unwrought-aluminium exports fell 41.7% YoY and NALCO's captive power is coal-based (least CBAM-favourable), but NALCO's own EU export share was not quantified.",
    "5th-stream commissioning unconfirmed as of Jul-2026 \u2014 the guided June-2026 date had passed with a commissioning-support tender still pre-bid on 01-Jul-2026; a second slip cannot be ruled out.",
  ]},
  { type: "text", size: 19, text: "Other open item: 0.5 MT smelter incremental ROCE/payback is not computable pre-DPR; the project is excluded from the estimate horizon." },

  { type: "spacer", h: 100 },
  { type: "callout", title: "Disclaimer", color: NAVY, text:
    "This report is for educational analysis only and is not investment advice or a research report under SEBI (Research Analysts) Regulations, 2014. It has not been prepared by a SEBI-registered Research Analyst. Treat it as business analysis, not investment research. Always do your own due diligence before investing." },
  { type: "callout", title: "AI disclosure", color: GOLD, text:
    "Artificial intelligence was used to prepare substantially all of the analysis in this report (in line with the disclosure expectation SEBI introduced for AI use in research preparation). AI systems can make mistakes: figures are extracted and cross-verified against cited source pages, but errors may remain." },
  { type: "text", size: 17, opts: { italics: true, size: 17 }, text:
    "Prepared 2026-07-16. Company information changes with news flow and results; treat this analysis as decaying in reliability beyond ~12 months, and market data as of its pull timestamp only (2026-07-15). Sources: company annual reports, quarterly filings, transcripts and presentations; exchange/regulator websites; market data via yfinance; external research as cited. Full audit trail: forensic dossier (companion document)." },
];

module.exports = { masthead, title, blocks, footer: "NALCO \u2014 Equity Research (External)" };
