# Interpreting Sentiment-Cycle KPIs

How to read the sentiment/behavioral anchors defined in
`knowledge/data/kpis/` (india_vix, breadth_200dma, mf_retail_inflows,
fii_dii_flows). Engine mechanics:
`methodology/cycle_positioning_framework.md`; catalog entries:
`sentiment_behavioral_cycle`, `volatility_risk_regime_cycle`,
`fii_dii_capital_flows_cycle` in `knowledge/data/cycles/catalog.yaml`.
Companion: `methodology/narrative_intensity_scoring.md` (the qualitative
half of the same read).

## The cardinal rule: reliable at extremes, useless mid-range

Sentiment metrics are **most reliable near Phases 1 and 5 and are poor
mid-cycle timing tools — they can stay stretched for long stretches**
(framework section 3). A 60th-percentile VIX means nothing; a 97th
percentile VIX with three other extremes hitting simultaneously is a
regime signal. Confluence of extremes, not any single reading, is what
the framework acts on (section 4.4).

## India VIX (`india_vix`) — fear-type

- The "fear gauge": implied vol from Nifty options. **A spike above ~25
  signals severe panic — often a trough marker where maximum
  accumulation aggressiveness is warranted** (source-framework threshold,
  Phase-5 trigger; DRAFT until back-tested).
- Fear-type: INVERT before scoring. High VIX = capitulation =
  early-cycle opportunity; a long low-VIX grind = complacency, and is
  also a distinct RISK REGIME (position-sizing overlay via
  `volatility_risk_regime_cycle`) — low-vol grind and high-vol chop need
  different sizing at the same directional phase.
- The MISSING signal matters too: a market making new highs with VIX
  quietly rising off its floor is a classic Phase-2 divergence.

## Market breadth (`breadth_200dma`) — fear-type at the lows

- % of universe constituents above their own 200-DMA (50-DMA variant =
  faster confirmation read). Framework extremes: **<15% above 200-DMA =
  extreme oversold, bordering on a massive contrarian buy signal**;
  breadth NARROWING while the index holds up (leadership concentration)
  = the classic Phase-2 Distribution marker.
- Breadth is the honest version of the index: a cap-weighted index can
  be carried by a handful of names long after the median stock has
  rolled over. When index and breadth diverge, believe breadth.
- Derivable today from `daily_prices` (universe constituents' closes) —
  status `derivable`, a Phase-7 computation, not a new data source.

## Retail flows (`mf_retail_inflows`) — contrarian at extremes

- **Peak retail inflows concentrated in small/mid-cap funds AFTER those
  categories have already delivered outsized returns = "peak FOMO"**, an
  impending-top marker (Phase 1). The framework's "Reverse Asset
  Allocation" read: retail arrives at the top, capitulates at the bottom.
- The steady SIP base is NOT the signal — look at the marginal,
  category-switching flow (lump-sum surges into whatever just ran).
- IPO oversubscription (retail category) and new-account growth are
  corroborating markers from the same psychology.

## FII/DII flows (`fii_dii_flows`) — confirming, not originating

- **Flows chase returns: use to corroborate a call, never to generate
  one** (framework section 3). Rolling 3/6/12-month net flows as z-score
  vs a 5yr distribution.
- Capitulation extremes (record sustained FII outflows with domestic
  absorption) behave fear-type — they mark washouts. Trend-following the
  mid-range of flows is noise.
- FII and DII legs often oppose each other; the SPREAD between them is
  frequently more informative than either alone.

## Reconciling with the narrative read

The quantitative sentiment read and the Narrative Intensity Score
(`methodology/narrative_intensity_scoring.md`) are two halves of one
overlay: quant-cheap + narrative-still-dismissive is the contrarian sweet
spot (mandatory Pre-Mortem first); quant-expensive +
narrative-still-euphoric = reduce without waiting for narrative
confirmation, which always arrives after price.

## Common failure modes

1. Mid-range sentiment readings treated as signals (only extremes count).
2. Forgetting to invert fear-type metrics (a VIX spike read as euphoria
   inverts the entire output — the framework's canonical orientation
   error).
3. Trend-following flows (confirming indicator used as originating).
4. Single-metric extremes acted on without confluence.
5. Ignoring the vol REGIME (sizing overlay) because the directional read
   looks fine.
