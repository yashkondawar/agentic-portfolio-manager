# The Universal Cycle-Positioning Framework

A cross-asset decision-logic architecture for an AI-native investment system.

Verbatim source text: `docs/source-material/cycle-positioning-framework.txt`.
This file is a clean-markdown rendering of the same content for easier
in-repo reading and linking; if the two ever diverge, the `.txt` is
authoritative.

## 0. Scope, Lineage, and How to Use This Document

**What this is.** A reasoning framework — a set of definitions,
normalization methods, decision tables, and governance rules that convert
raw market/macro data into a position-in-the-cycle classification, and
that classification into allocation and selection logic. It is written to
be the "reasoning constitution" an AI investment system consults, not a
human-readable memo.

**What this is not.** This document contains no embedded tickers, no live
sector calls, no country-specific numbers beyond the illustrative
historical references already present in the source material it builds
on. Every specific number below is either (a) inherited directly from the
two source documents supplied, clearly flagged as such, or (b) an
illustrative default band that must be back-tested and calibrated against
real data before any capital is put behind it. Wherever this document says
"favor" or "reduce," it means a category of exposure defined by where it
sits in its own cycle, never a named instrument. The AI system consuming
this document is expected to supply the live universe, the live data, and
the live scoring — this document supplies the logic that turns that data
into a decision.

**Lineage.** This synthesizes three public bodies of thinking: Howard
Marks' writing on cycles and pendulum psychology; the yield-gap/valuation-
index style of dynamic allocation associated with S. Naren's contrarian
approach at ICICI Prudential AMC, whose recent commentary frames markets
as having moved from an easy, broad-based-gains phase into one requiring
meticulous, research-intensive stock selection in overlooked,
underperforming names; and the macro-thematic dashboard style of DSP
Mutual Fund's Netra/Navigator research series, which combines many
valuation, risk, and cycle indicators specifically to reduce reliance on
any single data point or prevailing narrative, without issuing directional
forecasts or return promises. What follows generalizes these public
philosophies into one asset-agnostic, machine-operable engine. It is an
independent synthesis, not a reproduction of any firm's proprietary model
or current portfolio.

**Standard institutional caveat.** This is a decision-support
architecture. It requires live data integration, back-testing of every
illustrative threshold, compliance/risk review, and a human governance
layer (Section 6) before any output drives real capital. Nothing here is
investment, legal, or tax advice.

## 1. First Principles

Four load-bearing ideas carry through everything below:

- **Forecasting is not the job; positioning is.** Precise macro prediction
  (exact GDP prints, exact rate paths) is largely unachievable with
  reliability. What is achievable is a probabilistic read of where a given
  metric sits relative to its own history and which direction it's
  moving. The system should never output "GDP will be X%" — it should
  output "the GDP cycle is in phase Y with confidence Z."
- **Mean reversion is the default hypothesis, not a certainty.** A sector,
  asset, or metric that has moved far from its own long-run behavior is
  more likely than not to revert — but "more likely than not" is not
  "certain," which is exactly why Section 6's Pre-Mortem exists.
- **"This time is different" is the correct default skepticism, held with
  humility.** Extrapolating a recent trend indefinitely is the most common
  institutional error. But because the historical window itself can
  occasionally break (regulation, disruption, a currency-regime change),
  the system must be able to test for a genuine structural break rather
  than assume one never happens.
- **Numbers describe the distribution; narrative tells you where the
  crowd stands inside it.** Two assets can have an identical valuation
  percentile and mean opposite things — one because nobody has noticed
  yet, one because everybody has already sold and it's a trap. Only a
  qualitative read of positioning and narrative separates the two. This
  is the entire justification for Section 2.5.

## 2. The Universal Cycle-Position Engine

This section answers the core design question directly: how do you take a
framework built around one number (the equity Yield Gap) and make it
apply to any asset, stock, index, sector, or country?

The answer is that Marks' cycle theory isn't really about equities — it's
about oscillation around an equilibrium, driven by reflexive human
behavior that overshoots in both directions. Anything with (a) a
measurable equilibrium/fair-value anchor and (b) participants whose
behavior can overshoot qualifies. Converting that into an algorithm takes
three moves.

### 2.1 Move One — The Anchor-Metric Abstraction

For any asset/cycle, identify the metric that plays the role the Yield
Gap plays for equities: a ratio or level with a meaningful long-run
equilibrium.

| Asset / Cycle type | Anchor metric that plays the "Yield Gap" role |
|---|---|
| Broad equity index | Yield Gap / BEER, or CAPE |
| Single stock or sector | P/E, P/B, EV/EBITDA vs. its own 5-10yr range, and vs. the market's |
| Currency | REER vs. its own 10yr average |
| Sovereign bonds / rates | Real policy rate vs. its own historical average; curve slope |
| Credit | Credit-to-GDP gap; high-yield spread |
| Gold / commodities | Real (inflation-adjusted) price vs. long-run trend; Gold-Silver Ratio vs. ~80:1 |
| Real estate | Rental yield minus mortgage rate (cap-rate spread) |
| GDP / growth | Output gap (actual vs. potential GDP) |

### 2.2 Move Two — Classify the Metric's Orientation

Not every anchor metric points the same way. Before scoring anything, tag it:

- **Value-type** (high reading = expensive/late-cycle): P/E, Yield Gap,
  REER overvaluation, credit-to-GDP gap, retail-inflow surge.
- **Fear-type** (high reading = distressed = early-cycle opportunity, i.e.
  invert before scoring): VIX, credit spreads, CDS spreads,
  redemption/outflow intensity.
- **Goldilocks-type** (both extremes are late-cycle stress; the middle is
  healthy, so score by distance from a target band, not by percentile
  direction): inflation, GDP growth rate itself, capacity utilization,
  capex-to-GDP.

Getting this tag wrong is the single most common way a generalized cycle
model breaks — treating a VIX spike as "euphoria" instead of
"capitulation" inverts the entire output.

### 2.3 Move Three — Normalize, Then Add Direction

For every correctly-oriented anchor metric:

- **Level:** compute its percentile rank over a lookback spanning at least
  one full historical cycle (10-20+ years, or full available history).
  Percentile rank is preferred over a raw z-score as the primary read
  because it's robust to fat tails; z-score is retained as a secondary
  cross-check.
- **Direction:** compute trailing 3-, 6-, and 12-month rate of change —
  rising, falling, or flat.
- **Momentum-of-momentum:** is that rate of change accelerating or
  decelerating?

Level alone is not the phase. A metric at the 20th percentile and falling
means something different from a metric at the 20th percentile and
turning up — this is exactly the distinction between "Value" (falling
into cheap) and "Attractive Growth" (rising out of cheap) even though both
sit in similarly low percentile territory.

### 2.4 The Eight-Phase Cycle Wheel

Crossing Level with Direction produces eight phases. This generalizes the
four phases (Value, Deep Value, Attractive Growth, Momentum) by adding
their four natural counterparts on the upper half of the wave.

| # | Phase | Position on the wave | Level (percentile, own history) | Direction | Illustrative quantitative trigger* | Qualitative / narrative marker | Default posture |
|---|---|---|---|---|---|---|---|
| 1 | Euphoria / Mania | Peak | >90th | Rising or flat-at-highs | Yield Gap >1.70; stock/sector P/E crossing the ~25x discomfort threshold; a "20-30 years of return in months" parabolic reading | "This time is different"; mainstream (non-financial) media coverage; product/IPO proliferation on the theme; leverage & new-account growth surging | Reduce toward the floor of the strategic range; systematic profit-booking regardless of narrative |
| 2 | Distribution | Just past peak | 75th-90th, stalling | Flattening / rolling over | Breadth narrows even as the index holds; credit spreads start widening while price is still near highs | Skepticism dismissed as "not getting it"; narrowing leadership | Continue trimming; rotate to quality/defensive tilt; raise hedges |
| 3 | Denial / Early Decline | Falling from the top | 55th-75th | Falling, still above average | Price falls, valuation still above its own long-run average | "Just a healthy correction" narrative with no fundamental improvement evidence | No fresh buying; do not average down pre-emptively; hold hedges |
| 4 | Value | Below average, falling | 20th-45th | Falling | Metric crosses below its own long-run average and keeps falling | Narrative turns cautious; outflows rising but not yet capitulatory | Begin staged, tranche-based accumulation |
| 5 | Deep Value / Capitulation | Trough, just before the turn | <10th-15th | Falling but decelerating (bottoming pattern) | Yield Gap <1.40; VIX >25; breadth extreme-oversold (e.g. <15% of names above their 200-DMA); several rare statistical extremes hitting simultaneously | "This asset class is dead"; forced/redemption-driven selling; no new product launches in the space; extreme underweight positioning | Maximum systematic accumulation, deployed in tranches |
| 6 | Attractive Growth / Early Recovery | Just after the trough | 15th-30th | Turning up | Early positive inflection in earnings/flow data while the metric is still cheap | "Dead cat bounce" skepticism; price stops making new lows despite still-negative headlines | Continue/accelerate accumulation as fundamentals confirm |
| 7 | Momentum / Confirmation | Rising through average | 45th-65th | Rising | Trend confirmed across price, breadth, and earnings revisions; metric crosses back above its own average | Narrative turns constructive, not yet euphoric; participation broadens | Ride the trend at normal-to-full strategic weight |
| 8 | Optimism / Belief | Rising, above average | 65th-85th | Rising, decelerating | Valuation rich but still "justified" by strong realized fundamentals | Herd participation broadens; skepticism gives way to endorsement | Begin trimming outsized winners; rebalance into laggards |

*Thresholds marked with specific numbers are inherited directly from the
source material (Yield Gap, VIX, breadth, P/E, parabolic-return examples).
Percentile bands are illustrative starting points — calibrate per asset
class via back-test, they are not universal constants.

### 2.5 The Qualitative / Narrative Overlay

Numbers alone can't tell you whether a historical range is still valid.
This is where an AI system's language-reasoning capability is a genuine
structural advantage over a traditional quant model — it can read news
flow, earnings-call transcripts, analyst notes, fund-flow commentary, and
retail sentiment, and score them.

- Markers of top-of-cycle psychology (Phases 1-2): narratives of
  structural permanence ("new paradigm," "structural re-rating");
  dismissal of valuation concerns as failure to understand a new reality;
  surging retail participation and leverage; proliferation of new
  products/instruments around the theme.
- Markers of bottom-of-cycle psychology (Phase 5): narratives of permanent
  impairment ("this is structurally broken," "nobody wants this"); forced
  or redemption-driven selling; capitulatory analyst downgrades even as
  operating metrics stabilize; an absence of new capital/product
  formation in the space.
- Markers of transition (Phases 3, 6): a persistent gap between price
  action and narrative — price stops falling despite continued bad
  headlines, or stops rising despite continued good ones; early, quiet
  positioning shifts ahead of broad recognition.

Score this as a Narrative Intensity Score (e.g. -100 to +100) derived from
systematic text analysis of the above categories, on the same phase scale
as the quantitative read. See `narrative_intensity_scoring.md` for the
detailed scoring rubric.

### 2.6 Reconciliation and Confidence

| Quantitative phase vs. Qualitative phase | Interpretation | Action |
|---|---|---|
| Aligned | High-confidence classification | Proceed at full conviction sizing per Section 5 |
| Quant reads cheap, narrative still dismissive/pessimistic | The classic contrarian sweet spot — the crowd hasn't repriced yet | Highest-conviction opportunity, but mandatory Pre-Mortem (Section 6.2) first, to rule out a genuine value trap |
| Quant reads expensive, narrative still euphoric | Late-cycle, textbook top-forming pattern | Reduce; do not wait for narrative confirmation, which arrives after price does |
| Ambiguous / conflicting in an unclear way | Genuine uncertainty | Lower confidence, smaller size, flag for human/deeper research review |

### 2.7 Fractal Application

This exact engine — anchor metric -> orientation -> percentile + direction
-> phase -> narrative overlay -> reconciliation — is applied identically at
every scope: broad market, sector, single security, country index,
currency, or commodity. Nothing changes structurally; only the anchor
metric and lookback window change. This is what makes it usable for "any
asset class or stock or index or sector or country specific index" — one
engine, many inputs.

## 3. The Cycle Catalog

The Valuation Cycle (Section 2's worked example) is one of many cycles
that need this treatment. The full 16-cycle catalog an AI system should
track (each scored through the Section 2 engine independently before
being combined in Section 4) is maintained as structured data in
`knowledge/data/cycles/catalog.yaml` — see that file for the
machine-readable version with anchor KPI cross-references. The narrative
table (primary anchor metrics, orientation, lookback, cadence, and
leads/lags for all 16 cycles) is preserved verbatim in
`docs/source-material/cycle-positioning-framework.txt` section 3.

The Three-Balance-Sheet meta-lens: the source material's
"Internal / External / Market" balance-sheet framing isn't a 17th cycle —
it's an organizing lens that maps directly onto Section 4's functional
groups: Internal balance sheet -> GDP/Business + Credit cycles; External
balance sheet -> Currency + Global Risk-Appetite cycles; Market balance
sheet -> Valuation + Sentiment + Flows cycles. Keeping this mapping
explicit prevents double-counting when cycles are combined below.

The Parabolic Return Compression Rule (generalized from the source's gold
example): if any asset delivers more than roughly its own long-run
average annual return compressed into a window of a few months (the
source's illustration: 20-30 years of typical return inside ~24 months,
200-400% appreciation), treat this as a structural Phase-1 signal and
trigger the systematic trim rule regardless of how compelling the
contemporaneous narrative is. This is a case where the "number"
(compression ratio) is deliberately given more weight than the "story,"
because parabolic moves are precisely where narrative is most persuasive
and most wrong.

## 4. Multi-Cycle Synthesis — Combining Everything Into One Flow

### 4.1 Functional Grouping

| Group | Cycles included | Question it answers |
|---|---|---|
| Macro-Regime | GDP/Business, Inflation, Rate/Liquidity, Credit/Debt | What's the economic weather? |
| Market-Structure | Valuation, Earnings/Margin, Sentiment/Behavioral, FII/DII Flows | Is the market/asset cheap or dear, and is money moving in or out? |
| External | Currency, Global Risk-Appetite/Dollar | What's happening to cross-border capital and the currency? |
| Idiosyncratic | Sector/Thematic, Commodity, Real Estate, Capex — scored at the relevant sub-portfolio level | Within the favored macro backdrop, what specifically looks attractive? |

### 4.2 Regime Classification

Use the Macro-Regime group alone to classify the prevailing backdrop into
one of five clusters: **Recovery -> Expansion -> Overheating -> Slowdown
-> Crisis/Capitulation**. This regime label determines how much weight the
other groups deserve — a cheap valuation means something different in a
Recovery than it does mid-Crisis.

### 4.3 Composite Score with Dynamic Weighting

Rather than fixed weights, weight the four functional groups by regime:

| Regime | Macro-Regime weight | Market-Structure weight | External weight | Why |
|---|---|---|---|---|
| Recovery | 30% | 45% | 25% | Valuation/Sentiment typically lead the turn; External confirms via currency bottoming |
| Expansion | 35% | 40% | 25% | Balanced — no single group dominates |
| Overheating | 45% | 35% | 20% | Macro imbalances (inflation, credit-to-GDP gap) become the binding constraint ahead of pure valuation |
| Slowdown | 40% | 40% | 20% | Earnings/Margin deterioration corroborates the Macro-Regime read |
| Crisis / Capitulation | 25% | 55% | 20% | Behavioral extremes become the single highest-value signal at true systemic troughs |

Treat these as priors to refine through back-tested optimization, not
fixed constants.

### 4.4 The Confluence / Alignment Score

Map each cycle's Phase to a simple directional lean (+1: Phases 5-7,
buy-favorable; 0: Phases 4, 8, ambiguous; -1: Phases 1-3, sell-favorable).
Alignment Score = the proportion of independently-scored cycles pointing
the same direction.

- High alignment, strong magnitude -> high-conviction call, larger
  tactical tilt.
- Low alignment / mixed signals -> stay close to strategic neutral
  weights, smaller tilts, mandatory Pre-Mortem before any shift.

This formalizes the "several statistical extremes hitting at once"
confluence logic that shows up in macro-thematic dashboards generally — a
single Phase-5 reading is a data point; five uncorrelated cycles
simultaneously reading Phase-5 is a regime signal.

### 4.5 Worked Logical Flow (illustrative, historical re-reads only)

- **2018 episode, re-read:** Rate/Liquidity cycle deteriorating (10Y yield
  6.46%->7.77%) while the Valuation-cycle anchor (equity earnings yield)
  stayed flat -> Yield Gap crosses past the 1.70 Phase-1/2 threshold ->
  Composite Score turns negative even before the Sentiment/Flows cycle
  turns — the engine would flag a defensive cut ahead of broad
  recognition, consistent with the source's 40%->20% clinical reduction.
- **2012 episode, re-read:** Currency/External cycle stressed (high CAD)
  simultaneously with the domestic Valuation cycle in Phase 4/5 -> a
  country-level Composite Score comparison (Section 5.2) tilts allocation
  toward markets/segments scoring better on the same composite —
  consistent with the source's rotation into IT and US-linked exposure.
- **Gold episode, re-read:** Commodity cycle triggers the Parabolic Rule
  override (Section 3) independent of what the Valuation-cycle percentile
  alone would say -> systematic trim from 20% to ~13%, benchmarked on
  standard fixing prices for consistency across the multi-asset sleeve.

## 5. From Cycle Position to Portfolio Action

### 5.1 Asset Allocation Engine

Illustrative bands, anchored to the source document's own thresholds —
calibrate before use:

| Composite reading | Regime label | Equity | Debt | Gold/REITs/InvITs | Cash/Arbitrage |
|---|---|---|---|---|---|
| Yield Gap <1.40 / Phase 5, high alignment | Deep Value / Capitulation | 70-90% | 5-15% | 5-10% | 0-5% |
| Value / Phase 4-6 | Value / Early Recovery | 55-70% | 15-25% | 8-12% | 0-5% |
| Neutral / Phase 6-7 | Momentum / Fair Value | 40-55% | 25-35% | 10-15% | 0-10% |
| Yield Gap >1.70 / Phase 1-2, high alignment | Distribution / Euphoria | 10-25% | 40-60%* | 10-20% | 5-15% |

*At the high-equity end of the range, tax-efficient implementation (see
5.5) can keep gross equity exposure near ~65% while net exposure runs as
low as 10-20% via cash-future arbitrage — a structural choice, not a
valuation call.

### 5.2 Country / Regional Allocation Engine

Apply Section 2's engine independently to each country's own Currency,
GDP, Valuation, and Flows cycles; rank countries by Composite Score to
guide relative allocation across a cross-border sleeve. This is the
identical mechanism used in the 2012 illustration above — it generalizes
to any country pair or basket, not just a single historical case.

### 5.3 Sector Rotation Reference (generic style factors — no named sectors)

This maps style/factor exposures, not specific industries, to
Business-Cycle phase. The live universe must be mapped onto these
categories using the Sector-Specific Cycle module (see
`knowledge/references/sectors/*.md`), not read off this table directly.

| Business-cycle phase | Style/factor exposures historically favored | Style/factor exposures historically reduced |
|---|---|---|
| Recovery | Rate-sensitive, high-operating-leverage cyclicals; deeply-discounted quality | Defensives priced as if the downturn is permanent |
| Expansion | Capex/investment-linked, margin-expansion beneficiaries | — (broad participation is typical) |
| Overheating | Pricing-power and real-asset/inflation-linked exposures | Long-duration growth names sitting in their own Phase-1 |
| Slowdown | Quality, low-leverage, high-FCF-yield compounders | High-operating-leverage cyclicals still priced for expansion |
| Crisis/Capitulation | Balance-sheet strength (high Cash/Total-Assets); the "neglected" cohort from 5.4 | Anything reliant on short-term/rollover-dependent financing |

### 5.4 Security Selection Funnel

See `funnel_4gate.md` for the full four-gate funnel (Cycle-Favorability,
Quality Screen, Idiosyncratic Value Screen, Neglect/Contrarian
Confirmation Screen) and sizing rule.

### 5.5 Multi-Asset Implementation Toolkit

- Cash-future arbitrage to preserve a tax-efficient equity-fund structure
  while running a materially lower net equity exposure than the gross
  figure implies.
- Tactical duration initiated when the Currency cycle's REER anchor
  bottoms relative to its own history, ahead of the capital-inflow
  response that typically compresses yields afterward.
- Standardized benchmarking (e.g. fixing-price conventions for gold) so
  the Commodity cycle's Parabolic Rule is measured consistently across
  the multi-asset sleeve rather than on a noisy spot quote.

## 6. Governance, Risk, and the AI Operating Protocol

### 6.1 Decision Checklist (procedural gate — run before finalizing any recommendation)

1. Is the signal corroborated by at least two independent cycle
   categories (one Macro-Regime + one Market-Structure), not valuation
   alone?
2. Has the qualitative Narrative Score been computed and reconciled
   against the quantitative phase (Section 2.6), with any divergence
   explicitly noted?
3. Does the normalization lookback span at least one full historical
   cycle, and has it been checked for an un-modeled structural break
   (regulatory reset, series redefinition, market-structure change)?
4. Is position size scaled to the Confidence/Alignment Score, not to
   narrative appeal alone?
5. If the Parabolic Return Compression Rule fired, was the systematic
   trim executed regardless of the prevailing narrative?
6. Is the call corroborated across at least two independent reporting
   periods, not one data point vulnerable to a one-off distortion?
7. Are the Currency/External and domestic cycles consistent, or does a
   conflict (e.g. cheap equity + currency stress) require an explicit
   hedge decision first?
8. Has the implementation/tax layer been checked so realized net exposure
   matches the model's intended exposure?
9. Does the shift exceed a human-in-the-loop threshold (6.3)? If so, is
   sign-off logged?
10. Is a dated, versioned rationale record being written for the
    post-mortem learning loop?

### 6.2 Pre-Mortem Protocol

For any allocation shift above a defined threshold, or any new
high-conviction security position: generate a written Pre-Mortem before
execution. Assume 12-24 months have passed and the position has
underperformed — articulate the single most plausible reason mean
reversion failed (permanent structural impairment, competitive
disruption, regulatory shock, an unmodeled break in the anchor metric's
own history). If a plausible, evidence-backed failure story emerges, the
system must do one of: reduce size, attach a specific monitoring trigger
tied to that failure story ("if metric X breaches Y, exit"), or escalate
to human review. This operationalizes the source material's "assume mean
reversion has failed" stress test for every cycle in this catalog, not
equities alone.

### 6.3 Position Sizing and Human-in-the-Loop Triggers

Illustrative sizing rule: Size multiplier = Confidence x Alignment (both
scaled 0-1), capped by standing concentration limits. Escalate to a human
reviewer when:

- any single rebalancing shift exceeds a defined percentage-point
  threshold;
- any anchor metric reads beyond roughly +/-3 standard deviations
  (possible data error or genuine regime break — both warrant a human
  look);
- Alignment Score is low but the recommended action size is not;
- a new sector/country exposure is being initiated for the first time; or
- a Pre-Mortem surfaces an unresolved plausible failure story.

### 6.4 Explainability and Audit Logging

Every output must log: which specific cycles and KPIs drove it, their raw
values, percentile/z-score, the qualitative markers detected, and the
final reconciliation. Versioned and timestamped. This is both a
governance requirement and the raw material for periodically checking
which cycles/KPIs were actually predictive, so the Section 4.3 weights
can be refined over time rather than held as permanent assumptions.

### 6.5 Suggested Output Schema

```
CycleAssessment {
  cycle_name: string
  scope: "market" | "sector" | "security" | "country" | "currency" | "commodity"
  as_of_date: date
  anchor_metrics: [string]
  orientation: "value" | "fear" | "goldilocks"
  lookback_window_years: number
  level_percentile: 0-100
  z_score: float
  direction_3m / direction_12m: "rising" | "falling" | "flat"
  momentum_state: "accelerating" | "decelerating" | "stable"
  quantitative_phase: enum[Euphoria, Distribution, Denial, Value, DeepValue, AttractiveGrowth, Momentum, Optimism]
  narrative_intensity_score: -100 to +100
  qualitative_markers_detected: [string]
  reconciled_phase: enum (same as above)
  confidence: 0-100
  contributing_kpis: [{name, value, weight}]
}

CompositeAllocationDecision {
  as_of_date: date
  scope: string
  regime_cluster: "Recovery"|"Expansion"|"Overheating"|"Slowdown"|"Crisis"
  cycle_assessments: [CycleAssessment]
  composite_score: -100 to +100
  alignment_score: 0-100
  recommended_action: { asset_class: allocation_% }
  position_size_multiplier: 0-1
  requires_human_review: boolean
  checklist_status: { item: pass|fail|na }
  pre_mortem_summary: string
  rationale_log: string
}
```

### 6.6 Cadence Summary

- **Daily:** volatility, breadth, curve slope, price-based valuation
  ratios, flow data.
- **Weekly:** cumulative flows, dollar-index trend.
- **Monthly:** inflation prints, PMI, REER, credit growth, retail-inflow
  trend.
- **Quarterly:** GDP, capacity utilization, corporate results/margins,
  NPA data, real-estate metrics.
- **Structural** (annual or event-triggered only): debt supercycle and
  demographic backdrop — these condition everything else but are not
  tactically actionable on their own.

## 7. Closing Scope Reminder

No ticker, sector, or country in this document represents a live
recommendation — every specific figure is either inherited from the
source material as a historical illustration or an explicitly-flagged
illustrative default requiring back-test calibration. This is a
decision-support reasoning layer for a system that still needs live data
feeds, back-testing, compliance review, and a human governance layer per
Section 6 before it touches real capital. Referenced past performance
(2001, 2007, 2012, 2018 episodes) illustrates how the mechanism would have
read those events, not a guarantee of how it will read the next one.

## Appendix: Ratios and KPIs (starting point, not exhaustive)

See `knowledge/data/kpis/*.yaml` and `knowledge/data/kpis/micro/*.yaml`
for the machine-readable versions of every KPI below, with current
sourcing status. Full descriptive text preserved in
`docs/source-material/cycle-positioning-framework.txt`.

1. **Macro & Systemic KPIs:** Yield Gap Ratio / BEER, Equity Valuation
   Index (EVI), Credit-to-GDP Gap, Yield Curve Shape, Real Effective
   Exchange Rate (REER).
2. **Micro & Company-Specific KPIs:** Price-to-Book Value (P/BV),
   Price-to-Earnings (P/E) & Shiller P/E (CAPE), Return on Equity (ROE) &
   Return on Capital Employed (ROCE), Free Cash Flow (FCF) Yield &
   Dividend Yield, Cash + Short Term Investments as % of Total Assets.
3. **Behavioral, Sentiment & Technical KPIs:** Retail Inflows & Reverse
   Asset Allocation, High-Yield Corporate Credit Spreads, Market Breadth
   (Moving Averages), India VIX.
4. **Asset Class Specific KPIs:** Real Estate Valuation Gap, Gold to
   Silver Ratio (GSR).
5. **Mutual Fund & Portfolio Performance KPIs:** Risk-Adjusted Returns,
   Upside and Downside Capture Ratios.
