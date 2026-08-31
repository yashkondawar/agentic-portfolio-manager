# Sector Pack — Generic *(tier 1 — fallback routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The method lives in the tier-2
playbook `prompts/sector_playbooks/generic.md`, which is a **classification** playbook rather
than a sector one. Per `prompts/03`, the playbook supersedes this pack wherever the two
differ. Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** the deliberate fallback. Three distinct situations land here, and the
playbook's first job is to say which:

1. **An uncovered sub-sector** — a coherent business the registry has no playbook for.
2. **A genuine conglomerate** — no dominant segment, several unrelated businesses.
3. **A low-confidence classification** — T2 returned `confidence: low` and this is provisional.

Collapsing these three is the main way a `generic` run produces a weak note.

## The one rule this family exists to enforce

**Classify before you analyse.** Answer, from the AR's business description and segment note:
what is sold and how is it priced · what the natural unit is · where the money goes · what
the business is structurally long and short · and which of five economic archetypes it is
(asset-heavy price-taker · brand/distribution compounder · contract/order-book executor ·
regulated utility · platform/network).

Then **borrow the nearest authored playbook's convention and say in the note which one and
why.** A stated methodological borrowing is defensible; silently applying someone else's
multiple is not. `prompts/sector_playbooks/generic.md` carries the mapping table, the
cross-sector forensic screens, and the requirement to find ≥3 KPIs the industry itself
tracks.

## Child playbooks

| Playbook | Covers | Unit lens |
|---|---|---|
| `generic` | the classification method itself | set by classification |

## Leaving this family

`generic` should shrink over time. Every run that lands here must raise an open question
proposing the registry entry the company should have had — suggested slug, family,
high-precision keywords (**never a bare 2-4 letter acronym**, per the warning in
`config/sector_registry.yaml`), signature KPIs found, and the valuation convention used.
Otherwise this becomes a permanent parking bay rather than a fallback.

Note also that **T2-RECHECK re-runs classification after module 03 has mapped the value
chain**. A company that entered `generic` on a thin keyword match will often leave it once
the business model is actually understood — that is the intended behaviour, not a failure.
