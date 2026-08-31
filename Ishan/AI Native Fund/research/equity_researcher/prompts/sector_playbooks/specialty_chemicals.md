# Sector Playbook — Specialty & commodity chemicals

*Tier 2. Family: `pharma_chemicals` (`prompts/sector_packs/pharma_chemicals.md`). Shared
rules: `prompts/31`.*
**Provenance:** corpus-grounded — Tata Chemicals (JM Financial, Oct-25, 40pp, SOTP),
Aether Industries (HDFC Securities, Jul-22), Jubilant Ingrevia (Anand Rathi, Dec-25).

## The economic engine
Two very different businesses hide under one label, and **the first analytical act is to
decide which one you are looking at**:

- **Commodity chemical** (soda ash, caustic, bulk intermediates): a price-taker whose
  earnings are a spread. Analyse it exactly like a metal — cost-curve position,
  supply-demand balance, spread per tonne. Never award it a specialty multiple.
- **True specialty / CRAMS**: molecules made to a customer's specification under
  multi-year contracts, where the moat is process chemistry, regulatory approval and
  switching cost. Earnings are contract-driven, not price-driven.

Most Indian "specialty chemical" companies are a blend. Split revenue and EBITDA between
the two before valuing anything — this is what Tata Chemicals' SOTP does.

## Analysis sequence
1. **Segment the portfolio** into commodity vs specialty vs CRAMS, by revenue and EBITDA.
2. **For the commodity leg:** capacity, utilisation, realisation per tonne, cost of
   production per tonne, and the resulting spread; then the global supply-demand balance
   including Chinese capacity, and the company's cost-curve quartile.
3. **For the specialty leg:** molecule count, revenue concentration by molecule and by
   customer, contract tenor, and the pipeline of molecules in validation.
4. **Backward integration** — which key raw materials and intermediates are made in-house,
   quantified as a margin advantage per unit, and the China dependence on the rest.
5. **Capacity pipeline** — multipurpose vs dedicated plants, capex per tonne of capacity,
   commissioning dates, and ramp.
6. **Regulatory and environmental** — consents, effluent capacity, and the pollution-norm
   capex ahead. In India this is a real barrier to entry and a real liability.
7. **China+1 evidence** — actual share shifts and customer wins, not the narrative.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **EBITDA per tonne** | segment EBITDA / volume | INR/t | The commodity leg's whole story; separates volume from spread | Segment note + volume disclosure |
| **Realisation per tonne** | segment revenue / volume | INR/t | Against the relevant global price index | Computed |
| **Capacity utilisation** | production / installed capacity | % | Drives operating leverage; the swing variable in a capex cycle | AR capacity table |
| **Revenue concentration** | top-5 molecule and top-5 customer share | % | The specialty leg's key risk; a "contracted" business with 60% in one molecule is not diversified | Decks, AR |
| **Contracted revenue share & tenor** | revenue under multi-year contract / total; weighted years | %, years | The difference between specialty and commodity, made numeric | Decks, transcripts |

## Supporting KPIs
Volume by segment; gross margin (raw-material spread); backward-integration %; R&D as %
of sales; molecules commercialised per year; export share and geography mix; capex per
tonne; net debt/EBITDA; working-capital days (chemicals run heavy); ROCE by segment.

## Standard exhibit set
Revenue and EBITDA split commodity vs specialty · capacity by plant and product ·
utilisation trend · realisation and cost per tonne with the spread · global price index
overlay · supply-demand balance including China · customer and molecule concentration ·
contract tenor profile · capex pipeline with commissioning · backward-integration map ·
segment ROCE · SOTP table.

## Valuation convention
**SOTP is the correct default for blended companies** — a different multiple for each leg,
each peer-anchored. Tata Chemicals (JM, Oct-25) is the corpus's best example: 9x Sep'27E
India business EBITDA, 8x UK business EBITDA, a **20% holding-company discount** on the
Rallis stake, summing to a Sep'26 TP of INR 970 with **implied blended 10x EV/EBITDA and
23x P/E published as a sanity check** (`docs/ER_CORPUS_FINDINGS.md` §7.7). Publishing the
implied blended multiple is the part most SOTPs omit, and it is what makes the parts
falsifiable.

*Traps:* (i) applying a specialty multiple to commodity earnings — the single most common
error in this sector; (ii) valuing peak-spread commodity earnings on a peak multiple;
(iii) ignoring the holdco discount on listed subsidiary stakes; (iv) crediting announced
capacity before commissioning.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The company trades at a blended 14x EV/EBITDA, in line with specialty peers.**
- *Fairly valued* (`peer_set_choice`).
- *A specialty multiple on commodity earnings* (`peer_set_choice`) — the single most common
  error in the sector. Tata Chemicals (JM, Oct-25) shows the discipline: 9x Sep'27E India
  EBITDA, 8x UK EBITDA, a 20% holding-company discount on the Rallis stake, summing to a
  Sep'26 TP of INR 970 — with the **implied blended 10x EV/EBITDA and 23x P/E published as
  a sanity check.** Publishing the implied blend is the part most SOTPs omit, and it is what
  makes the parts falsifiable.
- *Discriminator* (`disclosed_mechanism`) — segment EBITDA split by specialty versus
  commodity, each anchored to its own named peer set.

**2. EBITDA margin rose 500bps to 24%.**
- *Mix shift into specialty* (`growth_durability`).
- *A commodity spread* (`cycle_position`) — the commodity leg's spread widened and will
  narrow.
- *Discriminator* (`historical_distribution`) — segment margins against their own bands. A
  consolidated margin cannot separate the two; segment margins can.

## Forensic screens
- Volume flat while revenue rises → the "growth" is price, and price reverses.
- Gross margin expansion coinciding with a fall in a key input index → cyclical, not
  structural (see `margin-expansion.md` condition 5).
- Inventory days rising into a capacity ramp.
- Capitalised R&D or trial-run costs.
- Contract "wins" announced without value or tenor.
- Environmental show-cause notices, consent-to-operate lapses, effluent-related shutdowns.

## Dependencies to map
Crude and naphtha · key intermediate prices and Chinese export behaviour · anti-dumping
duties and their expiry · customer patent cliffs (for CRAMS) · rupee (mostly exporters) ·
state pollution-control boards · power and coal cost (energy-intensive) · PLI where
applicable.

## Common archetypes here
`capex-to-cashflow`, `margin-expansion`, `regulatory-tailwind` (China+1, PLI, anti-dumping),
`cyclical-recovery` for the commodity legs, `special-situation` where a demerger separates
the two businesses. Be alert to `cyclical-peak` dressed as structural specialty growth.
