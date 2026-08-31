# knowledge/ — the three-tier knowledge contract

This tree is the deep, machine-and-human knowledge layer behind the fund's
compact agent-facing vocabulary in `registry/`. It exists so that
`registry/` can stay small and cheap to load into every agent packet while
the actual definitions, sourcing status, and prose reasoning live somewhere
versioned, validated, and NOT duplicated across three places.

## The three tiers (plus one DB table) — who owns what

1. **`registry/`** (unchanged, pre-existing) — compact, agent-facing
   vocabulary. KPI *names* + units + categories (`registry/kpis/*.yaml`),
   strategy definitions, risk rules. This is what gets stuffed into LLM
   context packets directly (`orchestrator/context.py`). It answers "what is
   this KPI called and what bucket does it belong to," not "how is it
   computed" or "how do I read it."

2. **`knowledge/data/`** (this tree, machine-readable) — deep, structured
   KPI *definitions*: formula, inputs and their sourcing status
   (available/derivable/manual/missing), orientation (value/fear/goldilocks
   per the cycle-positioning framework), lookback window, cadence, and a
   cross-reference back to the registry entry it defines. Also the 16-cycle
   catalog (`knowledge/data/cycles/catalog.yaml`) that anchors cycles to
   KPI ids. This is pydantic-validated by `knowledge/loader.py` and is
   **the KPI finder**: `source_status` here is what gates whether the
   (Phase 7+) cycle engine can compute a given cycle live today, and doubles
   as a sourcing worklist for Phase 8.

3. **`knowledge/references/`** (this tree, prose) — how-to-analyze
   methodology, sector playbooks, and KPI interpretation guides. Markdown,
   NOT parsed or validated by the loader (listed only — path + a one-line
   summary is what agents get in a packet; an agent Reads the file itself
   only if it decides it needs the full prose). This is where the
   cycle-positioning framework, the buy-side depth methodology, the 4-gate
   funnel, and the narrative-intensity scoring rules live as clean
   reference documents, plus the 8 sector playbooks.

4. **`knowledge_base` (DB table, unchanged)** — NOT part of this
   directory tree. This is the machine-accumulated, timestamped notes table
   (`INSTRUMENT`/`SECTOR`/`MACRO`/`SITUATION` tagged) that agents like
   `macro_digest` write into over time — the fund's running research
   memory, distinct from the static definitions/prose above.

## A fifth, future tier: generated ER sector packs (Phase 9)

The external Equity Researcher subsystem (`research/equity_researcher/`,
copied in Phase 9) has its own `prompts/sector_packs/*.md`. Once Phase 9
lands, those become **GENERATED artifacts** — produced one-way by
`scripts/gen_sector_packs.py` FROM `registry/kpis/*.yaml` +
`knowledge/references/sectors/*.md`, stamped with a `<!-- GENERATED -->`
header. The registry + this tree are authoritative; the ER packs are a
rendering of them for the ER subsystem's own prompts, never edited by hand
and never a second source of truth. Not yet built — noted here so the
contract is documented before it exists.

## No duplication rule

If you find yourself writing the same sentence in two of these places,
that's a bug. The concrete rule: `registry/` never contains a formula,
`knowledge/data/` never contains a paragraph of prose reasoning, and
`knowledge/references/` never restates the registry's KPI list — it
cross-references KPI ids and points back into `registry/kpis/` and
`knowledge/data/kpis/` instead.

## Directory map

```
knowledge/
  README.md                        <- this file
  loader.py                        <- pydantic loader, mirrors registry/registry.py
  data/
    kpis/
      _schema.yaml                 <- field spec every KPI yaml must conform to
      *.yaml                       <- one file per macro KPI (yield_gap, evi, cpi_yoy, ...)
      micro/<8 sectors>.yaml       <- deep defs behind registry/kpis/<sector>.yaml vocabulary
    cycles/
      catalog.yaml                 <- the 16-cycle catalog
  references/
    methodology/
      cycle_positioning_framework.md
      buyside_depth.md
      funnel_4gate.md
      narrative_intensity_scoring.md
    sectors/<8>.md                 <- sector playbooks (superset of registry + ER packs)
    kpi_interpretation/
      valuation_cycle.md
      rate_liquidity_cycle.md
      credit_cycle.md
      sentiment_cycle.md
```

## Usage

```python
from knowledge.loader import load

k = load()
k.kpis["yield_gap"]          # KpiDef, by kpi_id, macro + micro merged
k.catalog.cycles              # list[CycleDef], the 16-cycle catalog
k.version                     # git-SHA (or content-hash fallback), same pattern as registry.Registry
```

`references/` is intentionally NOT exposed as parsed objects — only listed
(see `knowledge/loader.py`'s `references` field: path + first-line summary).
Agents get reference *pointers* in their context packets, never the whole
prose file, per `src/afund/orchestrator/context.py`'s packet-budget
discipline.
