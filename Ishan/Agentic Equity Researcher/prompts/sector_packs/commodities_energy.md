# Sector Pack — Commodities, Energy & Utilities *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in
`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the exhibit set
and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the
two differ.** Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** businesses that convert or move a physical commodity and cannot set their
own output price — metals, cement, oil & gas, city gas, thermal and renewable power,
transmission and distribution, coal.

## What the whole family genuinely has in common

- **Analyse the spread, never the price.** Earnings are `realisation − cost` per unit. A
  company can be excellent while its output price falls, and dreadful while it rises. Every
  child's signature KPI is some form of per-unit spread; the unit differs (see the table).
- **Cost-curve position is the only durable edge.** Price-takers cannot out-market anyone.
  What creates the position — ore or fuel captivity, energy mix, logistics, scale, vintage of
  plant — and, critically, **how durable it is.** A cost advantage from a legacy linkage that
  expires is not a moat.
- **Supply, not demand, usually sets the cycle.** Demand growth in these sectors is
  slow and fairly predictable; the violent variable is capacity coming on stream. This is why
  `prompts/31` makes the supply–demand balance a hard deliverable for this family: existing
  capacity + announced additions − curtailments, against demand, split by region where China
  matters.
- **Mid-cycle discipline.** Cyclicals earn high multiples on trough earnings and low
  multiples on peak earnings. Never peak-on-peak, never trough-on-trough. Say explicitly
  where in the cycle the earnings base sits — this is the family's single most common
  analytical failure, and `prompts/thesis_archetypes/cyclical-peak.md` exists for it.
- **Policy is an input cost.** Duties and safeguards, carbon and pollution-norm capex,
  fuel-allocation regimes, tariff orders. Note the **expiry or review date** of anything
  favourable; a protected spread with a sunset is an annuity, not a moat.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Covers | Unit lens |
|---|---|---|
| `ferrous_non_ferrous_metals` | steel, aluminium, zinc, copper, recycling | per tonne |
| `cement` | integrated and grinding cement | per tonne |
| `oil_gas_cgd` | upstream, refining & marketing, city gas | per barrel / per scm |
| `power_utilities` | thermal generation, transmission, distribution | per MW |
| `renewables` | solar and wind manufacturing and generation | per watt / per MW |

**Regional pricing warning (cement especially, metals partly):** freight makes these
hyper-local. A national average realisation hides everything that matters. Analyse by region,
with lead distances.

**All five children are `status: authored`** (as of 2026-08-03), so triage resolves to a tier-2
playbook and that playbook governs. The degradation path survives only for future registry
additions: if a child is ever marked `status: pending`, analyse on this pack plus the closest
authored sibling — `ferrous_non_ferrous_metals` or `cement` for any spread-per-tonne business,
`power_utilities` for a regulated-return asset — say in the note which convention you borrowed,
and do **not** fall through to `generic`.
