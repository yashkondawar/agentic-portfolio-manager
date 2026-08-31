# 41 — Final Note (≤14 pages, evidence-first)
*(the deliverable a fund manager actually reads; opus tier; template: `templates/final_note_template.md`)*

## Mandate
A publishable-quality note: **≤ 14 pages** (~5,500–6,500 words + tables), no ESG section, no DCF/WACC (config).

**Stance: `evidence_first` (`config.report.stance`).** The report exists so the READER can form their own opinion. That decides the shape of everything below:

- **Where the effort goes:** extraction depth, external research (industry, peers, comparables), and analysis and evaluation. These get the pages.
- **Where it does not:** arguing a call. The house view is one bounded section at the **end** (`config.report.recommendation_position: end`), and `config.rating.emit: false` removes it entirely — in which case the note states no rating, which is a legitimate deliverable rather than an incomplete one.
- **What does NOT shrink:** the rigour. `prompts/33` and `prompts/34` still run and are still not optional. Under this stance their visible output is the part a reader needs — the must-be-true table, the disconfirming exhibit, the red-team challenges — because that is *evidence about how good the evidence is*. What shrinks is the rating's prominence.

Why, in the repo's own numbers rather than as a matter of taste: across 165 initiations 94% of ratings are positive, so **"the rating carries almost no information. The analysis carries nearly all of it"** (`docs/ER_CORPUS_FINDINGS.md` §5).

**Crisp does not mean thinner.** Crispness is a property of form: numbers in tables rather than sentences, one claim per row, a `Source:` line on every exhibit, prose only where it carries a causal chain a table cannot. Detail that will not fit goes to the dossier **by reference** ("full ledger: dossier §7") — never deleted. Every number cited per the standard; sectional legends compact; the global legend lives in the dossier.

The note is a **compression of the dossier** — selection, not new analysis. Selection rule: include what a reader needs to reach their own view; push the rest to the dossier by reference.

## Page budget (guide, not straitjacket)

Order below is the *print* order under `evidence_first`. Note what moved: the house view is §9, not §1. Sections 3-6 are the evidence layer and carry the majority of the pages.

1. **p1 — What this company is, and what it earns.**
   **No rating on this page.** Page 1 answers "what is this business, what does it earn, and what is the single most important structural fact about it", so a reader who stops after page one leaves with the machine rather than a verdict.

   Open with the `net_position` one-liner from `state/business_model.json` — the "net long in alumina"-style structural tilt, which is the sharpest thing sayable in one sentence. Then the **snapshot block**: CMP (date), mcap, 52-wk range, promoter % (pledge %), FII/DII %, free float, 3m ADV, forward P/E (FY+1E/FY+2E). Then the **price-performance strip** from market_data: absolute + relative-to-index returns 1M/3M/6M/12M, benchmark named. Then the 3–4 evidence pillars, one short paragraph each, ≥2 evidence refs apiece — written as *findings*, not as advocacy.

   Then the **return decomposition, stated as arithmetic rather than as an argument**: *"at CMP the market pays X.Xx forward EPS; on the estimate set in §7, expected return is Y%, of which Z pp is EPS growth and W pp is the multiple moving from A x to B x on a &lt;base year&gt; base."* The corpus shows the multiple is the one real judgment call in a note and is almost never surfaced (`docs/ER_CORPUS_FINDINGS.md` §4); we surface it *early*, precisely so the reader can discount our §9 view against it. If the base year is rolled forward, give the un-rolled context beside it.

   The **archetype and the rating belong to §9**, not here.
1b. **p1-2 — "Story in exhibits" spread (NEW).** Six to ten exhibits that state the whole argument before the prose does — the single most transferable format in the corpus (a third of notes open this way; ICICI's HDB Financial note uses exhibits 1–9 for exactly this). Draw them from the sector playbook's **standard exhibit set** in `prompts/sector_playbooks/<slug>.md`. Every exhibit carries a `Source:` line.
2. **p2 — What's priced in, and what would have to be true.** Where we differ from guidance/consensus and why; the reverse-multiple read; top 4 risks with probability-impact tags (one line each). Where there is **no** variant view, say so — it is a legitimate finding, not a gap to paper over.
   Include the **must-be-true table** from `state/thesis.json`: each condition with `established / partial / unestablished` and one line of evidence. Present it as a **reader's checklist, not as our argument** — it tells them which planks are load-bearing and which are unproven, so they can weight them themselves. An `unestablished` row is the most useful row on the page and must never be dropped for tidiness.
   Include **at least one disconfirming exhibit** — evidence that cuts against our own thesis. Required by `config.thesis.require_disconfirming_exhibit` and audited as check #10 by module 34. The corpus precedent is ICICI publishing "HDB has grown slower than peers over the past 3 years" inside a BUY.
3. **p3 — Company & value chain.** What the business is; the **value-chain / asset map** from business_model.json rendered as a table (each node: own/buy/sell-into, capacity/detail — benchmark Ex 1) so the reader sees the physical machine; segment mix & evolution; the 2–3 structural facts that matter (integration, licenses, network position); the **capex / growth-project pipeline table** (project | description | investment | status | likely completion — benchmark Ex 16). Where the margin/bottleneck sits and whether the company owns it.
4. **p4–5 — Industry & competition.** Market size build (numbers, not adjectives), growth drivers quantified, value-chain bottleneck and who owns it, cycle position; the **industry supply–demand balance** (deficit/surplus, benchmark Ex 4) where the sector is commodity/cyclical; peer table (the decision-relevant cut: growth, margins, ROCE, leverage, **P/E, EV/EBITDA, P/B**, sector KPI — peer multiples are mandatory per module 31) with premium/discount verdict.
5. **p6–7 — Financial analysis + operating KPIs.** Multi-year summary table; the 3–4 findings that drive the thesis (margin architecture, capex→incremental ROCE, WC/cash conversion, funding), each why-chain compressed to 2–3 sentences. **Operating-KPI trend tables** (from module 20 / kpi_trends.md — the driver KPIs over available periods, no graphs needed), **per-unit economics** (revenue/EBIT/cost per unit by segment), and the **segment analytics** (EBIT-margin + % EBIT-contribution trend, the mix-shift story) — this is the "understand how the KPIs behave across the data" layer; keep it as tables + a 2–3 sentence read each.
6. **p8 — Earnings quality & governance.** Composite scores (earnings quality 0–100, governance 0–100 with verdict color), the confirmed flags that matter (severity high only; count of dismissed noted), guidance credibility summary.
7. **p9–10 — Estimates & valuation.** The estimates table (FY-2A…FY+2E per module 32 spec); the **driver-assumption table** (the swing drivers × periods — price/volume/FX — so the reader sees what the numbers rest on); the **sensitivity table** (EBITDA/EPS to each swing driver ±5/10%, with the one-line elasticities — benchmark Ex 25–27); the **valuation bridge** (FY+2E EBITDA → EV → equity → fair-value context, benchmark Ex 28) beside the peer-multiple table; forward P/E vs 5y band vs peers; scenarios table (base/bull/bear EPS CAGR seeds — explicitly *inputs to the downstream PT engine*, no price targets). Any driver bridge held OUT of the base (module 20's in/out flag) is stated here and reflected in the bull case only.
8. **p11 — Risks, catalysts, monitorables.** Risks with mitigants; dated catalysts calendar (results, commissioning, regulatory decisions, expiry of pledges/lock-ins); monitorables with the threshold that would change the view.
9. **p12 — The house view (bounded, and last).** Everything above is evidence; this section is opinion, labelled as such and confined here so a reader can skip it without losing anything.

   Emit only if `config.rating.emit` is true. Contents, and nothing more: the **rating stated exactly once**; the **archetype** in one clause with its skepticism weight; the rating's derivation in ≤5 lines (expected return → skepticism weight → red-flag/governance haircut → data-gap widening → scale); `not_higher_because` and `not_lower_because`, one line each; and the fair-value context labelled "indicative — formal TP from the downstream scenario engine, see handoff".

   Keep it to one page. If the argument needs more than a page, the evidence sections above are doing too little work. Where `config.rating.emit` is false, replace this section with a two-line statement that no house call is offered and why, and end the note at §10.

10. **p13-14 — Data gaps & limitations + disclosures.** Honest gaps (unanswered questions marked `disclosed`, verification UNVERIFIABLEs, missing documents); **the red-team verdict** from `findings/thesis_redteam.json` — the verdict, the number of material challenges raised, and how each high-severity one was resolved (so the reader knows the thesis was adversarially tested and how it fared); disclaimer + AI-use disclosure block (SEBI RA-regulation-style, from `templates/disclaimer.md`); note pointer to dossier + handoff JSON.

## Voice & guardrails
- Plain analytical prose. Banned words per config. No exclamation marks. Numbers do the persuading.
- Facts → interpretation → implication, in that order, in every section.
- Charts: describe as markdown tables in v1 (rendering to graphics is a later iteration); label each "Exhibit N".
- Nothing appears here that failed or skipped verification (gate per prompt 50).
- If loops exhausted with open high-severity questions, they appear in p12 — the note is honest about what it doesn't know.
