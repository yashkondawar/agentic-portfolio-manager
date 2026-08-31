<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — IT, Technology & Digital *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

**Core truth:** Human-capital arbitrage -> asset-light high ROCE; the durability question is non-linearity (revenue per employee) and AI's effect on both utilization and pricing.

## What the whole family has in common
- **Non-linear growth**: revenue growth vs headcount growth divergence; platform/IP revenue share; niche digital talent pool; sustained pricing power.
- **Margin levers**: pyramid structure (fresher %), subcontracting %, offshore/onsite mix, utilization — who has slack left.
- **Demand**: client-sector IT budgets (US/EU BFSI, retail, hi-tech), large-deal TCV pipeline and tenure, vendor-consolidation win/loss.
- **AI/GenAI disruption (mandatory)**: effect on pricing of core services, productivity pass-through demands from clients, each peer's monetization posture — evidence, not vendor slogans. Impact on utilization rates and pricing power for core services.
- **Talent**: attrition trend (replacement-cost drag), wage inflation for niche skills (cloud/cyber/data).
- **FX**: extent of the USD-revenue / INR-cost natural hedge; hedging policy.
- **Business model**: how the asset-light, human-capital-arbitrage model translates into observed high ROCE — verify the mechanism, don't assume it.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `it_services` | constant currency, total contract value, offshore mix | per employee | authored |
| `internet_platforms` | gross merchandise value, take rate, contribution margin | per transacting user | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `pe_forward`; secondary `ev_sales`, `ev_ebitda_forward`; conditioned by `growth_rate`, `growth_durability`, `own_history_anchor`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/it_technology.yaml` — 26 KPIs across 8 categories (Core Valuation, Core Profitability, Efficiency, Talent, Cash Flow, Cash Flow Quality, Pricing Stickiness, New Age Tech). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** P/E premium vs revenue-per-employee trajectory, attrition differential, and evidenced AI-defense — growth quality over growth quantity.

**Preferred sources:** Company factsheets (they disclose utilization/attrition), NASSCOM, Gartner/IDC citations, USD reporting where available.
