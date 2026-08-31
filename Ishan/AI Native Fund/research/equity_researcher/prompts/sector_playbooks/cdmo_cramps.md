# Sector Playbook — CDMO / CRAMS / CRDMO

*Tier 2. Family: `pharma_chemicals` (`prompts/sector_packs/pharma_chemicals.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Piramal Pharma (JM Financial, Dec-24 — carries the corpus's best
CDMO peer-comparison table, including the discovery/development-vs-commercial revenue split across six
listed peers), Aether Industries (HDFC Securities, Jul-22 — contract-manufacturing chemistry),
Supriya Lifescience (Choice Broking, Nov-25 — 38+ commercial molecules, demand-pull expansion),
with `specialty_chemicals` (Jubilant Ingrevia, Tata Chemicals) as the authored sibling for the
chemistry-side economics.

## The economic engine
A CDMO does not own the molecule. **It sells manufacturing capability and regulatory reliability to
whoever does**, under contract. So the asset being valued is not a product portfolio but a
*relationship book*, and its value is a function of switching cost:

`Revenue = Σ (molecules in the book × volume per molecule × price per kg/unit)`

Once a CDMO's site and process are written into a customer's regulatory filing, **changing supplier
requires re-filing and re-validating** — months to years of work and regulatory risk for a saving the
customer usually will not chase. That is the moat, and it is real. But it has a precise shape that
determines everything:

- **The moat exists only for *commercial* molecules.** Discovery and early-development work is
  low-switching-cost, low-revenue-per-project, and mostly a funnel. Commercial-stage manufacturing is
  where the annuity lives. Piramal's peer table makes exactly this split — **discovery + development
  as % of CDMO revenue vs commercial as % of CDMO revenue** — and the spread across peers is wide
  (commercial ranging from ~35% to >80%). **Get this split; it is the single most informative number
  in the playbook** and it distinguishes a research-services business from a manufacturing annuity.
- **The moat is per-molecule, so concentration is the risk.** A CDMO with 60% of revenue in one
  customer's one molecule has one contract, not a franchise — and that molecule's patent cliff,
  clinical failure or in-sourcing decision is the company's cliff.
- **Growth is customer-funded but capacity-led.** The customer brings the molecule; the CDMO must have
  the reactor, the suite and the approval waiting. So capex precedes revenue and utilisation is the
  swing variable — but **capacity built ahead of visible demand is speculation, while capacity built
  behind it is a constraint.** Supriya's framing distinguishes them well: 85-86% historical
  utilisation easing to ~75% on commissioning is "strategic slack created ahead of visible demand …
  not a capacity-led growth story; it is a demand-pull expansion."

The industry tailwind is genuine and quantified in the corpus: the global CRDMO market is projected to
grow at a **9.1% CAGR over 2023-28 from a USD 197bn base** (Piramal note), driven by China+1, the
revival in biotech funding, and Indian cost leadership. Piramal's own CDMO segment is forecast at
**17% CAGR over three years** against that ~9% market — so the note is claiming share gain, which is
the kind of claim that needs the capability evidence below.

## Analysis sequence
1. **Split the CDMO revenue into discovery, development and commercial** (Piramal's peer-table axis).
   Then treat them as three businesses with different multiples, different visibility and different
   moats. A company at 65% discovery+development is a CRO wearing a CDMO label.
2. **Count and characterise the molecule book.** Commercial molecules, molecules in validation, and
   the development pipeline by phase. Supriya's "38+ commercial molecules across multiple therapeutic
   categories" is the disclosure to look for. Then: revenue per molecule, and the distribution —
   a book of 38 molecules where three are 60% of revenue is a concentrated book.
3. **Customer concentration, at two levels** — top-5 customer share, and top-5 *molecule* share. Both
   matter and they are different: diversified customers each buying one molecule is still fragile if
   the molecules are correlated (same therapy, same patent cliff).
4. **Contract structure**, molecule by molecule where disclosed: tenure, take-or-pay or minimum-volume
   commitments, price-variation and raw-material pass-through clauses, exclusivity, and the notice
   period. **"Contracted revenue" with a 90-day notice period is not contracted.**
5. **The customers' own pipelines.** This is the step generalist analysis skips and it is decisive: a
   CDMO's revenue is a derivative of its customers' molecules. For each major molecule, the
   innovator's patent expiry, clinical-trial status, and commercial trajectory. **A customer patent
   cliff is the CDMO's revenue cliff, on a knowable date.**
6. **Capability and capacity** — reactor volume (kL), suite count, technology platforms (HPAPI, ADC,
   peptides, oligonucleotides, flow chemistry, sterile fill-finish), and which of these are genuinely
   differentiated versus commodity chemistry. Then utilisation, and whether spare capacity is
   strategic slack or idle asset.
7. **Compliance across every site** — the same binary as `pharma_generics`, and arguably more
   consequential, because a customer will de-risk by dual-sourcing away from a site under action and
   may not come back.
8. **The China+1 claim, evidenced.** Actual customer wins, RFQ conversion, share shifts — not the
   narrative. This is the family pack's standing requirement and it applies most sharply here.
9. **Then the multiple**, which in this sector is the whole argument (see below).

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Commercial molecule count** | molecules in commercial-stage manufacturing | count | The annuity's breadth. **Report alongside the discovery/development/commercial revenue split** — Piramal's peer table shows commercial ranging ~35% to >80% of CDMO revenue, and that spread is the difference between a manufacturing annuity and a research-services book. Supriya: 38+ | Decks, AR |
| **Revenue concentration (top-5)** | top-5 customer share, and separately top-5 molecule share | % | **Both, because they fail differently.** A "contracted" business with 60% in one molecule is not diversified — the phrasing is borrowed deliberately from `specialty_chemicals`, where the same trap applies | Decks, AR |
| **Contracted revenue share** | revenue under multi-year contract / total; with weighted tenor | %, years | The specialty-vs-commodity distinction made numeric. **Get the notice period and any minimum-volume commitment** — tenor without enforceability is decoration | Decks, transcripts |
| **Capacity utilisation** | production / installed capacity (or reactor-hours used / available) | % | The operating-leverage variable and the growth constraint. Distinguish **strategic slack ahead of contracted demand** (Supriya: 85-86% → ~75% on commissioning, demand-pull) from idle capacity built on hope | AR capacity table, decks |
| **Gross margin** | (revenue − material cost) / revenue | % | The complexity and pass-through measure. Rising gross margin should trace to molecule mix or process improvement; if it traces to a falling input index it is a cycle, and if raw material passes through then margin should be *stable*, not rising | P&L |

## Supporting KPIs
Discovery / development / commercial revenue split (as % of CDMO revenue); molecules in validation and
in each clinical phase; new molecule additions and attrition per year; revenue per commercial molecule;
customer count and new-customer additions; share of revenue from innovator (patented) vs generic
customers; geography mix of customers (US/EU/Japan/domestic); reactor capacity in kL and suite count;
technology-platform capability list and the revenue attributable to differentiated platforms; capex per
kL and commissioning dates; R&D as % of sales; scientist headcount and PhD count (for the
development-heavy models); site compliance status per facility with attributable revenue;
regulatory-inspection history; order book / firm purchase orders where disclosed; RFQ pipeline and
conversion rate; working-capital days (CDMOs carry customer-specific inventory); receivable
concentration; forex exposure and hedging; net debt/EBITDA and the capex-funding plan; ROCE and
ROCE excluding capital-work-in-progress (critical here, because pre-revenue capacity depresses
returns and is often excluded selectively).

## Standard exhibit set
**Discovery / development / commercial revenue split, with a peer comparison on the same axis** (the
Piramal exhibit — the most valuable single chart in this playbook) · commercial molecule count and
molecules in validation over time · revenue concentration: top-5 customer and top-5 molecule, both ·
contract tenor profile with notice periods and minimum-volume commitments flagged · **customer
patent-cliff calendar for the major molecules** · capacity by site in kL with utilisation trend and
the strategic-slack vs idle distinction annotated · capex pipeline with capex per kL and commissioning
dates against contracted demand · technology-platform capability map with revenue attributable to
differentiated platforms · site compliance table (site, classification, inspection date, attributable
revenue) · global CRDMO market size and growth with the company's growth against it (Piramal: 17%
company CAGR vs ~9.1% market) · China+1 evidence: RFQs, wins, share shifts · gross margin by segment ·
working-capital days · ROCE including and excluding CWIP · EV/EBITDA band vs generics peers and vs
global CDMO peers.

## Valuation convention
**A premium P/E or EV/EBITDA versus generics, and the entire analytical burden is justifying the
premium with contract tenor and switching cost — quantify both.** This is the registry entry where the
valuation convention *is* the thesis, because the multiple gap between a CDMO and a commodity generic
is large and is awarded on assertion far more often than on evidence.

Piramal is stated at **21x/17x FY26/FY27 EV/EBITDA, described as a ~38% discount to peers** — note that
this is *discount*-based reasoning, which `docs/ER_CORPUS_FINDINGS.md` §6 identifies as the weakest of
the four justification families. **If our note argues a discount should close, it must name the
mechanism and the falsifier** (`prompts/34`'s test): what specifically causes re-rating, and what
observation would prove it is not happening. "Trades below peers" is an observation, not an argument.

The defensible premium arguments, in descending order of rigour:
1. **Commercial-stage revenue share plus contract tenor** — a book that is 80% commercial under
   multi-year contracts with minimum volumes is structurally different from one that is 35% commercial
   on purchase orders. Show the two peers side by side.
2. **Differentiated platform capability with revenue attached** (HPAPI, ADC, peptides, sterile) — not
   a capability list, a revenue split.
3. **A realised switching-cost event** — a customer that stayed through a price negotiation or a
   competitor's approach, or a molecule retained across a technology transfer. The corpus's own
   standard: "a claim with a price attached beats an adjective" (§7.2).
4. **Discount-narrowing (weakest)** — permitted only with a named mechanism and falsifier.

Where the company blends CDMO with generics or specialty chemicals, use **SOTP** with a
peer-anchored multiple per leg and publish the implied blended multiple as a sanity check.

*Traps:* (i) awarding a CDMO multiple to a business that is mostly discovery/development services or
mostly commodity API — get the split first; (ii) treating "contracted revenue" as durable without the
notice period and volume commitment; (iii) ignoring the customer's patent cliff, which is a dated
revenue cliff; (iv) valuing announced capacity before commissioning *and* before contracted demand;
(v) capitalising a Covid-era or shortage-driven volume spike; (vi) discount-narrowing without a
mechanism; (vii) ROCE quoted excluding CWIP while the multiple is applied to consolidated earnings.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It is stated at 21x/17x FY26/FY27 EV/EBITDA, "a ~38% discount to peers".**
- *Cheap* (`peer_set_choice`) — Piramal's note frames it this way.
- *The weakest available argument* (`peer_set_choice`) — discount-based reasoning ranks last
  of the four justification families in `docs/ER_CORPUS_FINDINGS.md` §6. If our note argues
  a discount should close it must name the mechanism and the falsifier: what specifically
  causes the re-rating, and what would disprove it.
- *Discriminator* (`disclosed_mechanism`) — a named, dated cause. Absent one, this is F1 and
  the ledger entry stays unresolved.

**2. It trades at a premium to commodity generics.**
- *Correct — it is a CDMO* (`peer_set_choice`).
- *The premium is the entire analytical burden* (`growth_durability`) — this is the registry
  entry where the valuation convention *is* the thesis, because the gap between a CDMO and a
  commodity generic is large and is awarded on assertion far more often than on evidence.
  Contract tenor and switching cost must both be quantified.
- *Discriminator* (`disclosed_mechanism`) — average contract tenor, customer concentration,
  and the commercial-phase versus clinical-phase revenue split.

## Forensic screens (sector-specific)
- **The discovery/development/commercial split not disclosed**, or redefined between periods — the
  single most consequential omission in this sector.
- "Contracted revenue" or "committed revenue" quoted without tenor, notice period or minimum volume.
- A single molecule or customer above the concentration threshold in `config/agent_config.yaml`, with
  the exposure not named; customer names withheld while revenue concentration rises.
- Contract "wins" announced without value or tenor (the screen is inherited from
  `specialty_chemicals` and applies verbatim here).
- Molecules moved between "commercial" and "validation" categories, or the pipeline count restated.
- Revenue recognised on validation and exhibit batches as if commercial.
- Capacity announced in kL with no customer, or capex commissioned into idle capacity while described
  as strategic slack — check against contracted volumes, not against RFQs.
- Utilisation computed on a favourable subset of reactors, or on nameplate vs effective capacity.
- Capitalisation of process-development, technology-transfer or trial-run costs; R&D capitalised where
  the customer funds the work.
- Customer-funded capex (a real and legitimate structure) presented as the company's own asset base
  without disclosing the customer's rights over it, or the take-or-pay that supports it.
- Inventory of customer-specific intermediates rising without a matching order — this inventory has
  one buyer and no alternative market.
- Site compliance action not linked to attributable revenue; a customer dual-sourcing away from a site
  after an inspection, disclosed only as a volume decline.
- Related-party arrangements where the promoter group owns a customer, a CRO or an intermediate supplier.
- Forex gains presented inside operating margin (this is a dollar-revenue business).

## Dependencies to map
Global biotech and pharma **R&D spending and funding conditions** — the demand driver for development-
stage work, and the corpus names its revival explicitly as a CRDMO tailwind · big-pharma outsourcing
policy and dual-sourcing norms · **customer patent cliffs**, molecule by molecule, with dates ·
China+1 sourcing decisions, and Chinese CDMO capacity, pricing and geopolitical exposure — including
US legislative action targeting Chinese CDMOs, which is the single largest swing factor in the Indian
sector's addressable market · the US BIOSECURE-type legislative track and EU supply-chain-resilience
policy · USFDA/EDQM inspection outcomes at every site · PLI for APIs/KSMs and bulk-drug parks ·
KSM and solvent prices and Chinese export behaviour (link to `specialty_chemicals`) · state
pollution-control boards and effluent capacity, which gate any chemistry expansion in India ·
USD-INR · anti-dumping duties on intermediates with their expiry dates · clinical-trial regulation
(CDSCO, DCGI) for the development-services leg.

## Common archetypes here
`capex-to-cashflow` (capacity commissioning against contracted demand — the dominant archetype, and
the one where the "against contracted demand" qualifier does the analytical work),
`regulatory-tailwind` (China+1, BIOSECURE-type policy, PLI — genuine, but require evidenced wins per
the family pack), `margin-expansion` (mix shift toward commercial and toward differentiated platforms),
`quality-compounder` — **defensible in this sector, more so than in generics, but only on the strength
of the commercial-revenue share plus contract tenor plus a realised switching-cost event** —
`special-situation` where a demerger separates CDMO from generics (a recurring structure), and
`re-rating`, which is the sector's most frequently attached and least frequently earned archetype:
being cheap against global CDMO peers is not a mechanism. Watch for `cyclical-peak` dressed as
structural China+1 demand when a shortage or a single large contract is doing the work.
