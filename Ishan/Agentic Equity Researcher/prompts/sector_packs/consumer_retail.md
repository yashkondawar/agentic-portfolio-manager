# Sector Pack — Consumer, Retail & Hospitality *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in
`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the exhibit set
and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the
two differ.** Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** businesses selling to the end consumer — packaged goods, durables, apparel
and grocery retail, quick-service restaurants, jewellery, alcoholic beverages, and hotels.
*(Scope note: this family covers hospitality. An earlier version of this pack scoped itself
"FMCG, discretionary, durables, QSR, liquor" while the registry called the family "Consumer,
Retail & Hospitality" — the registry was right and hotels route here.)*

## What the whole family genuinely has in common

- **Growth must be decomposed before it means anything.** Volume, price/mix, and footprint
  are three different stories with three different durabilities. A value-growth number that
  is not split is not an analysis. Which decomposition applies differs by child — volume ×
  realisation for packaged goods, same-store × new-store for footprint businesses, occupancy
  × rate for hotels — but the *requirement* to decompose is universal here.
- **The moat is access to the customer**, not the product. Distribution reach, shelf, store
  location, brand recall, or a booking relationship. It is expensive to build, slow to erode,
  and it is what justifies any premium multiple in this family. Quantify it or drop the claim.
- **Gross margin through an input cycle is the pricing-power test.** Holding or expanding
  gross margin while a key input rose is evidence; asserting "strong brand" is not.
- **Consumption demand is macro-linked and seasonal.** Rural cash flow and the monsoon,
  urban discretionary income and credit, festive and wedding seasonality, and — for anything
  alcohol- or tobacco-adjacent — state excise and route-to-market regimes that change without
  notice.
- **Channel disruption is live across the whole family.** Quick-commerce, D2C and marketplace
  economics are simultaneously a growth channel and a cannibalisation risk. Ask what it does
  to gross margin and to the distribution moat above, not just to the growth rate.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Covers | Unit lens |
|---|---|---|
| `fmcg` | packaged goods, home and personal care, foods, beverages | per case |
| `apparel_grocery_retail` | apparel, footwear, grocery and value retail, durables retail | per store |
| `qsr` | quick-service and casual-dining restaurant chains | per store |
| `hotels` | hotels and resorts, owned and managed | per key |

Jewellery and alcoholic beverages currently route to `apparel_grocery_retail` and `fmcg`
respectively; both have footprint or state-regime specifics the playbook notes.

**All four children are `status: authored`** (as of 2026-08-03), so triage resolves to a tier-2
playbook and that playbook governs. The degradation path survives only for future registry
additions: if a child is ever marked `status: pending`, analyse on this pack plus the closest
authored sibling (`hotels`, `qsr` or `apparel_grocery_retail` for footprint economics; `fmcg`
for brand-and-distribution economics), state in the note which convention you borrowed, and do
**not** fall through to `generic`.

## Preferred sources for this family

Company decks and transcripts (the only place channel and reach data appears), NielsenIQ /
Kantar citations, IMD monsoon data, state excise notifications, industry-association volume
data, and airport/tourism statistics for hospitality. Per-child source notes live in the
playbook.
