"""Offline tests for the vendored research/disclosure_fetcher package and
its fund-side integration in afund.research.er_adapter.

Two things are exercised here, both fully offline (no network, no LLM):

1. research/disclosure_fetcher's own classifier/labeller logic (BSE
   announcement title -> DocType + fiscal-period label; ported from that
   package's tests/test_offline.py, adapted to pytest and scoped down to
   the pieces that matter for the fund: doc-type classification, fiscal
   quarter/half/annual labelling, noise filtering, and the key-free
   (enable_web_fallback=False) code path never importing google-genai /
   tavily / ddgs).
2. afund.research.er_adapter.fetch_er_documents' own mapping/renaming
   logic (disclosure_fetcher's downloads/<company>/<doc_type>/ output ->
   research/equity_researcher/input/<TICKER>/ with README-convention
   filenames), using a stubbed disclosure_fetcher.pipeline.run_pipeline so
   no real BSE/Screener call happens here — the live network path is
   covered separately (see docs/RUNBOOK.md or the KPITTECH live-run note
   in the disclosure-fetcher integration commit).

research/disclosure_fetcher/tests/test_offline.py is the canonical
upstream-style integration test for the vendored package itself (run
directly with `.venv\\Scripts\\python research/disclosure_fetcher/tests/test_offline.py`
since it isn't part of the fund's pytest collection — it inserts its own
sys.path and mocks bse.BSE at the module level, which would be invasive to
run inside the shared fund test session). This file instead unit-tests the
same underlying logic through pytest, plus the fund-specific mapping layer
that file doesn't cover at all.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

DISCLOSURE_FETCHER_DIR = Path(__file__).resolve().parents[2] / "research" / "disclosure_fetcher"
if str(DISCLOSURE_FETCHER_DIR) not in sys.path:
    sys.path.insert(0, str(DISCLOSURE_FETCHER_DIR))

from afund.research import er_adapter  # noqa: E402


# --------------------------------------------------------------------------- #
# Part 1: disclosure_fetcher's own classifier/labeller logic (no network,
# no `bse` client calls — pure text-in/DocType-and-label-out functions).
# --------------------------------------------------------------------------- #


@pytest.fixture()
def doc_type_enum():
    from disclosure_fetcher.models import DocType

    return DocType


@pytest.fixture()
def bse_source():
    from disclosure_fetcher.sources import bse_source

    return bse_source


@pytest.fixture()
def utils_mod():
    from disclosure_fetcher import utils

    return utils


def test_classify_quarterly_result(bse_source, doc_type_enum):
    text = "Un-Audited Financial Results for the quarter and year ended 31st March, 2026"
    assert bse_source._classify(text) == doc_type_enum.QUARTERLY_RESULT


def test_classify_earnings_transcript(bse_source, doc_type_enum):
    text = "Transcript of Earnings Call held on 8th August 2025"
    assert bse_source._classify(text) == doc_type_enum.EARNINGS_TRANSCRIPT


def test_classify_investor_presentation(bse_source, doc_type_enum):
    text = "Investor Presentation - Q3 FY26"
    assert bse_source._classify(text) == doc_type_enum.INVESTOR_PRESENTATION


def test_classify_annual_report(bse_source, doc_type_enum):
    text = "Annual Report for the financial year ended 31st March, 2025"
    assert bse_source._classify(text) == doc_type_enum.ANNUAL_REPORT


def test_classify_special_disclosure(bse_source, doc_type_enum):
    text = "CRISIL upgrades credit rating to AA+ / Stable"
    assert bse_source._classify(text) == doc_type_enum.SPECIAL_DISCLOSURE


def test_classify_noise_filtered(bse_source):
    text = "Newspaper Publication of Financial Results for the quarter ended 30th June, 2026"
    assert bse_source._classify(text) is None


def test_period_labelling_quarterly(bse_source, doc_type_enum):
    text = "Un-Audited Financial Results for the quarter and year ended 31st March, 2026"
    label, sort_key = bse_source._period_for(
        doc_type_enum.QUARTERLY_RESULT, text, date(2026, 5, 20)
    )
    assert label == "Q4 FY26"
    assert sort_key == "2026-Q4"


def test_period_labelling_annual(bse_source, doc_type_enum):
    text = "Annual Report for the financial year ended 31st March, 2025"
    label, sort_key = bse_source._period_for(
        doc_type_enum.ANNUAL_REPORT, text, date(2025, 8, 1)
    )
    assert label == "FY25"
    assert sort_key == "2025-FY"


def test_period_labelling_special_disclosure_uses_event_date(bse_source, doc_type_enum):
    label, sort_key = bse_source._period_for(
        doc_type_enum.SPECIAL_DISCLOSURE, "CRISIL upgrades credit rating", date(2026, 2, 14)
    )
    assert label == "Disclosure (2026-02-14)"
    assert sort_key == "2026-02-14"


def test_period_labelling_transcript_infers_nearest_quarter(bse_source, doc_type_enum):
    # No explicit "...ended DD Month YYYY" text -> falls back to the nearest
    # just-completed quarter as of the announcement date.
    label, _sort_key = bse_source._period_for(
        doc_type_enum.EARNINGS_TRANSCRIPT,
        "Transcript of Earnings Call held on 8th August 2025",
        date(2025, 8, 10),
    )
    assert label == "Q1 FY26"


def test_quarter_label_fiscal_year_math(utils_mod):
    # Indian FY (Apr-Mar): a July 2024 date falls in Q2 of FY ending Mar 2025.
    assert utils_mod.quarter_label(date(2024, 7, 15)) == "Q2 FY25"
    assert utils_mod.quarter_label(date(2025, 2, 1)) == "Q4 FY25"


def test_annual_label_fiscal_year_math(utils_mod):
    assert utils_mod.annual_label(date(2024, 7, 15)) == "FY25"
    assert utils_mod.annual_label(date(2025, 2, 1)) == "FY25"


def test_key_free_mode_never_imports_optional_deps():
    """enable_web_fallback=False (the fund's default) must never import
    disclosure_fetcher.llm_agent / disclosure_fetcher.sources.web_fallback
    (the two modules that import google-genai/tavily-python/ddgs at module
    level) — those two optional deps are NOT installed in the fund venv, so
    importing either module would break the primary path.

    Note: `tenacity` itself may already be in sys.modules by the time this
    test runs (it's a real transitive dependency of markitdown, which the
    fund does install for document conversion — see pyproject.toml) — that
    is expected and fine. What must never happen is *disclosure_fetcher's*
    own llm_agent module (which needs tenacity) getting imported when
    enable_web_fallback=False."""
    assert "disclosure_fetcher.llm_agent" not in sys.modules
    assert "disclosure_fetcher.sources.web_fallback" not in sys.modules

    import disclosure_fetcher.pipeline as pipeline_module

    llm = pipeline_module._make_llm_agent(gemini_api_key="", disable_llm=False, enable_web_fallback=False)
    web = pipeline_module._make_web_search_client(tavily_api_key="", enable_web_fallback=False)

    assert isinstance(llm, pipeline_module._NullLLMAgent)
    assert isinstance(web, pipeline_module._NullWebSearchClient)
    assert llm.classify_items("x", []) == {}
    assert web.search("x") == []

    assert "disclosure_fetcher.llm_agent" not in sys.modules
    assert "disclosure_fetcher.sources.web_fallback" not in sys.modules
    for mod_prefix in ("google.genai", "tavily", "ddgs"):
        assert not any(m == mod_prefix or m.startswith(mod_prefix + ".") for m in sys.modules), (
            f"{mod_prefix} must not be imported by the key-free code path"
        )


def test_enable_web_fallback_without_keys_raises():
    import disclosure_fetcher.pipeline as pipeline_module

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        pipeline_module._check_fallback_keys(gemini_api_key="", tavily_api_key="")


def test_enable_web_fallback_with_one_key_passes():
    import disclosure_fetcher.pipeline as pipeline_module

    pipeline_module._check_fallback_keys(gemini_api_key="fake-key", tavily_api_key="")
    pipeline_module._check_fallback_keys(gemini_api_key="", tavily_api_key="fake-key")


# --------------------------------------------------------------------------- #
# Part 2: afund.research.er_adapter's mapping/renaming layer.
# --------------------------------------------------------------------------- #


def test_period_to_er_suffix_quarterly():
    assert er_adapter._period_to_er_suffix("Q4 FY26") == "FY2026Q4"


def test_period_to_er_suffix_annual():
    assert er_adapter._period_to_er_suffix("FY26") == "FY2026"


def test_period_to_er_suffix_unparseable_returns_none():
    assert er_adapter._period_to_er_suffix("Disclosure (2026-02-14)") is None


def test_safe_stem_strips_punctuation_and_truncates():
    stem = er_adapter._safe_stem("CRISIL upgrades: AA+/Stable (rating action)!!", max_len=20)
    assert " " not in stem
    assert len(stem) <= 20
    assert stem  # never empty


def test_company_name_for_ticker_found(conn_with_infy):
    name = er_adapter._company_name_for_ticker(conn_with_infy, "INFY")
    assert name == "Infosys Limited"


def test_company_name_for_ticker_missing_returns_none(conn_with_infy):
    assert er_adapter._company_name_for_ticker(conn_with_infy, "NOTREAL") is None


@pytest.fixture()
def conn_with_infy(tmp_path):
    import sqlite3

    schema_path = Path(__file__).resolve().parents[2] / "src" / "afund" / "db" / "schema.sql"
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT INTO instruments (id, symbol, name, instrument_type, sector, active) "
        "VALUES (1, 'INFY', 'Infosys Limited', 'STOCK', 'Information Technology', 1)"
    )
    connection.commit()
    yield connection
    connection.close()


def _fake_candidate(doc_type_enum, doc_type, period_label, src_path, announced_on=None):
    from disclosure_fetcher.models import DocumentCandidate

    return DocumentCandidate(
        doc_type=doc_type_enum(doc_type),
        company="Test Fictional Ltd",
        period_label=period_label,
        period_sort_key=period_label,
        title=f"{doc_type} {period_label}",
        url="https://example.test/doc.pdf",
        source="BSE",
        announced_on=announced_on,
        heuristic_confidence=0.9,
        accepted=True,
        local_path=str(src_path),
    )


@pytest.fixture()
def _redirect_er_dirs(tmp_path, monkeypatch):
    er_root = tmp_path / "research" / "equity_researcher"
    input_dir = er_root / "input"
    raw_dir = tmp_path / "data" / "raw" / "disclosures"
    monkeypatch.setattr(er_adapter, "ER_INPUT_DIR", input_dir)
    monkeypatch.setattr(er_adapter, "RAW_DISCLOSURES_DIR", raw_dir)
    return {"input_dir": input_dir, "raw_dir": raw_dir}


def test_fetch_er_documents_maps_files_to_er_naming(tmp_path, monkeypatch, _redirect_er_dirs):
    from disclosure_fetcher.models import Company, DocType, PipelineResult

    raw_company_dir = tmp_path / "raw_downloads" / "Test_Fictional_Ltd"
    (raw_company_dir / "annual_reports").mkdir(parents=True)
    (raw_company_dir / "quarterly_results").mkdir(parents=True)
    (raw_company_dir / "transcripts").mkdir(parents=True)
    (raw_company_dir / "presentations").mkdir(parents=True)
    (raw_company_dir / "special_disclosures").mkdir(parents=True)

    ar_src = raw_company_dir / "annual_reports" / "fake-ar.pdf"
    ar_src.write_bytes(b"%PDF-1.4 fake ar")
    q_src = raw_company_dir / "quarterly_results" / "fake-q.pdf"
    q_src.write_bytes(b"%PDF-1.4 fake q")
    tr_src = raw_company_dir / "transcripts" / "fake-tr.pdf"
    tr_src.write_bytes(b"%PDF-1.4 fake tr")
    ppt_src = raw_company_dir / "presentations" / "fake-ppt.pdf"
    ppt_src.write_bytes(b"%PDF-1.4 fake ppt")
    sd_src = raw_company_dir / "special_disclosures" / "CRISIL_rating_action.pdf"
    sd_src.write_bytes(b"%PDF-1.4 fake sd")

    manifest_src = raw_company_dir / "manifest.csv"
    manifest_src.write_text("doc_type,company\nannual_report,Test Fictional Ltd\n", encoding="utf-8")

    company = Company(
        query="Test Fictional Ltd", name="Test Fictional Ltd", bse_scrip_code="999999",
        screener_slug="TESTFIC", screener_url="https://www.screener.in/company/TESTFIC/",
        nse_symbol="TESTFIC",
    )
    result = PipelineResult(
        company=company,
        downloaded=[
            _fake_candidate(DocType, "annual_report", "FY25", ar_src),
            _fake_candidate(DocType, "quarterly_result", "Q4 FY26", q_src),
            _fake_candidate(DocType, "earnings_transcript", "Q1 FY26", tr_src, announced_on=date(2025, 8, 10)),
            _fake_candidate(DocType, "investor_presentation", "Q3 FY26", ppt_src),
            _fake_candidate(DocType, "special_disclosure", "Disclosure (2026-02-14)", sd_src),
        ],
        warnings=[],
        manifest_path=str(manifest_src),
    )

    fake_pipeline_module = SimpleNamespace(run_pipeline=lambda **kwargs: result)
    fake_config_module = SimpleNamespace(FetchTargets=lambda: object())
    monkeypatch.setitem(sys.modules, "disclosure_fetcher.pipeline", fake_pipeline_module)
    monkeypatch.setitem(sys.modules, "disclosure_fetcher.config", fake_config_module)

    outcome = er_adapter.fetch_er_documents("TESTFIC", company_name="Test Fictional Ltd")

    assert outcome["status"] == "ok"
    assert outcome["counts"] == {
        "annual_report": 1,
        "quarterly_result": 1,
        "earnings_transcript": 1,
        "investor_presentation": 1,
        "special_disclosure": 1,
    }

    input_dir = _redirect_er_dirs["input_dir"] / "TESTFIC"
    landed = {p.name for p in input_dir.iterdir()}
    assert "AR_FY2025.pdf" in landed
    assert "Q_FY2026Q4.pdf" in landed
    assert "TR_2025-08-10.pdf" in landed
    assert "PPT_FY2026Q3.pdf" in landed
    assert "CRISIL_rating_action.pdf" in landed  # special_disclosure: unprefixed original name
    assert "manifest.csv" in landed
    assert outcome["manifest_path"] == str(input_dir / "manifest.csv")


def test_fetch_er_documents_unresolved_company_returns_warning(monkeypatch, _redirect_er_dirs):
    from disclosure_fetcher.models import Company, PipelineResult

    company = Company(query="Nonexistent Company XYZ")
    result = PipelineResult(company=company, warnings=["could not resolve"])

    fake_pipeline_module = SimpleNamespace(run_pipeline=lambda **kwargs: result)
    fake_config_module = SimpleNamespace(FetchTargets=lambda: object())
    monkeypatch.setitem(sys.modules, "disclosure_fetcher.pipeline", fake_pipeline_module)
    monkeypatch.setitem(sys.modules, "disclosure_fetcher.config", fake_config_module)

    outcome = er_adapter.fetch_er_documents("XYZTICKER", company_name="Nonexistent Company XYZ")
    assert outcome["status"] == "unresolved"
    assert outcome["counts"] == {}
    assert "could not resolve" in outcome["warning"].lower() or "warnings" in outcome["warning"].lower()


def test_fetch_er_documents_pipeline_exception_returns_error_not_raise(monkeypatch, _redirect_er_dirs):
    def _boom(**kwargs):
        raise RuntimeError("simulated network failure")

    fake_pipeline_module = SimpleNamespace(run_pipeline=_boom)
    fake_config_module = SimpleNamespace(FetchTargets=lambda: object())
    monkeypatch.setitem(sys.modules, "disclosure_fetcher.pipeline", fake_pipeline_module)
    monkeypatch.setitem(sys.modules, "disclosure_fetcher.config", fake_config_module)

    outcome = er_adapter.fetch_er_documents("TICKER", company_name="Whatever Ltd")
    assert outcome["status"] == "error"
    assert "simulated network failure" in outcome["warning"]
