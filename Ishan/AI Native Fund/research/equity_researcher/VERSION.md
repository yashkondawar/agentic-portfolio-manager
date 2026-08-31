# Agentic Equity Researcher — Version

## v2.1.1 — 2026-08-11

The interpretation layer. v2.1 could tell you *that* a target multiple was opinion; it had
no construct for the case where two competent readers agree on a verified fact and disagree
about what it means. A P/E of 30 is expensive against a ten-year median of 18 and cheap at
a PEG of 1.0 — both are arithmetic on the same disclosed numbers, and the taxonomy in
§§1-6 does not separate them. This release adds the construct that does.

- **`docs/OPINION_VS_ANALYSIS.md` §7 "Same fact, divergent readings"** — the rule
  (`fact + conditioning variable + sector convention → verdict`), the canonical PE-30 worked
  case, the **closed 12-token vocabulary** of conditioning variables, the **four admissible
  discriminator types** (historical distribution, peer distribution, disclosed mechanism,
  dated forward observable — and nothing else), and the escalation path when a divergence
  cannot be settled. §4's audit grows from 15 checks to 18: checks 1-15 test whether opinion
  is masquerading as analysis, 16-18 test whether legitimate divergence has been flattened
  into a single reading.
- **`schema/interpretation.schema.json`** (new) + **`state/interpretation_ledger.json`**
  (new run artefact). Every entry needs ≥2 readings, each naming a conditioning variable;
  a ledger where our reading is the only reading is F3 in a new costume.
- **`prompts/33_thesis_synthesis.md` step 6b** owns the ledger — one owner per artefact
  holds, since 33 already owns the thesis. **`prompts/34_thesis_redteam.md` Part 1b** audits
  it (checks 16-18) and emits `interpretation_audit` + `unresolved_divergences`. An entry
  downgraded by check 18 is promoted to a disclosed load-bearing assumption, never deleted.
- **`config/sector_registry.yaml`** gains `interpretation_vocabulary` (12 conditioners, 26
  multiples) and gives all 8 families and all 32 playbooks a `primary_multiple`,
  `secondary_multiples` and `multiple_conditioners`. Machine tokens only — three tokens, no
  sentences, so **E11 is not violated**. `tools/validate_sector_registry.py` gains **E12**
  (frame declared), **E13** (tokens in vocabulary) and **E14** (every authored playbook
  carries a "Divergence cases" section).
- **All 32 `prompts/sector_playbooks/*.md` gain `## Divergence cases`** — 2-3 canonical
  same-fact/different-reading pairs per sub-sector with the discriminator named. This is
  where the sector-conditioned prior lives: a P/E of 25 that is indefensible for a primary
  smelter is defensible for a metals recycler because the conditioner differs even though
  the industry does not. Written as prose, not tables, deliberately — E10 scans table rows
  for cross-tier KPI overlap.
- **`tools/validate_state.py`** gains `check_interpretation_ledger()`; the vocabulary and
  discriminator enums are read out of the schema rather than duplicated in the tool.
- **`schema/valuation_handoff.schema.json`** gains optional `interpretation_ledger` — the
  wire into the fund, so a downstream buy-side consumer inherits the divergence instead of
  silently adopting one reading as fact. **`prompts/60_buy_side.md`** gains "Facts, readings,
  discriminator" and two output fields, `multiple_conditioner` and `opposing_reading`. Its
  embedded EPS-bridge prose is untouched — that duplication is deliberate (see below).

## v2.1 — 2026-08-03

The corpus-derived knowledge layer, plus the validators that keep it honest.

**Knowledge layer (2026-08-02)**
- `tools/er_corpus/` — corpus toolchain (discover → fetch → convert → profile → digest), zero tokens
- 165-note broker corpus under `reference/er_corpus/`, 25 brokers, 2010–2026, Motilal Oswal excluded
- `docs/ER_CORPUS_FINDINGS.md` — what Indian initiation notes actually do, counted. **Supersedes the single-note evidence base of `docs/PROCESS_V2_REIMAGINED.md`**
- `docs/OPINION_VS_ANALYSIS.md` — the opinion/analysis taxonomy and the 15-check audit
- `docs/BROKER_CALIBRATION.md` — per-broker adjustment when citing competitor research
- `prompts/33_thesis_synthesis.md` + `34_thesis_redteam.md` (waves 6a/6b) — nothing owned the thesis before these; 33 owns `state/thesis.json`, 34 owns `findings/thesis_redteam.json` from a separate context, and the 33→34→33 round trip is mandatory
- `prompts/thesis_archetypes/` — 14 archetypes + README, each with must-be-true conditions, failure mode, falsifiers, skepticism weight
- Two-tier sector routing: 8 family packs (thin routers) + `config/sector_registry.yaml`

**Completed 2026-08-03**
- **`prompts/sector_playbooks/` — all 32 playbooks authored**, 0 pending. Full depth each: economic engine, ordered analysis sequence, signature KPIs with formula/unit/benchmark/source, standard exhibit set, valuation convention + traps, sector-specific forensic screens, dependencies, archetypes. Provenance declared per file; 4 are labelled domain-derived (`microfinance`, `qsr`, `diagnostics`, `oil_gas_cgd`) where the corpus has no note, with the adjacent files named. No fabricated corpus citations.
- De-duplication: registry stops restating each playbook's `valuation_convention` (32 copies removed; **E11** fails the build if prose returns). `docs/ER_CORPUS_FINDINGS.md` §10 is now the canonical owner of the 14 load-bearing corpus passages; other files paraphrase and cite the anchor.
- **New validators.** `tools/preflight.py` (deps · registry · schemas · configs · dead-reference scan · reportStyle.js byte-identity · tools compile · state) and `tools/validate_state.py` (a run's state vs `schema/*.json`, plus rule 6's binding-gate and itemised-override rules). `tools/validate_sector_registry.py` extended to E1–E11. New `schema/triage.schema.json`.
- Report chain wired: templates gained slots for all ten things `prompts/41` mandates (archetype, return decomposition, must-be-true table, red-team verdict, story-in-exhibits, disconfirming exhibit, price-performance strip, operating-KPI/per-unit/segment tables, value-chain map + capex pipeline, driver-assumption/sensitivity/valuation-bridge). `prompts/40` gained the thesis and red-team ledgers (§10, §11) and its numbering now matches the template 1:1.
- `prompts/50` + citation-auditor emit `final_gate_decision` by name and state rule 6's binding-gate and per-item override rules; path corrected to `state/verification_report.json`.
- `schema/valuation_handoff.schema.json` gained `sector_playbook`; `config/agent_config.yaml` gained the `thesis`/`adversarial` model tiers and role-group `THS: [33, 34]`; `config/eps_bridge_thresholds.yaml` `sector_overrides` populated and now resolves **family then playbook**, layered.
- Fixed: `tools/disclosure_fetcher/tests/test_offline.py` ImportError'd on the key-free install it was written to protect (module-level `llm_agent` import → pydantic/tenacity); a Windows MAX_PATH failure in the downloader (`bounded_dest()`); `compute_kpis.py` silently dropping a period with partial segment data; `rnd_pct_of_sales` renamed `rd_pct_of_sales` (the old key could never satisfy E8 — "R&D" squashes to `rd`).
- NALCO run brought up to the v2 spine: `business_model.json` written, per-unit economics computed via the tree path, `thesis.json` rewritten schema-valid (it had been missing 6 of 9 required fields), `thesis_redteam.json` produced. `python tools/preflight.py workspace/NALCO` → 8/8.

### Also 2026-08-03 — evidence-first stance, and the statement tree made real

- **Confirmed already working:** markitdown is the first conversion step (`tools/convert_docs.py`, per-page via pypdf split + pdfplumber tables).
- **3-level statement tree now actually builds.** Only level 1 becomes a root; level-2/3 records without a `parent` are attached by name-prefix inference or bucketed under a labelled node, never promoted. 185 period-alias metrics (`_prior`, `_h1`, `_q2`, `_fy20XX_full_year`) folded onto their base line item; derived `*_yoy_pct` routed out of the statements; classifier expanded (204 → 166 items outside the three statements, and that bucket renamed since what remains belongs there). NALCO: IS roots 117 → 47, depth 2 → 3. `prompts/10` now **requires** `parent` on level-2/3.
- **Excel: 7 tabs → 15.** Added `IS/BS/CF_horizontal` (YoY per line item), `IS/BS/CF_vertical` (common-size), `Other_metrics`, and a `Contents` tab. Rows now follow statement order rather than alphabetical. Fixed the basis collapse (consolidated preferred deterministically; dominance measured by fiscal-year coverage; off-basis rows blank **and disclosed** rather than blended). `_cell_safe()` stops one structured ledger field aborting the whole workbook.
- **Stance `evidence_first`** (`config.report.stance`): page budget 12 → 14 with the extra pages going to evidence; rating moved to a bounded §9 and switchable off via `config.rating.emit`; `config.report.evidence_floors` makes the depth requirement checkable and `tools/validate_state.py` warns per unmet floor. Justified by `docs/ER_CORPUS_FINDINGS.md` §5, not by preference. Modules 33/34 and the citation gate are unchanged and still mandatory.

## v2.0 — 2026-07-13
- Optional buy-side stage: buy-side-analyst agent + prompts/60_buy_side.md (self-contained EPS-bridge doctrine), NOT in default lifecycle
- EPS-bridge deterministic checker (tools/eps_bridge_check.py) + Excel export (tools/export_financials_xlsx.py)
- equity-research-formatter skill + tools/report_formatter/ Node engine → styled .docx FORMAT stage (step 9)
- prompts/03_business_model_and_value_chain.md, prompts/70_sparse_data_playbook.md, tools/compute_kpis.py (operating-KPI trends + unit economics)

## v1.1 — 2026-07-08 (retrofit)
- markitdown CONVERT step (0.5), comprehensive statement builder, level-3 note depth, quarterly seasonality, role groupings

## v1.0 — initial
- Staged pipeline (prompts 00-50), 14 subagents, JSON fact schemas, one citation standard, circular orchestration

## Sync policy

Standalone project is upstream for research logic. The fund copy (`research/equity_researcher/`)
regenerates the sector packs and `config/eps_bridge_thresholds.yaml` from the fund registry; the
fund-level `buy_side` agent (cycle-aware) is canonical under the fund. Sync is manual and
deliberate.

### What must move together (added v2.1)

Sector routing is now a two-tier contract with machine-checked edges, so these travel as a set. A
partial sync is worse than none, because the registry will claim routing the files cannot deliver.

1. **`config/sector_registry.yaml` + `prompts/sector_playbooks/*` + `prompts/sector_packs/*`.**
   The registry declares which playbook files exist (`status`) and which KPIs each must define
   (`signature_kpis`). Copying the registry without the playbooks fails E3; copying playbooks
   without the registry leaves them unroutable.
2. **`schema/valuation_handoff.schema.json`** — its `sector_pack` enum is generated from the
   registry's families. Re-run `python tools/validate_sector_registry.py --sync-schema` after any
   family change; E7 fails if the two drift.
3. **Do not re-add `valuation_convention` (or any other prose) to the registry.** It lives in the
   playbook's `## Valuation convention` section. **E11 fails the build** if it comes back — the
   registry carries only `family`, `status`, `keywords`, `signature_kpis`, `unit_denominator`.
4. **`.claude/skills/equity-research-formatter/scripts/reportStyle.js` and
   `tools/report_formatter/reportStyle.js` must stay byte-identical.** The runner's copy is the one
   that renders; the skill's is documentation. `preflight.py` hashes both.
5. **After any sync, run `python tools/preflight.py`.** It is the mechanical answer to "did that
   copy leave anything claiming something untrue?" — the failure mode this project has hit most.

Note the deliberate duplications that are NOT drift and should not be "fixed": `prompts/60_buy_side.md`
embeds the fund's EPS-bridge doctrine prose, and `config/eps_bridge_thresholds.yaml` inlines the
fund's `registry/rules/eps_bridge.yaml`, both because this project has no `registry/`. See
`docs/DESIGN_DECISIONS.md`.
