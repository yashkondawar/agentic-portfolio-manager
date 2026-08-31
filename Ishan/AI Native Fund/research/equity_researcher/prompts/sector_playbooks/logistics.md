# Sector Playbook — Logistics, warehousing, ports & aviation

*Tier 2. Family: `infra_capital_goods` (`prompts/sector_packs/infra_capital_goods.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Delhivery (Emkay Global, Jul-23 — express parcel, the per-shipment
model and the volume-vs-market-growth framing), TCI Express (ICICI Securities, Jan-18 and Apr-19 — asset-light
surface express), InterGlobe Aviation / IndiGo (Anand Rathi, Oct-25 and BOB Capital, Sep-20 — the
aviation leg, and the corpus's only source for ATF/crack-spread cost exposure). **Ports are
domain-derived** — the corpus has no port or shipping initiation, so the throughput/TEU content below is
labelled accordingly. `real_estate` is the authored sibling for warehousing-as-annuity economics.

## The economic engine
**This playbook covers models that differ more from each other than most registry siblings do, and the
first act is to identify which one — because the unit, the cost structure and the multiple all change.**

1. **Asset-light network (surface express, 3PL, freight forwarding)** — the company owns the network and
   the technology but hires the trucks. `EBITDA = volume × (realisation per tonne − linehaul cost)`. High
   ROCE, low capital intensity, and the moat is network density and load factor.
2. **Asset-heavy transport (own fleet, rail, shipping)** — owns the vehicles. Capital-intensive, cyclical,
   and the analysis is fleet utilisation and asset turns.
3. **Express parcel / e-commerce logistics** — the unit is the **shipment**, not the tonne, and the
   economics are per-shipment yield against per-shipment cost, with sortation automation driving the cost
   curve. Delhivery is the corpus's case: ~22-24% share of the non-captive B2C express market, with
   **shipment volume CAGR of 45% (FY19-23) against an e-commerce shipment market CAGR of 25%** — growth
   measured against the market it serves, which is the right framing.
4. **Warehousing** — a real-estate annuity wearing a logistics label. Occupancy, rent per sqft and WALE;
   value it at a cap rate, not on EBITDA (see `real_estate`).
5. **Ports and terminals (domain-derived)** — throughput in TEU or tonnes against capacity, with
   concession terms and tariff regulation. Closest in structure to `power_utilities`' regulated bucket.
6. **Aviation** — a per-seat-kilometre spread business with a dominant fuel input; RASK against CASK, and
   ATF is the swing item (link to `oil_gas_cgd`, where the crack spread that sets ATF is analysed).

**The unifying discipline: density and load factor are the moat.** In every one of these models, fixed
network cost is spread over volume, so **the incremental unit is far more profitable than the average
one** — which means market-share gain compounds into margin, and share loss compounds into losses. Get the
volume-vs-market-growth comparison before anything else.

## Analysis sequence
1. **Classify the model** (above) and split revenue and EBITDA by segment where the company runs more than
   one. Asset-light and asset-heavy legs must not share a multiple.
2. **Volume in the correct unit** — tonnes, tonne-km, shipments, TEU, ASKs — and against **the growth of
   the market it serves**, not against its own history. Delhivery's 45%-vs-25% comparison is the standard.
3. **Realisation per unit and its direction.** Express and parcel yields fall structurally as volume mix
   shifts to lighter, cheaper shipments and as competition intensifies; get realisation per shipment or per
   tonne, not just revenue.
4. **Cost per unit, decomposed** — linehaul, last-mile, sortation/hub, fuel, driver/pilot, and the
   fixed/variable split. **The gap between realisation per unit and cost per unit, times volume, is the
   business**; margin percentage is a derived number.
5. **Density and load factor** — vehicle/fleet utilisation, load factor, empty-running or backhaul share,
   route density, and shipments per facility. Automation matters here and is measurable (Delhivery's
   sortation system processing 16k shipments/hour is the kind of disclosure to seek).
6. **Customer concentration and contract structure** — for 3PL and e-commerce logistics, the top customer
   is often a large share, and captive-vs-non-captive matters: an e-commerce platform building its own
   logistics arm is simultaneously the largest customer and the emerging competitor.
7. **Network footprint** — hubs, branches, warehouses, pin-code coverage, and the capex behind it. Then
   the utilisation of recently added capacity.
8. **For warehousing:** area, occupancy, rent per sqft, WALE, tenant mix — and value at a cap rate.
   **For ports:** throughput vs capacity, concession tenure, tariff regime, draft and hinterland
   connectivity. **For aviation:** fleet, ASK, RASK, CASK, load factor, fuel as % of cost, and the
   lease structure.
9. **Then the segment-appropriate multiple.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Volume** | tonnes, tonne-km, shipments or TEU handled | tonnes / TEU | **In the unit the business actually sells**, and always against the served market's growth — Delhivery's 45% shipment CAGR against a 25% market CAGR is a share-gain statement; volume growth alone is not | Company disclosure |
| **Realisation per tonne** | segment revenue / volume (per tonne, or per shipment for express) | INR/t | Structurally falling in express and parcel as shipment mix lightens and competition bites. Separate genuine price from mix (weight, lane, service level) | Computed |
| **Fleet utilisation** | vehicle-km or trips achieved / capacity available | % | The asset-heavy productivity measure; pair with empty-running/backhaul share, which is the real efficiency lever. For asset-light models, substitute load factor per trip | Decks, AR |
| **Warehouse occupancy** | leased area / total operational area | % | The annuity leg's core metric; read with rent per sqft, WALE and the tenant mix. **Quote rent-paying occupancy, not "leased" including letters of intent** | Decks, AR |
| **EBITDA margin** | EBITDA / revenue | % | A derived number in this sector — bridge it into volume, realisation per unit and cost per unit before using it. State the Ind-AS-116 basis, since leased fleet, warehouses and aircraft are material | P&L |

## Supporting KPIs
Revenue and EBITDA by segment (express / 3PL / warehousing / rail / air / ports); shipments and average
shipment weight; realisation and cost per shipment; contribution per shipment; tonne-km and revenue per
tonne-km; linehaul cost as % of revenue; last-mile cost per shipment; sortation capacity and throughput per
hour; automation/mechanisation share of volume; hub and branch count; pin-code coverage; own vs hired fleet
mix; fleet size, age and capacity in tonnes; empty-running / backhaul share; fuel cost as % of revenue and
the pass-through mechanism (fuel surcharge clauses); driver availability and cost; customer concentration
(top-5 and top-1) with captive-vs-non-captive split; contract tenure and rate-revision mechanism;
warehousing area (operational / under-construction), occupancy, rent per sqft, WALE, tenant mix;
receivable days by customer type; asset turns and ROCE (the key metric for asset-light claims);
pre- and post-Ind-AS-116 EBITDA; net debt/EBITDA including lease liabilities.
*Ports (domain-derived):* throughput vs installed capacity, cargo mix (containers / bulk / liquid),
concession tenure and revenue-share to the authority, tariff regime, average turnaround time, draft,
rail/road hinterland connectivity, top-customer/shipping-line concentration.
*Aviation:* fleet count and type, ASK, RASK, CASK, CASK ex-fuel, passenger load factor, yield per pax,
ancillary revenue per pax, ATF cost per ASK, aircraft on ground, lease vs owned mix, sale-and-leaseback
gains, market share, on-time performance.

## Standard exhibit set
Volume in the correct unit against the **served market's** growth (the share-gain exhibit) ·
realisation per unit and cost per unit as two series, with the spread shown · cost per unit decomposed by
line with fixed/variable character · contribution per shipment or per tonne by lane/service · market
share within the served segment · fleet utilisation and empty-running/backhaul share · network footprint
(hubs, branches, pin codes) with capex and the utilisation of recent additions · automation share and
throughput per hour · customer concentration with captive-vs-non-captive split and contract tenure ·
fuel cost as % of revenue against the diesel/ATF index with the surcharge mechanism annotated ·
**warehousing: area, occupancy, rent per sqft, WALE, tenant mix — plus the cap-rate valuation** ·
receivable days by customer type · asset turns and ROCE by segment · pre- vs post-Ind-AS-116 EBITDA
reconciliation · net debt including lease liabilities · segment SOTP table where models are mixed.
*Ports:* throughput vs capacity, cargo mix, concession tenure, turnaround time.
*Aviation:* RASK vs CASK with the gap, load factor, ATF per ASK, fleet plan.

## Valuation convention
**EV/EBITDA on a forward year — and asset-light and asset-heavy models must not share a multiple.** This is
the registry's stated convention and it is the sector's most-violated rule. An asset-light surface-express
operator earning 25%+ ROCE on hired trucks and a fleet owner earning 12% on its own are different
businesses; the first deserves a materially higher multiple, and TCI Express versus a fleet-owning peer is
the corpus's illustration of the gap.

Delhivery is stated at **FY26E EV/EBITDA of 28x** (Emkay) — a growth multiple on a business that was
pre-profit at the time, which means the same discipline `internet_platforms` requires applies here:
**demand a dated path to profitability, and state which regime the multiple belongs to.** For genuinely
pre-profit network businesses, EV/Sales or EV/shipment with a DCF cross-check is more honest than a forward
EV/EBITDA struck on the first profitable year.

Where the company mixes models, use **SOTP**: express/3PL on EV/EBITDA, **warehousing at a cap rate on NOI**
(it is an annuity asset, and valuing it on EBITDA understates it), ports on DCF over the concession, and
publish the implied blended multiple as a sanity check.

*Traps:* (i) **one multiple across asset-light and asset-heavy legs** — the defining error; (ii) valuing
warehousing on EBITDA rather than at a cap rate; (iii) mixing pre- and post-Ind-AS-116 EBITDA across the
peer table (leases dominate here, as in `apparel_grocery_retail`); (iv) treating volume growth as share
gain without the served-market comparison; (v) capitalising a freight-rate or air-fare spike;
(vi) ignoring that an e-commerce customer's captive-logistics build-out can remove a large share of
revenue on a strategic decision; (vii) for aviation, valuing a fuel-driven margin window as structural.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. Two operators both trade at 20x EV/EBITDA.**
- *Comparable* (`peer_set_choice`).
- *Different businesses* (`capital_intensity`) — an asset-light surface-express operator
  earning 25%+ ROCE on hired trucks and a fleet owner earning 12% on its own fleet do not
  deserve the same multiple; the first deserves materially more. This is the sector's
  most-violated rule, and TCI Express against a fleet-owning peer is the illustration.
- *Discriminator* (`peer_distribution`) — ROCE and the owned-versus-hired fleet mix, side by
  side.

**2. It is valued at 28x FY26E EV/EBITDA while pre-profit.**
- *A growth multiple on a growth business* (`growth_rate`) — Delhivery is stated this way
  (Emkay).
- *A promise priced as a fact* (`growth_durability`) — the same discipline
  `internet_platforms` requires applies here: demand a dated path to profitability, and
  state which regime the multiple belongs to.
- *Discriminator* (`forward_observable`) — the dated crossover, per service line.

## Forensic screens (sector-specific)
- **Volume growth presented without the served-market comparison** — 20% growth in a 25%-growing market is
  share loss.
- Realisation per shipment or per tonne falling while revenue grows, with the mix shift undisclosed.
- Revenue recognised gross where the company acts as an agent (freight forwarding is the classic case) —
  check the principal-vs-agent judgement, because it transforms the apparent margin.
- Fuel surcharge income netted into revenue in one period and disclosed separately in another.
- Empty-running or backhaul share undisclosed while "network efficiency" is claimed.
- **Warehouse "leased" occupancy including letters of intent** or pre-commitments rather than rent-paying
  tenants; rent per sqft quoted on a favourable subset.
- Capitalisation of network build-out, hub commissioning or technology-development costs; capitalised
  software amortised over an implausible life.
- Pre- and post-Ind-AS-116 EBITDA quoted interchangeably; lease liabilities excluded from net debt and
  therefore from EV.
- **Sale-and-leaseback gains presented inside operating profit** (endemic in aviation and in fleet-owning
  logistics) — this converts a financing decision into apparent operating performance.
- Fleet depreciation policy or residual-value assumptions changed; older fleet not impaired.
- Receivables from a single large e-commerce customer stretching; that customer's captive-logistics
  expansion not disclosed as a risk.
- Contract renewals at lower rates disclosed only after the fact; rate-revision clauses absent from
  long contracts in an inflationary period.
- Related-party arrangements: promoter-owned trucking fleets, warehouses leased from promoter entities,
  or freight booked through a group entity.
- For ports: concession revenue-share obligations understated; throughput including transhipment
  double-counted; capacity quoted as design rather than operable.
- For aviation: maintenance provisions for leased aircraft (redelivery obligations) under-provided;
  ancillary revenue reclassified.

## Dependencies to map
**GST and the e-way-bill system**, which formalised interstate freight and is the structural driver behind
organised logistics gaining share — the sector's genuine post-2017 story · e-commerce growth and
**per-capita parcel consumption**, which the Delhivery note frames as India's headroom versus comparable
economies · the **captive-vs-3PL decisions of the large e-commerce platforms**, which is simultaneously the
demand driver and the principal competitive threat · quick-commerce, which is creating a new
dark-store/last-mile demand pool and cannibalising some parcel volume · diesel and ATF prices and the
surcharge pass-through mechanism (ATF is set off the refining crack — link to `oil_gas_cgd`) · the
Dedicated Freight Corridor and the rail-coefficient shift, plus Gati Shakti and the National Logistics
Policy · road infrastructure and toll costs; the axle-load and scrappage rules · driver availability and
wage inflation · warehousing demand from 3PL, e-commerce and manufacturing, plus Grade-A supply and
**prevailing cap rates**, which set the annuity leg's value (link to `real_estate`) · port tariff
regulation (TAMP for major ports), concession terms and the major-vs-non-major port split · global
container freight rates and shipping cycles · **for aviation:** airport capacity and charges, slot
availability, DGCA regulation, fleet-delivery schedules and engine reliability, competitive capacity
addition (the single biggest determinant of fares), and rupee-dollar for leases and fuel.

## Common archetypes here
`capex-to-cashflow` (network and warehouse build-out reaching utilisation — the dominant archetype) ·
`market-share-gainer` — **the most defensible archetype in this sector when the served-market comparison is
made**, because density economics genuinely compound · `margin-expansion` (operating leverage on a fixed
network, plus automation — legitimate when cost per shipment is falling) · `regulatory-tailwind`
(GST/e-way bill formalisation, National Logistics Policy, DFC) · `cyclical-recovery` and `cyclical-peak`
for freight rates, shipping and aviation fares, where the cycle is violent and the peak is where
initiations cluster · `deep-value-sotp` where a warehousing or port annuity is buried inside a transport
multiple · `balance-sheet-repair` for the asset-heavy names. Treat `re-rating` with the standard
skepticism weight, and hold `quality-compounder` claims to the ROCE-through-a-cycle test — asset-light
network businesses can genuinely qualify, asset-heavy ones rarely do.
