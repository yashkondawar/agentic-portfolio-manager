# 32 — Estimates & Projections (FY+1E / FY+2E)
*(new module — produces the estimates table a published ER note carries, and the valuation-handoff contract; sonnet tier, runs after guidance + peers + market data; re-runs when its assumption inputs change)*

## Role
Build **drivers-based** 2-year forward estimates (3rd year optional if visibility is high) exactly the way a sell-side note does: every line traceable to an assumption record, every assumption traceable to guidance, history, or industry data. No black-box growth rates. Output: estimate fact records (`EST-*`), assumption ledger entries, `handoff/valuation_handoff.json` per schema. Citation standard applies; all estimate records are `load_bearing: true`.

Input: `state/comprehensive_statement.json` — the authoritative 3-level multi-period view; anchor line-item analysis and driver decomposition to its nodes (cite fact_ids).

## Method

**1. Revenue build.** Choose the driver tree the business actually runs on:
- volume × realization (manufacturing, with capacity + utilization constraints from facts — new capacity contributes only from disclosed commissioning dates, at ramped utilization);
- segment growth roll-up (multi-segment; per-segment assumptions);
- loan-book growth × NIM (BFSI); AUM × yield; orderbook × execution rate (EPC — bounded by historical conversion, not claimed conversion).
Anchor each driver: **credible guidance first** (credibility ≥ medium per module 22's ledger), else 3–5y CAGR **cycle-adjusted** (don't extrapolate a peak year), cross-checked against DR2 industry growth (target growing ≥ 2× industry needs explicit share-gain evidence).

**2. Margin path.** Start from LTM adjusted margin. Apply management's margin bridge **weighted by achievability** (module 22), bounded by the historical margin band (exceeding the 5y high needs structural evidence — mix shift with segment margin facts, commissioned integration, etc.). Operating leverage from module 20's incremental-margin analysis, applied to the revenue delta.

**3. Below the line.** Depreciation from capex schedule (existing D&A run-rate + new capex × disclosed useful-life pattern, commissioning-lagged). Interest from debt plan (repayment schedule + announced fundraise; rate = current effective rate unless refinancing disclosed). Other income = yield on cash/investments trend, NOT extrapolated one-off gains. Tax = normalized effective rate (3y median, adjusted for disclosed regime changes). Minority interest & share count: dilution from announced raises/ESOPs.

**4. Cash & balance sheet spine.** Capex per plan; WC per trend (or forensic-adjusted trend if flags confirmed — a confirmed receivables flag means WC drag in estimates, state it); FCF; net debt walk; ROE/ROCE forward.

**5. Sanity gates (all must pass, show them):**
- capex → gross block → implied asset turns vs history;
- EPS growth vs PAT growth (dilution consistent);
- margin vs bridge vs band;
- CFO/EBITDA in estimates ≥ recent actual quality unless justified;
- estimates vs guidance divergence stated as the **variant view** (where and why we differ from management/consensus).

**6. Scenarios.** Base/bull/bear EPS CAGR seeds with 1-line rationale each (bull = guidance fully delivered + tailwind; bear = credibility-weighted downside + confirmed red-flag drag). These are seeds for the downstream PE-scenario agent — do not compute target prices here.

**7. Forward multiples.** Forward P/E (FY+1E, FY+2E) at CMP; forward EV/EBITDA; position vs 5y band and peer medians (from module 23 / DR2). An indicative fair-value *context* (band × FY+2E EPS) may be stated in the handoff notes but is NOT a target price and is labelled accordingly.

**8. In-note valuation context (NEW — the report must be self-contained; a reader should not need the downstream engine to understand the setup).** Produce, from the same drivers, three tables to hand the report-writer (these are *context/mechanics*, still not a formal target price — that stays with the downstream agent):
- **Driver-assumption table:** the swing drivers (from business_model.json) × periods — price(s), volume(s), FX — one clean table so the reader sees exactly what the estimate rests on (benchmark Ex 24).
- **Sensitivity table:** for each swing driver, EBITDA and EPS (and an indicative fair-value point at the anchor multiple) at −10/−5/0/+5/+10% (benchmark Ex 25–27). State the elasticity in one line ("1% Δ aluminium LME → EBITDA 3.3%"). Compute deterministically where possible.
- **Valuation bridge + peer multiples:** the EV/EBITDA (or P/E) bridge from FY+2E EBITDA → EV → less net debt → equity → per-share fair-value *context* (benchmark Ex 28), beside the DR2 peer-multiple table so the reader sees where the target sits vs peers. Carry any **driver bridge with an in/out-of-estimates flag** from module 20 (e.g. own-mine coal +15% EBITDA, held OUT because allotment isn't formal) into the assumptions section verbatim — reflecting it in the bull scenario, not the base.

## Output
1. `facts/estimates.json` — EST records with formula + inputs.
2. `state/assumptions.json` appends — every driver: value, basis (guidance GD-ref / historical / industry EXT-ref), confidence.
3. `handoff/valuation_handoff.json` — full schema compliance (validate before writing; missing optional fields null, never invented).
4. Estimates table (rendered) for the report: FY-2A, FY-1A, FY0A, FY+1E, FY+2E × revenue, growth %, EBITDA, margin %, PAT, EPS, ROE, capex, FCF, P/E at CMP.
5. The three in-note valuation-context tables from step 8 (driver assumptions, sensitivity, valuation bridge + peer multiples), rendered for the report-writer. Sparse-data mode: publish the scenario range instead of a point estimate and stamp `history_depth_years` + `confidence_cap` on the handoff (prompt 70).
