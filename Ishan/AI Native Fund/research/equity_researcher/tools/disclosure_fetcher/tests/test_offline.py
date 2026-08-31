"""
Offline, no-network integration test.

Mocks all four external dependencies (BSE, Screener, Tavily/DuckDuckGo,
Gemini) with realistic canned data and runs the *entire* pipeline
end-to-end, so the orchestration logic (dedup, gap detection, selection,
confidence handling, manifest writing) gets exercised without needing any
API keys or live network access.

This intentionally does NOT mock disclosure_fetcher.utils - the real
fiscal-quarter math runs, since that's exactly the part most worth
catching regressions in.

Fund vendoring note: `run()` below exercises the full pipeline with
enable_web_fallback=True (mocked LLM/web-search clients patched in via
pipeline_module._make_llm_agent/_make_web_search_client, the lazy-import
factories that replaced the old module-level LLMAgent/WebSearchClient
names) so the web-fallback code path stays covered even though the fund's
own default run is BSE+Screener-only (enable_web_fallback=False, exercised
separately in run_key_free_only_scenario() below).

Run with: python tests/test_offline.py
"""
from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bse as bse_module

import disclosure_fetcher.company_resolver as company_resolver_module
import disclosure_fetcher.pipeline as pipeline_module
from disclosure_fetcher.models import DocType
from disclosure_fetcher.sources.web_fallback import SearchResult
from disclosure_fetcher.config import FetchTargets

TEST_OUTPUT_DIR = Path(__file__).resolve().parent / "_offline_test_output"


# --------------------------------------------------------------------------- #
# LLM extras are OPTIONAL here, and that is the whole point.
#
# disclosure_fetcher.llm_agent imports pydantic and tenacity unconditionally.
# Those are web-fallback extras (tools/disclosure_fetcher/requirements.txt), NOT
# part of the key-free install in tools/requirements.txt. Importing
# ItemClassification at module scope therefore made this file ImportError on the
# sanctioned key-free install — while asserting, 260 lines below, that key-free
# mode never imports the LLM/web extras. The test contradicted its own premise.
#
# So: resolve it lazily, and let the key-free scenario run without the extras.
# Do not "fix" this by adding pydantic/tenacity to tools/requirements.txt; that
# would defeat the key-free split the assertions exist to protect.
# --------------------------------------------------------------------------- #

def _item_classification_cls():
    """Import ItemClassification on demand. Returns None if the LLM extras
    (pydantic, tenacity) are not installed."""
    try:
        from disclosure_fetcher.llm_agent import ItemClassification
        return ItemClassification
    except ImportError:
        return None


LLM_EXTRAS_AVAILABLE = _item_classification_cls() is not None


# --------------------------------------------------------------------------- #
# Fake BSE announcements, in the real schema (NEWSID/NEWSSUB/HEADLINE/
# NEWS_DT/ATTACHMENTNAME/SUBCATNAME) verified against the actual `bse`
# package's sample data.
# --------------------------------------------------------------------------- #

FAKE_ANNOUNCEMENTS = [
    {  # quarterly result, explicit period-end text -> Q4 FY26
        "NEWSID": "1001", "SCRIP_CD": "999999",
        "NEWSSUB": "Test Fictional Ltd - Financial Results",
        "HEADLINE": "Un-Audited Financial Results for the quarter and year ended 31st March, 2026",
        "NEWS_DT": "2026-05-20T16:00:00",
        "ATTACHMENTNAME": "fake-q4fy26-result.pdf",
        "SUBCATNAME": "Financial Results",
    },
    {  # investor presentation, period inferred from announcement date -> Q3 FY26
        "NEWSID": "1002", "SCRIP_CD": "999999",
        "NEWSSUB": "Test Fictional Ltd - Investor Presentation",
        "HEADLINE": "Investor Presentation - Q3 FY26",
        "NEWS_DT": "2026-01-25T18:30:00",
        "ATTACHMENTNAME": "fake-q3fy26-ppt.pdf",
        "SUBCATNAME": "Investor Presentation",
    },
    {  # earnings transcript, period inferred from announcement date -> Q1 FY26
        "NEWSID": "1003", "SCRIP_CD": "999999",
        "NEWSSUB": "Test Fictional Ltd - Transcript of Earnings Call",
        "HEADLINE": "Transcript of Earnings Call held on 8th August 2025",
        "NEWS_DT": "2025-08-10T11:00:00",
        "ATTACHMENTNAME": "fake-q1fy26-transcript.pdf",
        "SUBCATNAME": "Transcript",
    },
    {  # annual report, explicit FY-end text -> FY25
        "NEWSID": "1004", "SCRIP_CD": "999999",
        "NEWSSUB": "Test Fictional Ltd - Annual Report",
        "HEADLINE": "Annual Report for the financial year ended 31st March, 2025",
        "NEWS_DT": "2025-08-01T09:15:00",
        "ATTACHMENTNAME": "fake-annual-report-fy25.pdf",
        "SUBCATNAME": "Annual Report",
    },
    {  # rating action -> special_disclosure
        "NEWSID": "1006", "SCRIP_CD": "999999",
        "NEWSSUB": "Test Fictional Ltd - Credit Rating",
        "HEADLINE": "CRISIL upgrades credit rating to AA+ / Stable",
        "NEWS_DT": "2026-02-14T12:00:00",
        "ATTACHMENTNAME": "fake-rating-action.pdf",
        "SUBCATNAME": "Credit Rating",
    },
    {  # noise - must be filtered before it ever becomes a candidate
        "NEWSID": "1005", "SCRIP_CD": "999999",
        "NEWSSUB": "Test Fictional Ltd - Newspaper Publication",
        "HEADLINE": "Newspaper Publication of Financial Results for the quarter ended 30th June, 2026",
        "NEWS_DT": "2026-07-02T10:00:00",
        "ATTACHMENTNAME": "fake-newspaper-pub.pdf",
        "SUBCATNAME": "Newspaper Publication",
    },
]


def fake_lookup(self, text):
    return {
        "company_name": "Test Fictional Ltd",
        "symbol": "TESTFIC",
        "isin": "INE000X00000",
        "bse_code": "999999",
    }


def fake_announcements(self, page_no=1, from_date=None, to_date=None, scripcode=None, category=None, **kwargs):
    if page_no > 1:
        return {"Table": [], "Table1": [{"ROWCNT": 0}]}
    return {"Table": FAKE_ANNOUNCEMENTS, "Table1": [{"ROWCNT": len(FAKE_ANNOUNCEMENTS)}]}


class FakeLLMAgent:
    """Approves everything BSE/Screener found, and approves exactly one
    web-search hit per gap query so the fallback path gets exercised too."""

    available = True
    disabled = False

    def generate_search_queries(self, company_name, doc_type, period_label, hint=""):
        return [f'"{company_name}" {doc_type} {period_label} filetype:pdf']

    def classify_items(self, company_name, items):
        out = {}
        for item in items:
            source = item.get("source", "")
            is_web = source.startswith("WebSearch")
            out[item["index"]] = _item_classification_cls()(
                index=item["index"],
                is_relevant=True,
                doc_type=item["doc_type_guess"],
                period_label=item["period_label_guess"],
                confidence=0.75 if is_web else 0.9,
                reasoning="mocked verdict for offline test",
            )
        return out

    def extract_company_identifier(self, *a, **kw):
        return None


class FakeWebSearchClient:
    def __init__(self, tavily_api_key=""):
        pass

    def search(self, query, max_results=5, include_domains=None):
        # Always return exactly one plausible-looking PDF hit.
        return [
            SearchResult(
                title=f"Result for: {query}",
                url=f"https://example-ir-page.test/{abs(hash(query)) % 100000}.pdf",
                snippet="a mocked search result snippet",
                engine="mock",
            )
        ]


def fake_download_candidate(candidate, out_dir, session=None):
    """Simulate a successful download without touching the network."""
    from disclosure_fetcher.downloader import _DOC_TYPE_DIRS
    from disclosure_fetcher.utils import bounded_dest, safe_filename

    doc_dir = out_dir / _DOC_TYPE_DIRS.get(candidate.doc_type.value, "other")
    doc_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_filename(f"{candidate.period_label}__{candidate.source}__{candidate.title}")
    # mirrors the real downloader: bound the ABSOLUTE path, not just the filename.
    dest = bounded_dest(doc_dir, stem, ".pdf")
    dest.write_bytes(b"%PDF-1.4 fake test content")
    candidate.local_path = str(dest)
    return True


def run():
    if TEST_OUTPUT_DIR.exists():
        shutil.rmtree(TEST_OUTPUT_DIR)

    # --- wire up the mocks ---
    bse_module.BSE.lookup = fake_lookup
    bse_module.BSE.announcements = fake_announcements
    company_resolver_module.resolve_via_screener = lambda name, session=None: {}
    # Patch the lazy-import factories (not module-level LLMAgent/WebSearchClient
    # names, which the fund's ENABLE_WEB_FALLBACK gating removed from
    # pipeline.py's namespace) so this exercises the full web-fallback path
    # with mocked clients, without needing google-genai/tavily/ddgs installed.
    pipeline_module._make_llm_agent = lambda gemini_api_key, disable_llm, enable_web_fallback: FakeLLMAgent()
    pipeline_module._make_web_search_client = lambda tavily_api_key, enable_web_fallback: FakeWebSearchClient()
    pipeline_module._check_fallback_keys = lambda gemini_api_key, tavily_api_key: None
    pipeline_module.download_candidate = fake_download_candidate
    pipeline_module.screener_source.fetch_screener_candidates = lambda company, session=None: []

    targets = FetchTargets(
        annual_reports=5, quarterly_results=8, half_yearly_results=4,
        earnings_transcripts=4, investor_presentations=4, special_disclosures=8,
        lookback_years=6,
    )

    result = pipeline_module.run_pipeline(
        "Test Fictional Ltd", targets=targets, output_dir=TEST_OUTPUT_DIR,
        enable_web_fallback=True,
    )

    # --- assertions ---
    assert result.company.is_resolved(), "company should resolve via mocked BSE lookup"
    assert result.company.bse_scrip_code == "999999"

    counts = result.counts_by_type()
    print("Downloaded counts by type:", counts)
    print("Warnings:")
    for w in result.warnings:
        print(" -", w)

    # the noise item must never have become a candidate at all
    noise_titles = [c.title for c in result.candidates if "Newspaper" in c.title]
    assert not noise_titles, f"noise item leaked through as a candidate: {noise_titles}"

    # the explicit BSE items should have landed in the right buckets with
    # the right period labels
    by_period = {(c.doc_type.value, c.period_label): c for c in result.candidates if c.source == "BSE"}
    assert (DocType.QUARTERLY_RESULT.value, "Q4 FY26") in by_period
    assert (DocType.INVESTOR_PRESENTATION.value, "Q3 FY26") in by_period
    assert (DocType.EARNINGS_TRANSCRIPT.value, "Q1 FY26") in by_period
    assert (DocType.ANNUAL_REPORT.value, "FY25") in by_period
    assert (DocType.SPECIAL_DISCLOSURE.value, "Disclosure (2026-02-14)") in by_period

    # gap-filling should have kicked in for the many periods the fake BSE
    # feed didn't cover, and those should show up as WebSearch-sourced
    web_filled = [c for c in result.downloaded if c.source == "WebSearch"]
    assert web_filled, "expected at least some gaps to be filled via the mocked web search"
    print(f"\nWeb-fallback filled {len(web_filled)} gap(s), e.g.: {web_filled[0].doc_type.value} / {web_filled[0].period_label}")

    # every doc type with a positive target should have hit its count
    # exactly, since the mocks approve everything they're asked about
    for doc_type, target_n in [
        (DocType.ANNUAL_REPORT, targets.annual_reports),
        (DocType.QUARTERLY_RESULT, targets.quarterly_results),
        (DocType.HALF_YEARLY_RESULT, targets.half_yearly_results),
        (DocType.EARNINGS_TRANSCRIPT, targets.earnings_transcripts),
        (DocType.INVESTOR_PRESENTATION, targets.investor_presentations),
    ]:
        got = counts.get(doc_type.value, 0)
        assert got == target_n, f"{doc_type.value}: expected {target_n}, got {got}"

    assert Path(result.manifest_path).exists(), "manifest.csv should exist on disk"
    manifest_rows = Path(result.manifest_path).read_text().splitlines()
    print(f"\nmanifest.csv has {len(manifest_rows) - 1} data rows at {result.manifest_path}")

    downloaded_files = list(Path(TEST_OUTPUT_DIR).rglob("*.pdf"))
    print(f"{len(downloaded_files)} .pdf files actually written to disk under {TEST_OUTPUT_DIR}")
    assert len(downloaded_files) == len(result.downloaded)

    print("\nALL OFFLINE INTEGRATION CHECKS PASSED")


def run_key_free_only_scenario():
    """enable_web_fallback=False (the fund's actual default — see
    config.ENABLE_WEB_FALLBACK / README.md "Fund integration") - verifies
    the key-free BSE+Screener-only mode: BSE candidates (heuristic
    confidence ~0.7-1.0) should still download fine, no candidate should
    ever come from WebSearch (the fallback stage must not run at all, not
    just run unverified), and google-genai/tavily/ddgs must never be
    imported. This intentionally does NOT patch _make_llm_agent /
    _make_web_search_client - the real (gated) factories run and must
    themselves return the Null stand-ins without importing anything.
    """
    key_free_dir = Path(__file__).resolve().parent / "_offline_test_output_key_free"
    if key_free_dir.exists():
        shutil.rmtree(key_free_dir)

    # Restore the real (gated) factories - this scenario tests them directly.
    import importlib

    importlib.reload(pipeline_module)
    bse_module.BSE.lookup = fake_lookup
    bse_module.BSE.announcements = fake_announcements
    company_resolver_module.resolve_via_screener = lambda name, session=None: {}
    pipeline_module.download_candidate = fake_download_candidate
    pipeline_module.screener_source.fetch_screener_candidates = lambda company, session=None: []

    targets = FetchTargets(annual_reports=2, quarterly_results=2, half_yearly_results=0,
                            earnings_transcripts=0, investor_presentations=0, special_disclosures=0)

    result = pipeline_module.run_pipeline(
        "Test Fictional Ltd", targets=targets, output_dir=key_free_dir,
        enable_web_fallback=False,
    )

    assert result.company.is_resolved()
    bse_sourced = [c for c in result.candidates if c.source == "BSE"]
    web_sourced = [c for c in result.candidates if c.source == "WebSearch"]
    assert bse_sourced, "expected the explicit BSE quarterly/annual-report items to still show up"
    assert all(c.heuristic_confidence >= 0.4 for c in bse_sourced), "BSE heuristic confidence should clear the default threshold on its own"
    assert not web_sourced, "web-search fallback must not run at all when enable_web_fallback=False"
    assert any("Web-search fallback disabled" in w for w in result.warnings)
    downloaded_sources = {c.source for c in result.downloaded}
    assert "WebSearch" not in downloaded_sources
    assert "google.genai" not in sys.modules, "key-free mode must never import google-genai"
    assert "tavily" not in sys.modules, "key-free mode must never import tavily"
    print(f"\n[key-free scenario] {len(bse_sourced)} BSE candidate(s) auto-accepted, "
          f"0 WebSearch candidates (fallback stage did not run).")
    print("KEY-FREE-ONLY SCENARIO CHECKS PASSED")


def run_fallback_enabled_without_keys_raises():
    """enable_web_fallback=True with neither GEMINI_API_KEY nor
    TAVILY_API_KEY set must raise RuntimeError, not silently degrade - see
    config.py's "Fund vendoring note" and pipeline._check_fallback_keys."""
    import importlib

    importlib.reload(pipeline_module)
    bse_module.BSE.lookup = fake_lookup
    bse_module.BSE.announcements = fake_announcements

    try:
        pipeline_module.run_pipeline(
            "Test Fictional Ltd", output_dir=Path(__file__).resolve().parent / "_should_not_be_created",
            enable_web_fallback=True, gemini_api_key="", tavily_api_key="",
        )
    except RuntimeError as exc:
        assert "GEMINI_API_KEY" in str(exc) and "TAVILY_API_KEY" in str(exc)
        print("\nRuntimeError correctly raised for enable_web_fallback=True with no keys set.")
        print("NO-KEYS-RAISES SCENARIO CHECKS PASSED")
        return
    raise AssertionError("expected RuntimeError when enabling web fallback with no keys configured")


def main():
    """The key-free scenario is the one that must pass on a key-free install, so it
    runs unconditionally. The two web-fallback scenarios need the optional LLM extras
    (pydantic/tenacity via disclosure_fetcher.llm_agent) and are skipped — loudly —
    when those are absent. Exit code stays 0 on a skip: a key-free install running the
    key-free tests is a pass, not a failure."""
    skipped = []
    if LLM_EXTRAS_AVAILABLE:
        run()
    else:
        skipped.append("run() [full pipeline with mocked web fallback]")

    run_key_free_only_scenario()

    if LLM_EXTRAS_AVAILABLE:
        run_fallback_enabled_without_keys_raises()
    else:
        skipped.append("run_fallback_enabled_without_keys_raises()")

    if skipped:
        print("\nSKIPPED (optional LLM extras not installed — pydantic/tenacity, from")
        print("tools/disclosure_fetcher/requirements.txt, needed only for the web-fallback path):")
        for s in skipped:
            print(f"  - {s}")
        print("Install them only if you are deliberately enabling --enable-web-fallback.")
        print("\nKEY-FREE CHECKS PASSED (web-fallback scenarios skipped).")


if __name__ == "__main__":
    main()
