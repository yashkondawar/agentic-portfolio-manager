# 31 — Deep Research 2: Sector, Peers & KPI Benchmarking
*(refined from DR2 + sector prompt family; sonnet tier; WebSearch/WebFetch + market-data script for listed-peer numbers.)*

## Why this module carries more weight now

`config.report.stance` is `evidence_first`, and external research is one of the three things the
report is *for* (extraction, research, analysis). The NALCO run's single largest disclosed gap was
"domestic peer multiples not located" — under this stance that is not a footnote, it is a failure of a
headline deliverable. `config.report.evidence_floors` sets the floors you are held to:
`external_sources_min: 6` independent non-filing sources and `peer_count_min: 5` domestic listed
comparables **with multiples actually pulled**. Report any floor you could not reach, naming the peer
and the field, rather than leaving the table thin without comment.

## Ground rules
Same as prompt 30 (deterministic-first, citation tiers, prefilled-research reuse, `impacts` tagging). Additionally: **peer market data (price, mcap, multiples) for listed peers comes from `tools/market_data.py`** — request pulls via your return summary (orchestrator runs them) or run the script yourself if Bash is available. Web-source only what has no feed (private peers, operational KPIs, industry volumes). Convert international peers to INR (record FX rate + date as an assumption).

**Consume the business-model research seeds.** Read `state/business_model.json.research_seeds` and `.peer_set` — module 03 already named the exact industry questions (supply-demand balance, cost-curve position, demand CAGR, peer set) tied to the swing drivers. Answer THOSE, don't research the sector generically. This is what "research in the loop, not one go" means: precise, driver-tagged questions in → cited answers out.

**Micro-search primitive (the circular loop).** Analysts (modules 20/21/23/32) may raise a single bounded question mid-analysis — one fact that would change a finding (a peer's current multiple, an industry balance number, whether a plant commissioned) — tagged with the `impacts` module. Batch these into a short focused pass (≤3 web queries each), not a new full DR. New facts propagate via the existing staleness engine (impacts tags → re-run only affected findings). Keep a running micro-search budget; never expand into an unbounded "research everything" pass.

## Step 1 — Peer identification (priority order, from triage seed list)
1. Peers named in supplied documents (already seeded in triage.json) — keep, with doc refs.
2. Extend via Screener.in / Tickertape / Capitaline-style screens and credible sector reports: **≤ 8 domestic listed** comparable-by-business, then **≤ 8 international** of similar size/model. Record the exact query + source + retrieval date per addition.
3. Per peer: business-model deltas vs target (segment mix, integration, geography) in one line — comparability caveats travel with the peer into every downstream table.

## Step 2 — Value chain & bottleneck (top-down context)
Map horizontal chain (raw material → processing → end user) and vertical layer (where domestic competitors sit). Identify: the **bottleneck** that grants pricing power in this chain (spectrum in telecom, NPPA/NLEM in pharma, freight in cement…), whether the target's integration (backward/forward) targets input volatility or distribution control, and who currently owns the bottleneck.

## Step 3 — Apply the sector pack **and the tier-2 playbook**
Read **both** routing tiers, in this order:

1. `prompts/sector_packs/<family>.md` — the family pack chosen at triage. It routes: family scope, the statement fork, the cross-cutting lenses, and the child index. It deliberately carries no KPI table.
2. **`prompts/sector_playbooks/<playbook>.md` — the tier-2 playbook** (slug from `state/triage.json`). **This is where the research targets actually live**: the signature KPIs with their formula/unit/benchmark/source, the standard exhibit set, the valuation convention, the sector-specific forensic screens, and the **"Dependencies to map"** section — which is a ready-made research checklist for this sub-sector and should be worked through explicitly. All 32 playbooks are authored, so there is no pending-fallback case to handle.

Per `prompts/03`, **the playbook supersedes the pack wherever the two differ.** For multi-segment companies, pull KPI tables only from the secondary playbooks named in `state/triage.json.secondary_playbooks`.

Produce ONE research report:

**Qualitative** (bullets, cited):
- *Company-specific*: each key peer's strategic edge per the pack's lenses; industry voice — what competitors' management is saying (their latest transcripts/presentations, tone noted); moat sustainability incl. regulatory moats (PLI/licensing/tariffs).
- *Sector-specific*: Porter's evidence (≥2 cited items per force — scoring happens in module 23); demand drivers & pricing determinants with data; pass-through vs operating-leverage character of the sector; 3–5 recent (≤6 months) growth forecasts/tailwinds/headwinds from credible industry sources; leading indicators (PMI, freight, sector-specific); India-specific electoral/policy and counterparty risks.
- *Cycle overlap checks* (mandatory): valuation cycle vs earnings cycle — are current sector multiples justified by ROCE stability or pure multiple expansion? credit cycle vs capex cycle — can the sector fund its growth plans at current credit conditions? policy cycle vs profit cycle — how durable is any policy-driven moat?

**Quantitative — two mandatory tables** (target + all peers), both are hard deliverables, not optional:

*(a) Peer valuation & KPI table.* Common core: price date, mcap, EV, P/E (LTM), forward P/E (consensus if findable — cite), EV/EBITDA, P/B where relevant; revenue/EBITDA/PAT (LTM, ex-one-offs with adjustments shown); GM/EBITDA/PAT margins; ROCE/ROE; net debt/EBITDA; CFO, capex, FCF, FCF yield; growth rates. Plus the pack's sector KPI rows (SSSG, NIM/GNPA, EBITDA/tonne, NRR, CPV, order-book/bill…). **Peer multiples are the module's single most-requested-and-most-missed output** (our NALCO run flagged "domestic peer multiples not located" as its biggest gap) — pull every listed peer's P/E, EV/EBITDA, P/B from `market_data.py`; only mark a cell `MISSING` after the feed genuinely has no value, and say which peer/field. Ratios 2dp; money in ₹ cr.

*(b) Industry supply–demand balance* (for commodity/cyclical sectors; skip with a one-line reason where not applicable). A quantified balance for the company's output: production (existing + additions − curtailments), imports/exports, demand, and the resulting **net deficit/surplus** — split by region where it matters (e.g. China vs RoW), sourced from independent industry data (producer presentations, agency/association reports). This is what lets the report say "the commodity is in deficit by X" instead of "prices may improve." Name the major global/domestic players and the target's share of third-party supply where findable. Where a full balance can't be sourced, publish the pieces you can (demand CAGR + announced supply additions) and label the gap.

**Relative valuation commentary** (the one allowed paragraph, 3–6 sentences): is the target's premium/discount justified by the pack's stated justifier (ROCE stability, cost-curve position, non-linear growth…)? Max 5 load-bearing data points, cited.

## Step 3b — Citing competitor research: apply the broker calibration
**Read `docs/BROKER_CALIBRATION.md` before quoting any broker note**, and apply it per house rather than treating all broker research as equivalent evidence.

Two rules are binding:

- **Motilal Oswal is excluded.** This exclusion already governs the corpus toolchain — `tools/er_corpus/corpus_lib.py` carries `EXCLUDED_BROKERS = {"motilal_oswal"}` and `fetch_corpus.py` drops matches with `note="Motilal Oswal excluded by instruction"` — but until now it existed *only* there, so live web research could reintroduce exactly what the corpus was instructed to keep out. **Do not cite Motilal Oswal research in DR2.** If a search result is a Motilal note, skip it and record the skip; if a third party quotes Motilal, attribute the underlying fact to the primary source or drop it.
- **Kotak Institutional: strong numbers, structurally conservative conclusions.** Where a Kotak note's *analysis* supports a better outcome than its *rating* concedes, that gap is usually the most honest bear case available on the name, and it is the single most useful thing to extract. Emit it as a record:

```json
"broker_divergence": [
  {"broker": "kotak_institutional",
   "what_the_analysis_shows": "...",
   "what_the_rating_says": "...",
   "source": "SRC id or URL + access date"}
]
```

Write these into `facts/external/dr2_*.json`. The record shape is defined in `docs/BROKER_CALIBRATION.md`; before this module emitted it, the shape was defined there and produced nowhere. Never treat a Kotak REDUCE as corroboration of our own bearish view without checking whether their analysis actually supports it — two pessimists agreeing is not independent evidence.

Note the calibration doc's own honest limit: six Kotak notes reached the corpus, enough to confirm house style but not to measure its rating tilt. Treat the calibration as a prior to test, not a fact to assert.

## Step 4 — Company-claim checks
Independently verify company-made TAM/market-share/industry-growth claims flagged `company_claim` by extraction. Support / contradict / neutral, 2–3 external sources each, regulator or industry-association reports preferred.

## Output
`facts/external/dr2_*.json` + `research/dr2_report.md` + answered questions + new questions + summary with `impacts` (typically: peer-valuation-analyst, forensic where peer norms adjudicate flags, estimates-builder where industry growth anchors assumptions).

`facts/external/dr2_*.json` must carry, in addition to the fact records: the two mandatory tables' underlying values, any `broker_divergence` records from step 3b, and the list of Motilal Oswal sources skipped (so the exclusion is auditable rather than invisible).
