# Interpreting Credit-Cycle KPIs

How to read the credit/debt-cycle anchors defined in
`knowledge/data/kpis/` (credit_to_gdp_gap, hy_spreads) and the sector
credit micro-KPIs (bfsi_gnpa, generic_net_debt_to_ebitda,
infra_receivable_days). Engine mechanics:
`methodology/cycle_positioning_framework.md`; catalog entry:
`credit_debt_cycle` in `knowledge/data/cycles/catalog.yaml`.

## Why this cycle matters most at extremes

The credit cycle is **the best early-warning indicator of systemic
stress** in the catalog. Credit excess builds slowly and quietly (the
"benign" phase feels like prosperity), then unwinds fast. Its signals are
asymmetric: mid-range readings carry little information; tail readings
carry the most information of any cycle.

## Credit-to-GDP gap (`credit_to_gdp_gap`)

- Current credit-to-GDP ratio minus its HP-filtered long-term trend
  (lambda ~400,000, the Basel convention). **A gap exceeding ~10
  percentage points is the BIS early-warning threshold** for a probable
  severe bust — historically the most accurate single predictor of
  systemic banking crises.
- Value-type: a large POSITIVE gap = late credit cycle (over-leveraged
  system), a deeply negative gap after a bust = early-cycle repair
  (lenders able but unwilling — the contrarian's raw material).
- Quarterly, slow — a regime conditioner, not a timing tool. The 50-75yr
  debt supercycle behind it is background context only, never tactically
  actionable (framework section 3).

## High-yield spreads (`hy_spreads`) — fear-type

- HY corporate yield minus matching-tenor G-Sec. **Fixed-income markets
  are forward-looking: equity at highs + spreads actively widening =
  smart money pricing deterioration equity hasn't acknowledged** — the
  framework's Phase-2 (Distribution) marker.
- Invert before scoring (fear-type): spread blowouts are
  capitulation/opportunity at the wides, complacency at the tights.
  Spread COMPRESSION from wides is the early-recovery confirmation.
- Tight spreads carry information too: multi-year tights = no
  compensation for credit risk = late-cycle complacency, even if nothing
  breaks for a while (fear-type metrics can stay stretched — poor
  mid-cycle timing tools, per the framework's sentiment-cycle caveat).

## NPA / asset-quality cycle (sector level: `bfsi_gnpa`)

- GNPA is a LAGGING confirmation — NPAs are recognized quarters after the
  underlying stress. Use for cycle-phase confirmation, never early
  warning. The leading versions: credit growth vs deposit growth
  divergence, unsecured-mix expansion, and vintage seasoning disclosures
  (see `sectors/bfsi.md`: easy-money vintages sour later).
- Provision coverage (PCR) qualifies the GNPA print: falling GNPA with
  falling PCR is cosmetic, not real, improvement.

## Corporate leverage (sector level: `generic_net_debt_to_ebitda`)

- Read against the sector's own norm (an EPC name and an FMCG name at
  the same Net Debt/EBITDA are in different worlds) and against the
  RATE cycle: leverage that services comfortably at 6% repo breaks at 9%.
- Aggregate corporate deleveraging after a bust is the quiet setup for
  the next capex cycle — cross-read with `capex_investment_cycle`.

## Working-capital stress (sector level: `infra_receivable_days`)

- Receivable-days expansion is the credit cycle transmitting through the
  REAL economy: slow-paying counterparties (state bodies especially) push
  stress onto contractor balance sheets long before it appears in bank
  NPAs.

## Common failure modes

1. Treating mid-range credit readings as informative (they aren't; tails
   are).
2. Using GNPA as early warning (it's a lagging confirmation).
3. Scoring spreads value-type instead of fear-type (inverts the read).
4. Trading the debt supercycle (context only, never actionable).
5. Reading leverage without the rate cycle next to it.
