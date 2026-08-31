# Sector Playbook — Hotels

*Tier 2. Family: `consumer_retail` (`prompts/sector_packs/consumer_retail.md`). Shared
rules: `prompts/31`.* **Not covered by any pack before this file — hotels previously fell
through to `generic`.**
**Provenance:** corpus-grounded — SAMHI Hotels (Yes Securities, Sep-25, 64pp),
ITC Hotels (ICICI Securities, Dec-25), a hotels sector note (ICICI Securities, Sep-25),
Bharat Hotels/DII (IDBI Capital, Sep-21).

## The economic engine
A hotel is a fixed-cost asset selling a perishable unit — the room-night. Once occupancy
covers the fixed cost, incremental revenue drops to EBITDA at very high rates, so **the
sector's defining feature is operating leverage on ARR**. Value is created at two moments:
what you pay per key when you acquire or build, and what ARR you can push through it.

`Revenue = keys × 365 × occupancy × ARR` → RevPAR = occupancy × ARR is the compressed form.

## Analysis sequence
1. **Inventory and its shape.** Keys by property, by segment (luxury / upper-upscale /
   upscale / mid / budget), by city, and by ownership form — owned, leased, managed,
   franchised. Owned keys carry the operating leverage; managed keys are an annuity.
2. **Entry cost per key.** For an acquirer, the cost per key versus replacement cost is
   the whole capital-allocation discipline. SAMHI's strategy explicitly "hinges on buying
   an asset at a discount to replacement cost, which ensures robust ROCE post turnaround".
3. **RevPAR decomposition** — always split into occupancy and ARR. They have different
   drivers and different ceilings: occupancy is capped at ~80-85% practically; ARR is not.
4. **Supply-demand by micro-market.** Hotels are hyper-local. National supply data is
   nearly useless; what matters is keys under construction within the catchment of *this*
   asset over the next 3 years.
5. **Cost structure and the break-even occupancy** — payroll and F&B as % of revenue,
   fixed vs variable, and the occupancy at which the asset covers fixed cost.
6. **Renovation/rebranding pipeline** — capex per key, the rooms out of service while it
   happens, and the ARR uplift achieved on comparable past projects.
7. **Balance sheet and asset recycling** — net debt/EBITDA, the deleveraging path, and
   evidence of disposals at credible multiples.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **ARR** (average room rate) | room revenue / room-nights sold | INR | The pricing variable; drives almost all incremental margin | Company decks |
| **Occupancy** | room-nights sold / available | % | Practical ceiling ~80-85%; above ~70% pricing power arrives | Decks |
| **RevPAR** | occupancy × ARR | INR | The headline, but never analyse it undecomposed | Computed |
| **EBITDA per key** | property EBITDA / keys | INR mn/yr | The unit economics; makes assets of different sizes comparable | Computed |
| **Cost per key vs replacement cost** | acquisition EV / keys, vs build cost | INR mn, % discount | The acquirer's discipline and the deep-value anchor | Deal disclosures, industry build costs |

## Supporting KPIs
Keys (owned / leased / managed / pipeline); segment mix; city mix; F&B share of revenue;
management-fee income; payroll as % of revenue; break-even occupancy; ARR premium vs
micro-market; net debt/EBITDA; ROCE post-stabilisation; ESOP expense (material and
frequently normalised); attributable EBITDA where JV partners hold economic stakes.

## Standard exhibit set
Key count by property and segment · owned vs managed split · ARR and occupancy time
series (ideally 10 years, through Covid) · RevPAR vs micro-market · EBITDA per key ·
cost per key vs replacement cost · renovation pipeline with capex and ARR uplift ·
supply pipeline in each micro-market · segment-wise industry RevPAR · net debt walk ·
peer scorecard · EV/EBITDA band.

## Valuation convention
**EV/EBITDA on a forward year** is standard (SAMHI: 15x Jun'27 attributable EV/EBITDA),
frequently cross-checked with a **DCF** (three-stage, WACC ~10-11%, terminal ~3%) and
sanity-checked against **EV per key** versus replacement cost and versus realised
transactions. The attributable-EBITDA adjustment, the Duet India disposal that evidences the
recycling claim, and the replacement-cost-as-acquisition-discipline reading are treated in full
at `docs/ER_CORPUS_FINDINGS.md` §7.1, §7.2 and §7.9 — and note that the same note's fifth
pillar is a peer-discount re-rating argument the corpus uses as a negative example (§6).

*Traps:* (i) **attributable vs headline EBITDA** — where a JV partner (e.g. GIC) holds an
economic share, headline EV/EBITDA is not comparable to a wholly-owned peer's; SAMHI's
note adjusts for this and it is the correct treatment; (ii) valuing a portfolio
mid-renovation on current EBITDA when rooms are out of service; (iii) capitalising a
cyclical ARR peak — Indian hotel cycles are long and violent.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 15x forward EV/EBITDA, in line with the peer set.**
- *Fairly valued* (`peer_set_choice`).
- *Not comparable as printed* (`earnings_base_quality`) — where a JV partner such as GIC
  holds a share of the portfolio, headline EV/EBITDA compares nothing. SAMHI is published
  on *attributable* EV/EBITDA (15x Jun'27) precisely for this reason.
- *Discriminator* (`peer_distribution`) — the peer set restated on an attributable basis,
  net of minority and JV shares.

**2. RevPAR is up 22%.**
- *Structural demand* (`growth_durability`) — corporate travel and a supply-constrained
  market.
- *A cyclical high in ARR* (`cycle_position`) — supply responds to rate strength with a
  three-to-four-year lag, and the response is already announced.
- *Discriminator* (`historical_distribution`) — ARR against its own ten-year band, set
  beside the announced supply pipeline by micro-market.

**3. EV per key sits below replacement cost.**
- *A valuation floor* (`capital_intensity`).
- *A floor only where the asset is genuinely replaceable at that price* (`capital_intensity`)
  — in a micro-market where nobody would build, replacement cost is a number, not a floor.
- *Discriminator* (`peer_distribution`) — realised transaction values per key in the same
  micro-market. SAMHI's Duet India disposal is the corpus's worked example of
  replacement-cost-as-acquisition-discipline.

## Forensic screens
- ARR growth driven by mix (more luxury keys) rather than like-for-like pricing — demand
  same-store ARR.
- Managed-portfolio "keys signed" counted as if operational; check keys *opened*.
- Capitalised renovation cost that is really maintenance.
- EBITDA before ESOP, or before lease charges post-Ind-AS 116, compared against peers
  reporting after.
- Related-party management contracts with the promoter's other properties.

## Dependencies to map
Domestic air-passenger traffic and airport capacity · corporate travel budgets · MICE and
wedding seasonality · foreign tourist arrivals · micro-market supply · state excise and
liquor licensing (material to F&B margin) · property tax and land-lease renewals ·
interest rates (asset-heavy, leveraged).

## Common archetypes here
`turnaround` (acquire-renovate-rebrand), `capex-to-cashflow`, `balance-sheet-repair`,
`cyclical-recovery`, `deep-value-sotp` (replacement cost) — and very frequently
`re-rating` bolted on. SAMHI carries four of these at once; decompose before accepting.
