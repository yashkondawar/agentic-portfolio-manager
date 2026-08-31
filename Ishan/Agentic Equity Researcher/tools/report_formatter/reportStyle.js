/**
 * reportStyle.js
 * Shared visual design system for institutional-style research report .docx
 * generation. Three archetypes use this module: ER (sell-side), Forensic
 * (dossier / fact registry), Buy-side (thesis / EPS-bridge).
 *
 * Built on docx-js. Respects the docx skill's gotchas:
 *  - table shading uses ShadingType.CLEAR (SOLID renders black)
 *  - tables set BOTH columnWidths (table) and width (each cell), in DXA
 *  - bullets use a numbering config, never literal "•"
 *  - no "\n" inside TextRuns — every line is its own Paragraph
 *  - horizontal rules are paragraph borders, not 1-row tables
 */
const {
  Document, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, LevelFormat,
  Header, Footer, PageNumber, VerticalAlign, HeadingLevel,
} = require("docx");

// ---------------------------------------------------------------- tokens --
const NAVY = "1B2A4A", SLATE = "44546A", GOLD = "B08D57";
const RED = "8B1E1E", AMBER = "C4711B", GREEN = "2E6E3E";
const LGRAY = "F2F2F2", MGRAY = "D9D9D9", WHITE = "FFFFFF", INK = "1A1A1A";

const FONT_HEAD = "Georgia";
const FONT_BODY = "Calibri";

const RATING_COLOR = {
  BUY: GREEN, ADD: GREEN, ACCUMULATE: GREEN,
  HOLD: AMBER, REDUCE: AMBER,
  SELL: RED, AVOID: RED,
};
const STATUS_COLOR = {
  HIGH: RED, "MEDIUM-HIGH": RED, CONFIRMED: RED, OPEN: RED, FAIL: RED, LOW: GREEN,
  MEDIUM: AMBER, "LOW-MED": AMBER, "MEDIUM-LOW": AMBER, "PASS (THIN)": AMBER,
  PASS: GREEN, DISMISSED: GREEN, CLEAN: GREEN, DISCLOSED: AMBER,
  NA: "808080", "N/A": "808080",
};

const PAGE_WIDTH = 11906; // A4, twips
const MARGIN = 1000;      // ~1.76cm
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2; // 9906

const NUMBERING = {
  config: [{
    reference: "bullets",
    levels: [{
      level: 0, format: LevelFormat.BULLET, text: "\u2022",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 420, hanging: 260 } } },
    }],
  }],
};

// --------------------------------------------------------------- helpers --
const hr = (color = MGRAY, size = 6, after = 160) => new Paragraph({
  spacing: { after },
  border: { bottom: { style: BorderStyle.SINGLE, size, color, space: 4 } },
  children: [],
});

function run(text, { bold, italics, size = 21, color = INK, font = FONT_BODY } = {}) {
  return new TextRun({ text, bold, italics, size, color, font });
}

function masthead(firmLabel, reportLabel) {
  return [
    new Paragraph({
      spacing: { after: 40 },
      children: [
        run(firmLabel.toUpperCase(), { bold: true, size: 18, color: NAVY, font: FONT_HEAD }),
        run("    |    " + reportLabel.toUpperCase(), { size: 17, color: SLATE }),
      ],
    }),
    hr(NAVY, 18, 220),
  ];
}

function titleBlock(company, tickerLine, subtitle) {
  return [
    new Paragraph({
      spacing: { after: 20 },
      children: [run(company, { bold: true, size: 40, color: NAVY, font: FONT_HEAD })],
    }),
    new Paragraph({
      spacing: { after: 120 },
      children: [run(tickerLine, { italics: true, size: 19, color: SLATE })],
    }),
    new Paragraph({
      spacing: { after: 240 },
      children: [run(subtitle, { size: 25, color: INK, font: FONT_HEAD })],
    }),
  ];
}

function sectionHeading(text, number) {
  const label = number != null ? `${number}.  ${text}` : text;
  return [
    new Paragraph({
      spacing: { before: 280, after: 40 },
      children: [run(label, { bold: true, size: 25, color: NAVY, font: FONT_HEAD })],
    }),
    hr(MGRAY, 4, 140),
  ];
}

function bodyText(text, { size = 21, italics = false, after = 140, bold = false } = {}) {
  return new Paragraph({
    spacing: { after },
    children: [run(text, { size, italics, bold })],
  });
}

function bullets(items, { size = 21 } = {}) {
  return items.map((text) => new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 70 },
    children: [run(text, { size })],
  }));
}

function subLabel(text) {
  return new Paragraph({
    spacing: { after: 60 },
    children: [run(text, { italics: true, size: 18, color: SLATE })],
  });
}

// ---- cells -----------------------------------------------------------
function cell(text, { bold = false, italics = false, color = INK, size = 19, bg = null,
  align = AlignmentType.LEFT, width, font = FONT_BODY } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    verticalAlign: VerticalAlign.CENTER,
    shading: bg ? { type: ShadingType.CLEAR, color: "auto", fill: bg } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 2, color: MGRAY },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: MGRAY },
      left: { style: BorderStyle.SINGLE, size: 2, color: MGRAY },
      right: { style: BorderStyle.SINGLE, size: 2, color: MGRAY },
    },
    children: [new Paragraph({
      alignment: align,
      children: [run(String(text), { bold, italics, color, size, font })],
    })],
  });
}

function widths(n, weights) {
  const w = weights || Array(n).fill(1);
  const total = w.reduce((a, b) => a + b, 0);
  return w.map((x) => Math.floor((x / total) * CONTENT_WIDTH));
}

/** Data table with a navy header row, zebra body, optional colorized status column. */
function dataTable(headers, rows, { colAligns, colorizeCol, colWeights, size = 19 } = {}) {
  const n = headers.length;
  const colW = widths(n, colWeights);
  const aligns = colAligns || ["left", ...Array(n - 1).fill("center")];
  const A = { left: AlignmentType.LEFT, center: AlignmentType.CENTER, right: AlignmentType.RIGHT };

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, j) => cell(h, {
      bold: true, color: WHITE, bg: NAVY, size, align: AlignmentType.CENTER, width: colW[j],
    })),
  });

  const bodyRows = rows.map((r, i) => {
    const band = i % 2 === 1 ? LGRAY : WHITE;
    return new TableRow({
      children: r.map((val, j) => {
        let color = INK, bold = false, bg = band;
        if (colorizeCol != null && j === colorizeCol) {
          const c = STATUS_COLOR[String(val).trim().toUpperCase()];
          if (c) { color = c; bold = true; }
        }
        return cell(val, { color, bold, bg, size, align: A[aligns[j]], width: colW[j] });
      }),
    });
  });

  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: colW,
    rows: [headerRow, ...bodyRows],
  });
}

/** Two-row label/value strip; fields[0] is colored as the rating/verdict. */
function tombstone(fields) {
  const n = fields.length;
  const colW = widths(n);
  const labelRow = new TableRow({
    children: fields.map(([label], j) => cell(label, {
      bold: true, color: WHITE, bg: SLATE, size: 16, align: AlignmentType.CENTER, width: colW[j],
    })),
  });
  const valueRow = new TableRow({
    children: fields.map(([, value], j) => {
      let bg = LGRAY, color = INK;
      if (j === 0) {
        const key = String(value).split(/[\s(]/)[0].toUpperCase();
        bg = RATING_COLOR[key] || NAVY; color = WHITE;
      }
      return cell(value, { bold: true, color, bg, size: 21, align: AlignmentType.CENTER, width: colW[j] });
    }),
  });
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: colW,
    rows: [labelRow, valueRow],
  });
}

/** Single-cell shaded callout with a left accent border (e.g. "Bottom line", "Invalidation"). */
function callout(title, text, color = NAVY) {
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: [CONTENT_WIDTH],
    rows: [new TableRow({
      children: [new TableCell({
        width: { size: CONTENT_WIDTH, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, color: "auto", fill: LGRAY },
        margins: { top: 140, bottom: 140, left: 220, right: 220 },
        borders: {
          left: { style: BorderStyle.SINGLE, size: 24, color },
          top: { style: BorderStyle.SINGLE, size: 2, color: MGRAY },
          bottom: { style: BorderStyle.SINGLE, size: 2, color: MGRAY },
          right: { style: BorderStyle.SINGLE, size: 2, color: MGRAY },
        },
        children: [
          new Paragraph({ spacing: { after: 60 }, children: [run(title.toUpperCase(), { bold: true, size: 19, color, font: FONT_HEAD })] }),
          new Paragraph({ children: [run(text, { size: 20 })] }),
        ],
      })],
    })],
  });
}

const spacer = (h = 100) => new Paragraph({ spacing: { after: h }, children: [] });

// -------------------------------------------------------- block renderer --
/**
 * Data-driven renderer: turns an array of block descriptors into docx-js
 * elements. Lets a report be authored as plain data instead of hand-called
 * builder functions — this is the piece a future run should reuse most.
 *
 * Block types: heading, text, bullets, table, tombstone, callout, spacer, sub
 */
function renderBlocks(blocks) {
  const out = [];
  for (const b of blocks) {
    switch (b.type) {
      case "heading": out.push(...sectionHeading(b.text, b.number)); break;
      case "text": out.push(bodyText(b.text, b.opts || {})); break;
      case "sub": out.push(subLabel(b.text)); break;
      case "bullets": out.push(...bullets(b.items, b.opts || {})); break;
      case "table":
        out.push(dataTable(b.headers, b.rows, b.opts || {}));
        out.push(spacer(120));
        break;
      case "tombstone": out.push(tombstone(b.fields)); out.push(spacer(160)); break;
      case "callout": out.push(callout(b.title, b.text, b.color)); out.push(spacer(120)); break;
      case "spacer": out.push(spacer(b.h)); break;
      default: throw new Error("Unknown block type: " + b.type);
    }
  }
  return out;
}

function pageNumberFooter(text) {
  return new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        run(text + "   |   Page ", { size: 14, italics: true, color: SLATE }),
        new TextRun({ children: [PageNumber.CURRENT], size: 14, italics: true, color: SLATE, font: FONT_BODY }),
        run(" of ", { size: 14, italics: true, color: SLATE }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 14, italics: true, color: SLATE, font: FONT_BODY }),
      ],
    })],
  });
}

function buildDocument(blocks, footerText) {
  return new Document({
    numbering: NUMBERING,
    styles: { default: { document: { run: { font: FONT_BODY, size: 21, color: INK } } } },
    sections: [{
      properties: { page: { margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
      footers: { default: pageNumberFooter(footerText) },
      children: renderBlocks(blocks),
    }],
  });
}

module.exports = {
  NAVY, SLATE, GOLD, RED, AMBER, GREEN, LGRAY, MGRAY, WHITE, INK,
  masthead, titleBlock, pageNumberFooter, NUMBERING,
  renderBlocks, buildDocument, Packer: require("docx").Packer,
};
