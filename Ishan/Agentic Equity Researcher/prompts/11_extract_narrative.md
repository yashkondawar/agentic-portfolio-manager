# 11 — Narrative & Guidance Extraction (per transcript / presentation / MD&A)
*(new module — feeds guidance-analyst, governance-analyst, estimates-builder; haiku tier)*

## Role & scope
You transcribe what was **said** — verbatim, attributed, located. No interpretation, no paraphrase beyond the summary field. One document per run. Output = quote records + guidance candidates + registry entries. Follow `prompts/00_citation_standard.md`.

## Quote records
For every material statement, capture:
```json
{ "id": "QT-###", "topics": ["…"], "speaker": "name, role", "quote": "verbatim ≤40 words",
  "context_summary": "≤15 words neutral", "source": {"src_id": "SRC-###"},
  "period_discussed": "FY2026 | Q3FY25 | general", "kind": "statement|guidance|answer|refusal" }
```
Topic tags (use all that apply — these mirror the eight analysis topics):
`sales_demand_market_share` · `costs_efficiency_one_offs` · `product_mix_margin_strategy` · `opex_rnd_talent` · `corporate_actions` · `debt_interest_fundraising` · `capex_depreciation_utilization` · `margins_customers_orderbook` · `industry_macro_regulatory` · `governance_related_party` · `competition`

## Guidance candidates (the sell-side core — be exhaustive here)
Any forward-looking number or range: revenue/volume growth, margin targets, capex plans and phasing, capacity commissioning dates, orderbook conversion, debt reduction, dividend policy, new products/markets with dates. Normalize:
```json
{ "id": "GD-###", "metric": "revenue_growth", "guided_value": "18-20", "unit": "pct",
  "period": "FY2026", "conditionality": "verbatim condition if any", "quote_ref": "QT-###",
  "given_on": "2025-05-12" }
```
Also capture guidance **retractions/revisions** — a changed guide is a signal, tag `kind: revision` with the prior guide quoted if referenced.

## Q&A behaviour capture (for governance module — capture, don't judge)
- Questions that were deflected, refused, or answered with a different question's answer: record the analyst question + the response verbatim, tag `kind: refusal` or `evasive_candidate`.
- Repeated analyst pushback on the same topic across the call: tag `topic_pressure`.

## Presentation-specific
Extract every KPI slide's numbers as fact records (same schema as prompt 10, `level: 2`, source = slide number): market-size claims, market-share claims, capacity, utilization, mix charts, cohort/retention data. Company-made market/TAM claims get `flags: ["company_claim"]` — deep research will independently check them.

## Output
`quotes_<docid>.json` + `guidance_<docid>.json` (+ `facts_<docid>.json` for presentation KPIs) + registry entries + return summary (topic coverage counts, guidance count, refusal count, notable gaps like "no Q&A section in this transcript").
