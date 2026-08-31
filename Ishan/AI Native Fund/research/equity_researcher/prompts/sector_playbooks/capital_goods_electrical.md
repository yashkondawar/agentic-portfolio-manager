# Sector Playbook — Electrical capital goods (T&D equipment)

*Tier 2. Family: `infra_capital_goods` (`prompts/sector_packs/infra_capital_goods.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — APAR Industries (Nuvama, Jan-25 — the corpus's **best** worked SOTP,
with per-segment peer anchoring, and the note `docs/ER_CORPUS_FINDINGS.md` §4.1 cites as the most
rigorous valuation justification in the whole corpus; plus ICICI Securities, Feb-26), Voltamp
Transformers (Nuvama, Dec-25), Bharat Bijlee (Sushil Finance, Oct-22), Thermax (JM Financial, Jan-26),
Orient Electric (Equirus, Jul-19).

## The economic engine
An electrical capital-goods maker sits between a **commodity input it cannot control** and a **capex cycle
it cannot influence.** Most of these businesses — conductors, cables, transformers, switchgear — convert
metal into engineered product, so the economics are a per-tonne conversion spread wrapped in an order book:

`EBITDA = volume (tonnes) × EBITDA per tonne` — where the metal itself is substantially passed through

**The single most important structural fact: revenue is a poor measure of this sector's performance,
because the metal price flows through it.** When aluminium or copper rises, revenue rises with no
economic gain. So:

> **Analyse volume and EBITDA per tonne. Treat revenue growth as almost uninformative.**

APAR's own model makes this explicit — the note forecasts **EBITDA/mt of INR 38,000 → 40,000** for
conductors alongside an EBITDA *margin* that falls 9.3% → 8.9%. **Those two facts are consistent and
together they are the whole insight**: rising metal prices depress the percentage margin while per-tonne
profitability improves. A note reading only the margin line would report deterioration where there is
improvement.

Two more features:

- **The portfolio is usually multi-segment with genuinely different economics**, which is why SOTP is the
  convention here (see below). APAR is simultaneously India's largest conductor maker, the #1 exporter of
  cables & wires, and the world's third-largest transformer-oil manufacturer — three businesses with
  three peer sets. Conductors ~48% of revenue, oils ~26%.
- **Product-mix upgrade is the durable margin story.** Moving from plain ACSR conductors to
  high-efficiency/high-temperature conductors, from LT to HT and specialty cables, from distribution to
  power transformers — each step raises realisation per tonne and narrows the competitive set. This is
  the sector's equivalent of `auto_ancillary`'s value curve.

## Analysis sequence
1. **Segment the business by revenue, EBITDA and EBITDA per tonne** — and identify each segment's own
   peer set, because that is what the valuation will need.
2. **Volume and realisation per tonne by segment**, then EBITDA per tonne. Build the series for as many
   years as available. This is the core analytical artefact.
3. **Separate metal pass-through from conversion margin.** Establish the contractual mechanism — price
   variation clauses indexed to LME/domestic metal, formula-based pass-through, or fixed-price with
   hedging — and the lag. Then compute the conversion spread net of metal.
4. **Product-mix ladder** — the share of high-value-added product in each segment and its trajectory.
   APAR's thesis rests on demand for "high value-added/efficient conductors"; quantify the mix, don't
   accept the adjective.
5. **Order book and the demand pipeline** — order book by segment with execution schedule, plus the
   upstream capex drivers: transmission-line award tenders, discom distribution capex (RDSS), renewable
   evacuation build-out, and **re-conductoring** of existing lines (APAR names re-conductoring and export
   pickup as the key catalysts). Size the addressable opportunity where the note can: APAR's is put at
   INR 3.2-5.1tn for conductors and INR 10-12tn for domestic cables & wires.
6. **Exports, separately and carefully.** Export share, geography, margin versus domestic, and the trade
   exposure (antidumping, tariffs, freight). Exports in this sector often carry better margins and are the
   swing factor in a domestic downcycle.
7. **Capacity and utilisation by segment**, with the expansion pipeline and capex per tonne.
8. **Working capital**, which is heavy: receivables from utilities and EPC contractors, inventory carrying
   metal price risk, and the hedging policy. Metal inventory is a commodity position whether the company
   calls it one or not.
9. **Then SOTP by segment.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Order book** | unexecuted confirmed orders, by segment | INR cr | With execution schedule and segment split. Read alongside the upstream award pipeline (transmission tenders, RDSS) rather than in isolation | Company disclosure |
| **Capacity utilisation** | production / installed capacity, by segment | % | The operating-leverage variable and the constraint on accepting orders. Note that conductor and cable capacity is not interchangeable | AR capacity table |
| **Realisation per tonne** | segment revenue / tonnes sold | INR/t | Against the metal index. **A rise that matches the metal index is pass-through, not pricing power**; a rise above it is mix or price. Separate them explicitly | Computed |
| **EBITDA per tonne** | segment EBITDA / tonnes sold | INR/t | **The sector's true performance metric** (APAR conductors: INR 38,000 → 40,000/mt). Report it beside EBITDA margin % and explain the divergence — margin can fall while per-tonne profit rises | Computed |
| **Export share** | export revenue / total revenue | % | With margin versus domestic and the trade-remedy exposure by geography. APAR is India's #1 cables & wires exporter, and export pickup is a named catalyst | Segment reporting, decks |

## Supporting KPIs
Volume by segment and product grade; revenue mix by segment (APAR: conductors ~48%, oils ~26%);
high-value-added product share within each segment; EBITDA margin by segment (conductors ~9%, oils ~6%
for APAR — the spread between segments is the reason SOTP is needed); metal cost as % of revenue and the
pass-through mechanism and lag; price-variation-clause coverage of the order book; hedging policy and
open metal position; capacity by segment and plant with utilisation; capex per tonne and commissioning
dates; export revenue by geography with margin; antidumping/safeguard exposure and expiry dates;
receivable days by customer type (utility / EPC / private / export) with ageing; inventory days and metal
inventory in tonnes; net working capital as % of revenue; net debt/EBITDA and interest cover; bank-guarantee
and LC utilisation; ROCE by segment; fixed-asset turnover; customer concentration; R&D and product-approval
status for new grades; power and freight cost per tonne.

## Standard exhibit set
Volume, realisation per tonne and **EBITDA per tonne by segment** as three series (the sector's defining
exhibit) · **EBITDA per tonne against EBITDA margin % on one chart, with the metal index overlaid** — the
exhibit that prevents the margin-percentage misreading · realisation per tonne against the aluminium/copper
index with the pass-through lag annotated · revenue and EBITDA mix by segment · high-value-added product
share by segment · order book by segment with execution schedule · **the upstream demand pipeline:
transmission-line awards, RDSS/discom capex, renewable evacuation, re-conductoring** · addressable-market
sizing by segment · capacity and utilisation by segment with the expansion pipeline · export share and
margin by geography with trade-remedy expiry dates · receivable ageing by customer type · metal inventory
position and hedging · working-capital days · segment ROCE · net debt/EBITDA · **the SOTP table with each
segment's peer set named and its multiple justified** · blended implied P/E as a sanity check.

## Valuation convention
**SOTP with a peer-anchored multiple per division — and this is the corpus's single best example of the
practice, so follow it closely.** APAR Industries (Nuvama, Jan-25): conductors valued at **45x** against
T&D equipment peers trading **above 50x**; the oils division at **20x**, "largely in line with peer Savita
Oil"; blended to a **38x** FY27E EPS target and an SOTP-based TP of **INR 12,700**.

`docs/ER_CORPUS_FINDINGS.md` §4 ranks this as the most rigorous of the four justification families —
**segment-specific peer anchoring** — precisely because each leg is separately defensible and the blend is
published rather than assumed. Three things it does that our notes must do:

1. **Each segment gets its own named peer set**, not a house-wide multiple.
2. **The multiple is positioned relative to those peers with a stated reason** (45x *against* peers above
   50x — a deliberate discount, explained).
3. **The blended multiple is published** as a sanity check on the parts.

*Traps:* (i) **valuing the whole company on one multiple** when a conductor business at ~9% EBITDA margin
and a transformer-oil business at ~6% with different growth and different peer sets are bolted together;
(ii) reading falling EBITDA margin % as deterioration when EBITDA per tonne is rising — the metal-price
artefact; (iii) capitalising a metal-price-inflated revenue base; (iv) crediting a transmission-capex
supercycle at peak order-inflow multiples (`cyclical-peak` applies to the order cycle);
(v) valuing export margins as durable without checking antidumping expiry and freight; (vi) ignoring the
open metal position, which can turn a conversion business into a commodity bet.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. A blended 38x FY27E EPS is applied.**
- *A house-wide multiple, reasonably struck* (`peer_set_choice`).
- *Only defensible because it was built up, not assumed* (`peer_set_choice`) — APAR
  Industries (Nuvama, Jan-25) is the corpus's single best SOTP: conductors at **45x** against
  T&D equipment peers trading above 50x, the oils division at **20x** "largely in line with
  peer Savita Oil", blended to 38x and an SOTP-based TP of INR 12,700. Segment-specific peer
  anchoring ranks first of the four justification families precisely because each leg is
  separately defensible and the blend is published rather than assumed.
- *Discriminator* (`peer_distribution`) — a named peer set per segment. A blended multiple
  with no build-up behind it is an assertion.

**2. The order book grew 35%.**
- *Structural growth* (`growth_durability`).
- *A capex cycle* (`cycle_position`) — T&D ordering follows utility capex plans, which are
  published and finite.
- *Discriminator* (`disclosed_mechanism`) — the utility and PGCIL capex plan with years
  attached, set against the company's historical share of it.

## Forensic screens (sector-specific)
- **Revenue growth presented as performance when it is metal pass-through** — check volume and EBITDA per
  tonne before accepting any growth narrative.
- EBITDA margin % improvement that is really a *falling* metal price inflating the percentage on a smaller
  revenue base, with per-tonne profit flat.
- Realisation per tonne rising exactly with the metal index, described as premiumisation or mix.
- Unhedged metal inventory carried as inventory rather than acknowledged as a commodity position; hedging
  gains/losses presented inside operating margin.
- Order book without price-variation clauses in a rising-metal environment — margin will compress on
  execution, and the book's stated value is misleading.
- Order book including L1/LoI positions; the same order counted twice across segments.
- Receivables from state utilities and discoms ageing (link to `power_utilities` — the discom receivable
  problem transmits directly to their suppliers); bill discounting used to present better days.
- Capacity announced in tonnes with no order or customer approval; product-grade approvals (utility
  vendor registration) assumed rather than obtained.
- Capitalisation of new-line commissioning or product-development costs.
- Export incentive, duty-drawback or RoDTEP income presented inside operating EBITDA.
- Segment reporting that changes definition between years, or an "others" segment absorbing a
  loss-making line; inter-segment transfer prices not disclosed (relevant where oils feed transformers).
- Related-party arrangements: promoter-owned trading or distribution entities, group-company sales.
- Antidumping duty expiry in a key export market inside the forecast horizon, undisclosed.

## Dependencies to map
**Aluminium and copper prices** (LME and domestic), plus the contractual pass-through mechanism — the
sector's largest single variable · **transmission capex**: the CEA/CTU national transmission plan,
TBCB tender awards, PGCIL capex, and state transmission utilities' plans · **RDSS and discom distribution
capex**, which drives cables, transformers and switchgear demand · renewable evacuation and the
ISTS build-out, which is the current structural driver (link to `renewables` and `power_utilities`) ·
**re-conductoring demand** — replacing existing conductors with high-efficiency grades, named as a
catalyst by APAR and a genuinely new demand pool · steel, polymer and insulating-material prices for
cables · crude/base-oil prices for transformer oils · export-market demand and trade remedies
(antidumping, safeguards, US/EU tariffs) with expiry dates · freight rates and container availability ·
BIS standards and utility vendor-approval regimes, which are a real barrier to entry ·
PLI and domestic-content preference in government procurement · discom financial health, which determines
payment behaviour · interest rates (working-capital heavy).

## Common archetypes here
`capex-to-cashflow` (capacity commissioning into a transmission-capex upcycle — the dominant archetype) ·
`margin-expansion` (product-mix upgrade toward high-value-added grades — **the defensible version, and it
must be shown as EBITDA per tonne, not as margin %**) · `regulatory-tailwind` (RDSS, transmission plans,
domestic-content preference, antidumping protection — each with a date) · `market-share-gainer`
(export share gain, or share gain as the metal cycle stresses weaker competitors) · `cyclical-recovery`
and **`cyclical-peak`, which deserves real attention: the transmission-capex cycle and this sector's order
inflows and multiples peak together**, so a note initiating at peak inflow must say where in the cycle it
is · `deep-value-sotp` where the market prices a multi-segment company on its worst segment's multiple.
`quality-compounder` is arguable for names with genuine grade leadership and utility approvals, but the
claim needs the per-tonne series across a full metal cycle to support it.
