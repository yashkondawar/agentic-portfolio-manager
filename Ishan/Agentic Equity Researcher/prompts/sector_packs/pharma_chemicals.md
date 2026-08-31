# Sector Pack — Pharma, Healthcare & Chemicals *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in
`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the exhibit set
and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the
two differ.** Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** regulated-molecule and regulated-care businesses — generic and domestic
formulations, APIs and intermediates, CDMO/CRAMS, specialty and commodity chemicals,
agrochemicals, hospitals and diagnostics.

## What the whole family genuinely has in common

- **A regulator caps the price, and a different regulator caps the right to sell.** NPPA/NLEM
  on domestic drug prices, scheme tariffs on hospital procedures, USFDA/EDQM on market access,
  state pollution boards on the right to operate a chemical plant. **Two independent ceilings**
  — one on price, one on access — and losing either one is an existential event, not a margin
  event. This is the family's defining feature.
- **Complexity is the moat; commodity is the default.** Value accrues to what is hard to
  replicate — a validated molecule, a clean facility, a mature hospital cluster, a
  multi-year contracted process. Everything else erodes toward cost. **The first analytical
  act in this family is deciding which half of the business you are looking at**, because a
  contracted CDMO and a commodity generic must never share a multiple. Most Indian companies
  here are a blend; split revenue and EBITDA before valuing anything.
- **Compliance history is a hard input, not a soft one.** Facility-by-facility inspection
  outcomes, warning letters, import alerts, consent-to-operate lapses. Quantify revenue at
  risk per site and assess remediation credibility against the company's own past record.
- **Capacity and capability take years, so the pipeline is the growth.** Filings, approvals,
  molecules in validation, beds under construction, labs being accredited. New capacity is
  dilutive to margins while it ramps — never blend a ramping asset with a mature one.
- **China is the reference cost curve** for anything molecule-based, in both directions: a
  source of input dependence, and the reason China+1 demand exists. Require evidenced share
  shifts and customer wins, not narrative.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Covers | Unit lens |
|---|---|---|
| `pharma_generics` | US/EM generics, domestic formulations | per molecule |
| `cdmo_cramps` | contract development and manufacturing, custom synthesis | per molecule |
| `specialty_chemicals` | specialty and commodity chemicals, agrochemicals | per tonne |
| `hospitals` | hospital chains | per bed |
| `diagnostics` | pathology and radiology chains | per test |

APIs and intermediates route to `specialty_chemicals` where the economics are spread-per-tonne,
or to `cdmo_cramps` where revenue is contracted per molecule — decide by which describes the
majority of revenue, and record why.

**All five children are `status: authored`** (as of 2026-08-03), so triage resolves to a tier-2
playbook and that playbook governs. The degradation path survives only for future registry
additions: if a child is ever marked `status: pending`, analyse on this pack plus the closest
authored sibling (`specialty_chemicals` for chemistry, `pharma_generics` or `cdmo_cramps` for a
regulated molecule, `hospitals` or `diagnostics` for care delivery), state in the note which
convention you borrowed, and do **not** fall through to `generic`.

## Preferred sources for this family

USFDA inspection classification database, NPPA/NLEM lists, CDSCO, PLI notifications, IQVIA
citations for domestic market share, state pollution-control board orders, and Ayushman
Bharat / state scheme rate notifications for care delivery. Per-child source notes live in
the playbook.
