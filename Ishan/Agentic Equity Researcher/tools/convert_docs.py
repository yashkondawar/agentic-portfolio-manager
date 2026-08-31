"""Step 0.5 CONVERT — deterministic, zero-token PDF preprocessing.

For every PDF in input/<TICKER>/, produce two DERIVED artifact sets so
extractor subagents (haiku tier) read structured text/tables instead of raw
PDF layout:

  workspace/<TICKER>/cache/markdown/<docid>.md
      markitdown conversion, page-by-page (via pypdf split — markitdown loses
      page boundaries when fed a whole multi-page PDF; splitting first and
      converting each single-page PDF separately guarantees a page anchor per
      chunk), stitched back together with `<!-- page N -->` anchor comments.

  workspace/<TICKER>/cache/tables/<docid>_p<N>_t<K>.json
      pdfplumber per-page table extraction: rows as lists of cell strings,
      plus page number + bbox in metadata. One file per (page, table) pair.

IMPORTANT: PDFs in input/<TICKER>/ are never modified or moved — the
markdown/tables are derived, cached artifacts. The citation-verification wave
(prompts/50) still opens the original PDF at the cited page for grounding;
these caches are a reading aid for extraction, not a replacement source.

Idempotent: skips a document if its cache is newer than the source PDF
(mtime check on the markdown file only — tables regenerate alongside it).

Usage:
  python tools/convert_docs.py <TICKER>
  python tools/convert_docs.py <TICKER> --force     # ignore cache freshness
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]  # research/equity_researcher/


def _docid(pdf_path: Path) -> str:
    return pdf_path.stem


def _split_pages(pdf_path: Path):
    """Yield (page_number_1_indexed, single_page_pdf_bytes) for each page,
    using pypdf so markitdown can be run per-page (guarantees an anchor)."""
    from pypdf import PdfReader, PdfWriter
    import io

    reader = PdfReader(str(pdf_path))
    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        yield i, buf


def convert_markdown(pdf_path: Path, out_path: Path) -> int:
    """Convert one PDF to markdown with per-page anchor comments. Returns the
    page count converted. Falls back to whole-document conversion (single
    implicit page 1 anchor) if the PDF cannot be split (e.g. encrypted)."""
    from markitdown import MarkItDown

    md = MarkItDown()
    chunks = []
    page_count = 0
    try:
        for page_no, page_buf in _split_pages(pdf_path):
            try:
                result = md.convert(page_buf, file_extension=".pdf")
                text = (result.markdown or "").strip()
            except Exception as e:  # noqa: BLE001 - degrade, never crash the run
                text = f"*[unreadable page — markitdown error: {e}]*"
            chunks.append(f"<!-- page {page_no} -->\n\n{text}")
            page_count += 1
    except Exception as e:  # noqa: BLE001 - split failed entirely; whole-doc fallback
        print(f"WARN {pdf_path.name}: page split failed ({e}); converting whole document", file=sys.stderr)
        result = md.convert(str(pdf_path))
        chunks = [f"<!-- page 1 -->\n\n{(result.markdown or '').strip()}"]
        page_count = 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    return page_count


def extract_tables(pdf_path: Path, out_dir: Path) -> int:
    """Extract per-page tables with pdfplumber; one JSON file per
    (page, table) pair: {"page": N, "table_index": K, "bbox": [...], "rows": [[...]]}.
    Returns the number of table files written."""
    import pdfplumber

    out_dir.mkdir(parents=True, exist_ok=True)
    docid = _docid(pdf_path)
    written = 0
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                try:
                    tables = page.find_tables()
                except Exception as e:  # noqa: BLE001
                    print(f"WARN {pdf_path.name} p{page_no}: table scan failed ({e})", file=sys.stderr)
                    continue
                for t_idx, table in enumerate(tables, start=1):
                    try:
                        rows = table.extract()
                    except Exception as e:  # noqa: BLE001
                        print(f"WARN {pdf_path.name} p{page_no} t{t_idx}: extract failed ({e})", file=sys.stderr)
                        continue
                    payload = {
                        "doc": pdf_path.name,
                        "page": page_no,
                        "table_index": t_idx,
                        "bbox": list(table.bbox) if table.bbox else None,
                        "rows": rows,
                    }
                    out_file = out_dir / f"{docid}_p{page_no}_t{t_idx}.json"
                    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                    written += 1
    except Exception as e:  # noqa: BLE001 - never crash the whole run on one bad PDF
        print(f"WARN {pdf_path.name}: table extraction failed entirely ({e})", file=sys.stderr)
    return written


def is_cache_fresh(pdf_path: Path, md_out: Path) -> bool:
    return md_out.exists() and md_out.stat().st_mtime >= pdf_path.stat().st_mtime


def convert_ticker(ticker: str, *, force: bool = False, base_dir: Path | None = None) -> dict:
    base = base_dir or REPO_ROOT
    input_dir = base / "input" / ticker
    md_dir = base / "workspace" / ticker / "cache" / "markdown"
    tables_dir = base / "workspace" / ticker / "cache" / "tables"

    if not input_dir.exists():
        raise FileNotFoundError(f"no input directory for {ticker}: {input_dir}")

    pdfs = sorted(input_dir.glob("*.pdf"))
    summary = {"ticker": ticker, "converted": [], "skipped_cached": [], "tables_written": 0}

    for pdf_path in pdfs:
        docid = _docid(pdf_path)
        md_out = md_dir / f"{docid}.md"

        if not force and is_cache_fresh(pdf_path, md_out):
            summary["skipped_cached"].append(docid)
            continue

        page_count = convert_markdown(pdf_path, md_out)
        n_tables = extract_tables(pdf_path, tables_dir)
        summary["converted"].append({"docid": docid, "pages": page_count, "tables": n_tables})
        summary["tables_written"] += n_tables

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--force", action="store_true", help="ignore cache freshness, reconvert everything")
    a = ap.parse_args()

    summary = convert_ticker(a.ticker, force=a.force)
    print(f"OK: {a.ticker} — converted {len(summary['converted'])} doc(s), "
          f"skipped {len(summary['skipped_cached'])} cached, "
          f"{summary['tables_written']} table file(s) written")
    for c in summary["converted"]:
        print(f"  {c['docid']}: {c['pages']} pages, {c['tables']} tables")
    if summary["skipped_cached"]:
        print(f"  (cached, unchanged): {', '.join(summary['skipped_cached'])}")


if __name__ == "__main__":
    main()
