# Sector Playbook — Diagnostics (pathology & radiology)

*Tier 2. Family: `pharma_chemicals` (`prompts/sector_packs/pharma_chemicals.md`). Shared rules:
`prompts/31`.*
**Provenance:** **domain-derived.** The 165-note corpus contains **no dedicated diagnostics
initiation** — Dr Lal PathLabs, Metropolis, Thyrocare, Vijaya Diagnostics and Krsnaa are all absent.
Corpus support is indirect and limited to the care-delivery adjacency, which supplies the
capacity-maturity and payor-mix method rather than any diagnostics KPI: Max Healthcare (Nuvama,
Sep-25), Yatharth Hospital (Nuvama, Dec-25), Global Health / Medanta (Axis Capital, May-24) and
Artemis Medicare (Choice Broking, Nov-25). Nothing KPI-specific below may be cited as corpus practice.
**Raise an open question to add diagnostics notes to `reference/er_corpus/seeds/`.** The authored
sibling closest in method is `hospitals` (maturity cohorts, payor mix, per-unit economics); for the
network-rollout economics, `apparel_grocery_retail` and `qsr` are the closest analogues.

## The economic engine
A diagnostics chain runs a **hub-and-spoke logistics network over a fixed-cost laboratory**. Samples
are collected at many cheap touchpoints, moved to a few expensive labs, and processed at a marginal
cost that is a small fraction of the price:

`Revenue = test volume × realisation per test` — where `test volume = patients × tests per patient`
`Lab-level economics: very high operating leverage — the incremental test is nearly all margin`

Four features define the analysis and separate it from `hospitals`:

- **The asset is the network, not the lab.** Labs are commoditised (the analysers are the same
  worldwide); collection-centre density and logistics turnaround time are what a competitor cannot
  replicate quickly. **Count the touchpoints and measure the turnaround, not the equipment.**
- **Price is the structural risk, and volume is the defence.** Realisation per test falls over time:
  competitive entry, online aggregators, government scheme rates and radical discounters all push the
  same way. **A revenue-growth number in this sector is uninterpretable without the volume/price
  split** — revenue can grow while the franchise erodes.
- **Tests per patient is the quietest and best margin lever.** A panel or profile costs little more to
  process than a single test but prices at a multiple. Rising realisation per *patient* with falling
  realisation per *test* is the healthy pattern; the reverse is price-taking.
- **B2C and B2B are different businesses.** Direct-to-consumer (walk-in, home collection) carries the
  brand and the margin; B2B (hospital lab management, referral from other labs, corporate wellness)
  is volume at a discount. **Get the mix and the realisation of each**; a shift toward B2B lowers
  blended realisation with no operating deterioration, and must not be read as one.

## Analysis sequence
1. **Map the network physically** — reference/mother labs, satellite labs, collection centres (own vs
   franchised), pick-up points, and home-collection phlebotomists, each by city tier and region.
   Then the *ratio* of collection points to labs, which is the leverage in the model.
2. **Decompose revenue into volume and price**, then volume into patients and tests per patient. Three
   series, always. This is the sector's equivalent of the volume/price/mix decomposition in `fmcg`.
3. **B2C vs B2B mix, with realisation and margin for each.** Then the direction of travel and its
   effect on blended realisation.
4. **Test mix and its economics** — routine/basic vs specialised/esoteric vs wellness packages vs
   radiology. Specialised tests carry higher realisation and are less contestable on price; wellness
   packages carry volume and brand-building at thin margin.
5. **Maturity cohorts, as in `hospitals`** — labs and collection centres by vintage. A network adding
   30% to its touchpoints will show falling blended margin while every mature cluster improves. Split
   before drawing any conclusion about margin.
6. **Geographic concentration and local density.** Diagnostics is won city by city; a dominant
   position in three cities beats a scattered national footprint, because density drives both logistics
   cost per sample and brand recall.
7. **Payor and channel mix** — self-pay, insurance/TPA, corporate, and government schemes (Ayushman
   Bharat, state schemes, PPP radiology contracts). Government work pays low and pays late; it drives
   both realisation and working capital.
8. **Competitive intensity, specifically the discounters and aggregators.** Online health platforms and
   radical-discount entrants have repeatedly reset price in Indian metros. Establish the price gap
   between the company and the cheapest credible competitor in each core city.
9. **Unit economics of the incremental touchpoint** — capex per collection centre, breakeven volume,
   payback — and of the incremental lab.
10. **Then margin as a weighted cohort result, ROCE, and the multiple.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Test volume** | tests/samples processed in the period | mn | The franchise measure, since price falls structurally. Split routine vs specialised, and B2C vs B2B — blended volume growth carried by discounted B2B is not franchise growth | Decks, AR |
| **Realisation per test** | segment revenue / tests processed | INR/test | **The number to watch, not revenue.** Structurally declining; decompose any change into test mix, B2C/B2B mix and genuine price. A blended realisation rise during a B2C mix shift is mix, not pricing power | Computed |
| **Patients** | unique patients served | mn | Paired with tests per patient — the two together are the honest volume story. Rising realisation per patient with flat realisation per test is the healthy pattern (more tests per visit, same price) | Decks |
| **Collection centres** | own + franchised collection points, with pick-up points separately | count | The network asset. **Get own vs franchised split and gross adds vs closures** — franchised expansion is capital-light but dilutes realisation and control, and closures are the site-discipline signal | Decks |
| **EBITDA margin** | EBITDA / revenue | % | High operating leverage means this must be read against the maturity-cohort mix and the B2C/B2B mix, never as a bare performance statement. State the Ind-AS-116 basis, as leases are material | P&L |

## Supporting KPIs
Tests per patient; realisation per patient; B2C vs B2B revenue and volume mix with realisation each;
specialised/esoteric test share of revenue; wellness-package share; radiology vs pathology split;
reference labs, satellite labs and their utilisation; samples per lab; turnaround time by test category;
logistics cost per sample; consumables/reagent cost as % of revenue and the reagent-rental vs
purchased-analyser structure; employee cost per test; phlebotomist count and home-collection share;
collection centres by city tier with own/franchise split; revenue per collection centre; capex per
collection centre and per lab; breakeven volume per touchpoint; touchpoint payback years; maturity-cohort
mix; city-level market position and price gap vs the cheapest credible competitor; payor mix and
government-scheme share; receivable days by payor; franchisee margin share; doctor/referral
concentration; accreditation status (NABL/CAP) by lab; pre- and post-Ind-AS-116 EBITDA; ROCE and ROCE
excluding goodwill (this sector consolidates by acquisition, so goodwill is usually large).

## Standard exhibit set
Revenue decomposed into volume and realisation, then volume into patients and tests per patient · test
volume and realisation per test as two series on one chart (the sector's defining exhibit — they usually
move in opposite directions) · realisation per patient vs realisation per test · B2C vs B2B mix with
realisation and margin for each · test mix (routine / specialised / wellness / radiology) with
realisation by bucket · network map: labs and collection centres by city tier, own vs franchised ·
collection-centre adds and closures shown separately · revenue per collection centre by vintage cohort ·
maturity-cohort mix of the network · touchpoint unit economics (capex, breakeven volume, payback) ·
turnaround time by category · logistics cost per sample · reagent cost as % of revenue · city-level
market position with the price gap to the cheapest competitor · payor mix and receivable days by payor ·
pre- vs post-Ind-AS-116 EBITDA reconciliation · ROCE including and excluding goodwill · EV/EBITDA band ·
peer table on realisation per test and volume growth, not on multiples alone.

## Valuation convention
**EV/EBITDA on a forward year**, cross-checked with a **DCF** where the network rollout is a knowable
capex schedule (the same logic as `qsr`'s and `hospitals`' rollout cross-checks). EV per collection
centre or per lab is a weak third anchor — weaker than `hotels`' EV-per-key or `hospitals`' EV-per-bed,
because a collection centre is cheap and easily replicated, so it carries little replacement-cost
information.

**Price competition is the structural risk, so the valuation must be anchored on realisation per test,
not on revenue.** A company growing revenue 15% with realisation per test falling 5% is a
volume-share story with a deteriorating unit economic, and it deserves a lower multiple than a company
growing 12% with stable realisation. Publish the realisation assumption the target implies — the same
discipline `ferrous_non_ferrous_metals` applies to the LME and `renewables` to module prices.

Where the company is mid-expansion, value mature and ramping cohorts separately or roll the base
forward far enough that the ramp has happened — inherited directly from `hospitals`, and for the same
arithmetic reason.

*Traps:* (i) **valuing revenue growth without checking realisation per test** — the sector's defining
error; (ii) treating a B2B-led volume surge as franchise growth; (iii) capitalising a Covid-era testing
windfall (the 2020-21 RT-PCR distortion remains in some base years — check the comparatives);
(iv) applying a mature-network multiple to a company in expansion, whose blended margin is depressed by
ramping touchpoints; (v) ignoring goodwill from acquisitions in the ROCE that justifies the premium;
(vi) comparing EBITDA margins across pre- and post-Ind-AS-116 reporters; (vii) crediting franchised
touchpoint additions at own-store economics.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. Revenue grew 15%; the peer grew 12%.**
- *Share gain* (`growth_durability`).
- *A deteriorating unit economic* (`incremental_roce`) — realisation per test fell 5%. A
  company growing 15% on falling realisation is buying volume share, and it deserves a
  *lower* multiple than the peer growing 12% with flat realisation. Price competition is the
  structural risk here, so the valuation must be anchored on realisation per test, not on
  revenue.
- *Discriminator* (`disclosed_mechanism`) — the volume-versus-realisation decomposition.

**2. EV per collection centre is below the peer's.**
- *Cheap on assets* (`capital_intensity`).
- *A weak anchor* (`capital_intensity`) — a collection centre is cheap and easily
  replicated, so it carries little replacement-cost information. It is a weaker third anchor
  than `hotels`' EV-per-key or `hospitals`' EV-per-bed, and should not carry a thesis.
- *Discriminator* (`peer_distribution`) — fall back to EV/EBITDA on a forward year,
  cross-checked with a DCF where the network rollout is a knowable capex schedule.

## Forensic screens (sector-specific)
- **Revenue growth reported without the volume/price split**, or realisation per test disclosed only
  when it is rising.
- Test volume growth carried by discounted B2B or by wellness packages, presented as B2C franchise
  growth; the mix not disclosed.
- Collection-centre count including "pick-up points", franchisee outlets and inactive centres in one
  number; net adds quoted without closures; the definition changed between periods.
- Revenue per collection centre falling while the count grows — the network is being extended into
  unproductive locations.
- Tests-per-patient rising because panels were bundled and repriced rather than because more testing is
  occurring — check realisation per patient against realisation per test.
- Covid-era comparatives not restated or not flagged, making FY22-FY23 growth uninterpretable.
- Receivable days rising with government-scheme or corporate share — growth funded by the balance sheet
  (the screen is inherited from `hospitals` and applies identically).
- Reagent-rental arrangements (analyser supplied free against a reagent commitment) creating an
  off-balance-sheet volume obligation; take-or-pay reagent contracts not disclosed.
- Acquisition accounting: goodwill never tested down after an acquired lab's volumes decline; acquired
  entities' realisation not disclosed separately.
- Franchisee revenue recognised gross while the franchisee's share sits in expenses, inflating both
  revenue and apparent realisation.
- Capitalisation of lab pre-operative costs, accreditation costs or franchise-onboarding costs.
- NABL/CAP accreditation lapses at a specific lab; a lab's results being re-run or referred out.
- Related-party arrangements with a promoter-owned hospital chain that is also the B2B customer, or
  with the logistics provider.
- Doctor or referral-source concentration undisclosed; referral fees (regulated and reputationally
  sensitive) treated as marketing spend.

## Dependencies to map
Health-insurance penetration and TPA reimbursement behaviour · Ayushman Bharat, CGHS and state scheme
rates for diagnostics, plus PPP radiology contract terms — these set the price floor in the segments
they touch (link to `hospitals` and `general_health_insurance`) · **online health aggregators and
radical-discount entrants**, which have repeatedly reset metro pricing and are the sector's principal
competitive threat · reagent and consumable import costs, customs duty, and analyser-vendor pricing
power (the installed base creates lock-in to a reagent supplier) · NABL and CAP accreditation
requirements; the Clinical Establishments Act and state-level lab licensing · NPPA-type price-capping
risk on diagnostic tests, which has been debated and would be existential in the capped segments ·
telemedicine and at-home-testing regulation · doctor-referral regulation and the MCI/NMC code, which
constrains the sector's historical customer-acquisition channel · epidemiology and seasonality (vector-borne
disease seasons drive a real volume cycle) · preventive-health and corporate-wellness adoption ·
genomics and molecular-testing technology shifts, which move tests between the esoteric and routine
buckets — and therefore between price regimes.

## Common archetypes here
`capex-to-cashflow` (network rollout maturing — the dominant archetype, and the one whose cohort
arithmetic must be shown rather than asserted), `margin-expansion` (operating leverage on a fixed lab
base plus specialised-test mix — legitimate when realisation per test is stable), `market-share-gainer`
(must be city-level to mean anything, and must survive the price check), `quality-compounder` for
genuinely dense, brand-led networks — the claim requires stable realisation, since compounding through
structural price decline requires the volume and mix to outrun it — and `special-situation` for the
sector's frequent consolidation. Treat `re-rating` with the standard skepticism weight. Be especially
alert to `cyclical-peak` in any base year containing Covid testing revenue.
