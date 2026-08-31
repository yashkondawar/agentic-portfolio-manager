const fs = require("fs");
const path = require("path");
const { Document } = require("docx");
const style = require("./reportStyle.js");

const OUT = "/mnt/user-data/outputs";
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

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

async function run() {
  // This worked example ships with the NALCO content used to build this
  // skill. To use it on a new company: copy the three example_*_content.js
  // files, replace their `blocks` arrays with content extracted from your
  // own source markdown (see references/report_models.md for the field
  // list per archetype), and update the filenames below.
  const jobs = [
    ["Example_Equity_Research_Report.docx", require("./example_er_content.js")],
    ["Example_Forensic_Dossier_Report.docx", require("./example_forensic_content.js")],
    ["Example_BuySide_EPSBridge_Note.docx", require("./example_buyside_content.js")],
  ];
  for (const [filename, content] of jobs) {
    const doc = assemble(content);
    const buf = await style.Packer.toBuffer(doc);
    const outPath = path.join(OUT, filename);
    fs.writeFileSync(outPath, buf);
    console.log("Wrote", outPath, buf.length, "bytes");
  }
}

run().catch((e) => { console.error("BUILD FAILED:", e.stack || e); process.exit(1); });
