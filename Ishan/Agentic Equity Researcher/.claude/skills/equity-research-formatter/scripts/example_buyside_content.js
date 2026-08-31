const { NAVY, GOLD, AMBER, RED } = require("./reportStyle.js");

const masthead = ["Buy-Side Research", "Independent Note \u2014 EPS-Bridge Doctrine \u2014 Internal"];
const title = [
  "National Aluminium Company Limited",
  "NSE: NATIONALUM  |  Metals & Mining \u2014 Aluminium  |  India  |  15 July 2026",
  "NALCO \u2014 Buy-Side EPS-Bridge Note",
];

const blocks = [
  { type: "tombstone", fields: [
    ["Recommendation", "AVOID (do not initiate)"],
    ["Conviction", "0.72"],
    ["CMP", "\u20b9361.65"],
    ["Base Target", "\u20b9248.32"],
    ["Downside", "~31%"],
    ["Fwd P/E vs 5y Median", "11.0x / 11.7x  vs.  7.58x"],
  ]},
  { type: "text", opts: { italics: true, size: 19 }, text:
    "Independent buy-side rerating call on National Aluminium Company Ltd (NSE: NATIONALUM). CMP \u20b9361.65 (2026-07-15). Basis: consolidated estimates, standalone historicals where noted. All facts cite the handoff/dossier registry. This note is independent of the sell-side REDUCE and reaches its conclusion from the EPS-bridge doctrine alone." },

  { type: "heading", text: "Verdict up front", number: 1 },
  { type: "text", text:
    "Recommendation: AVOID (do not initiate at CMP). Conviction 0.72. This is not a quality verdict \u2014 the business is sound. It is a rerating verdict, and the rerating case fails at the first rung. Under the doctrine, PE re-rates only when EPS growth is consistent and >20% while the starting PE is low relative to that growth. NALCO offers a base-case 2yr EPS CAGR of \u22120.98% (F-EST-01) at a fwd PE of 11.0x/11.7x (S1396/S1397) \u2014 flat-to-down earnings at a multiple that is ~2x the stock's own five-year band ceiling (4.6x\u20138.7x, median 7.6x; pe_bands). Every ingredient the doctrine requires for a rerating is inverted: growth is absent, and the starting multiple is already at a record high. This is a de-rating setup, not a re-rating one." },

  { type: "heading", text: "The EPS = Price \u00d7 PE frame \u2014 the rerating condition fails on both legs", number: 2 },
  { type: "text", text:
    "The one PASS in the checker (eps_growth_20pct, FY2025 +164.82%) is a thin, single-year print and the doctrine explicitly disqualifies it: \u201ca single strong year is not consistency.\u201d That +165% was a cyclical LME/alumina realization spike (EBITDA margin 24.9%\u219244.6%, +1,966bps, F-DER-FUN-03/04), not a structural step-up \u2014 and the reversal is already visible (Q4 FY2026 PAT \u221217.4% YoY, S693). The revenue_growth_consistency rule correctly FAILs (FY2024 \u22127.76% breaks the floor; the five-year series is 58.7/0.3/\u22127.8/27.7/6.3 \u2014 the signature of a price-taker, not a compounder). Consistency is the gate, and NALCO does not clear it. Starting PE is not low relative to growth; it is high relative to no growth." },

  { type: "heading", text: "EPS decomposition ladder (volume / price / mix / cost / leverage)", number: 3 },
  { type: "text", size: 19, text:
    "The deterministic checker is 1 PASS / 1 FAIL / 7 NA \u2014 the seven NAs are extraction-sparsity artifacts, not passes. Bridge reconstructed from the handoff and dossier:" },
  { type: "table", headers: ["Lever", "Read"], opts: { colAligns: ["left","left"], colWeights: [1, 3.2] }, rows: [
    ["Volume", "Only credible growth lever. Metal volumes near rated smelter capacity (~4.6\u20134.7 lakh MT), guidance credibility high (470K guided vs 471K actual, <0.3% miss). But capacity-constrained volume caps upside \u2014 it cannot compound."],
    ["Price", "The dominant and uncontrollable driver. Realization is spot/LME-linked, repriced every 3 days, near-zero hedging. Base case anchors to World Bank/Platts normalization off the FY26 peak \u2014 a fade, not a tailwind. Alumina structural oversupply (Indonesian ramp to 7 MTpa by CY2026) compressed the alumina-to-LME premium from 15\u201317% to 11\u201311.5%."],
    ["Mix", "Shift to 73/27 metal/alumina is framed as margin-supportive, but segment-EBIT data is non-monotonic (Aluminium EBIT share fell 61.2%\u219255.5% FY24\u2192FY25) \u2014 the mix story is not a clean, durable margin driver."],
    ["Cost", "The genuine positive. Caustic soda 121\u219299 kg/t (~\u20b9129cr); captive coal +41.84% YoY toward ~4 MTpa; Pottangi captive bauxite (MDO awarded Dec-2025) as a medium-term input-cost offset. A cost-structure moat that defends margin in a downturn \u2014 it does not drive earnings growth or justify multiple expansion (moat composite 4.3/10)."],
    ["Operating leverage / D&A", "No operating-leverage tailwind ahead (revenue flat FY27E\u2192FY28E, \u22121.25%). D&A rises 745\u2192857\u2192895, a mechanical drag on EPS as capacity depreciates ahead of the ramp."],
  ]},
  { type: "callout", title: "Bridge verdict", color: NAVY, text:
    "Volume capped, price fading, mix ambiguous, cost helpful but defensive, leverage negative. The bridge does not build to >20% consistent EPS growth \u2014 it builds to roughly flat." },

  { type: "heading", text: "Funding discipline & working capital (doctrine rungs iii\u2013iv)", number: 4 },
  { type: "text", text:
    "These rungs are where NALCO scores best, but they are not rerating catalysts. Funding-quality hierarchy: tier 1 (internally funded) \u2014 near-debt-free (D/E ~0.0, interest coverage 152x\u2013172x FY22/23; interest just \u20b959\u2013129cr against EBITDA ~\u20b98,600cr). The 5th-stream capex has been self-funded from operating cash. This is the best rung on the sheet \u2014 but a pre-existing multi-year condition (F-FUND-07), so it cannot explain a rerating over the last 12\u201318 months. No dilution risk (GoI-majority, no ESOP/QIP). CFO positive through expansion (FY2025 CFO \u20b95,806cr). Working capital immaterial \u2014 DSO ~4 days on ~1.1% of sales; the DSO flags (RF-002/003) were dismissed on materiality. A clean, near-debt-free balance sheet with disciplined funding is a floor under the business, not a lever under the multiple." },

  { type: "heading", text: "Qualitative gate (doctrine rung v) \u2014 split verdict, growth lever fails", number: 5 },
  { type: "text", text:
    "The doctrine requires management to be actively delivering the exact strategies (positioning, share capture, portfolio expansion) with a delivery-vs-promise track record. NALCO splits: passes on what it controls \u2014 metal volume (high credibility) and cost efficiency (medium-high, captive coal delivered). Fails on the single largest swing factor. The 5th-stream alumina refinery \u2014 the only near-term growth lever \u2014 has low guidance credibility: contribution cut ~40% in-year (500kt\u2192300kt\u2192200kt, RF-GUI-01 confirmed), commissioning slipped from the guided Jun-2026 date and remains unconfirmed as of Jul-2026, consistent with an ~18-month historical slippage pattern. Capex overruns ~20% recurringly (F-FUND-04). Governance is Amber (73.3) with a confirmed, fined LODR board-composition breach (F-EXT-1155) and an open CBI probe (F-EXT-1156). Per the doctrine: \u201ca numerically clean bridge from a management team that fails this gate is not sufficient on its own.\u201d Here the bridge is not even clean and the growth-lever gate fails. Management's own tone is \u201cBullish/self-confident\u201d precisely on the lowest-credibility families." },

  { type: "heading", text: "What entry price/multiple would make this attractive", number: 6 },
  { type: "text", size: 19, text:
    "Under the doctrine, absent consistent >20% growth, the only route to attractiveness is a low starting PE \u2014 mean-reversion to the cyclically-appropriate band, not a rerating. On base FY27E EPS 32.76:" },
  { type: "table", headers: ["Multiple", "P/E", "Implied Price", "Read"], opts: { colAligns: ["left","center","center","left"], colWeights: [1,0.7,1,2] }, rows: [
    ["5y median", "7.6x", "~\u20b9249", "Fair-cycle value"],
    ["p75", "8.2x", "~\u20b9269", "Upper-cycle, still a discount to CMP"],
    ["5y max", "8.66x", "~\u20b9284", "Ceiling the stock has ever paid; still ~21% below CMP"],
  ]},
  { type: "text", text:
    "An accumulate-worthy entry under this doctrine would require CMP near \u20b9250\u2013270 (median-to-p75 on base EPS), i.e. a 25\u201330% de-rating from here \u2014 OR a confirmed rerating catalyst (5th-stream commissioned and ramping, credit-rating upgrade, or index-weight change), of which peer-valuation found none (F-VAL-05). CMP at 11.0x/11.7x fwd is pricing bull-case optionality the numbers do not support." },

  { type: "heading", text: "Scenario inputs (traceable) and base target", number: 7 },
  { type: "table", headers: ["Scenario", "FY27E EPS", "FY28E EPS"], opts: { colAligns: ["left","center","center"] }, rows: [
    ["Bear", "24.04", "21.26"],
    ["Base", "32.76", "31.05"],
    ["Bull", "\u2014", "42.42"],
  ]},
  { type: "table", headers: ["Min", "P25", "Median", "P75", "Max"], opts: { colAligns: ["center","center","center","center","center"] }, rows: [
    ["4.61x", "6.39x", "7.58x", "8.20x", "8.66x"],
  ]},
  { type: "text", size: 18, opts: { italics: true, size: 18 }, text:
    "EPS scenarios: S1394/S1395/S1391/S1390/S1393. PE scenarios: the full 5y historical band (min/p25/median/p75/max, pe_bands), deliberately anchored to history rather than the CMP-implied 11.0x, because the doctrine rerates only on earned consistency, which is absent." },
  { type: "callout", title: "Base target: \u20b9248.32", color: GOLD, text:
    "Base FY27E EPS 32.76 \u00d7 5y-median 7.58x \u2014 a grid cell, and the doctrine-consistent fair value. This is ~31% below CMP." },
  { type: "callout", title: "Invalidation", color: AMBER, text:
    "5th-stream refinery confirmed commissioned AND ramping \u2265200kt within one quarter of a re-guided date (Q1 FY27 call, ~Aug-2026), OR LME aluminium sustained >$3,300/t with alumina premium re-widening above 15% \u2014 either would move base EPS toward the bull path and re-open the rerating case." },

  { type: "heading", text: "Bridge summary", number: 8 },
  { type: "table", headers: ["Rule", "Verdict", "Read"], opts: { colAligns: ["left","center","left"], colorizeCol: 1, colWeights: [1.4,0.9,2.3] }, rows: [
    ["revenue_growth_consistency", "FAIL", "FY24 \u22127.8% breaks floor; price-taker volatility"],
    ["eps_growth_20pct", "PASS (thin)", "Single-year cyclical spike, not consistency"],
    ["gross_margin_trend", "NA", "Sparse cost data \u2014 not a pass"],
    ["receivables_pct_revenue_trend", "NA", "Immaterial (~1.1% of sales)"],
    ["interest_vs_ebit_growth", "NA", "Near-debt-free; qualitatively clean"],
    ["dilution_consecutive", "NA", "No dilution (GoI-majority)"],
    ["cfo_positive_expansion", "NA", "CFO positive; <3 capex periods"],
    ["dna_adjusted_eps_growth", "NA", "D&A rising \u2014 flagged as EPS drag"],
    ["interest_coverage", "NA", "Coverage 152\u2013172x historically"],
  ]},

  { type: "callout", title: "Bottom line", color: NAVY, text:
    "A well-built, cheap-fuel, near-debt-free ship on a sea it cannot control (dossier \u00a711). Sound hull, no wind. The rerating case fails the consistency gate and the starting-multiple gate simultaneously; the qualitative gate fails on the one growth lever that matters. AVOID at CMP; re-engage near \u20b9250\u2013270 or on a confirmed 5th-stream/price catalyst." },

  { type: "spacer", h: 60 },
  { type: "text", size: 17, opts: { italics: true, size: 17 }, text:
    "Internal buy-side research note. Not investment advice; prepared with AI assistance and cross-checked against the source dossier. Full audit trail and source registry: forensic dossier (companion document), \u00a713." },
];

module.exports = { masthead, title, blocks, footer: "NALCO \u2014 Buy-Side Note (Internal)" };
