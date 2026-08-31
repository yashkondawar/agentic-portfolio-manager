# Sector Playbook — Quick-service & casual-dining restaurants

*Tier 2. Family: `consumer_retail` (`prompts/sector_packs/consumer_retail.md`). Shared rules:
`prompts/31`.*
**Provenance:** **domain-derived**, with partial corpus support. The 165-note corpus contains **no
mainstream QSR-chain initiation** — Jubilant FoodWorks, Devyani, Sapphire, Westlife and Restaurant
Brands Asia are all absent. Corpus support comes from Travel Food Services (ICICI Securities,
Nov-25, 49pp, 71 exhibits), a **travel/airport-concession QSR** whose concession and JV mechanics
are directly transferable and are used below, plus a retail sector note (Anand Rathi, Jun-10) and
Ethos (Axis Capital, Jan-24) for the same-store-sales treatment. The store-payback and
ADS content is domain-derived. **Raise an open question to add a mainstream QSR note to
`reference/er_corpus/seeds/`** — with `microfinance`, this is the registry's largest coverage hole.
Sibling `apparel_grocery_retail` and `hotels` are the authored files closest in method.

## The economic engine
A QSR chain is a **replicable box with a payback period**. Corporate value is the number of boxes
times the value each creates, so the whole analysis is: what does one store earn, what did it
cost, and how many more can be built before the good sites run out.

`Store revenue = ADS × 365` where `ADS = transactions/day × average bill value`
`Store contribution = revenue × (1 − food cost − payroll − occupancy − other store opex)`
`Payback years = capex per store / annual store EBITDA`

Distinguishing features against the sibling playbooks:

- **The unit is small, so the site decision is the strategy.** A wrong site cannot be fixed by
  merchandising the way a wrong retail assortment can. Site quality shows up as ADS dispersion
  across the estate, which almost no company discloses and which you should ask for.
- **Delivery has restructured the economics.** Delivery revenue carries aggregator commission
  (typically 18-25%) but uses the same kitchen, so it is *margin-accretive on operating leverage
  and margin-dilutive on gross take*. Get the dine-in / takeaway / delivery split with the
  contribution margin of each, and never accept a blended figure.
- **Ind AS 116 dominates the reported numbers**, exactly as in `apparel_grocery_retail`. Most QSR
  peer tables in the market are quietly comparing pre- and post-lease-capitalisation EBITDA.
- **Concession and franchise structures can decouple reported revenue from the business.** Travel
  Food Services is the corpus's worked warning: system-wide revenue growing at a 21% CAGR
  (FY25-28E) while *reported consolidated* revenue grows 6%, because units and lounges were
  mobilised from the parent into JVs. **Reported revenue was not the business.** Always establish
  whether you are looking at system-wide, reported, or attributable numbers — the same discipline
  `hotels` applies to attributable EBITDA.

## Analysis sequence
1. **Store-level unit economics first, not consolidated margin.** Capex per store, ADS at
   maturity, store EBITDA margin, payback. Everything else is a multiple of this.
2. **Decompose SSSG into transactions and average bill value.** SSSG driven by price/ticket while
   transactions fall is a shrinking franchise being harvested — the single most important
   distinction in this sector, and the one most often blurred.
3. **The maturity cohort split** — stores <1 year, 1-2 years, mature. New stores drag consolidated
   margin while ramping; a chain adding 20% to its store count will report falling margins with
   every cohort improving.
4. **Channel mix with contribution margin by channel** — dine-in, takeaway, delivery (own app vs
   aggregator). Include aggregator commission and, separately, discounting funded by the brand.
5. **Cost stack and its input exposure** — food and packaging cost as % of revenue (chicken,
   cheese, wheat, edible oil, potato, coffee), payroll, occupancy, energy. Then the pass-through
   mechanism, which in QSR is menu repricing and is *visible to the customer* — hence limited.
6. **Estate quality and whitewater** — store count by city tier and format, ADS dispersion, and
   the closure record. Closures are the honest signal about site discipline.
7. **Brand/franchise structure** — master-franchise royalty rate, territory rights, capex
   obligations under the development agreement, and renewal dates. For a franchisee, **the
   franchisor's royalty is a permanent claim on the P&L that peers who own their brand do not
   carry** — normalise before comparing.
8. **Expansion pipeline against the site funnel** — signed leases, not intentions — and the capex
   and funding plan.
9. **Then consolidated margin as a weighted result, ROCE, and the multiple.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **SSSG** | revenue growth of stores open ≥12 months | % | **Always decomposed into transaction growth and average-bill-value growth.** Positive SSSG on falling transactions is price-led and self-limiting. Get the qualifying-store definition | Decks, transcripts |
| **Average daily sales (ADS)** | store revenue / operating days | INR/store/day | The sector's core productivity unit. Track by cohort and by format; ask for dispersion across the estate, not just the mean | Decks |
| **Store EBITDA margin** | store-level EBITDA / store revenue | % | Pre-corporate-overhead unit profitability — the number that decides whether the next store creates value. State the Ind-AS basis explicitly | Decks, or derived |
| **Store count** | operating stores, gross adds and closures | count | **Closures are the site-discipline signal**; net adds conceal them. Split by brand, city tier and format | Decks |
| **Store payback** | capex per store / annual store EBITDA | years | The capital-allocation test. Under ~3 years is genuinely good; above ~5 the rollout is destroying value however fast revenue grows | Derived from capex + store EBITDA |

## Supporting KPIs
Transactions per store per day; average bill value; dine-in / takeaway / delivery mix with
contribution margin by channel; aggregator commission rate and brand-funded discount as % of
delivery revenue; own-app share of delivery orders; food and packaging cost as % of revenue;
payroll as % of revenue; occupancy cost as % of revenue and the fixed/revenue-share lease split;
energy cost per store; menu price increase taken (and when); new-product contribution;
gross margin by menu category; store count by city tier and by format (mall / high-street /
drive-thru / travel / cloud kitchen); area per store; capex per store and per sq ft; pre- and
post-Ind-AS-116 EBITDA (both); royalty rate paid to the franchisor; development-agreement store
commitments and dates; loyalty membership and its order share; ROCE pre- and post-lease;
net debt including lease liabilities; **system-wide vs reported vs attributable revenue** where
JVs or concessions exist.

## Standard exhibit set
Store unit economics table (capex, mature ADS, store EBITDA, payback) · SSSG decomposed into
transactions and bill value · ADS by cohort and by format, with dispersion if obtainable ·
store count with gross adds and closures shown separately · maturity-cohort mix of the estate ·
channel mix with contribution margin by channel · aggregator commission and brand-funded
discount trend · food-cost ratio against the key input indices · cost stack as % of revenue with
each line's fixed/variable character · menu-price-increase history vs food inflation ·
store count by city tier · pre- vs post-Ind-AS-116 EBITDA reconciliation · royalty as % of
revenue vs brand-owning peers · **system-wide vs reported revenue bridge** where JV/concession
structures exist (the Travel Food Services lesson) · expansion pipeline with signed leases ·
ROCE pre- and post-lease · EV/EBITDA band · peer table on one consistent lease basis.

## Valuation convention
**EV/EBITDA on a forward year, with the lease-accounting basis stated and the peer table
reconciled to it.** State whether the multiple is pre- or post-Ind-AS 116; the market quotes
both, and the gap is large enough to change a rating. **Store-level economics gate the
multiple**: a chain whose stores pay back in 2.5 years deserves a materially higher multiple than
one at 5 years even at identical growth, because the second is converting shareholder capital into
revenue rather than into value.

A **DCF is the honest cross-check** here, because a rollout is a knowable capex schedule against
a knowable payback — and it prices the *end* of the site runway, which a multiple never does. Where
the company is a franchisee rather than a brand owner, normalise for the royalty before comparing
to a brand-owning peer, and say so.

Where a concession or JV structure decouples reported from system-wide revenue, value the
**attributable** economics and publish the bridge — Travel Food Services was valued on 42x
Sep'27E EPS *while* reported revenue grew 6% against 21% system-wide, and only the bridge makes
that coherent.

*Traps:* (i) mixing lease bases across the peer table; (ii) valuing consolidated margin
mid-expansion when ramping stores depress it — value cohorts separately or roll the base forward;
(iii) accepting price-led SSSG as franchise growth; (iv) extrapolating a post-Covid dine-in
recovery; (v) crediting an announced store pipeline without signed leases; (vi) comparing a
franchisee's multiple to a brand owner's without adjusting for royalty; (vii) reading
system-wide revenue growth as accruing to shareholders when it accrues to a JV.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 24x forward EV/EBITDA; the peer trades at 19x, and both grow at 20%.**
- *Expensive* (`peer_set_choice`) — a 26% premium at identical growth.
- *Cheap* (`incremental_roce`) — store payback is 2.5 years against the peer's 5. At
  identical growth the first converts shareholder capital into value and the second
  converts it into revenue. Store-level economics gate the multiple.
- *Discriminator* (`disclosed_mechanism`) — the store-level P&L and the disclosed payback
  period, not the consolidated margin.

**2. The multiple is quoted at 24x.**
- *Comparable to the peer at 19x* (`accounting_basis`).
- *Not until the basis is stated* (`accounting_basis`) — the market quotes both pre- and
  post-Ind-AS 116 and the gap is large enough to change a rating. State which, and
  reconcile the peer table to it.
- *Discriminator* (`disclosed_mechanism`) — the lease note. This one resolves cleanly and
  there is no excuse for leaving it open.

**3. Management guides to 200 new stores.**
- *Visible growth* (`growth_rate`).
- *A finite runway being consumed* (`capital_intensity`) — a multiple never prices the
  *end* of the site runway, and a rollout is a knowable capex schedule against a knowable
  payback.
- *Discriminator* (`forward_observable`) — a DCF on the disclosed rollout, plus white-space
  store count by city tier with a date by which saturation binds.

## Forensic screens (sector-specific)
- **SSSG positive on falling transactions** — price is masking traffic loss.
- Net store adds quoted without closures; a rising closure rate in a specific city or format.
- ADS quoted for the whole estate when new-store ADS is materially lower — a mean concealing a
  deteriorating cohort.
- **System-wide, reported and attributable revenue used interchangeably** (Travel Food Services'
  JV mobilisation is the disclosed, honest version; an undisclosed version is a serious flag).
- Pre-opening, fit-out and training costs capitalised beyond the fit-out asset.
- Store EBITDA quoted pre-Ind-AS while consolidated EBITDA is post, or vice versa.
- Delivery revenue booked gross of aggregator commission with the commission in "other expenses".
- Brand-funded discounts netted against revenue in one period and expensed in another.
- Royalty or brand fees to a promoter-related entity; related-party supply-chain or commissary
  arrangements.
- Impairment of closed-store assets deferred; onerous-lease provisions not taken on
  loss-making stores still counted in the estate.
- Menu price increases taken quietly and then described as mix improvement.
- Franchise/development-agreement store commitments that will force capex regardless of returns —
  check the schedule and the penalty for missing it.

## Dependencies to map
Urban discretionary spend and eating-out frequency · aggregator platform economics (Swiggy/Zomato
commission trajectory and their own-brand private-label push, which is a direct competitive threat)
· quick-commerce entry into prepared food · key food inputs (chicken, cheese, wheat, edible oil,
potato, coffee) and their seasonality · mall supply, footfall and rental cycles in target
micro-markets; airport concession cycles and passenger traffic for travel QSR (Travel Food
Services: 8-10% passenger CAGR, 30+ new airports by FY29 — the concession model's demand driver) ·
GST rate and input-tax-credit treatment on restaurant services (the 5%-without-ITC regime is a
structural margin constraint unique to this sector) · minimum wage and shop-establishment rules ·
FSSAI regulation and packaging/plastic rules · the master-franchisor's global brand health and
territory policy · commercial rent inflation and lease-renewal cliffs.

## Common archetypes here
`capex-to-cashflow` (store rollout maturing — the dominant archetype, and the one whose
payback arithmetic must be shown rather than asserted), `margin-expansion` (operating leverage on
a fixed store cost base — legitimate when ADS is rising, illusory when it is mix),
`market-share-gainer`, `turnaround` (estate rationalisation and closures), and `garp`. Treat
`re-rating` with the standard skepticism weight. Be especially alert to `quality-compounder`
claims from franchisees: a royalty-paying operator with no brand ownership has a weaker moat than
the multiple usually implies.
