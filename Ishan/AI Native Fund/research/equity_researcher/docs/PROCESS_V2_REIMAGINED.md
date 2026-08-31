# Reimagining the ER process — from filing-transcription to business understanding

> **SUPERSEDED IN PART — read `docs/ER_CORPUS_FINDINGS.md` first.**
>
> This document's *diagnosis* stands and has since been confirmed at scale: our process was
> filing-centric where a good analyst's is business-model-centric. But its **evidence base is
> a sample of one** — the Emkay NALCO note below. `docs/ER_CORPUS_FINDINGS.md` re-derives the
> same questions from a **165-note corpus** and is the authority wherever the two disagree.
>
> Three specific things here were wrong or stale. **All three are now marked inline at the
> section they affect** (2026-08-03), so a reader who jumps straight to a section sees the
> correction without having read this header:
>
> 1. **§1 row 6 inverted the finding on sensitivity tables.** It listed in-note sensitivity as a
>    capability gap to close. The corpus shows sensitivity tables appear in 14% of initiations as
>    a named section and **19% anywhere** — our `prompts/32` mandate already *exceeds* the genre.
>    `ER_CORPUS_FINDINGS.md` §1 says explicitly: do not weaken it to match the corpus.
>    → corrected in a callout under the §1 table.
> 2. **§7's implementation index was incomplete** — it predated the whole corpus-derived
>    knowledge layer. → **refreshed**: §7 now carries a second table, *"Added after this document
>    was written"*, listing the 2026-08-02/03 work (corpus toolchain, the three new `docs/`,
>    modules 33/34, the archetype library, two-tier sector routing with 32 playbooks, the
>    registry and its validator).
> 3. **§3's "Generic KPI-tree seeds by business archetype" table was a third KPI catalogue**,
>    alongside the playbooks and the registry's `signature_kpis`. → marked **illustrative only**
>    in a callout at that heading, pointing seeding at the tier-2 playbook instead.
>
> What remains uniquely valuable here: the five-layer framing in §2, the value-chain method in
> §3, the sparse-data reasoning in §6, and the honest-limits section in §8.

Written 2026-07-19 after benchmarking our NALCO output against a professional
initiation-of-coverage note (Emkay Global, "National Aluminium Co — Better positioned
in a rough weather!", 15-Jan-2016, 24pp, 31 exhibits). This document is the design
rationale; the concrete changes live in the new/edited prompts, `tools/compute_kpis.py`,
`CLAUDE.md`, and `config/agent_config.yaml`.

## 0. The one-sentence diagnosis

**Our process is filing-centric and audit-centric; a good analyst's process is
business-model-centric and KPI-centric.** We are excellent at "every number in the
filings, verified, with a red-flag ledger and governance score." We are thin at the
thing that actually makes a report worth reading: *understanding the business as a
physical, economic machine and tracking the handful of numbers that drive it over
time.* The fix is not more sections in the report — our report already has the same
section headings as the benchmark. The fix is an **analytical layer we skip**, upstream
of the report, that the benchmark is built on.

## 1. What the benchmark does that we don't (evidence, not impression)

Cross-checked the 31 benchmark exhibits against our `report/final_note.md` (4 exhibits) and
`report/dossier.md` (24 tables). The benchmark's edge is concentrated in six capabilities:

| # | Capability (benchmark) | Benchmark exhibit(s) | Our output | Root cause of the gap |
|---|---|---|---|---|
| 1 | **Operating-KPI time series** — production, utilization, realization, exports %, cost/tonne tracked 10–15 years | Ex 5,8,9,12,13 | We extract volumes as facts but never build the trend tables; note has none | No module *mandates* operating-KPI trends; no tool *computes* them |
| 2 | **Per-unit economics** — EBIT/tonne by segment, cost/tonne, realization/tonne | Ex 20 (Alumina vs Aluminium EBIT/tn 2005–15) | Absent | We never join segment-EBIT (financials) to volumes (operations) → no unit economics |
| 3 | **Segment analytics over time** — segment EBIT-margin split, % EBIT from each segment, mix swings, *why* they swung | Ex 10, 11 | We have segment facts per year; no trend, no "net-long-alumina" insight | Fundamental prompt treats segments as one of 8 analyses, not the spine |
| 4 | **Value-chain / asset map** — capacity of every operating unit; physical integration; logistics; where the co sits in the industry structure | Ex 1, 2, 3 (map) | Prose mentions of captive bauxite/coal; no asset map, no industry capacity table | Value-chain mapping lives *late* in DR2 (research), not *first* where it should drive everything |
| 5 | **Industry supply–demand balance** — quantified deficit/surplus, named global players, third-party share | Ex 4, 5, 6 | DR2 got price outlook & CBAM; no supply-demand balance table | DR2 asks for "growth forecasts," not a *balance model* |
| 6 | **Estimates plumbing IN the note** — explicit driver-assumption table (price×volume×FX), sensitivity (EBITDA/EPS/TP to each driver ±10%), valuation bridge, peer multiples, P/E & EV/EBITDA bands | Ex 24–31 | We *defer* sensitivity+TP to a downstream handoff; peer multiples flagged "not located" | Design choice to hand off valuation; peer-multiple retrieval under-specified |

> **CORRECTED BY THE CORPUS — row 6, the sensitivity half.** Written from one note, this row reads
> in-note sensitivity as a gap where we trail the genre. The 165-note corpus **inverts that**:
> sensitivity tables appear in 14% of initiations as a named section and **19% anywhere**
> (`docs/ER_CORPUS_FINDINGS.md` §1 and §8). `prompts/32`'s mandate to publish a driver
> sensitivity table already exceeds what five in six professional initiations do, and
> `ER_CORPUS_FINDINGS.md` §1 says explicitly: **do not weaken it to match the corpus.** The rest
> of row 6 — driver-assumption table, valuation bridge, peer multiples, multiple bands — stands,
> and those *are* genuine gaps: peer multiples appear in 56% of notes and the valuation section
> in 79%.

Two things the benchmark quantifies that we only narrate, worth calling out because they
are the "give weightage to the right information" the user asked for:

- **The driver bridge with an explicit in/out-of-estimates flag.** Benchmark p7: own-mine
  coal saves ~Rs2000/t coal → ~Rs500/t aluminium → **+15% EBITDA**, *"At present we are
  NOT factoring this into our estimates"* because the allotment isn't formal. That single
  sentence — quantify the catalyst AND state whether it's in the numbers — is the
  difference between analysis and a wish list. Our estimates probability-weight drivers
  but rarely publish the bridge and the inclusion decision side by side.
- **The contracted-price de-risking.** Benchmark p5: "NALCO has already contracted 70% of
  its alumina at 17.5% of LME for CY16." A forward, price-mechanism fact that reframes the
  risk. We captured lots of guidance but didn't surface the *pricing mechanism* as a KPI.

### What we do BETTER than the benchmark (keep these — they are our moat)

Not everything cuts against us. Our process is materially stronger on: the **red-flag
ledger** (23 adjudicated candidates, confirmed/disclosed/dismissed with why-chains);
**earnings-quality and governance scoring** (the benchmark has *no* governance section —
it never surfaced the LODR board-composition fine or the CBI probe our DR found); the
**citation/verification discipline** (every load-bearing number re-derived from source);
and **explicit data-gap honesty**. The 2016 benchmark also had the luxury of Bloomberg
consensus and a human's years of sector memory. The goal of V2 is **not** to abandon our
audit spine — it is to put a business-understanding spine *next to it*.

## 2. The reframing: five layers, and the two we're missing

A good report is built in layers. Map our pipeline onto them:

```
Layer                         Benchmark  Us (v1)   Fix in v2
A. Business model & value      STRONG     WEAK*     NEW: prompt 03 (early, first-class)
   chain (what IS this machine)
B. Company-specific KPI tree   STRONG     MISSING   NEW: prompt 03 defines it,
   & unit economics                                 tools/compute_kpis.py builds it
C. Financial statement mastery MEDIUM     STRONG    keep (our comprehensive_statement)
D. Earnings quality / gov      WEAK       STRONG    keep (forensic + governance)
E. Estimates, valuation,       STRONG     PARTIAL   enhance 32: sensitivity + bridge +
   sensitivity, peers                               peer multiples IN-note
```
*Layer A exists in our prompt 31 (DR2) Step 2 "value chain & bottleneck," but it runs
*during research, late, and only for sector context — it never shapes what we extract or
which KPIs we track. Elevating it to the front is the single highest-leverage change.*

**The central idea of V2:** insert Layers A+B at the front (right after triage, before
deep extraction analysis), let them emit a `state/business_model.json` that names *the
value chain, the 8–15 KPIs that actually drive THIS business, the unit-economics
definitions, and the 3–5 swing drivers* — and let that artifact steer everything
downstream (what to extract deeply, what trends to compute, what to research, what to put
in the report). This is also exactly what makes the process **generic across industries**
and **resilient to sparse data**, because it is a *method for deciding what matters*, not a
fixed metals template.

## 3. Layer A — Business-model & value-chain mapping (the new spine)

A method that works for **any company in any industry** (prompt 03, `state/business_model.json`):

1. **One-line business identity.** In ≤2 sentences: what does the company sell, to whom,
   and how does it make money? (Force this first — it disciplines everything.)
2. **Value chain map (horizontal).** Draw the chain from raw input → conversion steps →
   product → channel → end-customer. Mark, at each node: does the company *own* it
   (integration), *buy* it (exposure), or *sell into* it? Metals: bauxite→alumina→
   aluminium→product. Bank: deposits→underwriting→loans→fees. FMCG: commodity inputs→
   manufacturing→brand→distribution→shelf. SaaS: R&D→product→sales→retention→expansion.
3. **Where the margin/bottleneck sits.** Which node in this chain earns the economic
   rent, and does the company own that node? (Alumina cost-curve position; spectrum in
   telecom; brand+distribution in FMCG; switching costs in SaaS.) This is *the* moat
   question and it is a value-chain question.
4. **Net-long / net-short.** What is the company structurally *long* and *short*? NALCO is
   net-long alumina, net-short nothing (integrated), exposed to LME + coal. This single
   framing ("net long in alumina") was the benchmark's entire thesis. Every business has
   one: a bank is long duration/short liquidity; an airline is short fuel; a lender is
   long credit.
5. **The KPI tree (Layer B).** Derive, from the value chain, the **8–15 metrics that
   actually move this P&L** — not a generic ratio dump. Tag each: `driver` (moves
   revenue/margin), `health` (balance-sheet/quality), or `moat` (durability). For each,
   specify: unit, the fact(s) it's computed from, and whether we can build it from the
   filings we have. This is the extraction and analysis targeting list.
6. **Unit economics.** Define the per-unit denominator this business is measured in
   (per tonne / per store / per subscriber / per seat / per room-night / per loan) and the
   per-unit revenue, cost, and profit to be tracked over time.
7. **Swing drivers (3–5).** The variables that, if wrong, break the thesis — the ones that
   deserve a sensitivity table. For NALCO: LME aluminium, alumina price, coal cost, INR.
8. **Peer set + comparability deltas**, and the **industry questions** (supply-demand
   balance, cost-curve position, demand CAGR) to route to DR2.

This artifact is *cheap* (one sonnet pass on the latest AR's business/segment sections +
what triage already found) and it **pays for itself** by making every later wave sharper
and by being the thing that lets a thin-data company still get a real report.

### Generic KPI-tree seeds by business archetype (starter, not exhaustive)

> **ILLUSTRATIVE ONLY — not a KPI source.** When this was written the sector packs were the
> only KPI lists. There are now two authoritative ones: `config/sector_registry.yaml`'s
> `signature_kpis` (the machine-readable coverage contract `tools/compute_kpis.py` enforces)
> and the 32 tier-2 playbooks in `prompts/sector_playbooks/`, which carry each KPI with its
> formula, unit, benchmark and source. **The registry and the playbooks are the single source of
> truth; this table is retained only to make the *method* legible.** Do not seed a KPI tree from
> it — seed from the playbook for the slug in `state/triage.json`.

The tier-1 packs route and the tier-2 playbooks hold the KPI tables; prompt 03 turns the
playbook's signature KPIs into a *tracked tree*. Cross-industry starter so the method is
legible:

| Archetype | Driver KPIs | Unit economics | Net long/short |
|---|---|---|---|
| Commodity/metals | volume, realization, cost/t, utilization, segment EBIT/t | per tonne | long output commodity, short input+energy |
| Bank/NBFC | loan growth, NIM, CASA, credit cost, C/I | per ₹ of assets | long credit/duration, short liquidity |
| FMCG/consumer | volume growth, realization, gross margin, A&P %, distribution reach | per case/SKU | long brand, short commodity input |
| IT services | USD revenue growth, CC growth, EBIT margin, utilization, attrition, revenue/employee | per employee | long wage arbitrage, short USD/INR + wage inflation |
| Pharma | US/DF/EM mix, gross margin, R&D %, ANDA pipeline, price erosion | per molecule/market | long pipeline, short price erosion + USFDA |
| EPC/infra | order book, book-to-bill, execution rate, WC days, NWC/sales | per project | long backlog, short WC + commodity |
| Retail/QSR | SSSG, footprint growth, gross margin, store payback, ADS | per store | long footprint, short rent+labour |

## 4. Layer B — the deterministic KPI computer (`tools/compute_kpis.py`)

`compute_ratios.py` does accounting ratios. It cannot do per-unit economics because it
doesn't join **operating volumes** (extracted as facts by the narrative/doc extractors)
to **segment financials**. The new tool does exactly that, driven by the KPI tree:

- **Per-unit economics:** revenue/unit, EBIT/unit (by segment), cost/unit, realization/unit
  — for every period where both the numerator (segment revenue/EBIT) and denominator
  (segment volume) exist.
- **Operating-KPI trend tables:** each KPI in the tree as a period-by-period row
  (FY and quarterly), with YoY deltas — the tables the user explicitly asked for
  ("KPIs behaving across available data … in a table, no graphs is fine").
- **Segment analytics:** segment-EBIT margin by segment over time; % EBIT contribution by
  segment; mix shift. (This is what produced the benchmark's "net-long-alumina" thesis.)
- Output: `facts/kpis.json` (KPI fact records, `method: computed`, formula+inputs) +
  `state/kpi_trends.md` (rendered trend tables). Zero tokens, like the other tools.

Deterministic-first still holds: the *computation* is a script; the *interpretation* of the
trend (why utilization fell in FY14, why segment mix swung) is the analyst's job.

## 5. The circular research loop, made concrete (user's "in the loop, not one go")

We already loop (DR waves + staleness re-runs). V2 tightens it into a **driver-question
loop** and adds a lightweight **micro-search** primitive so research is pulled by specific
analytical needs, not pushed in one big pass:

1. **Business-model map (prompt 03) emits the industry questions** with the swing drivers →
   these seed DR2 precisely (supply-demand balance, cost-curve position, demand CAGR,
   peer multiples) instead of a generic "research the sector."
2. **Analysts may raise a micro-search** — a single bounded question with an `impacts`
   tag, answered by ≤3 web queries — mid-analysis, when a specific external fact would
   change a finding (a peer's multiple, a commodity balance number, whether a plant
   commissioned). The orchestrator batches these into a short research wave rather than a
   new full DR. (This is SOP §7's rule, now a first-class step.)
3. **New external facts propagate by the existing staleness engine** (impacts tags →
   re-run only affected findings). Nothing else changes; the loop is the same, the
   *targeting* is sharper.

Rule of thumb (unchanged from SOP §7, restated for V2): two bounded deep passes as the
skeleton (DR1 with analysis; DR2 after the business-model map) + a micro-search budget for
driver-specific facts + single-query orchestrator lookups for rating-box facts. Never an
unbounded "research everything" pass.

## 6. Sparse-data mode (only a few filings, nothing else)

The business-model spine is what makes a thin-data run still useful, because Layer A is
built from *first principles + one AR*, not from a rich document set. Prompt 70 (sparse-data
playbook) formalizes it:

- **Always possible from even one annual report:** the value-chain map, the KPI tree, the
  unit-economics definitions, the segment structure, the balance-sheet quality read, and
  whatever KPI trend the single filing's own comparatives allow (an AR carries the prior
  year; a few ARs carry a short series).
- **Lean harder on external anchoring:** when internal history is short, the industry
  supply-demand, demand CAGR, peer multiples and cost-curve position (all external) carry
  more of the report — the circular micro-search does more work.
- **Estimates degrade gracefully:** with < 3 years of history, don't fake a driver model;
  publish a scenario range off the current run-rate + the external price/volume outlook,
  and *say* the confidence is capped by history depth.
- **Gap discipline is the deliverable, not an apology:** the report explicitly lists what a
  fuller document set would have added, so the reader knows the boundary of the analysis.
  A good thin-data report is one where the reader finishes knowing the business and knowing
  exactly what is and isn't established.

## 7. What changes, concretely (implementation index)

| Change | File | Type |
|---|---|---|
| Business-model & value-chain mapping | `prompts/03_business_model_and_value_chain.md` | NEW |
| Deterministic KPI / unit-economics builder | `tools/compute_kpis.py` | NEW |
| Sparse-data playbook | `prompts/70_sparse_data_playbook.md` | NEW |
| Consume KPI tree; mandate operating-KPI trend tables, per-unit economics, segment analytics, driver bridges w/ in-out-of-estimates flag | `prompts/20_fundamental_analysis.md` | EDIT |
| Industry supply-demand *balance* table; peer *multiples* as a hard deliverable; micro-search primitive | `prompts/31_deep_research_sector_peers.md` | EDIT |
| In-note sensitivity table + valuation bridge + peer-multiple table (not only handoff) | `prompts/32_estimates_projections.md` | EDIT |
| Dispatch prompt 03 at triage; sparse-data branch | `prompts/02_triage_rules.md` | EDIT |
| New report exhibits: value-chain/asset map, capex pipeline, KPI trends, segment analytics, sensitivity, peer multiples, price performance | `prompts/41_final_report.md`, `prompts/40_dossier_assembly.md` | EDIT |
| Lifecycle: insert BUSINESS-MODEL (step 1.5) + KPI compute; config toggles | `CLAUDE.md`, `config/agent_config.yaml` | EDIT |
| Operating manual for the above | `docs/SOP_ORCHESTRATOR_RUNS.md` §10 | EDIT |

### Added after this document was written (2026-08-02 / 2026-08-03)

This index covered only the 2026-07-19 redesign. The corpus work that followed added a
knowledge layer this document does not describe, and which supersedes parts of it:

| Change | File | Type |
|---|---|---|
| 165-note corpus toolchain (discover → fetch → convert → profile → digest) | `tools/er_corpus/` | NEW |
| What Indian initiation notes actually do, counted — **supersedes this document's evidence base** | `docs/ER_CORPUS_FINDINGS.md` | NEW |
| Opinion/analysis taxonomy + the 15-check audit | `docs/OPINION_VS_ANALYSIS.md` | NEW |
| Per-broker calibration when citing competitor research | `docs/BROKER_CALIBRATION.md` | NEW |
| Thesis ownership: return decomposition, archetype typing, must-be-true checklist, bottom-up rating | `prompts/33_thesis_synthesis.md`, `.claude/agents/thesis-synthesizer.md`, `schema/thesis.schema.json` | NEW |
| Adversarial pass in a separate context; the mandatory 33↔34 round trip | `prompts/34_thesis_redteam.md`, `.claude/agents/thesis-redteam.md` | NEW |
| 14 thesis archetypes with conditions, failure modes, falsifiers, skepticism weights | `prompts/thesis_archetypes/` | NEW |
| Two-tier sector routing: 8 family packs (routers) + **32 sub-sector playbooks** (analysis) | `prompts/sector_packs/`, `prompts/sector_playbooks/` | NEW |
| Single source of truth for sector routing + the signature-KPI coverage contract | `config/sector_registry.yaml` | NEW |
| Registry integrity checks E1-E11 (incl. playbook/pack de-duplication and no-prose-in-registry) | `tools/validate_sector_registry.py` | NEW |
| Waves 6a/6b inserted; thesis and red-team artefacts added to shared state | `CLAUDE.md`, `prompts/01_orchestration_protocol.md` | EDIT |

**Read `docs/DESIGN_DECISIONS.md` for why each of those was built.** Where this document and
`ER_CORPUS_FINDINGS.md` disagree on what a professional note does, the corpus wins.

## 8. The honest limits (what this still won't be)

This does not turn the system into a 20-year-veteran analyst, and shouldn't pretend to.
What it *can't* close: proprietary/paid data (Bloomberg consensus, CRU/WoodMac cost curves,
channel checks, expert calls); genuine industry intuition about which management teams
under-promise; and primary-source docket screens our tooling still can't reach. What it
*can* close: the structural understanding of the business, the KPI trends from available
data, the industry balance from public sources, the unit economics, and a self-contained
report where — the user's bar — **after one read you understand the company, its industry,
and what drives the stock.** That is the target, and it is reachable from the PDFs we have
plus disciplined, looped web research.
