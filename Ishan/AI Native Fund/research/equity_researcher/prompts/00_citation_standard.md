# Citation & Audit-Trail Standard (supersedes all module-level audit instructions)

Every module — extraction, analysis, research, estimates, report — follows this one standard. If any prompt text conflicts with this file, this file wins.

## 1. Source registry (global, per run)

`workspace/<TICKER>/state/source_registry.json` — append-only map:

```json
{ "SRC-004": { "doc": "AR_FY2024.pdf", "kind": "annual_report", "page": 187,
               "locator": "Note 24 — Revenue from operations", "period": "FY2024",
               "url": null, "accessed": null } }
```

- Internal documents: `doc` + `page` + `locator` (note/schedule/table/speaker). Page = PDF page as read.
- External (web/research): `url` + `accessed` (ISO date) + `locator` (section/quote). External sources are additionally tagged `corroboration: primary|secondary|unverified` (regulator filing = primary; reputable press = secondary; blogs/social = unverified).
- Market data pulls: `doc: "yfinance"`, `locator: "<ticker> <field>"`, `accessed` = pull timestamp.
- IDs are global per run and never reused. Modules request new IDs by appending; `tools/citation_check.py` detects collisions and orphans.

## 2. Fact records (the only way numbers move between modules)

Every number extracted or derived becomes a record per `schema/fact_record.schema.json`. Key rules:

- `method: reported` — value transcribed exactly as printed. **No rounding, no unit conversion at extraction time.** Record the source unit in `unit`.
- `method: computed` — must carry `formula` and `inputs` (list of fact ids). Computation is done by `tools/compute_ratios.py` wherever possible; an LLM computes only when a script cannot, and then must show the arithmetic in `formula`.
- **Reported-over-computed precedence:** if the company discloses a ratio (e.g., ROCE in the AR), the reported value is used in deliverables; the computed value is kept as a cross-check. Divergence > 1% of value → discrepancy entry in `state/red_flags.json` (category `data_quality`).
- Quarterly vs annual conflicts for the same period: annual report wins; the superseded record is kept with `flags: ["superseded"]`. Restated prior-year figures: latest restatement wins; original kept with `flags: ["restated_original"]`.

## 3. Rendering citations in deliverables

- Numeric cell: `1,234.5 [S4]` where `S4` ↔ `SRC-004`. One bracket per cell; if a computed figure has multiple inputs, cite the derived fact's own id and let the legend expand inputs.
- Verbatim quotes: ≤ 25 words, quotation marks, speaker + doc + page/timestamp: `"…we expect capex of ₹200 cr in FY26" — CFO, TR_2025-05-12, p.9 [S31]`.
- Every table is followed by a **sectional legend** listing only the SRC ids used in that table. The dossier ends with the **global legend** (all SRC ids, no duplication). Legends are generated from the registry — never hand-written.
- Cite the *original* source, not the intermediate module ("Task 1 output" is never a citation; trace through to the AR page it came from).

## 4. Missing data & assumptions

- Missing: `N/A — missing <field> (<docs checked>)`. Never silently blank, never estimated without labeling.
- Proxy values (e.g., peer median): value + `proxy — peer median [S…]`.
- Every assumption used in a calculation (tax rate, day-count, FX) is a record in the assumptions ledger `state/assumptions.json` with rationale and its own SRC id (`doc: "assumption"`).
- Facts vs opinions: research outputs label each item `fact` (with citation) or `opinion/interpretation` (attributed).

## 5. Confidence

`high` — primary document, unambiguous. `medium` — derived, or single secondary source. `low` — indirect inference, or conflicting sources (conflict must be described). Confidence flows through: a finding's confidence ≤ min(confidence of its evidence).

## 6. Verification hooks

Records marked `load_bearing: true` (anything in the rating box, thesis pillars, estimates table, red-flag evidence) get 100% re-verification in the verification wave; others are sampled per config. A record that fails verification is marked `flags: ["unverified"]` and may not appear in the final note without an explicit gap disclosure.
