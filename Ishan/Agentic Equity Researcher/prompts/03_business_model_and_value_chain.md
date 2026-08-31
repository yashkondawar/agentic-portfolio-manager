# 03 — Business-Model & Value-Chain Mapping (the analytical spine)
*(NEW in v2; sonnet tier, medium thinking; runs ONCE early — right after triage, before the analysis wave — and is re-touched only if a restatement/segment change invalidates it. Rationale: `docs/PROCESS_V2_REIMAGINED.md`.)*

## Why this module exists (read first)
A good report is not "every number in the filing." It is an understanding of the business
as a physical, economic machine plus the 8–15 numbers that actually drive it. This module
builds that understanding **up front** so it can steer everything downstream: what to
extract deeply, which KPI trends `tools/compute_kpis.py` should compute, what DR2 should
research, and which exhibits the report must carry. It is **sector-agnostic** — a method for
deciding what matters in *any* industry, not a metals template — which is also what makes
the system work when only a couple of filings exist (see `prompts/70_sparse_data_playbook.md`).

Do not do financial analysis here (that's module 20) or valuation (32). Here you decide
*what the analysis should be about*.

## Inputs
- Latest annual report business-overview + segment note + MD&A (from `cache/markdown/`).
- `state/triage.json` (sector pack, segment count, peer seed), `state/manifest.json` (what
  documents exist — this sets how much history you can promise).
- The chosen `prompts/sector_packs/<pack>.md` (tier-1 family) — its KPI list is raw material.
- **The tier-2 playbook** named in `state/triage.json`, if `playbook_status: authored`:
  `prompts/sector_playbooks/<slug>.md`. It supersedes the family pack wherever they differ,
  and its **signature KPIs carry formula, unit, benchmark read and source** — use those
  definitions verbatim rather than inventing your own.
- `config/sector_registry.yaml` → this playbook's `signature_kpis` and `unit_denominator`.
  **Every signature KPI must appear in your `kpi_tree`** — either `computable: true` with
  its inputs named, or `computable: false` naming the missing input. Silently omitting one
  is a defect: it is how the NALCO run ended up with segment margins and no per-unit
  economics at all.
- Investor-presentation KPI slides if present (fast source of the operating metrics).
Do NOT web-search here; you emit the *questions* for DR2. Keep it to the documents.

## Produce `state/business_model.json` — the 8 fields

### 1. `identity` — the business in ≤2 sentences
What it sells, to whom, how it earns. Force brevity; it disciplines the rest.
Also: `listing`, `reporting_segments` (names), `basis_note` (standalone vs consolidated
primacy from triage), and `promoter_type` (family / MNC / PSU / institution).

### 2. `value_chain` — the horizontal map, node by node
For each node from raw input → conversion → product → channel → end-customer:
```json
{ "node": "Alumina refining", "position": "own",   // own | buy | sell_into
  "detail": "2.1 MTPA Damanjodi refinery fed by captive Panchpatmali bauxite",
  "evidence": ["fact/SRC ids or AR page"] }
```
Mark integration explicitly (own = integrated, buy = input exposure, sell_into = channel/
customer exposure). This is what makes "backward-integrated / asset-light / franchise"
concrete instead of a label.

### 3. `margin_pool` — where the economic rent sits, and who owns it
Which node captures the profit in this chain, WHY (cost-curve position, scarcity, brand,
switching cost, regulatory licence, network), and whether the target owns that node. One
paragraph + `owns_bottleneck: true|false|partial`. This is the moat question in value-chain
form; module 23 will score it, you frame it.

### 4. `net_position` — what the business is structurally long and short
`long: [...]`, `short: [...]`, `exposed_to: [...]` (the exogenous variables it can't
control). One line naming the *single most important* structural tilt — the benchmark's
whole NALCO thesis was "net long in alumina." Every business has one; name it.

### 5. `kpi_tree` — the 8–15 metrics that ACTUALLY move this P&L
Not a ratio dump. Derive them from the value chain. For each:
```json
{ "kpi": "aluminium_ebit_per_tonne", "kind": "driver",   // driver | health | moat
  "unit": "INR/tonne", "computable": true,
  "inputs": ["segment_ebit_aluminium", "aluminium_sales_volume"],
  "why_it_matters": "unit profitability of the metal leg; separates cyclical price from structural cost",
  "source_of_inputs": "segment note + volume table (both extracted)" }
```
Coverage rule: include every KPI in the sector pack that is *computable from the documents
we have*, plus any value-chain-specific one the pack misses. Mark `computable:false` (with
the missing input) for KPIs a fuller document set would enable — that list seeds
extraction-deeper and the report's data-gap section. Tag `driver` KPIs that belong in the
sensitivity table.

### 6. `unit_economics` — the per-unit lens
`denominator` (per tonne / store / subscriber / seat / loan / room-night …) and the
per-unit lines to track over time: revenue/unit, cost/unit, EBIT/unit (per segment where
segmented). Name the exact facts `compute_kpis.py` will divide. If the business has no
natural physical unit (e.g. a bank), say so and give the economic denominator (per ₹ of
average assets / per branch).

### 7. `swing_drivers` — the 3–5 variables that break the thesis if wrong
The ones that deserve a sensitivity table and the tightest monitoring. For each: name,
current level (fact ref), direction of P&L sensitivity, and whether it is exogenous
(commodity price, FX, rate) or company-influenceable (utilization, mix). These flow to
module 32's sensitivity table and the report's monitorables.

### 8. `research_seeds` — the industry questions for DR2 (the circular loop's fuel)
Concrete questions, each tagged with the swing driver it informs: supply-demand balance for
the output commodity; cost-curve/quartile position; end-demand CAGR (and the company's own
claim to verify); named global/domestic players and their scale; peer *multiples*
(P/E, EV/EBITDA, P/B). Also list the `peer_set` (≤8 domestic + ≤8 international) with a
one-line comparability delta each. DR2 consumes this verbatim — precise seeds are how we
research "in the loop," not in one generic pass.

## Also emit
- A ≤10-line `business_model_summary` the orchestrator can paste into `thesis.json` seeds:
  the identity line, the net-position line, the 3 KPIs that matter most, the 3 swing drivers.
- **Extraction feedback:** if the KPI tree needs a number no extractor was told to capture
  (e.g. cost of production per tonne, capacity by unit, contracted-price mechanism), append
  an open question routed `extraction_deeper` naming the document+note — so the KPI becomes
  computable on the next pass. This is the loop that closes gaps cheaply.

## Guardrails
- Method over template: do not force a metals KPI tree onto a bank. Start from *this*
  company's value chain every time.
- No invention: every node/KPI/number cites a fact id or AR page, or is marked
  `computable:false`/`assumption`. Missing is declared, never filled.
- This runs before deep analysis: keep it to structure and targeting, ~1 sonnet pass. The
  numbers get interpreted later by 20/23/32 — you are drawing the map they will walk.
