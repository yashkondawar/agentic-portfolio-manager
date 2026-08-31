"""Offline tests for the ER retrofit's two deterministic (zero-token) tools:

  research/equity_researcher/tools/convert_docs.py
      PDF -> page-anchored markdown + per-page table JSON (step 0.5 CONVERT).

  research/equity_researcher/tools/build_comprehensive_statement.py
      merged facts -> 3-level line-item tree per statement x period
      (step 3 COMPUTE).

Neither tools/ directory is an importable package under src/, so both
modules are loaded directly by file path (mirroring
tests/test_research/test_gen_sector_packs.py's pattern for scripts/
gen_sector_packs.py) rather than adding tools/ to sys.path wholesale.

No live ER run exists (no ticker documents in input/ yet) -- these tests
exercise the tools against small, hand-built fixtures instead: a 2-page PDF
built from raw PDF syntax (no reportlab dependency available) with real
extractable text and one pdfplumber-detectable table, and a synthetic
3-level/2-period fact-record set.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ER_TOOLS_DIR = REPO_ROOT / "research" / "equity_researcher" / "tools"
CONVERT_DOCS_PATH = ER_TOOLS_DIR / "convert_docs.py"
BUILD_STATEMENT_PATH = ER_TOOLS_DIR / "build_comprehensive_statement.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def convert_docs():
    return _load_module("convert_docs", CONVERT_DOCS_PATH)


@pytest.fixture(scope="module")
def build_comprehensive_statement():
    return _load_module("build_comprehensive_statement", BUILD_STATEMENT_PATH)


# --- fixture PDF construction -----------------------------------------------
# Hand-built minimal PDF (no reportlab/fpdf available in this venv): valid
# PDF 1.4 syntax, Helvetica base font, two pages. Page 1 has real text plus a
# ruled 2-row x 2-col grid that pdfplumber's line-based table detector picks
# up as a table; page 2 is text-only (exercises the "not every page has a
# table" path).

def _make_minimal_pdf(pages_content: list[bytes]) -> bytes:
    n_pages = len(pages_content)
    page_obj_start = 4
    content_obj_start = page_obj_start + n_pages
    page_ids = list(range(page_obj_start, page_obj_start + n_pages))
    content_ids = list(range(content_obj_start, content_obj_start + n_pages))

    objects: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i in range(n_pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_ids[i]} 0 R >>".encode()
        )
    for content in pages_content:
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(out)
    n_obj = len(objects) + 1
    out += f"xref\n0 {n_obj}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n" + f"<< /Size {n_obj} /Root 1 0 R >>\n".encode()
    out += b"startxref\n" + f"{xref_offset}\n".encode() + b"%%EOF"
    return bytes(out)


def _fixture_pdf_bytes() -> bytes:
    page1 = (
        b"BT /F1 12 Tf 20 270 Td (Fixture Company Ltd - Annual Report FY2024) Tj ET\n"
        b"BT /F1 10 Tf 20 245 Td (Note 5: Borrowings by instrument and maturity) Tj ET\n"
        b"20 150 m 380 150 l S\n20 200 m 380 200 l S\n"
        b"20 150 m 20 200 l S\n200 150 m 200 200 l S\n380 150 m 380 200 l S\n"
        b"BT /F1 9 Tf 25 180 Td (Instrument) Tj ET\n"
        b"BT /F1 9 Tf 210 180 Td (Amount INR cr) Tj ET\n"
        b"BT /F1 9 Tf 25 160 Td (Term loan 1-3y) Tj ET\n"
        b"BT /F1 9 Tf 210 160 Td (120.0) Tj ET\n"
    )
    page2 = (
        b"BT /F1 12 Tf 20 270 Td (Fixture Company Ltd - Page 2) Tj ET\n"
        b"BT /F1 10 Tf 20 245 Td (Note 6: Revenue by segment) Tj ET\n"
        b"BT /F1 9 Tf 20 210 Td (Segment A revenue for FY2024 was 600.0 INR cr.) Tj ET\n"
    )
    return _make_minimal_pdf([page1, page2])


@pytest.fixture
def er_ticker_dir(tmp_path):
    """Builds input/FIXT/ar_fixture.pdf under a throwaway ER-shaped base dir
    and returns (base_dir, ticker)."""
    base = tmp_path / "er_base"
    input_dir = base / "input" / "FIXT"
    input_dir.mkdir(parents=True)
    (input_dir / "ar_fixture.pdf").write_bytes(_fixture_pdf_bytes())
    return base, "FIXT"


# --- convert_docs.py ---------------------------------------------------------


def test_convert_docs_produces_page_anchored_markdown(convert_docs, er_ticker_dir):
    base, ticker = er_ticker_dir
    summary = convert_docs.convert_ticker(ticker, base_dir=base)

    assert summary["converted"] == [{"docid": "ar_fixture", "pages": 2, "tables": 1}]
    assert summary["skipped_cached"] == []

    md_path = base / "workspace" / ticker / "cache" / "markdown" / "ar_fixture.md"
    assert md_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "<!-- page 1 -->" in text
    assert "<!-- page 2 -->" in text
    assert text.index("<!-- page 1 -->") < text.index("<!-- page 2 -->")
    assert "Fixture Company Ltd - Annual Report FY2024" in text
    assert "Note 5: Borrowings by instrument and maturity" in text
    assert "Segment A revenue for FY2024 was 600.0 INR cr." in text


def test_convert_docs_extracts_at_least_one_table_with_page_metadata(convert_docs, er_ticker_dir):
    base, ticker = er_ticker_dir
    convert_docs.convert_ticker(ticker, base_dir=base)

    tables_dir = base / "workspace" / ticker / "cache" / "tables"
    table_files = sorted(tables_dir.glob("*.json"))
    assert len(table_files) >= 1

    payload = json.loads(table_files[0].read_text(encoding="utf-8"))
    assert payload["page"] == 1
    assert payload["table_index"] == 1
    assert payload["doc"] == "ar_fixture.pdf"
    assert payload["bbox"] is not None and len(payload["bbox"]) == 4
    assert isinstance(payload["rows"], list) and len(payload["rows"]) >= 1
    flat = " ".join(str(c) for row in payload["rows"] for c in row if c)
    assert "Instrument" in flat or "Term loan" in flat


def test_convert_docs_is_idempotent_on_unchanged_source(convert_docs, er_ticker_dir):
    base, ticker = er_ticker_dir
    first = convert_docs.convert_ticker(ticker, base_dir=base)
    assert first["converted"], "first run should convert the fixture PDF"

    second = convert_docs.convert_ticker(ticker, base_dir=base)
    assert second["converted"] == []
    assert second["skipped_cached"] == ["ar_fixture"]


def test_convert_docs_force_reconverts_even_when_cached(convert_docs, er_ticker_dir):
    base, ticker = er_ticker_dir
    convert_docs.convert_ticker(ticker, base_dir=base)

    forced = convert_docs.convert_ticker(ticker, base_dir=base, force=True)
    assert forced["converted"] == [{"docid": "ar_fixture", "pages": 2, "tables": 1}]


def test_convert_docs_raises_on_missing_input_dir(convert_docs, tmp_path):
    with pytest.raises(FileNotFoundError):
        convert_docs.convert_ticker("NOPE", base_dir=tmp_path / "er_base")


def test_convert_docs_leaves_source_pdf_untouched(convert_docs, er_ticker_dir):
    base, ticker = er_ticker_dir
    pdf_path = base / "input" / ticker / "ar_fixture.pdf"
    original_bytes = pdf_path.read_bytes()

    convert_docs.convert_ticker(ticker, base_dir=base)

    assert pdf_path.read_bytes() == original_bytes


# --- build_comprehensive_statement.py ---------------------------------------

THREE_LEVEL_TWO_PERIOD_FACTS = [
    {"id": "F-REV-FY2024-001", "metric": "revenue_from_operations", "label": "Revenue from operations",
     "value": 1000.0, "unit": "INR_cr", "period": "FY2024", "period_type": "FY", "basis": "consolidated",
     "level": 1, "parent": None, "source": {"src_id": "SRC-001"}, "method": "reported", "confidence": "high"},
    {"id": "F-REV-FY2025-001", "metric": "revenue_from_operations", "label": "Revenue from operations",
     "value": 1200.0, "unit": "INR_cr", "period": "FY2025", "period_type": "FY", "basis": "consolidated",
     "level": 1, "parent": None, "source": {"src_id": "SRC-002"}, "method": "reported", "confidence": "high"},
    {"id": "F-BORROW-FY2024-001", "metric": "borrowings_noncurrent", "label": "Borrowings (non-current)",
     "value": 300.0, "unit": "INR_cr", "period": "FY2024", "period_type": "FY", "basis": "consolidated",
     "level": 1, "parent": None, "source": {"src_id": "SRC-001"}, "method": "reported", "confidence": "high"},
    {"id": "F-BORROW-FY2025-001", "metric": "borrowings_noncurrent", "label": "Borrowings (non-current)",
     "value": 340.0, "unit": "INR_cr", "period": "FY2025", "period_type": "FY", "basis": "consolidated",
     "level": 1, "parent": None, "source": {"src_id": "SRC-002"}, "method": "reported", "confidence": "high"},
    {"id": "F-BORROWINST-FY2024-001", "metric": "borrowings_term_loan", "label": "Term loan",
     "value": 200.0, "unit": "INR_cr", "period": "FY2024", "period_type": "FY", "basis": "consolidated",
     "level": 2, "parent": "F-BORROW-FY2024-001", "source": {"src_id": "SRC-001"}, "method": "reported",
     "confidence": "high"},
    {"id": "F-BORROWINST-FY2025-001", "metric": "borrowings_term_loan", "label": "Term loan",
     "value": 210.0, "unit": "INR_cr", "period": "FY2025", "period_type": "FY", "basis": "consolidated",
     "level": 2, "parent": "F-BORROW-FY2025-001", "source": {"src_id": "SRC-002"}, "method": "reported",
     "confidence": "high"},
    {"id": "F-BORROWMAT-FY2024-001", "metric": "borrowings_term_loan_maturity_1_3y",
     "label": "Term loan maturing 1-3y", "value": 120.0, "unit": "INR_cr", "period": "FY2024",
     "period_type": "FY", "basis": "consolidated", "level": 3, "parent": "F-BORROWINST-FY2024-001",
     "source": {"src_id": "SRC-001"}, "method": "reported", "confidence": "high"},
    # Level-3 note present only in FY2024 -- FY2025 should render gracefully missing, not crash.
    {"id": "F-CFO-FY2024-001", "metric": "cfo", "label": "Cash flow from operations", "value": 150.0,
     "unit": "INR_cr", "period": "FY2024", "period_type": "FY", "basis": "consolidated", "level": 1,
     "parent": None, "source": {"src_id": "SRC-001"}, "method": "reported", "confidence": "high"},
]


@pytest.fixture
def facts_file(tmp_path):
    p = tmp_path / "financials.json"
    p.write_text(json.dumps({"facts": THREE_LEVEL_TWO_PERIOD_FACTS}), encoding="utf-8")
    return p


def test_build_trees_produces_three_level_tree_shape(build_comprehensive_statement, facts_file):
    facts = build_comprehensive_statement.load_facts(facts_file)
    trees = build_comprehensive_statement.build_trees(facts)

    borrowings = trees["balance_sheet"]["borrowings_noncurrent"]
    assert borrowings.level == 1
    assert set(borrowings.values.keys()) == {"FY2024", "FY2025"}

    term_loan = borrowings.children["borrowings_term_loan"]
    assert term_loan.level == 2

    maturity = term_loan.children["borrowings_term_loan_maturity_1_3y"]
    assert maturity.level == 3
    assert maturity.values["FY2024"]["value"] == 120.0
    assert "FY2025" not in maturity.values  # graceful missing-level-3 for that period


def test_build_trees_classifies_statements_correctly(build_comprehensive_statement, facts_file):
    facts = build_comprehensive_statement.load_facts(facts_file)
    trees = build_comprehensive_statement.build_trees(facts)

    assert "revenue_from_operations" in trees["income_statement"]
    assert "borrowings_noncurrent" in trees["balance_sheet"]
    assert "cfo" in trees["cash_flow"]


def test_build_trees_two_periods_on_root_node(build_comprehensive_statement, facts_file):
    facts = build_comprehensive_statement.load_facts(facts_file)
    trees = build_comprehensive_statement.build_trees(facts)

    revenue = trees["income_statement"]["revenue_from_operations"]
    assert revenue.values["FY2024"]["value"] == 1000.0
    assert revenue.values["FY2025"]["value"] == 1200.0
    assert revenue.values["FY2024"]["fact_id"] == "F-REV-FY2024-001"


def test_build_comprehensive_statement_cli_writes_json_and_md(build_comprehensive_statement, facts_file, tmp_path):
    out_json = tmp_path / "state" / "comprehensive_statement.json"
    out_md = tmp_path / "state" / "comprehensive_statement.md"

    import sys
    argv_backup = sys.argv
    sys.argv = ["build_comprehensive_statement.py", str(facts_file),
                "--out-json", str(out_json), "--out-md", str(out_md)]
    try:
        build_comprehensive_statement.main()
    finally:
        sys.argv = argv_backup

    assert out_json.exists()
    assert out_md.exists()

    tree_json = json.loads(out_json.read_text(encoding="utf-8"))
    assert "borrowings_noncurrent" in tree_json["balance_sheet"]
    term_loan_node = tree_json["balance_sheet"]["borrowings_noncurrent"]["children"][0]
    assert term_loan_node["level"] == 2
    maturity_node = term_loan_node["children"][0]
    assert maturity_node["level"] == 3

    md_text = out_md.read_text(encoding="utf-8")
    assert "Borrowings (non-current)" in md_text
    assert "Term loan maturing 1-3y" in md_text
    assert "FY2024" in md_text and "FY2025" in md_text


def test_build_comprehensive_statement_handles_empty_facts_gracefully(build_comprehensive_statement, tmp_path):
    empty_facts = tmp_path / "empty.json"
    empty_facts.write_text(json.dumps({"facts": []}), encoding="utf-8")
    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"

    import sys
    argv_backup = sys.argv
    sys.argv = ["build_comprehensive_statement.py", str(empty_facts),
                "--out-json", str(out_json), "--out-md", str(out_md)]
    try:
        build_comprehensive_statement.main()
    finally:
        sys.argv = argv_backup

    tree_json = json.loads(out_json.read_text(encoding="utf-8"))
    assert tree_json == {"income_statement": {}, "balance_sheet": {}, "cash_flow": {}, "unclassified": {}}
    assert "No periods found" in out_md.read_text(encoding="utf-8")


def test_classify_root_handles_unknown_metric_as_unclassified(build_comprehensive_statement):
    assert build_comprehensive_statement.classify_root("some_bespoke_kpi") == "unclassified"
    assert build_comprehensive_statement.classify_root("revenue_from_operations") == "income_statement"
    assert build_comprehensive_statement.classify_root("trade_receivables") == "balance_sheet"
    assert build_comprehensive_statement.classify_root("cfo") == "cash_flow"
