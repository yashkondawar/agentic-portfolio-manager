# Interpreting Rate & Liquidity-Cycle KPIs

How to read the interest-rate/liquidity and inflation anchors defined in
`knowledge/data/kpis/` (curve_slope, cpi_yoy, dxy). Engine mechanics:
`methodology/cycle_positioning_framework.md`; catalog entries:
`interest_rate_liquidity_cycle`, `inflation_cycle`,
`global_risk_appetite_dollar_cycle` in
`knowledge/data/cycles/catalog.yaml`.

## Why this cycle gets extra weight

The rate/liquidity cycle **leads the credit and valuation cycles,
typically by 6-18 months** — it is one of the few genuinely leading
inputs in the catalog. The 2018 worked example (framework section 4.5) is
the canonical illustration: the 10Y yield moving 6.46%->7.77% while
equity earnings yield stayed flat pushed the Yield Gap through the 1.70
threshold BEFORE sentiment or flows turned.

## Yield curve slope (`curve_slope`)

- 10Y minus 2Y G-Sec spread. **Inversion (negative spread) is a classic
  leading recession indicator** — a fear-type event even though the level
  itself is scored value-type.
- Steepening from inversion matters as much as the inversion: a
  bull-steepening (short rates collapsing) usually means the central bank
  is already responding to weakness — Phase 5-6 territory for risk
  assets; a bear-steepening (long rates rising on supply/inflation fear)
  is a different, hostile regime.
- Daily cadence; percentile over 15-20yrs so at least one full rate cycle
  is in the window.

## Real policy rate (context, not yet a seeded KPI)

- Repo rate minus CPI YoY vs its own history: high real rates = late
  tightening cycle (restrictive, equity headwind but a coiled spring for
  the next easing); deeply negative real rates = emergency accommodation
  (early-cycle fuel, late-cycle inflation risk).

## CPI YoY (`cpi_yoy`) — a goldilocks-type metric

- Scored by **distance from the RBI's 4% +/- 2pp target band**, NOT by
  percentile direction. Both tails are late-cycle stress: high inflation
  forces tightening; deflation signals demand collapse.
- Inflation LEADS the rate cycle via the central-bank reaction function —
  a CPI trend break is an early input to the rate-cycle read, not a
  separate story.
- Watch the core-vs-headline gap: headline spikes from food/fuel that
  core doesn't confirm are usually looked through by the RBI; core
  breakouts are not.

## DXY / US real yields (`dxy`)

- An EXTERNAL CONDITIONING variable for India, not a domestic signal: a
  strong/rising dollar plus rising US real yields = tighter global
  liquidity for EM — historically hostile to Indian flows and the rupee
  regardless of domestic fundamentals.
- Read jointly with the currency cycle (`reer`) and flows
  (`fii_dii_flows`): dollar strength + REER richness + FII outflows is a
  three-way confluence against domestic risk; dollar rolling over while
  REER is washed out is the classic EM-inflow setup.

## Systemic liquidity (context, not yet a seeded KPI)

- Banking-system liquidity surplus/deficit (LAF absorption/injection) is
  the fastest-moving liquidity read; sustained deficit while credit
  growth runs hot = late-cycle squeeze.

## Common failure modes

1. Scoring inflation by percentile direction instead of
   distance-from-band (orientation error — the framework's canonical
   example of a broken read).
2. Treating an inversion as just a "low percentile" of slope rather than
   a regime event.
3. Reading DXY as a value signal for the dollar itself rather than as an
   EM-liquidity conditioning variable.
4. Ignoring the 6-18 month lead: acting on rate-cycle turns with
   valuation-cycle immediacy.
