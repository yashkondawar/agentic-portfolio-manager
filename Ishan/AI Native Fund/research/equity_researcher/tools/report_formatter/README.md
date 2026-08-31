# tools/report_formatter — FORMAT stage engine (step 9)

Deterministic docx-js renderer for the Agentic Equity Researcher pipeline. Turns the
report-writer's per-note **content modules** into institutional-style `.docx` (navy/gold
palette, serif headings, styled tables, rating tombstones, color-coded status columns).

This is the zero-judgment half of the FORMAT stage. The judgment half — reading each
markdown note and extracting it into a content module — belongs to the report-writer agent
and is governed by `.claude/skills/equity-research-formatter/SKILL.md`.

## Files

- `reportStyle.js` — the shared design system (verbatim copy of the skill's engine). Exports
  `masthead`, `titleBlock`, `renderBlocks`, `pageNumberFooter`, `Packer`, palette constants.
  **Do not fork the palette/tokens here and in the skill** — keep them identical so the
  skill's example content and this engine stay in sync.
- `build_reports.js` — CLI runner. Scans `workspace/<TICKER>/report/formatted/*.content.js`
  and writes one `.docx` per module into `workspace/<TICKER>/report/`.
- `package.json` + `node_modules/` — local `docx` dependency (installed once; not global).

## Content module contract

Each `workspace/<TICKER>/report/formatted/<name>.content.js` does:

```js
module.exports = {
  masthead: [firmLabel, reportLabel],
  title:    [company, tickerLine, subtitle],
  blocks:   [ /* ordered typed blocks: heading|text|sub|bullets|table|tombstone|callout|spacer */ ],
  footer:   "footer text with page numbers appended by the engine",
  outfile:  "NALCO_ER.docx"   // optional; defaults to <name>.docx
};
```

Block types and options are documented in the skill's SKILL.md (§ Block types).

## Usage

```bash
# 1. report-writer emits workspace/NALCO/report/formatted/*.content.js
# 2. render every module to .docx:
node tools/report_formatter/build_reports.js NALCO
# optional: node tools/report_formatter/build_reports.js NALCO --repo "D:/path/to/repo"
```

## Verify (Windows / Word)

No LibreOffice in this environment — export to PDF with Word COM, then view the PDF:

```powershell
$w = New-Object -ComObject Word.Application
$d = $w.Documents.Open('<abs path>\NALCO_ER.docx')
$d.SaveAs([ref]'<abs path>\NALCO_ER.pdf', [ref]17)   # 17 = wdFormatPDF
$d.Close(); $w.Quit()
```

Check at least one wide multi-column-table page and one text-heavy 2-column-table page per
document — column-width ratios go wrong there first.
