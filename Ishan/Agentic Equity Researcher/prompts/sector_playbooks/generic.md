# Sector Playbook — Generic (classification-first)

*Tier 2. Family: `generic` (`prompts/sector_packs/generic.md`). Shared rules: `prompts/31`.*
**Provenance:** method file, not a sector. Derived from the structure of the 165-note corpus
(`docs/ER_CORPUS_FINDINGS.md` §3) rather than from any one sector's notes.

## When you are here

Triage resolved to `generic` because one of these is true, and **which one it is changes what
you do next**:

| Reason | What to do |
|---|---|
| **Uncovered sub-sector** — a real, coherent business the registry has no playbook for | Work through §1, then borrow the nearest playbook's convention and **say which and why**. Raise an open question proposing a new registry entry. |
| **Genuine conglomerate** — no segment dominant, several unrelated businesses | Do not pick one playbook. Run §1 per segment, then value by SOTP with a per-segment convention borrowed from each segment's playbook. |
| **Low-confidence classification** (T2 returned `confidence: low`) | Treat this as provisional. §1's output is what T2-RECHECK re-classifies against once module 03 has run. Expect to leave `generic`. |

Record which of the three applies in `state/triage.json`. A conglomerate and an unrecognised
single business need different work, and collapsing them is the main way this route
produces a weak note.

## §1 — Classify the machine

The corpus's reasoning chain starts with "what is this machine?" before any number. Answer
these five, from the AR's business description and segment note:

1. **What is sold, to whom, and how is it priced?** Contract, list price, regulated tariff,
   auction, spread over an index, subscription, or take-rate on someone else's transaction.
   Pricing mechanism determines almost everything downstream.
2. **What is the natural unit?** Tonne, litre, unit, store, bed, key, room-night, seat,
   subscriber, loan, project, kilometre, square foot, transaction. If there is no physical
   unit, name the economic one (per ₹ of average assets, per employee). This becomes
   `unit_economics.denominator` in `state/business_model.json`.
3. **Where does the money go?** The three largest cost lines as a % of revenue, and whether
   each is fixed, variable, or index-linked. This is what makes the margin move.
4. **What is it structurally long and short?** (`prompts/03` field 4.) A price-taker long
   its output and short its energy input behaves nothing like a franchise long its brand and
   short a commodity.
5. **Which of these five archetypes fits?** — from `prompts/sector_packs/generic.md`:
   asset-heavy price-taker · brand/distribution compounder · contract/order-book executor ·
   regulated utility · platform/network. State the answer and the evidence.

## §2 — Borrow, and declare the borrowing

Map the §1 answer to the nearest authored playbook and adopt its analysis sequence,
exhibit set and valuation convention:

| §1 answer | Borrow from |
|---|---|
| Asset-heavy price-taker, spread over an index | `ferrous_non_ferrous_metals` / `cement` / `specialty_chemicals` (commodity leg) |
| Brand + distribution, volume × realisation | `fmcg` |
| Footprint economics, per-site payback | `apparel_grocery_retail` / `qsr` / `hotels` / `hospitals` |
| Order book converted to revenue | `epc_construction` / `capital_goods_electrical` / `defence_manufacturing` |
| Regulated or contracted returns on an asset base | `power_utilities` / `renewables` |
| Spread on money, credit risk priced | `nbfc_diversified` / `banks_private` |
| Take-rate on third-party transactions | `internet_platforms` |
| People-hours arbitraged | `it_services` |

**Write the borrowing down in the note.** "We analyse X on the contract-executor playbook
because 78% of revenue is fixed-price EPC with a disclosed order book" is a defensible
methodological statement. Silently applying someone else's multiple is not.

## Signature KPIs

There are none by definition — that is what makes this the fallback. Instead, the **hard
deliverable is to find at least three KPIs the industry itself tracks** and define each with
formula, unit and source, from company decks, industry-association data and competitor
disclosure. `prompts/sector_packs/generic.md` states the same rule; this file is where you
execute it.

Test of a real sector KPI: **competitors disclose it too.** If only this company reports it,
it is a management-chosen metric, and management-chosen metrics flatter management. Tag it
`company_defined: true` and treat it as a claim to verify, not a benchmark.

Always computable regardless of sector, so there is never an empty KPI table: revenue growth,
gross and EBITDA margin, ROCE, ROE, cash conversion (CFO/EBITDA), working-capital days,
net debt/EBITDA, capex/revenue, and the §1 per-unit denominator applied to revenue, cost
and EBIT wherever volumes exist.

## Standard exhibit set

Segment revenue and EBIT mix over time · the value-chain map from `state/business_model.json`
(node, own/buy/sell-into, capacity) · the cost stack as % of revenue with each line's
fixed/variable/index character · the ≥3 industry KPIs found above · per-unit economics on
the §1 denominator · capex pipeline · peer table on a comparability-adjusted basis ·
own multiple band with the dates and causes of both extremes.

## Valuation convention

Borrow from §2 and **name the source of the convention**. Where no peer set is defensible,
fall back to the company's own multiple band with the earnings base explicitly normalised,
and say that the peer anchor is missing — a disclosed absence beats a fabricated comp set.

*Traps:* (i) applying a conglomerate's blended multiple when the segments deserve different
ones — use SOTP and publish the implied blended multiple as a sanity check, the way
`specialty_chemicals` does; (ii) borrowing a compounder's multiple for a business with half
the ROCE; (iii) a peer set assembled by SIC-code similarity rather than by economics.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The conglomerate trades at a blended 22x.**
- *Cheap against the market* (`peer_set_choice`).
- *A blend nobody built* (`peer_set_choice`) — applying a conglomerate's blended multiple
  when the segments deserve different ones is the standing trap. Use SOTP and publish the
  implied blended multiple as a sanity check, the way `specialty_chemicals` does.
- *Discriminator* (`disclosed_mechanism`) — segment EBIT with a named peer set per segment.

**2. No defensible peer set exists.**
- *Use the nearest sector* (`peer_set_choice`) — something is better than nothing.
- *A disclosed absence beats a fabricated comp set* (`own_history_anchor`) — fall back to
  the company's own multiple band with the earnings base explicitly normalised, and say
  plainly that the peer anchor is missing.
- *Discriminator* (`historical_distribution`) — the company's own band, with the
  normalisation stated. Where the convention is borrowed from another playbook, name the
  source of the convention.

**3. A peer set was assembled from companies with similar industry codes.**
- *Standard practice* (`peer_set_choice`).
- *Similarity of code is not similarity of economics* (`incremental_roce`) — borrowing a
  compounder's multiple for a business with half the ROCE is the same error in a different
  costume.
- *Discriminator* (`peer_distribution`) — ROCE, capital intensity and growth across the
  proposed set. If they do not cluster, it is not a peer set.

## Forensic screens

Cross-sector screens that apply whatever the business turns out to be:
- Segment reporting that changes definition between years — check the prior-year comparatives
  were restated, and whether the change flatters the growth segment.
- "Other" or "unallocated" growing faster than named segments.
- Revenue growth outpacing cash conversion for two or more years.
- Capex without a corresponding rise in the asset base or in capacity disclosure.
- Related-party revenue or purchases as a share of the total.
- A single customer, contract or geography above the concentration threshold in
  `config/agent_config.yaml`.
- Frequent changes of auditor, CFO, or accounting policy.

## Dependencies to map

Whatever §1's answers imply — but always check: the input the cost stack is most exposed to,
the regulator with pricing power over this business, the counterparty concentration, the FX
exposure (both revenue and debt), and the policy or duty regime that could change the
economics.

## Common archetypes here

Any. Type the thesis from the evidence per `prompts/thesis_archetypes/README.md`, not from
the sector — that is the whole point of typing return decomposition before archetype. Be
especially alert to `re-rating` and `deep-value-sotp`, which are the two theses most often
attached to businesses nobody has bothered to classify properly.

## Before you finish

Raise an open question proposing the registry entry this company should have had: the
suggested playbook slug, its family, high-precision keywords (**never a bare 2-4 letter
acronym** — see the warning in `config/sector_registry.yaml`), the signature KPIs you found,
and the valuation convention you used. That is how `generic` shrinks over time instead of
becoming a permanent parking bay.
