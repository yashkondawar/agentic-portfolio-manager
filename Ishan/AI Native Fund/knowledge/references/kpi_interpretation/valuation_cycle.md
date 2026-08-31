# Interpreting Valuation-Cycle KPIs

How to read the valuation-cycle anchors defined in
`knowledge/data/kpis/` (yield_gap, evi, mcap_gdp, index_eps_growth,
gold_to_nifty, gsr, reer, and the sector P/E-P/B micro KPIs). The engine
mechanics live in `methodology/cycle_positioning_framework.md` sections
2.1-2.4; this guide is the interpretation layer on top.

## Yield Gap / BEER (`yield_gap`)

- **Definition**: 10Y G-Sec yield x Nifty trailing P/E (or equivalently,
  bond yield vs equity earnings yield). Source-framework thresholds:
  **<1.40 = equities deeply undervalued** (Phase-5-consistent; the
  framework's max-equity allocation band, 70-90%), **>1.70 = severely
  overvalued** (Phase-1/2-consistent; defensive shift toward debt).
- **Reading it**: it is a RELATIVE-value metric — equities vs bonds — not
  an absolute-cheapness metric. Both legs can be expensive (low rates,
  high P/E) and the gap can still look "normal"; always cross-check
  against the absolute P/E percentile before acting.
- **Thresholds are DRAFT**: inherited from the source material,
  calibrated to Indian history; must be back-tested before capital moves
  on them (framework section 0 caveat applies to every number here).
- **Current sourcing**: Nifty P/E is live in `index_data`; the G-Sec leg
  is a Phase-8 sourcing task (monthly FRED series per plan section C) —
  until then this KPI is `missing` and MUST NOT be fabricated.

## Equity Valuation Index (`evi`)

- Equal-weighted composite of P/E, P/B, (G-Sec Yield x P/E), Mcap/GDP —
  designed to filter out temporary accounting distortions any single
  ratio suffers (P/E during an earnings collapse, P/B during a
  revaluation). Read the composite percentile as
  Attractive / Neutral / Alert-Expensive bands.
- If a sub-component is missing (Mcap/GDP today), the composite must be
  recomputed on the available legs and *labeled as partial* — a silently
  degraded composite is worse than none.

## Index/sector P/E and P/B percentiles

- **Percentile-vs-own-history is the read**, not the absolute number: a
  22x P/E means nothing until placed against that index's own 5-10yr
  distribution (`index_data` now holds 2016-2026 daily P/E for NIFTY
  50/500 and the 8 sector indices).
- **Level + direction together** (framework section 2.3): 20th percentile
  AND falling = Phase 4 (Value); 20th percentile AND turning up = Phase 6
  (Attractive Growth). Never classify on level alone.
- **Methodology break caveat**: NSE moved index P/E from standalone to
  consolidated earnings around April 2021 — a level shift, not a market
  signal. Rows carry `source` provenance
  (`backfill_niftyindices_daily_snapshot`) so percentile windows can be
  scoped if the shift matters for a given index. Check before trusting a
  10-year percentile that straddles the boundary.
- **Sector overlay**: a sector P/E percentile is read RELATIVE to the
  market's percentile as well as its own history — a sector at its 60th
  own-percentile while the market sits at the 90th is relatively cheap.

## Mcap/GDP (`mcap_gdp`) and CAPE

- Slow, structural metrics — quarterly at best. Use to condition the
  faster reads, not to time anything. CAPE's role: prevents being tricked
  by temporarily bloated margins at expansion peaks.

## Cross-asset relative value (`gold_to_nifty`, `gsr`)

- Regime hints, not trade signals: a rising gold-to-Nifty ratio with an
  equity Phase 1-2 read is confluence toward defensiveness. GSR ~80:1
  long-run average; <50:1 flags silver speculative froth.
- Gold is the framework's canonical Parabolic-Rule asset: if gold
  delivers decades of average return inside months, the trim rule fires
  regardless of narrative.

## REER (`reer`)

- Valuation metric for the CURRENCY, feeding the currency/external cycle;
  a REER bottom vs own 10yr history historically precedes capital-inflow
  turns (framework 5.5: tactical-duration trigger).

## Common failure modes

1. Reading absolute multiples without percentile context.
2. Classifying on level without direction (Value vs Attractive Growth).
3. Trusting a composite silently missing a leg.
4. Ignoring the Apr-2021 P/E methodology break.
5. Treating relative-value (yield gap) as absolute cheapness.
