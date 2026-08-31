# Sector Playbook — Auto ancillaries, components & tyres

*Tier 2. Family: `auto_engineering` (`prompts/sector_packs/auto_engineering.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Sona BLW Precision (Nuvama, Feb-22 — notably a *sceptical* note on
valuation, rare in a 94%-positive corpus, and the source of the value-curve / EV-mix framing), CEAT
(Emkay Global, Sep-24) and Balkrishna Industries (JM Financial, Mar-26) for tyres, Tenneco Clean Air
India (JM Financial, Jan-26), Belrise Industries (LKP, Sep-25), Sansera Engineering (Nirmal Bang,
Jul-24), Minda Industries (Nov-20).

## The economic engine
A component maker sells into a platform, not to a market. **Its revenue is the OEM's volume multiplied
by how much of each vehicle it supplies** — so the whole business reduces to one metric and its
durability:

`Revenue = OEM volume × content per vehicle (CPV)` — and CPV is where all the strategy lives

That produces the sector's characteristic risk-return shape:

- **The customer is also the counterparty and the price-setter.** OEMs run annual price-down
  negotiations (typically 1-3% p.a.), fund tooling, and can dual-source. So a supplier's margin is
  structurally squeezed unless CPV rises or the content becomes hard to replace.
- **A platform win is an annuity with a fixed end.** Business is awarded per platform for its model
  life (5-8 years), so the order book is real but finite — and **the replacement risk when a platform
  ends is the single most under-analysed exposure in this sector.** Ask what share of revenue sits on
  platforms in their final two years.
- **Growth comes from three separable sources, and they must be split:** OEM volume growth (the cycle,
  not the company), CPV growth on existing platforms (mix and value-curve movement), and new platform
  wins. Sona BLW's note frames it exactly as "an interplay of value curve, market share gain and EV
  revenue" — three drivers, named separately.
- **Tyres are a different animal within this playbook** — they sell substantially into the
  *replacement* market, so demand is a function of the vehicle *parc* rather than of new-vehicle
  production, and the economics are closer to a branded consumer business with a commodity input
  (natural rubber, carbon black, crude derivatives). Treat OEM and replacement as separate segments
  with separate margins, and note that replacement is the higher-margin annuity.

**The EV transition is the sector's live re-rating engine, and it cuts both ways per component.** A
powertrain-agnostic part (suspension, brakes, interiors, lighting) is unaffected; an ICE-specific part
(exhaust, fuel systems, transmissions) faces terminal decline; an EV-levered part (driveline, motors,
BMS, thermal) sees CPV multiply. Sona BLW's EV revenue share rising from 14% (FY21) to ~31.5% (FY24E)
is the disclosure to demand — **EV revenue share, not "EV-readiness".**

## Analysis sequence
1. **Decompose the product portfolio by powertrain exposure**: agnostic, ICE-specific, EV-levered.
   Then revenue and EBIT by bucket. This is the first analytical act and it determines whether the
   company has a terminal-value problem.
2. **Content per vehicle, per platform and per customer** — current, and the trajectory. Then the
   "value curve": is the company moving from a low-value part to a system or module? Module supply
   raises CPV and switching cost simultaneously.
3. **Customer and platform concentration, both** — top-5 customer share *and* the top platforms by
   revenue, with each platform's model-life stage. Diversified customers on correlated platforms is
   not diversification.
4. **The order book / booked business**, with its conversion mechanics: awarded lifetime value, the
   start-of-production dates, and the ramp assumption. **A "lifetime order book" divided by a model
   life is not a revenue forecast** — check the historical conversion rate, exactly as
   `epc_construction` requires for order books.
5. **Split growth into the three sources** (OEM volume, CPV, new wins) for the historical period, and
   require the forecast to do the same. This is where most theses in this sector are either proved or
   exposed.
6. **Pass-through mechanics, read from the contract not the commodity chart** — indexed quarterly
   clauses vs annual negotiation vs spot exposure, and the lag in each direction. Then the annual
   price-down commitment, which is the standing headwind.
7. **Aftermarket and export exposure** — both are higher-margin and less OEM-dependent. For tyres, the
   replacement/OEM/export split *is* the business. For components, aftermarket share is a quality
   marker.
8. **Capacity, utilisation and capex per unit**, with the tooling and customer-funded portion
   identified. Capacity built for a specific platform is not fungible.
9. **Return on capital and its trajectory** — Sona BLW's RoCE rising 22% (FY21) → 38% (FY24E) is the
   kind of series that justifies a premium, and the note still questioned the multiple.
10. **Then the multiple — and read the corpus's warning below before awarding a premium.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Content per vehicle** | revenue from a platform / vehicles produced on it | INR/vehicle | The core metric. Track per platform and per customer, and separate CPV growth from OEM volume growth — they are different theses. Rising CPV via module supply also raises switching cost | Decks, transcripts, derived |
| **Customer concentration (top-5)** | top-5 customer revenue / total revenue | % | **Read with platform concentration and platform age.** Structural in this sector, so the question is not whether it is high but whether the platforms are young and the content is hard to replace | AR, decks |
| **EV revenue share** | EV-platform revenue / total revenue | % | The transition measure, and it must be a *revenue* number. Sona BLW: 14% (FY21) → ~31.5% (FY24E). Pair it with the ICE-specific share, which is the offsetting decline nobody volunteers | Decks, segment disclosure |
| **Capacity utilisation** | production / installed capacity | % | Operating leverage, and the constraint on accepting new platform awards. Note how much capacity is platform-specific and therefore not fungible | AR capacity table |
| **EBITDA margin** | EBITDA / revenue | % | Bridge into mix (CPV, module vs part, aftermarket, export), operating leverage, commodity pass-through and the annual price-down. An unbridged margin forecast in this sector ignores a known structural headwind | P&L |

## Supporting KPIs
Revenue by powertrain bucket (agnostic / ICE-specific / EV-levered); revenue and EBIT by product line;
revenue by customer and by platform with model-life stage; booked/awarded lifetime business and its
start-of-production schedule; historical order-to-revenue conversion; kit value per vehicle; module vs
component revenue share; aftermarket revenue share and margin; export share by geography and margin;
annual price-down concession granted (%); raw-material cost as % of revenue with the indexation
mechanism per contract; tooling revenue and customer-funded tooling assets; R&D as % of revenue and the
capitalised portion; new-product/new-platform revenue share; plant count and capacity by location;
capex per unit of capacity and the platform-specific share; working-capital days by customer (OEM
payment terms are long and non-negotiable); warranty and recall provisioning; ROCE and ROCE excluding
CWIP; net debt/EBITDA; JV and technology-licence royalty payments to a foreign partner (very common
here, and a permanent margin claim).
*Tyres specifically:* replacement / OEM / export volume and revenue mix with margin each; volume in
tonnes and in units; realisation per kg; natural rubber, synthetic rubber and carbon-black cost per kg;
capacity by category (TBR/PCR/OTR/2W); brand and dealer count; OTR/specialty mix (Balkrishna's
economics rest on this); antidumping and trade-remedy exposure in export markets.

## Standard exhibit set
Revenue split by powertrain exposure: agnostic / ICE-specific / EV-levered (the exhibit that frames the
terminal-value question) · **content per vehicle by platform and customer, with the trajectory** ·
growth decomposed into OEM volume vs CPV vs new wins · booked business with start-of-production
schedule and the historical conversion rate · customer and platform concentration with platform
model-life stage · EV revenue share against ICE-specific revenue share on one chart · raw-material cost
against the relevant indices with the pass-through mechanism and lag annotated · annual price-down
history · aftermarket and export share with margin each · capacity and utilisation by plant with the
platform-specific share marked · capex and tooling with the customer-funded portion · ROCE trend
including and excluding CWIP · royalty/technology-fee as % of revenue · working-capital days by
customer · warranty provisioning · P/E band against the company's own history · peer table on CPV
growth, EV share and ROCE — not on multiples alone.
*Tyres:* replacement/OEM/export mix with margin · realisation per kg vs natural-rubber price ·
capacity by category and utilisation · dealer network.

## Valuation convention
**P/E on forward EPS, and a premium must be earned with evidenced content-per-vehicle growth or
awarded EV-platform business — not with press releases.** This is the registry's stated convention and
the corpus supplies an unusually candid illustration of why.

**The Sona BLW warning, which this playbook exists partly to encode.** Nuvama's Feb-22 initiation
forecast the company would "triple its revenue and quadruple its PAT over FY21-24" with RoCE reaching
38% — and then said of the valuation: *"Current valuations imply SONA would sustain its supernormal
momentum beyond the current order book tailwind. Empirical evidence indicates it is difficult to
maintain such growth momentum beyond a particular size. Current valuations are similar to some new-age
companies."* In a corpus where 94% of initiations are positive
(`docs/ER_CORPUS_FINDINGS.md` §5), a note that accepts the operating forecast and still challenges the
multiple is the behaviour this repo's `prompts/34` is built to reproduce. **The test to carry forward:
does the multiple require growth beyond the visible order book — and if so, say so explicitly.**

Where the company has separable legs (a tyre maker's replacement vs OEM business, a component maker's
domestic vs overseas subsidiaries, an ICE-specific leg with a terminal decline), consider **SOTP** and
publish the implied blended multiple. An ICE-specific business genuinely deserves a lower multiple and
a shorter horizon; blending it in hides the terminal-value problem.

*Traps:* (i) paying a premium for EV *ambition* rather than awarded business with a start-of-production
date; (ii) capitalising a peak-cycle OEM volume year; (iii) accepting a lifetime order book divided by
model life as a revenue forecast without the historical conversion rate; (iv) ignoring the annual
price-down in the margin forecast; (v) valuing an ICE-heavy portfolio on a perpetual-growth multiple;
(vi) margin expansion that is really a falling rubber or steel price (acute for tyres); (vii) missing
that a foreign-partner royalty is a permanent claim peers may not carry.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The company will "triple its revenue and quadruple its PAT over FY21-24" with RoCE
reaching 38%.**
- *An exceptional franchise, premium justified* (`growth_rate`) — that is Nuvama's Feb-22
  Sona BLW forecast.
- *The same note says otherwise* (`growth_durability`) — *"Current valuations imply SONA
  would sustain its supernormal momentum beyond the current order book tailwind. Empirical
  evidence indicates it is difficult to maintain such growth momentum beyond a particular
  size."* This is a note whose own analysis contradicts its conclusion, which
  `docs/OPINION_VS_ANALYSIS.md` §6 flags as the highest-value signal in competitor research.
- *Discriminator* (`historical_distribution`) — the base rate for sustaining that growth
  past that revenue scale. The note names the base rate and then does not apply it; we must
  apply it.

**2. The EV order book is large and growing.**
- *Content per vehicle is structurally rising* (`growth_rate`).
- *Not until it is awarded* (`earnings_base_quality`) — a premium must be earned with
  evidenced content-per-vehicle growth or **awarded** EV-platform business, not with press
  releases and pipeline.
- *Discriminator* (`disclosed_mechanism`) — awarded business with start-of-production dates,
  separated from pipeline.

## Forensic screens (sector-specific)
- **Order book or "booked business" quoted as lifetime value without the SOP schedule** or the
  conversion history; the same award counted in successive years.
- CPV growth claimed while the customer's own volume falls — check whose number is moving.
- EV revenue defined loosely (components that *could* go into an EV counted as EV revenue), or the
  definition changed between periods; the ICE-specific decline never quantified.
- Platform expiries inside the forecast horizon not disclosed; revenue concentration in platforms in
  their final years.
- Tooling revenue recognised upfront while the associated production has not started; customer-funded
  tooling capitalised as the company's own asset.
- R&D and product-development capitalised aggressively, or amortised over longer than the platform life.
- Price-down concessions granted but the margin forecast assuming they stop.
- Raw-material pass-through claimed as automatic while the contract shows annual negotiation — read the
  contract terms, not the commentary.
- Warranty and recall provisioning flat as EV/electronics content rises.
- Receivables from a single OEM stretching; bill-discounting or factoring used to present better
  working capital while the credit risk remains.
- Subsidiary or JV losses (overseas acquisitions are common and frequently loss-making) parked outside
  the reported segment; goodwill from those acquisitions never tested.
- Royalty or technology fees to a promoter-affiliated foreign partner rising ahead of revenue.
- Export-incentive or PLI income presented inside operating EBITDA.
- For tyres: inventory build in a falling-rubber environment; realisation per kg rising only on mix;
  antidumping duty expiry in a key export market undisclosed.

## Dependencies to map
**Each customer's own volume cycle and launch calendar** — this is a derivative business, so
`auto_oem`'s dependency map applies upstream in full, per customer · SIAM/FADA/VAHAN data · steel,
aluminium, copper, natural and synthetic rubber, carbon black, resin and rare-earth/magnet prices, with
the contractual indexation mechanism · **the EV transition's speed and shape**, including battery
chemistry (which determines demand for thermal and BMS content) and the OEMs' localisation
requirements · PLI for auto components and for advanced chemistry cells, with localisation thresholds ·
semiconductor and electronic-component supply · emission, safety and ADAS regulation, each of which
raises CPV for specific suppliers (a genuine regulatory tailwind, unusually well-evidenced in this
sector) · export-market cycles, tariffs, antidumping and trade remedies (Balkrishna and the tyre makers
are directly exposed) · USD/EUR-INR · the vehicle **parc** and scrappage policy for aftermarket and
replacement demand · foreign technology-partner relationships and their renewal terms.

## Common archetypes here
`market-share-gainer` in its sector-specific form — content-per-vehicle gain, which is share of the
*vehicle* rather than of the market, and the most defensible archetype here when CPV data supports it ·
`regulatory-tailwind` (emission/safety/ADAS content mandates and PLI — well-evidenced) ·
`capex-to-cashflow` (capacity for awarded platforms) · `margin-expansion` (mix toward modules,
aftermarket and exports — must survive the price-down and commodity tests) · `cyclical-recovery` and
`cyclical-peak` inherited from the OEM cycle · `re-rating`, which in this sector is almost always an
EV-transition argument and should be held to awarded business with dates. **Treat
`quality-compounder` with particular care: the Sona BLW note is the corpus's own demonstration that a
company can deliver tripling revenue and 38% RoCE while its multiple still implies more than the order
book supports.**
