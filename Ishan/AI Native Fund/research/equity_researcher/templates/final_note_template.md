<!-- Final Note skeleton — spec in prompts/41_final_report.md. Placeholders in {braces}.
     Every slot corresponds to a numbered item in prompt 41's page budget. If a slot has no content,
     write the explicit absence ("no variant view — see below") rather than deleting the heading: a
     missing heading reads as an oversight, a stated absence reads as a finding. Exhibit numbering
     runs continuously.

     STANCE: evidence_first (config.report.stance). Page 1 is the business and its economics — NOT a
     rating. The house view is the last substantive section, bounded to one page, and is omitted
     entirely when config.rating.emit is false. Order here is deliberate: a reader must be able to
     stop before the opinion and still have everything they need to form their own. -->

# {Company Name} ({TICKER}) — Company Analysis

> **{One-line structural read — the `net_position` from state/business_model.json. The "net long in
> alumina"-style tilt: what this business is structurally long and short, in one sentence.}**

*This report is evidence-first. Sections 1–8 are findings and analysis; the analyst's own view is
confined to §9 and can be skipped without losing anything above it.*

**Snapshot** *(as of {date})*

| CMP | Mcap (₹ cr) | 52-wk H/L | Promoter % (pledge) | FII / DII % | Free float | 3m ADV | Fwd P/E FY+1E / FY+2E |
|---|---|---|---|---|---|---|---|
| {} [S] | {} [S] | {} [S] | {} [S] | {} [S] | {} [S] | {} [S] | {} / {} [S] |

**Exhibit 1 — Price performance** *(from facts/market_data.json; benchmark {index})*

| | 1M | 3M | 6M | 12M |
|---|---|---|---|---|
| Absolute % | {} | {} | {} | {} |
| Relative to {index} % | {} | {} | {} | {} |

**What the price implies** *(arithmetic, not argument — the multiple is the one real judgment call in
any note and is almost never surfaced; `docs/ER_CORPUS_FINDINGS.md` §4)*

| | |
|---|---|
| At CMP the market pays | {X.X}x forward {metric} |
| On the §7 estimate set, expected return is | {Y}% over {horizon} |
| …of which {metric} growth contributes | {Z} pp |
| …and the multiple moving {A}x → {B}x contributes | {W} pp ({M}% of the total) |
| Valuation base year | {FY} {If rolled forward: un-rolled context is {…}} |

## Story in exhibits
<!-- prompt 41 §1b. Six to ten exhibits that state the whole argument before the prose does — the
     most transferable format in the corpus (docs/ER_CORPUS_FINDINGS.md §1). Draw them from the
     "Standard exhibit set" section of prompts/sector_playbooks/{slug}.md. Every exhibit carries a
     Source: line. Number Exhibit 2..N; later sections refer back rather than repeat. -->

**Exhibit 2 — {title}** {table} · *Source: {}*

**Exhibit 3 — {title}** {table} · *Source: {}*

{… through Exhibit {7–11}. Then: name any exhibit in the playbook's standard set that could **not** be built, and why — a disclosed absence beats a silent one.}

## Key findings
{3–4 findings (`config.thesis.max_pillars`). One short paragraph each, ≥2 evidence refs apiece. Write them as **findings, not advocacy**: what the evidence shows and what follows from it. A reader should be able to disagree with our §9 view while still accepting every finding here.}

## What's priced in, and what would have to be true
{The reverse-multiple read: "CMP implies ~X% EPS CAGR at constant multiple Y×." Where we differ from guidance or consensus, say where and why. Where there is **no** variant view, say so — a legitimate finding, not a gap to paper over.}

**Exhibit {n} — Must-be-true conditions** *(from state/thesis.json → `must_be_true`; the archetype's checklist)*

| # | Condition | Status | Evidence (one line) |
|---|---|---|---|
| 1 | {} | established / partial / unestablished | {} [S] |

{Present this as the **reader's checklist, not our argument**: it shows which planks are load-bearing and which are unproven, so they can weight them independently. An `unestablished` row is the most useful row on the page — never drop one for tidiness.}

**Exhibit {n} — Disconfirming evidence** *(mandatory per `config.thesis.require_disconfirming_exhibit`; audited as check #10 by module 34)*
{At least one exhibit that cuts against our own reading. Corpus precedent: ICICI published an exhibit showing HDB grew *slower* than peers inside a BUY — `docs/ER_CORPUS_FINDINGS.md` §7.3.} · *Source: {}*

**Top 4 risks:** {one line each, probability–impact tagged}

## Company & value chain
{What the business is; the 2–3 structural facts that matter — integration, licences, network position. Where the margin/bottleneck sits and whether the company owns it.}

**Exhibit {n} — Value-chain / asset map** *(from state/business_model.json)*

| Node | Own / buy / sell-into | Capacity or detail | Note |
|---|---|---|---|
| {} | {} | {} [S] | {} |

**Exhibit {n} — Segment mix & evolution** {table: revenue and EBIT by segment across years, with % contribution}

**Exhibit {n} — Capex / growth-project pipeline**

| Project | Description | Investment (₹ cr) | Status | Likely completion |
|---|---|---|---|---|
| {} | {} | {} [S] | {} | {} |

## Industry & competition
{Market-size build with numbers; quantified growth drivers; value-chain bottleneck and who owns it; **cycle position — say explicitly where in the cycle the earnings base sits**.}

**Exhibit {n} — Industry supply–demand balance** *(mandatory for commodity/cyclical sectors; otherwise give the one-line reason for omission)*
{table: production (existing + additions − curtailments) · imports/exports · demand · net deficit/surplus, split by region where it matters}

**Exhibit {n} — Peer comparison** *(decision-relevant cut; peer multiples are mandatory per module 31)*
{table: growth | margins | ROCE | leverage | **P/E | EV/EBITDA | P/B** | sector KPI — with the premium/discount verdict below, and the comparability deltas carried from module 31}

## Financial analysis & operating KPIs
**Exhibit {n} — Financial summary** {multi-year rendered table}

{The 3–4 findings that drive the thesis: margin architecture · capex→incremental ROCE · working capital/cash conversion · funding. Each why-chain compressed to 2–3 sentences.}

**Exhibit {n} — Operating-KPI trends** *(from state/kpi_trends.md and facts/kpis.json — the driver KPIs over available periods)*
{table: KPI × period, then a 2–3 sentence read.}

**Exhibit {n} — Per-unit economics** *(revenue / EBIT / cost per {unit_denominator for this playbook, from config/sector_registry.yaml} by segment)*
{table, then a 2–3 sentence read: is the move volume, spread, or mix?}

**Exhibit {n} — Segment analytics** {table: EBIT margin + % EBIT contribution by segment across years — the mix-shift story, then a 2–3 sentence read.}

{Where a signature KPI from the playbook could not be computed, **name it and say why** — `compute_kpis.py` emits a named skip for each unmet signature KPI, and those skips belong on the page, not only in state.}

## Earnings quality & governance
{Earnings-quality score /100 with drivers; governance verdict (Green/Amber/Red) + score; confirmed high-severity flags; count of checks passed/dismissed; guidance credibility summary.}

## Estimates & valuation
**Exhibit {n} — Estimates** {FY-2A … FY+2E table: revenue, growth %, EBITDA, margin %, PAT, EPS, ROE, capex, FCF, P/E@CMP}

**Exhibit {n} — Driver assumptions** *(the swing drivers × periods — what the numbers rest on)*

| Driver | FY-1A | FY0E | FY+1E | FY+2E | Basis |
|---|---|---|---|---|---|
| {price / volume / FX / spread} | {} | {} | {} | {} | {} [S] |

**Exhibit {n} — Sensitivity** *(EBITDA/EPS to each swing driver ±5/10%)*

| Driver | −10% | −5% | Base | +5% | +10% | Elasticity (one line) |
|---|---|---|---|---|---|---|
| {} | {} | {} | {} | {} | {} | {} |

**Exhibit {n} — Valuation bridge** *(FY+2E EBITDA → EV → equity → fair-value context)*

| Step | Value | Note |
|---|---|---|
| FY+2E EBITDA | {} | |
| × target multiple | {}x | {justification — peer-anchored; name the peer set and the playbook's convention} |
| = EV | {} | |
| − net debt (+ investments, − minorities) | {} | |
| = equity value per share | {} | |

{The 5 assumptions that matter, each with basis. Forward P/E vs 5y band vs peers. Any driver bridge held **out** of the base (module 20's in/out flag) is stated here and reflected in the bull case only.}

**Scenarios (inputs to the downstream PT engine — not price targets):** base / bull / bear EPS CAGR + one-line rationale each.

## Risks, catalysts & monitorables
{Risks with mitigants · dated catalyst calendar · monitorables with the threshold that would change the view — from state/thesis.json → `monitorables` (the archetype's falsifiers, thresholded).}

## §9 — The analyst's view *(opinion, bounded — skip without loss)*
<!-- Emit ONLY if config.rating.emit is true. Keep to one page. If the argument needs more than a
     page, the evidence sections above are doing too little work. Where rating.emit is false,
     replace this whole section with a two-line statement that no house call is offered, and why. -->

| **{RATING}** | *the only recommendation statement in this report* |
|---|---|
| **Fair-value context** | {range} — indicative band ({basis}); formal TP pending the downstream scenario engine (see handoff) |
| **Thesis archetype** | {archetype from state/thesis.json} · skepticism weight {n}/5 |

**How this rating was derived** *(≤5 lines, from state/thesis.json → rating.derivation)*
{expected return → archetype skepticism weight → red-flag/governance haircut → data-gap widening → the scale in config.rating.scale. Show each step's effect on the range, not just the conclusion.}

**Not higher because** {one line} · **Not lower because** {one line}

## Data gaps & limitations
{Unanswered high-severity questions (marked `disclosed`) · verification UNVERIFIABLEs · missing documents.}

**Exhibit {n} — Red-team verdict** *(from findings/thesis_redteam.json — module 34)*

| | |
|---|---|
| Verdict | {survives / survives_with_qualifications / not_established} |
| Material challenges raised | {n} |
| Round trips completed | {n} (minimum per `config.thesis.redteam_min_rounds`) |
| Disconfirming exhibit | {which exhibit above} |

{Each high-severity challenge and how it was answered — one line each. A challenge that was **not** resolved is stated as unresolved, never dropped. This is what tells the reader the thesis was adversarially tested and how it fared.}

---
{Disclaimer + AI-use disclosure — templates/disclaimer.md verbatim}
*Full audit trail: report/dossier.md · machine-readable estimates: handoff/valuation_handoff.json · thesis: state/thesis.json · red team: findings/thesis_redteam.json*
