# 70 — Sparse-Data Playbook (few filings, nothing else)
*(NEW in v2; branch selected at triage when the document set is thin; not a separate agent — a MODE that changes how modules 03/20/31/32/41 behave. Rationale: `docs/PROCESS_V2_REIMAGINED.md` §6.)*

## When this fires
Triage sets `data_mode: sparse` when the input is, e.g., ≤2 annual reports, or only a few
quarterly results, or a single AR + a presentation — and there is no transcript history, no
peer material, no prior deep research. The goal is unchanged: a report where **after one read
the investor understands the business, its industry, and what drives the stock** — honestly
bounded by what the documents support.

The core reason a thin-data run can still be good: the **business-model spine (prompt 03) is
built from first principles + one annual report**, not from a rich document set. Structure
survives data scarcity; only the trend depth and the estimate confidence shrink.

## What is ALWAYS possible from even a single annual report
Do these fully; they carry the report:
1. **Value-chain map + KPI tree + unit economics** (prompt 03) — first-principles, needs only
   the business/segment/MD&A sections. This is the report's backbone.
2. **Segment structure & the net-long/short framing** — from the segment note.
3. **Balance-sheet quality & solvency read** — one balance sheet + its comparative is enough
   for leverage, liquidity, working-capital-intensity, and a first earnings-quality pass.
4. **Whatever KPI trend the filing's own comparatives allow** — every AR carries the prior
   year; N annual reports carry an N+1 year series; a quarterly result carries YoY-quarter.
   Run `compute_kpis.py` and `compute_ratios.py` on whatever periods exist and label the
   series length honestly (a 2-point "trend" is a change, not a trend — say so).

## What must carry MORE weight when internal history is short
Shift the center of gravity to **external anchoring via the circular micro-search loop**
(prompt 31 + orchestrator lookups), because the industry context does not depend on the
company's filing count:
- Industry **supply-demand balance** and **demand CAGR** (independent sources).
- **Cost-curve / competitive position** of the company's output.
- **Peer multiples and peer operating KPIs** (listed peers via `market_data.py` + web) — a
  peer set with 5 years of history substitutes for the target's missing history: "the target
  trades at X vs a peer median of Y" is available even when the target itself is newly listed.
- **Price mechanism facts** (contracts, regulation, tariffs) that de-risk or frame the story.
Budget more micro-searches here than in a data-rich run; each is bounded and driver-tagged.

## Estimates degrade gracefully (do NOT fake precision)
- With **< 3 years of history**, do not build a false driver model off two points. Instead:
  anchor to the **current run-rate** (latest FY or annualized latest quarter) and flex it with
  the **external price/volume outlook** from DR2. Publish a **scenario range** (bear/base/bull),
  not a false point estimate.
- State the confidence cap explicitly: "estimate confidence is capped `low` by <N years>
  of history; the range widens accordingly." The downstream valuation handoff carries
  `history_depth_years` and `confidence_cap` so the PE/TP agent inherits the caveat.
- Reported-over-computed and no-invention rules are unchanged — a thin dataset is not a
  licence to estimate unlabelled.

## Gap discipline IS the deliverable
The report's data-gaps section is not an apology — it is a map of the analysis boundary. List:
- what a fuller document set would have added (e.g. "5 years of transcripts would establish a
  guidance-credibility track record; with 1 AR we cannot score management delivery");
- which findings are `disclosed` gaps vs established facts;
- the confidence cap on estimates and why.
A good sparse-data report is one where the reader finishes knowing the business **and** knowing
exactly where the evidence stops. That honesty is worth more than a padded page count.

## Module-by-module deltas in sparse mode
- **03 business-model:** run in full — it is the whole point.
- **10/11 extraction:** extract everything available to ≥ level 2; the marginal value of each
  fact is higher when there are fewer of them.
- **20 fundamental / 21 forensic:** run, but scope claims to the series length; a 2-year
  "trend" is flagged as such; earnings-quality score notes the short window as a confidence cap.
- **22 guidance:** likely thin/absent (no transcripts) — say so; do not manufacture a
  credibility score from one data point.
- **31 DR / micro-search:** does MORE of the work; industry + peers carry the report.
- **32 estimates:** run-rate + external outlook + scenario range, confidence-capped.
- **41 report:** same structure; the industry/business-model/peer sections expand to fill what
  the internal-history sections cannot; the gaps section is prominent, not buried.
