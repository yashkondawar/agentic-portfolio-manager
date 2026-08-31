# Sector Pack — IT, Technology & Digital *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in
`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the exhibit set
and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the
two differ.** Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** IT and ER&D services, software products and SaaS, and consumer internet
and fintech platforms.

## What the whole family genuinely has in common

- **Asset-light means the balance sheet is not the story — the income statement is.** ROCE is
  structurally high because there is little capital employed, so a high ROCE here is not the
  achievement it would be in a manufacturer. Judge these businesses on growth durability and
  margin architecture, not on returns on a small denominator.
- **The scaling question is linearity.** Does revenue require proportionate headcount, or
  does it decouple? Revenue per employee for services, contribution margin for platforms —
  different metrics, same underlying question, and it is the question that determines the
  multiple.
- **Revenue concentration is the standing risk.** Top-client share for services, top-category
  or top-city share for platforms. A concentrated book is a contract, not a franchise.
- **AI is a mandatory lens across the whole family, in both directions.** For services: does
  it compress pricing on core work, and is the client demanding the productivity gain? For
  platforms and SaaS: does it lower a competitor's cost to entry? Require evidence — deal
  terms, disclosed pricing, headcount-to-revenue trajectory — not vendor slogans. This is the
  one lens where a company's own narrative is least reliable.
- **Currency runs through everything.** Mostly USD revenue against an INR cost base, so a
  reported-INR growth rate conflates operating performance with FX. Constant-currency or
  USD-denominated growth is the honest series; note the hedging policy separately.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Covers | Unit lens |
|---|---|---|
| `it_services` | IT services, ER&D, BPM, engineering outsourcing | per employee |
| `internet_platforms` | marketplaces, consumer internet, fintech platforms, SaaS | per transacting user |

Software product and SaaS businesses route to `internet_platforms`, which carries the
recurring-revenue metrics (NRR, ARR, Rule of 40). A services company with a material product
line is multi-segment: primary by largest EBIT, the other as a `secondary_playbook`.

**Both children are `status: authored`** (as of 2026-08-03), so triage resolves to a tier-2
playbook and that playbook governs. The degradation path survives only for future registry
additions: if a child is ever marked `status: pending`, analyse on this pack plus the closer of
`it_services` and `internet_platforms`, state in the note which convention you borrowed, and do
**not** fall through to `generic`.

## Preferred sources for this family

Company factsheets (utilisation, attrition and offshore mix appear nowhere else), NASSCOM,
Gartner/IDC citations, USD-reported segment data, and app/traffic third-party estimates for
platforms — the last always tagged as an estimate, never as a disclosure. Per-child source
notes live in the playbook.
