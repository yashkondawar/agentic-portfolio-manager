---
name: equity-research-formatter
description: Formats finance/equity-research markdown notes into polished Word (.docx) documents styled like institutional equity research reports — navy/gold palette, serif headings, styled tables, rating tombstones, color-coded status columns. Use whenever the user has research notes in markdown about a stock or company — a fact-registry/forensic dossier, a sell-side-style equity research note, and/or a buy-side thesis or EPS-bridge note — and wants them turned into professional Word documents. Trigger on requests to format a "research report," "ER report," "forensic report," "dossier," or "buy-side note" into Word/docx, or to make research markdown "look like an equity research report." Applies even for just ONE of the three note types, not only all three together. Produces one styled .docx per input note, sharing a design system so notes on the same company read as a matched set while staying visually distinct by archetype.
---

# Equity Research Report Formatter

## Overview

Converts markdown research notes into styled `.docx` files that read like institutional research: a masthead, a title block, styled tables, and archetype-specific components (rating tombstone, red-flag severity table, EPS-scenario grid). Built on **docx-js** (the `docx` npm package, per this environment's `docx` skill — not python-docx). One shared design system (`scripts/reportStyle.js`) is reused across three note archetypes.

The docx-js gotchas this engine already handles (table shading via `ShadingType.CLEAR`, dual column widths, bullet numbering via a numbering config, horizontal rules as paragraph borders, no `\n` inside TextRuns) are baked into `reportStyle.js` — respect them if you extend it.

## Wiring in this repo (Agentic Equity Researcher)

This skill is wired as the **FORMAT stage** (step 9) of the run lifecycle — it runs after RENDER (report-writer → `report/dossier.md` + `report/final_note.md`) and, when present, after the buy-side note. The deterministic engine lives at `tools/report_formatter/` (a copy of `scripts/reportStyle.js` + `build_reports.js` runner + a local `docx` install); it is not re-installed per run.

> ### `scripts/` is REFERENCE-ONLY — do not run it
>
> Everything under `.claude/skills/equity-research-formatter/scripts/` is a reading copy. Those
> files `require("docx")`, but this directory has **no `package.json` and no `node_modules`**, so
> `node scripts/build_example.js` fails with `Cannot find module 'docx'`. That is intentional and
> not a bug to fix by adding a second npm install: `tools/report_formatter/` already carries the
> `package.json`, the lockfile, the installed `docx`, and the runner the lifecycle actually calls.
> Duplicating the install would create two dependency trees to keep in sync.
>
> - **To render:** `node tools/report_formatter/build_reports.js <TICKER>` (step 9). Permitted by
>   `Bash(node tools/*)` in `.claude/settings.json`.
> - **To read the design system:** `scripts/reportStyle.js` — a byte-identical copy of
>   `tools/report_formatter/reportStyle.js`.
> - **To read worked examples:** `scripts/example_*_content.js` and `scripts/build_example.js`,
>   which shows the standalone assembly pattern. Read them; don't execute them.
>
> **The two `reportStyle.js` copies must stay byte-identical**, and nothing enforced that until
> `tools/preflight.py` was written — it hashes both and fails if they diverge. If you change the
> design system, change `tools/report_formatter/reportStyle.js` (the one that runs), copy it over
> the skill's, and re-run `python tools/preflight.py`.

Per-run flow (native mode, Windows):
1. Classify the run's notes → archetypes: `report/final_note.md` = **ER**, `report/dossier.md` = **forensic**, `report/buy_side_note.md` = **buy-side** (only if the buy-side stage ran).
2. Extract each into a content module written to `workspace/<TICKER>/report/formatted/<name>.content.js`, each exporting `{ masthead, title, blocks, footer, outfile }`. Extraction is your judgment — build from the run's OWN notes/registry numbers, using `scripts/example_*_content.js` only as structural reference.
3. Build: `node tools/report_formatter/build_reports.js <TICKER>` → writes one `.docx` per content module into `workspace/<TICKER>/report/`.
4. Verify by rendering (not by reading code): this environment has **Microsoft Word**, not LibreOffice — export each `.docx` to PDF via Word COM (`powershell` `Word.Application` → `SaveAs` `wdFormatPDF=17`), then `view`/Read at least one wide-table page and one 2-column-text page per document. (If Word is ever unavailable, fall back to structural checks: unzip the `.docx`, confirm `word/document.xml` parses and expected strings are present.)
Outputs are `.docx` beside the markdown, not a separate deliverables mount — there is no `/mnt/user-data/outputs` in this repo.

## The three archetypes

Classify each source file before building — the components differ enough that guessing wrong changes the document's meaning, not just its look.

| Archetype | Signals in the source | Rating shown? | Fact-ID citations kept? |
|---|---|---|---|
| **ER** (sell-side / external) | A rating (BUY/ADD/REDUCE/SELL) with a target or fair-value range; client-facing prose; no internal fact-ID codes visible; standard sections (findings, financials, valuation, risks) | Yes — but see the evidence-first note below: the tombstone goes LAST, not first, and is dropped entirely when the source note carries no rating | No — external documents don't expose internal citation codes |
| **Forensic** (dossier / fact registry) | Heavy use of fact-ID codes (`F-...`, `S###`, `GD-...`, `RF-...`, `OQ-...`); organized as ledgers/registries rather than argument; explicit "no recommendation" language; often has a red-flag ledger with confirmed/disclosed/dismissed status | No — omit the rating tombstone; use an "Instrument Snapshot" or "No recommendation" callout instead | Yes — the fact-ID apparatus is the point of the document; never strip it |
| **Buy-side** | Explicit stated methodology/doctrine, scenario tables (bear/base/bull), an "invalidation" or "what would change my mind" section, a conviction score, fact-ID citations inherited from the dossier | Yes — recommendation + conviction score badge | Yes |

If a source doesn't cleanly match one archetype, ask which it's closest to rather than guessing.

Real dossiers, sell-side notes and buy-side notes can be very long (the reference build in this skill ran 578 / 149 / 100 source lines → 10 / 5 / 4 rendered pages). Don't be surprised by a long source file — condense repetitive, low-signal sub-content (e.g. a 16-row block of rounding/regrouping deltas) into a compact summary, but never drop the substantive findings just to shorten the document. Say what you condensed.

## Workflow

1. **Read every source markdown file in full** before writing any code — for a large file, use `view` with explicit line ranges rather than one call, since a full-file view truncates past ~16,000 characters and you cannot afford to miss facts in the middle (this is exactly where red-flag ledgers and estimate tables tend to sit).
2. **Classify** each file into one of the three archetypes above.
3. **Extract content into a plain data structure** — a `{ masthead: [firmLabel, reportLabel], title: [company, tickerLine, subtitle], blocks: [...], footer: string }` object, one file per report (see `scripts/example_*_content.js` for three complete worked examples). Do this extraction yourself; don't try to regex-parse the source markdown automatically — judgment calls about what's a red flag vs. context, or what to condense, belong to you.
4. **Render** with `reportStyle.js`. `blocks` is an ordered array of typed objects consumed by `renderBlocks()` — see the block-type reference below. In this repo, write each content module to `workspace/<TICKER>/report/formatted/<name>.content.js` and let `tools/report_formatter/build_reports.js <TICKER>` assemble every module into a `.docx` — do NOT reinvent document assembly or re-`npm install docx` (the runner + local dep already exist). `scripts/build_example.js` shows the equivalent standalone assembly pattern if you need to understand it.
5. **Verify by rendering, not by reading your own code.** This repo has Microsoft Word (no LibreOffice): export each `.docx` to PDF via Word COM (`powershell -Command "$w=New-Object -ComObject Word.Application; $d=$w.Documents.Open('<abs .docx>'); $d.SaveAs([ref]'<abs .pdf>',[ref]17); $d.Close(); $w.Quit()"`), then `view`/Read at least one wide multi-column-table page and one text-heavy 2-column-table page per document — that's where column-width ratios go wrong first.
6. **Save `.docx` into `workspace/<TICKER>/report/`** (beside the markdown) with clear filenames (`<TICKER>_<Archetype>.docx`); the build runner does this. There is no `/mnt/user-data/outputs` mount in this repo.

## Block types (`renderBlocks` input)

- `{ type:"heading", text, number }` — numbered or unnumbered section heading with a rule underneath.
- `{ type:"text", text, opts:{ size, italics, bold, after } }` — a paragraph. `size` is in half-points (21 = 10.5pt body default; use ~17–18 for fine print like disclaimers).
- `{ type:"sub", text }` — small italic sub-label above a table (e.g. "Exhibit 3 — Financial summary").
- `{ type:"bullets", items:[...] }` — real bullet glyphs via a numbering config, never literal "•".
- `{ type:"table", headers:[...], rows:[[...]], opts:{ colAligns, colorizeCol, colWeights } }` — navy header row, zebra body. `colorizeCol` colors that column's text by matching its value (case-insensitive) against `STATUS_COLOR`/`RATING_COLOR` in reportStyle.js (PASS/HIGH/CONFIRMED → red or green as appropriate; NA → gray). `colWeights` sets relative column widths — **always widen the column that holds prose** (e.g. `[1, 3.2]` for a Lever/Read table), or narrow text wraps awkwardly against a full-width numeric-table default.
- `{ type:"tombstone", fields:[[label,value], ...] }` — ER/buy-side only. `fields[0]` is colored by matching its first word against `RATING_COLOR` (BUY/REDUCE/AVOID/etc.).
- `{ type:"callout", title, text, color }` — shaded box with a left accent rule, for "Bottom line," "Invalidation," "No recommendation," "Disclaimer," "AI disclosure," etc.
- `{ type:"spacer", h }`.

## Design tokens

Headings/masthead font **Georgia**; body/table font **Calibri**. Navy `#1B2A4A` (headings, rules, masthead, ER tombstone default), Slate `#44546A` (secondary text, tombstone label row), Gold `#B08D57` (accent — good for a "base case" or neutral-synthesis callout that isn't a warning), Green `#2E6E3E` / Amber `#C4711B` / Red `#8B1E1E` (rating and status semantics), light gray `#F2F2F2` / mid gray `#D9D9D9` (table shading/borders). All exported as named constants from `reportStyle.js` — import them rather than hardcoding hex strings in content files.

## Common mistakes to avoid

- **Don't put a rating tombstone on a forensic/dossier document.** It has no recommendation by design — that's often stated explicitly in the source ("the rating does not appear in this document"). Use a "no recommendation" callout instead.
- **Evidence-first ER documents: the tombstone goes at the END.** This repo runs
  `config.report.stance: evidence_first`, so `report/final_note.md` opens with the business and its
  economics and confines the house view to a bounded final section (`prompts/41` §9). Mirror that in
  the `.docx` — do not hoist the rating to page 1 just because the ER archetype traditionally does:
  1. Open with a **structural-read callout** (the one-line `net_position`) plus the **instrument
     snapshot** table, then the "what the price implies" decomposition table.
  2. Place the **tombstone in the closing section**, immediately under the "The analyst's view"
     heading, so it reads as a bounded conclusion rather than a headline.
  3. If the source note has no rating (`config.rating.emit: false`), emit **no tombstone at all** and
     use the forensic archetype's "no recommendation" callout instead. A document whose evidence is
     the product should not be given a verdict it does not make.
  The reason is measured, not stylistic: across 165 real initiations 94% of ratings are positive, so
  the rating carries almost no information while the analysis carries nearly all of it
  (`docs/ER_CORPUS_FINDINGS.md` §5). Leading with the least informative element is a design error the
  genre has normalised.
- **Don't strip fact-ID codes from forensic or buy-side documents.** That traceability is their main value over a sell-side note — a forensic report with the citations sanded off is just a summary with extra steps.
- **Don't invent new analytical content** (executive summaries, synthesized conclusions, severity rankings) that isn't in the source. Format faithfully. If a source is missing a synthesis section a reader would want, say so to the user and offer to draft one — don't quietly write a point of view into a document that's supposed to be neutral.
- **Preserve regulatory/AI-disclosure boilerplate verbatim, not paraphrased.** If the source carries a specific disclaimer (e.g. a SEBI Research Analyst Regulations disclaimer, an AI-use disclosure), that's compliance language — reproduce it exactly, don't summarize it.
- **Match column weights to content**, per the table block type above — this is the single most common visual defect (cramped prose columns) and it's a one-line fix per table.
- **Keep the archetypes visually related but not identical.** Same fonts/palette across all three; but ER gets a tombstone + peer table, forensic gets a snapshot/no-rec callout + severity-colored ledger, buy-side gets a scenario grid + invalidation box. Making every document use the same structure regardless of type makes the thinnest one look thin by comparison rather than by design.
- **Cross-check numbers that appear in more than one source file** (a fact cited in the buy-side note should match the dossier it's drawn from). Where the same-looking figure differs across sources — e.g. a "5-year P/E band" computed on a strictly audited window vs. one that rolls forward to include an unaudited cross-check year — that's usually not an error, it's a methodology difference worth a one-line footnote, not silent reconciliation.

## Reference

`references/report_models.md` has the fuller field checklist per archetype if you want it before extracting; `scripts/example_*_content.js` are three complete, real worked examples (an ER note, a forensic dossier, a buy-side note) built from an actual triad of AI-prepared research notes on an NSE-listed company — read one end to end before writing your first content file, it's faster than the checklist alone.
