/**
 * build_reports.js — FORMAT stage runner (deterministic, zero LLM tokens).
 *
 * Renders one styled institutional-research .docx per note, using the shared
 * design system in reportStyle.js. It consumes CONTENT MODULES — plain data
 * objects the report-writer agent extracts from each markdown note per the
 * equity-research-formatter skill (SKILL.md). This runner performs no parsing
 * or judgment: content in, .docx out.
 *
 * Layout convention (matches the rest of tools/):
 *   input :  workspace/<TICKER>/report/formatted/*.content.js
 *              each module: module.exports = { masthead:[..], title:[..],
 *                                              blocks:[..], footer:"..",
 *                                              outfile:"Name.docx" }
 *            (outfile optional; defaults to the content file's basename)
 *   output:  workspace/<TICKER>/report/<outfile>.docx
 *
 * Usage:
 *   node tools/report_formatter/build_reports.js <TICKER>
 *   node tools/report_formatter/build_reports.js <TICKER> --repo "D:/path/to/repo"
 *
 * The `docx` dependency is installed locally in this folder (npm install here),
 * so the runner resolves it from tools/report_formatter/node_modules and never
 * depends on a global install.
 */
const fs = require("fs");
const path = require("path");
const { Document } = require("docx");
const style = require("./reportStyle.js");

function repoRoot(argv) {
  const i = argv.indexOf("--repo");
  if (i !== -1 && argv[i + 1]) return path.resolve(argv[i + 1]);
  // tools/report_formatter/ -> repo root is two levels up
  return path.resolve(__dirname, "..", "..");
}

function assemble(content) {
  const { masthead, title, blocks, footer } = content;
  const mastheadEls = style.masthead(masthead[0], masthead[1]);
  const titleEls = style.titleBlock(title[0], title[1], title[2]);
  const bodyEls = style.renderBlocks(blocks);
  return new Document({
    numbering: style.NUMBERING,
    styles: { default: { document: { run: { font: "Calibri", size: 21, color: "1A1A1A" } } } },
    sections: [{
      properties: { page: { margin: { top: 1000, bottom: 1000, left: 1000, right: 1000 } } },
      footers: { default: style.pageNumberFooter(footer) },
      children: [...mastheadEls, ...titleEls, ...bodyEls],
    }],
  });
}

async function main() {
  const ticker = process.argv[2];
  if (!ticker || ticker.startsWith("--")) {
    console.error("usage: node build_reports.js <TICKER> [--repo <path>]");
    process.exit(2);
  }
  const repo = repoRoot(process.argv);
  const reportDir = path.join(repo, "workspace", ticker, "report");
  const inDir = path.join(reportDir, "formatted");
  if (!fs.existsSync(inDir)) {
    console.error(`no content directory: ${inDir}`);
    console.error("expected report-writer to emit *.content.js there (see equity-research-formatter skill).");
    process.exit(1);
  }
  const contentFiles = fs.readdirSync(inDir).filter((f) => f.endsWith(".content.js")).sort();
  if (contentFiles.length === 0) {
    console.error(`no *.content.js modules found in ${inDir}`);
    process.exit(1);
  }

  let ok = 0;
  for (const f of contentFiles) {
    const modPath = path.join(inDir, f);
    let content;
    try {
      content = require(modPath);
    } catch (e) {
      console.error(`SKIP ${f}: require failed — ${e.message}`);
      continue;
    }
    const outfile = content.outfile || f.replace(/\.content\.js$/, ".docx");
    try {
      const doc = assemble(content);
      const buf = await style.Packer.toBuffer(doc);
      const outPath = path.join(reportDir, outfile);
      fs.writeFileSync(outPath, buf);
      console.log(`OK  ${f} -> ${path.relative(repo, outPath).replace(/\\/g, "/")}  (${buf.length} bytes)`);
      ok++;
    } catch (e) {
      console.error(`FAIL ${f}: ${e.stack || e}`);
    }
  }
  console.log(`built ${ok}/${contentFiles.length} report(s)`);
  if (ok !== contentFiles.length) process.exit(1);
}

main().catch((e) => { console.error("BUILD FAILED:", e.stack || e); process.exit(1); });
