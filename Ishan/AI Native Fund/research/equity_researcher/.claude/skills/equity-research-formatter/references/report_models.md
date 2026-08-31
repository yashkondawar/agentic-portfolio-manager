# Report content checklists

Field checklist per archetype, for extracting source markdown into a `blocks` array. Not every field will be present in every source — omit gracefully rather than inventing values. This is a checklist, not a template to fill in mechanically: real sources vary, and section order/naming should follow the source, not this list.

## ER (sell-side / external-facing)

- **Masthead**: firm/desk label (e.g. "Equity Research"), report-type label (e.g. "Initiating Coverage").
- **Title**: company, ticker line (exchange, sector, date), headline subtitle.
- **Tombstone**: rating, CMP, target or fair-value range, downside/upside, market cap, 52-week range, forward P/E. If the source explicitly declines to give a single target ("this is context, not a target"), preserve that hedge in a caption under the tombstone — don't manufacture a single number for tidiness.
- **Snapshot table**: CMP, mcap, 52-wk H/L, promoter %/pledge status, FII/DII %, free float, forward P/E.
- **Investment thesis**: numbered/bulleted points — usually 3–5, each a full argument, not a fragment.
- **Variant view**: what the market may be pricing that the note disagrees with, and why the note doesn't adopt that view.
- **Company section + segment exhibit**: business description, segment mix table.
- **Industry & competition + peer exhibit**: market sizing, pricing/cost context, peer comparison table.
- **Financial analysis + exhibit**: multi-year summary table, 3–4 bullet findings.
- **Earnings quality & governance**: composite scores, what's driving them.
- **Estimates & valuation + exhibit**: multi-year estimates table, the assumptions that matter, scenario table.
- **Risks, catalysts & monitorables**: risk/mitigant pairs, dated catalyst calendar, threshold conditions that would change the view.
- **Data gaps & limitations**: honest, named gaps — don't paper over them.
- **Disclaimer / AI disclosure / validity / sources**: reproduce verbatim if present in the source.

## Forensic (dossier / fact registry)

- **No-recommendation callout**: near the top, prominent — this is often explicitly stated in the source and should not be buried.
- **Input manifest / run record** (if present): what documents fed the analysis, and the pipeline/process that produced it. This is itself a quality signal for an audit document — don't cut it just because it looks like metadata.
- **Executive summary**: thesis paragraph, core financial health, valuation synopsis, principal risks — dossiers aren't always "just a ledger"; check for a real synthesis section before assuming you need to add one.
- **Industry & market analysis**: value chain, competitive-forces scoring (e.g. Porter's five forces table), demand/pricing context, policy exposure.
- **Company deep-dive**: segments, unit economics, a weighted moat/quality matrix if present, competitive positioning narrative.
- **Historical financials**: multi-year income statement / balance sheet / cash flow tables, standalone and consolidated distinguished where the source distinguishes them.
- **Management & governance**: leadership table (role, tenure, background), weighted governance-composite table, guidance-credibility ledger (metric family × history × credibility, color-coded), management quotes bank — attribute quotes by **role** in the callout/citation, keep the named leadership table separate for governance-completeness; a governance chronology.
- **Red-flag ledger**: every entry has an ID, status (confirmed/disclosed/dismissed), severity, and a why-chain. Render confirmed and disclosed entries individually; condense large blocks of dismissed, low-severity, same-cause entries (e.g. routine period-to-period rounding) into one summary paragraph rather than listing all of them — but state the count and that they were condensed, and never quietly drop a confirmed or disclosed entry.
- **Valuation & peers**: historical multiple bands (with the underlying yearly table if given, not just the summary percentiles), peer table, premium/discount analysis, a business-quality composite if present.
- **Estimates**: driver table, the assumptions that matter, scenario table.
- **Future outlook**: catalyst calendar, risk-factor table (type × probability × impact), concluding synthesis.
- **Open questions / gaps register**: at minimum the high-severity ones; note the total count and how many are answered vs. open.
- **Disclaimer / AI disclosure / validity / sources**: reproduce verbatim. A full page-level source registry can run to 100+ rows — include a representative sample and say the full registry lives in the source markdown, rather than reproducing every row.

## Buy-side (thesis / EPS-bridge)

- **Tombstone**: recommendation, conviction score, CMP, base target (or explicit statement that none is given), downside/upside, forward multiple vs. the anchor multiple the thesis uses.
- **Doctrine statement**: the explicit rule the thesis is applying (e.g. "P/E re-rates only when EPS growth is consistent and >20% while the starting P/E is low relative to that growth") — this is usually the single most load-bearing sentence in the note; don't paraphrase it into something vaguer.
- **Section-by-section doctrine walk**: however many "rungs"/legs the source's own methodology has — render each as its own heading, don't compress them into one wall of text.
- **A decomposition/bridge table** if the source has one (volume/price/mix/cost/leverage or equivalent) — this is usually the analytical core; give its prose column (the "read" per lever) generous width.
- **Scenario grid**: bear/base/bull, with the specific inputs (EPS, multiple) and a resulting target or fair-value figure.
- **Invalidation / what-would-change-my-mind box**: render as its own callout, not folded into prose — it's the falsifiability condition and readers look for it specifically.
- **Bottom-line callout**: the note's own closing verdict, verbatim where the source has a distinctive closing line (metaphors, doctrine references) rather than a generic restatement.
- **Bridge/rule summary table** if the source has one (rule × verdict × read) — color the verdict column.

## Fact-ID tag convention (forensic + buy-side only)

Preserve fact-IDs inline in prose exactly as the source cites them (parenthetical, e.g. "(F-EST-01)") rather than converting to a different visual scheme — analysts reading these documents are used to that citation style and reformatting it adds friction without adding clarity. Never invent a fact-ID that wasn't in the source, and never silently renumber one you're unsure about — if two source documents cite the same code for different values, keep each document's own number as written rather than "fixing" it to match the other; note the discrepancy to the user instead.
