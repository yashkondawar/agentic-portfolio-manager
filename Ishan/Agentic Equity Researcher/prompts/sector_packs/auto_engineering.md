# Sector Pack — Autos, Engineering & Manufacturing *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in
`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the exhibit set
and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the
two differ.** Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** discrete manufacturing — vehicle OEMs, auto ancillaries, tyres, electronics
manufacturing services, defence manufacturing and industrial products.

## What the whole family genuinely has in common

- **Volume is the independent variable and operating leverage does the rest.** These are fixed-
  cost businesses making discrete units, so a small volume miss moves margin hard. Every
  forecast in this family is a volume forecast with a margin consequence attached, and the
  break-even utilisation is the number that tells you how much room there is.
- **Demand is cyclical and each end-market has its own clock.** CV volumes track freight and
  GDP, PV tracks consumer credit, 2W tracks rural cash flow, defence and industrial capex
  track government budgets, EMS tracks the consumer-electronics cycle. Never blend them into
  "auto demand" — position each sub-segment separately.
- **Input costs pass through with a lag, and the lag is the margin.** Steel, aluminium, copper,
  rubber, resins. What matters is the *mechanism*: quarterly indexed pass-through clauses
  versus spot exposure versus annual price negotiation. Read the contract structure, not the
  commodity chart. Margin gained purely from a falling input reverses.
- **Customer concentration is structural here.** A component maker's fortunes belong to its
  platforms, an EMS company's to a handful of brands, a defence supplier's to one ministry.
  Top-5 customer share, platform-win pipeline, and the replacement risk when a platform ends.
- **A technology transition is running underneath the whole family** — electrification,
  premiumisation of content, localisation under PLI. The question is always whether the
  company's content per unit rises or falls in the new architecture, evidenced by awarded
  business rather than by announcements.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Covers | Unit lens |
|---|---|---|
| `auto_oem` | PV, CV, 2W and tractor manufacturers | per vehicle |
| `auto_ancillary` | components, systems, tyres, forgings | per vehicle |
| `electronics_manufacturing` | EMS and ODM | per unit |
| `defence_manufacturing` | defence platforms, systems and ordnance | per order |

Order-book-driven industrial equipment makers may fit `infra_capital_goods` →
`capital_goods_electrical` better than this family; decide on whether revenue is recognised
per unit shipped (here) or per project executed (there), and record the reason.

**All four children are `status: authored`** (as of 2026-08-03), so triage resolves to a tier-2
playbook and that playbook governs. The degradation path survives only for future registry
additions: if a child is ever marked `status: pending`, analyse on this pack plus the closest
authored sibling (`auto_ancillary` for anything sold into a platform,
`electronics_manufacturing` for contract assembly, `defence_manufacturing` for order-book
execution), state in the note which convention you borrowed, and do **not** fall through to
`generic`.

## Preferred sources for this family

SIAM, FADA and the VAHAN registration portal (registrations versus wholesale dispatches is
the channel-inventory tell), company monthly volume disclosures, MoD and MoRTH
announcements, PLI notifications, and steel/aluminium/rubber price indices. Per-child source
notes live in the playbook.
