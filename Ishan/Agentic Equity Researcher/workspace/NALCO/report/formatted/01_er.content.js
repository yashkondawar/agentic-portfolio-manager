const { GREEN, AMBER, RED, NAVY, GOLD } = require("../../../../tools/report_formatter/reportStyle.js");

const masthead = ["Equity Research", "Initiating Coverage — External Distribution"];
const title = [
  "National Aluminium Company Limited",
  "NSE / BSE: NATIONALUM  |  Metals & Mining — Aluminium  |  India  |  15 July 2026",
  "Near-Debt-Free, Input-Cost-Advantaged — but Priced at ~2x Its Own History — REDUCE",
];

const blocks = [
  { type: "tombstone", fields: [
    ["Rating", "REDUCE"],
    ["CMP", "₹361.65"],
    ["Fair-value context", "₹190–275"],
    ["Fwd P/E FY27E/FY28E", "11.04x / 11.65x"],
    ["Market Cap", "₹66,421.8 cr"],
    ["52-wk H/L", "₹445.15 / 179.93"],
  ]},
  { type: "text", opts: { italics: true, size: 19 }, text:
    "Fair-value context: ₹190–275 indicative band — 5y forward-P/E band (~6.3x median, up to ~8.7x) applied to FY28E EPS of ₹31.05; formal target price pending the scenario engine (see handoff). This band is context, not a target — the rating (REDUCE) is the only recommendation statement in this note." },

  { type: "heading", text: "Snapshot (as of 2026-07-15)", number: null },
  { type: "table", headers: ["CMP", "Mcap (₹cr)", "52-wk H/L", "Promoter % (pledge)", "FII / DII %", "Free float", "Fwd P/E FY27/28E"],
    rows: [["361.65", "66,421.8", "445.15 / 179.93", "51.28% (nil — sovereign)", "N/A — not in filings", "~48.7% (implied)", "11.04x / 11.65x"]],
    opts: { colAligns: ["center","center","center","center","center","center","center"], colWeights: [1,1.2,1.2,1.6,1.3,1.2,1.3] } },
  { type: "text", opts: { italics: true, size: 18 }, text:
    "FII/DII split and exact free-float were not in the supplied documents (shareholding-pattern filings not provided); promoter is the President of India / Ministry of Mines, so pledge does not apply. Full audit trail and legend: dossier §13." },

  { type: "heading", text: "Investment thesis", number: null },
  { type: "bullets", items: [
    "Operationally sound, input-cost-advantaged — but a price-taker with zero smoothing. NALCO's FY2025 standalone EBITDA margin expanded ~1,966 bps (24.9%→44.6%) on a cyclical realization tailwind, not structural efficiency; metal is repriced every 3 days and alumina sold spot-tendered with near-zero hedging. The genuine, widening advantage is cost structure — captive bauxite and a captive-coal ramp to ~4 MTpa (~57% of fuel), the cleanest-delivered lever in the guidance ledger. This supports margin resilience in a downturn; it does not confer pricing power (buyer power 7/10, switching costs 1/10).",
    "Earnings quality is above-median for an Indian commodity CPSE, with disclosed — not concealed — soft spots. Forensic composite 75/100: unqualified audits FY2021–FY2025, CAG “Nil” both covered years, a single non-recurring exceptional item (FY2024). The FY2023 CFO/other-income flag is a denominator effect in a commodity trough, corroborated independently from the revenue-cycle side; the DSO doubling is immaterial off a ~1.1%-of-sales receivables base. This is not a “numbers are fake” case — the reported figures are a reliable estimates base.",
    "Governance is Amber, not Green — an active, fined LODR breach plus an open CBI probe. BSE and NSE each fined NALCO ₹5,42,800 (total ₹10.86 lakh incl. GST, notices 27-Feb-2026) for breaching SEBI LODR Reg. 17(1)'s 50% independent-director minimum after three IDs ceased 31-Mar-2026 without replacement; a waiver was requested 17-Mar-2026 but not yet granted (corroborated across trade-press sources). Separately, a 2026 CBI recruitment-fraud probe at the Haradghana site is open (company disputes the “raid” framing). Composite governance score 73.3/100; the accounting sub-score itself is clean (90/100).",
    "Guidance/execution credibility is low on the levers that matter most for FY27–28. The 5th-stream refinery — the single largest near-term capacity catalyst — had its FY26 volume contribution cut ~40% in-year (500KT→300KT) then deferred to FY27, and commissioning was still unconfirmed as of Jul-2026 (commissioning-support tender pre-bid 01-Jul-2026). FY2026 capex overshot budget ~24% (₹400cr over ₹1,700cr) with no disclosed cause, while CWIP/net-PPE nearly quadrupled (19.6%→72.6% FY2021–FY2025) with the largest tranche (₹18,000cr smelter) not yet started.",
  ]},

  { type: "heading", text: "Variant view & what's priced in", number: null },
  { type: "text", text:
    "The market may be correctly pricing NALCO's balance-sheet optionality and cost-structure moat rather than mispricing its cyclical earnings. NALCO is near-debt-free and its captive-input position is genuinely widening; if the market is now treating it as a structurally lower-risk PSU deserving a permanent re-rating — on a broader PSU/commodity theme, prospective index-weight changes, or credit re-assessment — then the historical 4–8x band is the wrong anchor and ~11–12x could be a fair through-cycle level. This note does not adopt that view because peer-valuation checked explicitly for a re-rating catalyst (rating upgrade, index inclusion, DPR-approved capacity) and found none, and the balance-sheet strength is a multi-year pre-existing condition that does not explain a re-rating specifically over the last 12–18 months." },
  { type: "text", text:
    "Reverse-multiple read: at CMP and FY2025 EPS the stock trades at 12.5x versus a 5y average of ~6.3x. Holding the historical average multiple, the price implies FY2027+ EPS roughly double the FY2025 peak-cycle print (~EPS 57–58) — against a base case of −0.98% 2yr EPS CAGR. Equivalently, at a constant ~11x multiple the price already capitalises the bull scenario, not the base." },
  { type: "sub", text: "Top 4 risks" },
  { type: "table", headers: ["Risk", "Probability × Impact"], rows: [
      ["Valuation reversion toward the 5y band", "High × High"],
      ["5th-stream slips again / ramps below plan", "Medium-High × High"],
      ["LODR breach + CBI probe unresolved", "Medium × Medium"],
      ["Alumina structural oversupply (Indonesia) drives realizations lower", "High × Medium"],
    ], opts: { colAligns: ["left","center"], colWeights: [3.2,1] } },

  { type: "heading", text: "Company", number: null },
  { type: "text", text:
    "NALCO is a Navratna CPSE (GoI 51.28%) and a fully integrated bauxite→alumina→aluminium producer with captive power. Two reportable segments — Chemicals (alumina) and Aluminium (metal) — sit inside one value chain; NALCO has no downstream/specialty business, so output is bulk primary metal and alumina sold on spot/LME terms." },
  { type: "sub", text: "Exhibit 1 — Segment mix & structural facts" },
  { type: "table", headers: ["Item", "Detail"], rows: [
      ["Revenue mix (FY2026)", "~73% metal / ~27% alumina, shifted from ~70/30; management frames as margin-supportive"],
      ["Segment EBIT nuance", "Aluminium EBIT share 61.2% (FY24) → 55.5% (FY25) — non-monotonic vs revenue mix; carried as an open question"],
      ["Alumina sales", "~90.5% export / 9.5% domestic (Q4 FY26); spot-only, no long-term contracts currently"],
      ["Integration", "Captive Panchpatmali bauxite; captive coal ~4 MTpa (~57% fuel); pending Pottangi mine (MDO to Dilip Buildcon Dec-2025)"],
      ["Balance sheet", "Near-debt-free (D/E ~0.002x); interest coverage 152–172x FY22–23"],
    ], opts: { colAligns: ["left","left"], colWeights: [1, 2.8] } },
  { type: "text", opts: { size: 19 }, text:
    "The 2–3 structural facts that matter: (i) a real, widening cost-structure moat (captive inputs) that is margin-defensive, not pricing-power-positive; (ii) scarce government-allocated mining leases (a barrier, though lease-expiry dates carry an unresolved discrepancy); (iii) a build-phase balance sheet — CWIP is ~73% of net PPE with the largest tranche not yet started." },

  { type: "heading", text: "Industry & competition", number: null },
  { type: "text", text:
    "Market-size build: India aluminium demand ~6.27% CAGR CY2024–2030 (TechSci, paid research, low confidence), the low end of a 5.9–7.8% spread; wire-rod +5.93% CAGR to 2030. Pricing: LME aluminium CY2027 spans US$2,400/t (Goldman bear) to US$3,000/t (World Bank central) to US$3,200/t (SMM high); spot was US$3,538/t on 28-Apr-2026. Alumina averaged US$306.91/t (Platts FOB-Australia, Q1 CY2026). Value-chain bottleneck: the alumina-to-LME premium compressed 15–17%→11–11.5% as Indonesian metallurgical alumina capacity ramps to 7 MTpa by CY2026 and primary aluminium capacity nearly triples 0.87→3.56mt (2025→2027) — the force behind NALCO's FY2026 alumina realization collapse (US$580→US$370). Cycle position: FY2025 was a realization peak; the FY2026 exit quarter was already negative YoY." },
  { type: "sub", text: "Exhibit 2 — Peer comparison (decision-relevant cut; domestic multiples not located — a data gap)" },
  { type: "table", headers: ["Peer", "EBITDA margin", "Scale (metal)", "Integration", "P/E", "EV/EBITDA"], rows: [
      ["NALCO (CMP)", "44.6% (FY25 std, peak)", "~471KT", "Full upstream + captive power", "12.5x", "7.7–8.4x"],
      ["Hindalco (India upstream)", "45.6%", "Larger", "Upstream + Novelis downstream", "Not pulled", "Not pulled"],
      ["Vedanta Aluminium", "OPBDITA/t $1,158–1,188", "2.46mt (~6x NALCO)", "To 100% captive", "Not pulled", "Not pulled"],
      ["Alcoa", "Adj EBITDA $595mn Q1", "Larger, multi-country", "Global upstream", "12.60x", "8.33x"],
    ], opts: { colAligns: ["left","center","center","left","center","center"], colWeights: [1.5,1.3,1.2,1.8,0.9,1] } },
  { type: "text", opts: { size: 19 }, text:
    "Premium/discount verdict: NALCO's FY2025 margin is in line with Hindalco's India-upstream segment (no operating-quality edge), and its multiples have converged with the larger, more diversified Alcoa at essentially no discount despite concentrated single-country risk and peak-cycle earnings — a parity unexplained by any evidenced quality edge." },

  { type: "heading", text: "Financial analysis", number: null },
  { type: "sub", text: "Exhibit 3 — Financial summary (standalone FY21–25; PAT/EPS on the standalone P&L, not the consolidated figures in Exhibit 4; FY26 EBITDA is company-reported consolidated PPT)" },
  { type: "table", headers: ["₹cr", "FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "FY2026 (PPT)"], rows: [
      ["Revenue", "8,955.8", "14,214.6", "14,254.9", "13,149.1", "16,787.6", "17,843.0"],
      ["Revenue growth %", "—", "58.7", "0.3", "−7.8", "27.7", "6.3"],
      ["EBITDA (reported cons)", "—", "—", "—", "—", "7,922", "8,613"],
      ["PBT (standalone)", "1,316.5", "3,954.9", "1,955.0", "2,712.1", "7,135.1", "7,767 (cons)"],
      ["PAT (standalone)", "1,299.4", "2,952.0", "1,544.5", "1,988.5", "5,324.7", "5,815.8 (cons)"],
      ["EPS diluted (₹, standalone)", "7.0", "16.1", "8.4", "11.2", "28.99", "31.67 (cons calc)"],
    ], opts: { colAligns: ["left","center","center","center","center","center","center"] } },
  { type: "bullets", items: [
    "Margin architecture is cyclical, not structural. The +1,966 bps FY2025 margin move traces to price/volume (metal realization ~$2,550→$2,700/t; alumina volumes offsetting a ~$200/t price fall) plus falling employee cost from retirements — a reversible tailwind, and the reversal has begun: Q4 FY2026 revenue −4.8% / PAT −17.4% YoY, masked by a positive full-year headline.",
    "Capex→incremental-ROCE is unproven. CWIP/net-PPE nearly quadrupled to 72.6%; the ₹18,000cr smelter is pre-DPR and excluded from the estimate horizon, so 3-year incremental ROCE cannot yet be computed.",
    "Working capital / cash conversion is clean. DSO peaked at 4.26 days off a ~1.1%-of-sales base; CFO/EBITDA conversion 73.3% in FY2025 — no confirmed working-capital drag.",
    "Funding is a future, not current, concern. Finance costs tripled off a near-zero base (17.2→59.0cr FY24→FY25) but leverage remains negligible; a debt-funded smelter would be the structural shift to watch.",
  ]},

  { type: "heading", text: "Earnings quality & governance", number: null },
  { type: "text", text:
    "Earnings-quality composite 75/100 — drivers: one-off frequency 92, audit cleanliness 92, accrual-ratio trend 78 (CFO exceeded PAT in 4 of 5 years), pulled down by cash conversion 62 (FY2023 CFO volatility) and disclosure quality 68 (four comparative-period deltas >1% without footnote traceability). Governance verdict: Amber, 73.3/100 — the accounting sub-score is clean at 90/100; the Amber gate is the fined LODR board-composition breach and the open CBI probe. No high-severity confirmed accounting flag exists; the two confirmed flags are guidance-credibility issues, not accounting-integrity issues. Checks run and cleared: 14 of 23 red-flag ledger entries dismissed, 7 disclosed, 2 confirmed, 0 candidate. Guidance credibility: high on metal volume and cost efficiency (delivered); low on 5th-stream volume, smelter timeline and commodity-price calls." },

  { type: "heading", text: "Estimates & valuation", number: null },
  { type: "sub", text: "Exhibit 4 — Estimates (consolidated, base case; FY2025 consolidated EPS 28.68 differs from the standalone 28.99 in Exhibit 3)" },
  { type: "table", headers: ["Metric", "FY2025A", "FY2026A (PPT)", "FY2027E", "FY2028E"], rows: [
      ["Revenue (₹cr)", "16,787.6", "17,843.0", "19,399.4", "19,156.4"],
      ["Growth %", "27.7", "6.3", "8.7", "−1.3"],
      ["EBITDA (₹cr)", "7,922", "8,613", "8,632.7", "8,237.2"],
      ["EBITDA margin %", "47.2", "48.3", "44.5", "43.0"],
      ["PAT (₹cr, cons)", "5,267.9", "5,815.8", "6,015.9", "5,702.8"],
      ["EPS diluted (₹, cons)", "28.68", "31.67", "32.76", "31.05"],
      ["Capex (₹cr)", "1,175.6", "N/A (AR pending)", "2,280", "2,250"],
      ["P/E @ CMP (x)", "—", "11.42", "11.04", "11.65"],
    ], opts: { colAligns: ["left","center","center","center","center"] } },
  { type: "text", text:
    "Base-case 2yr EPS CAGR −0.98%. The 5 assumptions that matter: (1) 5th-stream volume probability-weighted 0.40/0.55, not nameplate — the single largest swing factor, given low guidance credibility. (2) Price paths anchored to World Bank/Platts, not management guidance. (3) Margin faded to 44.5%/43.0%, within the 5y band. (4) Normalized ETR ~25.3%; no dilution. (5) Capex-overrun pattern (~20%) built as an upward bias to capex/D&A/finance cost. Forward P/E 11.0x/11.7x sits above the 5y band (4.6x–8.7x, median 7.6x) even on forward earnings; the only located peer forward multiple (Alcoa 10.04x) sits below NALCO's implied forward multiples." },
  { type: "text", opts: { italics: true, size: 17 }, text:
    "Footnote on the P/E band: the ~6.3x median in the fair-value context and reverse-multiple read is the strictly-audited FY2021–FY2025 P/E-on-average-price window; the 7.6x median (band 4.6x–8.7x) here is the pe_bands set, which rolls the FY2026 cross-check year forward. Both are reproduced from source and differ by window, not by error (see dossier §7.1)." },
  { type: "sub", text: "Scenarios (inputs to the downstream PT engine — not price targets)" },
  { type: "table", headers: ["Scenario", "FY27E EPS", "FY28E EPS", "2yr EPS CAGR", "Rationale"], rows: [
      ["Base", "32.76", "31.05", "−0.98%", "Probability-weighted 5th-stream; external price normalization off the FY26 peak."],
      ["Bull", "38.11", "42.42", "+15.74%", "5th-stream at nameplate; metal $3,200/t, alumina $340/t; margin 48–49%."],
      ["Bear", "24.04", "21.26", "−18.05%", "Zero incremental 5th-stream; metal ~$2,400/t, alumina $260–280/t; margin 37–39%; finance cost +30–50%."],
    ], opts: { colAligns: ["left","center","center","center","left"], colWeights: [0.9,0.9,0.9,1,2.8] } },
  { type: "text", opts: { size: 19 }, text:
    "The spread is driven primarily by the probability weight on the one capacity lever, not by price alone." },

  { type: "heading", text: "Risks, catalysts & monitorables", number: null },
  { type: "text", text:
    "Risks with mitigants: valuation reversion (no intrinsic mitigant — needs an EPS step-up or evidenced re-rating, neither present); 5th-stream slip (base case already probability-discounts it; metal-volume/cost delivery is on track); governance overhang (self-disclosed and appealed; a CPSE ID-appointment issue controlled by GoI, not misconduct; accounting clean); commodity downturn (near-debt-free balance sheet + captive-cost moat cushion margins)." },
  { type: "text", text:
    "Catalyst calendar: ~Aug-2026 Q1 FY27 call — first read on 5th-stream commissioning. Aug–Sept 2026 — smelter DPR targeted. On publication — FY2026 audited AR (tests the PPT figures; ~1% precedent gap). Pending — LODR fine-waiver outcome and board restoration; CBI probe resolution." },
  { type: "text", text:
    "Monitorables (thresholds that would change the view): a second commissioning slip or a second capex overshoot >15–20% is downgrade-supportive; a fine waiver granted AND board restored to LODR-compliance removes the Amber driver; alumina sustained above US$310/t and metal above US$3,100/t without a war premium moves the base toward bull; material FY2026 AR divergence from PPT figures re-opens FY2026-dependent findings." },

  { type: "heading", text: "Data gaps & limitations", number: null },
  { type: "bullets", items: [
    "FY2026 audited AR pending — all FY2026 full-year figures (revenue 17,843cr, PAT 5,816cr, EBITDA 8,613cr) are company-summarised Q4 PPT figures; FY2025 precedent shows a ~1% PPT-vs-AR gap at PBT/PAT.",
    "SEBI/NCLT/NCLAT docket screens unreachable — the portals are interactive/form-driven and not indexable across two attempts; the governance legal/regulatory sub-score (62/100) is “unverified-clean, disclosed gap,” not certified-clean.",
    "Domestic peer multiples missing — Hindalco/Vedanta P/E, EV/EBITDA, P/B were not located; premium/discount scored on operating-margin proxies only, with one international multiple (Alcoa) as cross-check.",
    "CBAM exposure unsized — India's EU unwrought-aluminium exports fell 41.7% YoY and NALCO's captive power is coal-based (least CBAM-favourable), but NALCO's own EU export volume/% of sales was not quantified.",
    "5th-stream commissioning unconfirmed as of Jul-2026 — the guided June-2026 date had passed with a commissioning-support tender still pre-bid on 01-Jul-2026; a second slip cannot be ruled out or confirmed.",
  ]},
  { type: "text", opts: { size: 19 }, text:
    "Other open high-severity item: 0.5 MT smelter incremental ROCE/payback is not computable pre-DPR; the project is excluded from the estimate horizon." },

  { type: "spacer", h: 100 },
  { type: "callout", title: "Disclaimer", color: NAVY, text:
    "This report is for educational analysis only and is not investment advice or a research report under SEBI (Research Analysts) Regulations, 2014. It has not been prepared by a SEBI-registered Research Analyst. Treat it as business analysis, not investment research. Always do your own due diligence before investing." },
  { type: "callout", title: "AI disclosure", color: GOLD, text:
    "Artificial intelligence was used to prepare substantially all of the analysis in this report (in line with the disclosure expectation SEBI introduced for AI use in research preparation). AI systems can make mistakes: figures are extracted and cross-verified against cited source pages, but errors may remain. Every number carries a source reference — verify load-bearing figures against the cited page before relying on them." },
  { type: "text", opts: { italics: true, size: 17 }, text:
    "Validity: prepared on 2026-07-16 (the later of: dates in supplied research documents; run date). Company information changes with news flow and results; treat the analysis as decaying in reliability beyond ~12 months, and the market data as of its pull timestamp only. Sources: company documents supplied by the user (annual reports, quarterly filings, transcripts, presentations); exchange/regulator websites; market data via yfinance (timestamped); external research as cited with URL and access date. The preparer holds no position information and expresses no view on suitability for any investor. Full audit trail: dossier.md (global source legend §13); machine-readable estimates: handoff/valuation_handoff.json." },
];

module.exports = { masthead, title, blocks, footer: "NALCO — Equity Research (External)", outfile: "NALCO_ER.docx" };
