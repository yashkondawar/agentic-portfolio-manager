"""Offline tests for afund.research.er_adapter — the file-based bridge to
the external equity researcher subsystem (research/equity_researcher/).

All filesystem roots (ER_ROOT/ER_INPUT_DIR/ER_WORKSPACE_DIR/
RESEARCH_PACKETS_DIR/PACKETS_DIR) are monkeypatched into tmp_path so these
tests never touch the real research/equity_researcher/ directory. No
network, no LLM calls -- ingest_er_output reads a synthetic fixture
(tests/fixtures/er_workspace_sample/) rather than a live ER run.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from afund.agents.contracts import ContractViolation
from afund.orchestrator import context
from afund.research import er_adapter

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "er_workspace_sample"

AS_OF = dt.date(2026, 7, 5)


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def _redirect_dirs(tmp_path, monkeypatch):
    er_root = tmp_path / "research" / "equity_researcher"
    input_dir = er_root / "input"
    workspace_dir = er_root / "workspace"
    research_packets_dir = tmp_path / "data" / "packets" / "research"
    packets_dir = tmp_path / "data" / "packets"

    monkeypatch.setattr(er_adapter, "ER_ROOT", er_root)
    monkeypatch.setattr(er_adapter, "ER_INPUT_DIR", input_dir)
    monkeypatch.setattr(er_adapter, "ER_WORKSPACE_DIR", workspace_dir)
    monkeypatch.setattr(er_adapter, "RESEARCH_PACKETS_DIR", research_packets_dir)
    monkeypatch.setattr(er_adapter, "PACKETS_DIR", packets_dir)
    monkeypatch.setattr(context, "PACKETS_DIR", packets_dir)
    yield {"er_root": er_root, "input_dir": input_dir, "workspace_dir": workspace_dir}


@pytest.fixture(autouse=True)
def _stub_fetch_er_documents(monkeypatch):
    """prepare_kickoff defaults to fetch_documents=True, which calls
    fetch_er_documents -> disclosure_fetcher.pipeline.run_pipeline (a real
    network call to BSE/Screener). These tests are offline by design, so
    stub fetch_er_documents to a deterministic no-op unless a test
    explicitly monkeypatches it back (see test_disclosure_fetcher.py for
    fetch_er_documents' own dedicated tests, and this module's live test
    for the real network path)."""

    def _fake_fetch(ticker, company_name=None):
        return {
            "status": "ok",
            "counts": {},
            "manifest_path": None,
            "raw_dir": "",
            "warning": None,
        }

    monkeypatch.setattr(er_adapter, "fetch_er_documents", _fake_fetch)
    yield _fake_fetch


def _insert_instrument(conn, instrument_id, symbol, sector, instrument_type="STOCK"):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector, active) VALUES (?, ?, ?, ?, 1)",
        (instrument_id, symbol, instrument_type, sector),
    )


def _seed_infy(conn):
    _insert_instrument(conn, 1, "INFY", "Information Technology")
    conn.commit()


def _drop_workspace_fixture(workspace_dir: Path, ticker: str = "INFY") -> None:
    ticker_dir = workspace_dir / ticker
    (ticker_dir / "report").mkdir(parents=True, exist_ok=True)
    (ticker_dir / "handoff").mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_DIR / "final_note.md", ticker_dir / "report" / "final_note.md")
    shutil.copy(FIXTURE_DIR / "valuation_handoff.json", ticker_dir / "handoff" / "valuation_handoff.json")


# --- prepare_kickoff -----------------------------------------------------------


def test_prepare_kickoff_writes_fund_context(conn, tmp_path, capsys):
    _seed_infy(conn)
    result = er_adapter.prepare_kickoff(conn, "INFY")

    fund_context_path = Path(result["fund_context_path"])
    assert fund_context_path.exists()
    fund_context = json.loads(fund_context_path.read_text(encoding="utf-8"))
    assert fund_context["ticker"] == "INFY"
    assert fund_context["sector"] == "Information Technology"
    assert fund_context["sector_kpi_key"] == "it_technology"


def test_prepare_kickoff_logs_prepared_agent_run(conn):
    _seed_infy(conn)
    result = er_adapter.prepare_kickoff(conn, "INFY")

    row = conn.execute(
        "SELECT role, status, backend, trigger FROM agent_runs WHERE id = ?",
        (result["agent_runs_id"],),
    ).fetchone()
    assert row is not None
    assert row["role"] == "equity_researcher"
    assert row["status"] == "PREPARED"
    assert row["backend"] == "claude_code"
    assert row["trigger"] == "equity_research_kickoff"


def test_prepare_kickoff_prints_instruction(conn, capsys):
    _seed_infy(conn)
    er_adapter.prepare_kickoff(conn, "INFY")
    captured = capsys.readouterr()
    assert "READY" in captured.out
    assert "INFY" in captured.out
    assert "research/equity_researcher" in captured.out or "research\\equity_researcher" in captured.out


def test_prepare_kickoff_unknown_ticker_has_null_sector_context(conn):
    # No instruments row for this ticker -- must degrade gracefully (no crash),
    # not fabricate a sector/cycle context that doesn't exist.
    result = er_adapter.prepare_kickoff(conn, "NOTREAL")
    fund_context = json.loads(Path(result["fund_context_path"]).read_text(encoding="utf-8"))
    assert fund_context["sector"] is None
    assert fund_context["sector_cycle_phase"] is None


# --- fetch_documents threading ---------------------------------------------


def test_prepare_kickoff_default_fetches_documents(conn):
    # fetch_documents defaults True; the autouse _stub_fetch_er_documents
    # fixture stands in for the real network call and returns status=ok.
    _seed_infy(conn)
    result = er_adapter.prepare_kickoff(conn, "INFY")
    assert result["documents_fetched"]["status"] == "ok"
    fund_context = json.loads(Path(result["fund_context_path"]).read_text(encoding="utf-8"))
    assert fund_context["documents_fetched"]["status"] == "ok"


def test_prepare_kickoff_fetch_documents_false_skips_fetch(conn, monkeypatch):
    _seed_infy(conn)
    calls = []
    monkeypatch.setattr(
        er_adapter, "fetch_er_documents", lambda *a, **kw: calls.append((a, kw))
    )
    result = er_adapter.prepare_kickoff(conn, "INFY", fetch_documents=False)
    assert calls == []
    assert result["documents_fetched"] is None
    fund_context = json.loads(Path(result["fund_context_path"]).read_text(encoding="utf-8"))
    assert fund_context["documents_fetched"] is None


def test_prepare_kickoff_fetch_error_does_not_block_kickoff(conn, monkeypatch):
    # A fetch failure must never prevent kickoff from completing (spec:
    # "Failure-tolerant: if fetcher errors, kickoff still completes with
    # clear 'documents not fetched' note").
    _seed_infy(conn)

    def _boom(ticker, company_name=None):
        raise RuntimeError("simulated fetch crash")

    monkeypatch.setattr(er_adapter, "fetch_er_documents", _boom)
    result = er_adapter.prepare_kickoff(conn, "INFY")
    assert result["documents_fetched"]["status"] == "error"
    assert "simulated fetch crash" in result["documents_fetched"]["warning"]
    assert Path(result["fund_context_path"]).exists()


def test_prepare_kickoff_fetch_error_note_in_instruction(conn, monkeypatch):
    _seed_infy(conn)
    monkeypatch.setattr(
        er_adapter,
        "fetch_er_documents",
        lambda ticker, company_name=None: {
            "status": "unresolved",
            "counts": {},
            "manifest_path": None,
            "raw_dir": "",
            "warning": "could not resolve company",
        },
    )
    result = er_adapter.prepare_kickoff(conn, "INFY")
    assert "not completed" in result["instruction"].lower() or "not fetched" in result["instruction"].lower() or "could not resolve" in result["instruction"]


# --- ingest_er_output -----------------------------------------------------------


def test_ingest_er_output_missing_files_raises(conn):
    _seed_infy(conn)
    with pytest.raises(FileNotFoundError):
        er_adapter.ingest_er_output(conn, "INFY")


def test_ingest_er_output_maps_rating_and_validates(conn, _redirect_dirs):
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])

    result = er_adapter.ingest_er_output(conn, "INFY")
    assert result["raw_rating_value"] == "BUY"
    assert result["rating"] == "BULLISH"  # RATING_MAP["BUY"] == "BULLISH"
    assert Path(result["note_json_path"]).exists()


def test_ingest_er_output_writes_research_reports_row(conn, _redirect_dirs):
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])

    result = er_adapter.ingest_er_output(conn, "INFY")
    row = conn.execute(
        "SELECT ticker, report_type, rating, status, handoff_path FROM research_reports "
        "WHERE ticker = ? AND report_type = 'EQUITY'",
        ("INFY",),
    ).fetchone()
    assert row is not None
    assert row["rating"] == "BULLISH"
    assert row["status"] == "OK"
    assert row["handoff_path"] == result["note"]["sources"][1]


def test_ingest_er_output_idempotent_upsert(conn, _redirect_dirs):
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])

    er_adapter.ingest_er_output(conn, "INFY")
    er_adapter.ingest_er_output(conn, "INFY")  # must not raise / must not duplicate

    rows = conn.execute(
        "SELECT id FROM research_reports WHERE ticker = ? AND report_type = 'EQUITY'", ("INFY",)
    ).fetchall()
    assert len(rows) == 1


def test_ingest_er_output_unmapped_rating_kept_as_none(conn, _redirect_dirs, tmp_path):
    _seed_infy(conn)
    workspace_dir = _redirect_dirs["workspace_dir"]
    ticker_dir = workspace_dir / "INFY"
    (ticker_dir / "report").mkdir(parents=True, exist_ok=True)
    (ticker_dir / "handoff").mkdir(parents=True, exist_ok=True)

    handoff = json.loads((FIXTURE_DIR / "valuation_handoff.json").read_text(encoding="utf-8"))
    handoff["rating"]["value"] = "SOMETHING_UNEXPECTED"
    (ticker_dir / "handoff" / "valuation_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
    (ticker_dir / "report" / "final_note.md").write_text(
        "# No parseable rating row here.\n", encoding="utf-8"
    )

    result = er_adapter.ingest_er_output(conn, "INFY")
    assert result["rating"] is None  # never fabricate a mapping the source doesn't support


def test_rating_map_covers_expected_tokens():
    assert er_adapter.RATING_MAP["BUY"] == "BULLISH"
    assert er_adapter.RATING_MAP["ADD"] == "BULLISH"
    assert er_adapter.RATING_MAP["HOLD"] == "NEUTRAL"
    assert er_adapter.RATING_MAP["REDUCE"] == "BEARISH"
    assert er_adapter.RATING_MAP["SELL"] == "BEARISH"
    assert er_adapter.RATING_MAP["AVOID"] == "BEARISH"


# --- build_buy_side_packet -------------------------------------------------------


def test_build_buy_side_packet_requires_prior_ingest(conn):
    _seed_infy(conn)
    with pytest.raises(LookupError):
        er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")


def test_build_buy_side_packet_basic_shape(conn, _redirect_dirs):
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])
    er_adapter.ingest_er_output(conn, "INFY")

    result = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")
    assert Path(result["path"]).exists()
    packet = result["packet"]
    assert packet["role"] == "buy_side"
    assert packet["ticker"] == "INFY"
    assert packet["valuation_handoff"]["company"]["ticker"] == "INFY"
    assert packet["valuation_handoff"]["pe_bands"]["fwd_pe_fy1"] == pytest.approx(23.7)
    assert packet["prior_equity_research"]["rating"] == "BULLISH"


def test_build_buy_side_packet_json_serializable(conn, _redirect_dirs):
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])
    er_adapter.ingest_er_output(conn, "INFY")

    result = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")
    json.dumps(result["packet"])  # must not raise


# --- Phase 11 EPS-bridge doctrine: packet keys ------------------------------


def test_build_buy_side_packet_degrades_gracefully_without_eps_bridge_artifacts(conn, _redirect_dirs):
    # No eps_bridge_check.json / exports/*.xlsx / findings/guidance.json for
    # this ticker (older run, or COMPUTE step predates these artifacts) --
    # the packet must still build, with all three keys present but None.
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])
    er_adapter.ingest_er_output(conn, "INFY")

    result = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")
    packet = result["packet"]
    assert packet["eps_bridge_check"] is None
    assert packet["xlsx_path"] is None
    assert packet["narrative_findings_reference"] is None


def test_build_buy_side_packet_inlines_eps_bridge_check_when_present(conn, _redirect_dirs):
    _seed_infy(conn)
    workspace_dir = _redirect_dirs["workspace_dir"]
    _drop_workspace_fixture(workspace_dir)
    er_adapter.ingest_er_output(conn, "INFY")

    state_dir = workspace_dir / "INFY" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    eps_bridge_payload = {
        "eps_growth_20pct": {"status": "PASS", "value": {"FY2025": 25.0}, "threshold": 20.0, "note": "consistent"},
        "_basis": "consolidated",
        "_periods": ["FY2024", "FY2025"],
    }
    (state_dir / "eps_bridge_check.json").write_text(json.dumps(eps_bridge_payload), encoding="utf-8")

    result = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")
    assert result["packet"]["eps_bridge_check"] == eps_bridge_payload


def test_build_buy_side_packet_xlsx_path_points_to_export_when_present(conn, _redirect_dirs):
    _seed_infy(conn)
    workspace_dir = _redirect_dirs["workspace_dir"]
    _drop_workspace_fixture(workspace_dir)
    er_adapter.ingest_er_output(conn, "INFY")

    exports_dir = workspace_dir / "INFY" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    xlsx_file = exports_dir / "INFY_financials.xlsx"
    xlsx_file.write_bytes(b"not a real xlsx, existence is all that's checked")

    result = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")
    assert result["packet"]["xlsx_path"] == str(xlsx_file)


def test_build_buy_side_packet_narrative_findings_reference_when_present(conn, _redirect_dirs):
    _seed_infy(conn)
    workspace_dir = _redirect_dirs["workspace_dir"]
    _drop_workspace_fixture(workspace_dir)
    er_adapter.ingest_er_output(conn, "INFY")

    findings_dir = workspace_dir / "INFY" / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    (findings_dir / "guidance.json").write_text(json.dumps({"findings": []}), encoding="utf-8")

    result = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")
    ref = result["packet"]["narrative_findings_reference"]
    assert ref is not None
    assert ref["path"] == str(findings_dir / "guidance.json")
    assert "management-intent" in ref["summary"]


def test_build_buy_side_packet_eps_bridge_check_none_on_malformed_json(conn, _redirect_dirs):
    _seed_infy(conn)
    workspace_dir = _redirect_dirs["workspace_dir"]
    _drop_workspace_fixture(workspace_dir)
    er_adapter.ingest_er_output(conn, "INFY")

    state_dir = workspace_dir / "INFY" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "eps_bridge_check.json").write_text("{not valid json", encoding="utf-8")

    result = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")
    assert result["packet"]["eps_bridge_check"] is None


# --- facts/interpretation layer: packet keys --------------------------------


def _drop_workspace_fixture_with(workspace_dir: Path, **handoff_overrides):
    """Same fixture, with the handoff patched — for the keys the sample
    predates (it was written before sector_playbook existed, which is exactly
    the "older run" case the adapter has to degrade through)."""
    _drop_workspace_fixture(workspace_dir)
    path = workspace_dir / "INFY" / "handoff" / "valuation_handoff.json"
    handoff = json.loads(path.read_text(encoding="utf-8"))
    handoff.update(handoff_overrides)
    path.write_text(json.dumps(handoff), encoding="utf-8")


def test_buy_side_packet_degrades_without_interpretation_artifacts(conn, _redirect_dirs):
    # No sector_playbook on the handoff, no ledger, no red team: the packet
    # still builds, the frame falls back to the fund's own family slug, and
    # the two absent artifacts read as "not computed" rather than "none".
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])
    er_adapter.ingest_er_output(conn, "INFY")

    packet = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")["packet"]
    assert packet["sector_playbook"] is None
    assert packet["interpretation_ledger"] is None
    assert packet["redteam_findings"] is None
    frame = packet["interpretation_frame"]
    assert frame["family"] == "it_technology"  # from instruments.sector, not the handoff
    assert frame["resolved_from"] == ["registry:family:it_technology"]
    assert frame["primary_multiple"] == "pe_forward"
    assert packet["opinion_audit_reference"]["fund_methodology"]["path"].endswith(
        "facts_vs_interpretation.md"
    )


def test_buy_side_packet_layers_playbook_frame_over_family(conn, _redirect_dirs):
    """life_insurance is bfsi, and bfsi's family default is P/B — but a life
    insurer is read on P/EV. The playbook layer has to win, or the packet
    hands the agent the wrong lens for the business the ER run classified."""
    _seed_infy(conn)
    _drop_workspace_fixture_with(
        _redirect_dirs["workspace_dir"], sector_playbook="life_insurance"
    )
    er_adapter.ingest_er_output(conn, "INFY")

    packet = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")["packet"]
    assert packet["sector_playbook"] == "life_insurance"
    frame = packet["interpretation_frame"]
    assert frame["family"] == "bfsi"  # from the ER registry, not instruments.sector
    assert frame["playbook"] == "life_insurance"
    assert frame["primary_multiple"] == "p_ev"
    assert frame["resolved_from"] == ["registry:family:bfsi", "er:playbook:life_insurance"]


def test_buy_side_packet_unknown_playbook_falls_back_to_fund_family(conn, _redirect_dirs):
    # An ER run newer than this checkout's vendored sector_registry: the
    # playbook slug means nothing here, and inventing a frame for it would be
    # worse than falling back to the family we do know.
    _seed_infy(conn)
    _drop_workspace_fixture_with(
        _redirect_dirs["workspace_dir"], sector_playbook="quantum_widgets"
    )
    er_adapter.ingest_er_output(conn, "INFY")

    packet = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")["packet"]
    assert packet["sector_playbook"] == "quantum_widgets"
    assert packet["interpretation_frame"]["family"] == "it_technology"
    assert packet["interpretation_frame"]["playbook"] is None


def test_buy_side_packet_prefers_handoff_ledger_over_state_file(conn, _redirect_dirs):
    workspace_dir = _redirect_dirs["workspace_dir"]
    _seed_infy(conn)
    entry = {
        "fact": "trailing P/E 30.2",
        "readings": [
            {"verdict": "expensive", "conditioning_variable": "own_history_anchor"},
            {"verdict": "cheap", "conditioning_variable": "growth_rate"},
        ],
        "our_reading": "cheap only if the growth holds five years",
    }
    _drop_workspace_fixture_with(workspace_dir, interpretation_ledger=[entry])
    state_dir = workspace_dir / "INFY" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "interpretation_ledger.json").write_text(
        json.dumps({"company": "Infosys", "as_of": "2026-07-05", "entries": [{"fact": "stale"}]}),
        encoding="utf-8",
    )
    er_adapter.ingest_er_output(conn, "INFY")

    ledger = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")["packet"][
        "interpretation_ledger"
    ]
    assert ledger["source"] == "valuation_handoff.interpretation_ledger"
    assert ledger["entries"] == [entry]


def test_buy_side_packet_falls_back_to_ledger_state_file(conn, _redirect_dirs):
    workspace_dir = _redirect_dirs["workspace_dir"]
    _seed_infy(conn)
    _drop_workspace_fixture(workspace_dir)
    state_dir = workspace_dir / "INFY" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "company": "Infosys",
        "as_of": "2026-07-05",
        "sector_playbook": "it_services",
        "entries": [{"fact": "trailing P/E 30.2"}],
    }
    (state_dir / "interpretation_ledger.json").write_text(json.dumps(payload), encoding="utf-8")
    er_adapter.ingest_er_output(conn, "INFY")

    ledger = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")["packet"][
        "interpretation_ledger"
    ]
    assert ledger["source"].endswith("interpretation_ledger.json")
    assert ledger["entries"] == payload["entries"]


def test_buy_side_packet_redteam_findings_are_sub_selected(conn, _redirect_dirs):
    """The long prose stays behind a pointer; the binding parts come inline,
    and 18 passing checks carry no information — only the failures do."""
    workspace_dir = _redirect_dirs["workspace_dir"]
    _seed_infy(conn)
    _drop_workspace_fixture(workspace_dir)
    findings_dir = workspace_dir / "INFY" / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "verdict": "survives_with_qualifications",
        "rating_change_recommended": "none",
        "disconfirming_exhibit_present": True,
        "checks": [
            {"check": 10, "status": "pass", "evidence": "exhibit 4"},
            {"check": 16, "status": "fail", "evidence": "the target multiple has no ledger entry"},
        ],
        "banned_reasoning_hits": ["deserves a re-rating as the sector re-rates"],
        "interpretation_audit": {"ledger_present": True, "check_16_coverage": "fail"},
        "unresolved_divergences": [{"fact": "P/E 30.2", "materiality": "high"}],
        "opposite_case": "x" * 4000,
        "premortem": "y" * 4000,
    }
    (findings_dir / "thesis_redteam.json").write_text(json.dumps(payload), encoding="utf-8")
    er_adapter.ingest_er_output(conn, "INFY")

    found = er_adapter.build_buy_side_packet(conn, "INFY", batch_id="test_batch")["packet"][
        "redteam_findings"
    ]
    assert found["verdict"] == "survives_with_qualifications"
    assert found["interpretation_audit"]["check_16_coverage"] == "fail"
    assert found["unresolved_divergences"] == payload["unresolved_divergences"]
    assert [c["check"] for c in found["failed_checks"]] == [16]
    assert "opposite_case" not in found and "premortem" not in found
    assert found["path"].endswith("thesis_redteam.json")


def test_ingest_er_output_records_interpretation_artifacts_as_sources(conn, _redirect_dirs):
    workspace_dir = _redirect_dirs["workspace_dir"]
    _seed_infy(conn)
    _drop_workspace_fixture(workspace_dir)
    state_dir = workspace_dir / "INFY" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "interpretation_ledger.json").write_text(
        json.dumps({"entries": [{"fact": "a"}, {"fact": "b"}]}), encoding="utf-8"
    )
    findings_dir = workspace_dir / "INFY" / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    (findings_dir / "thesis_redteam.json").write_text(
        json.dumps({"verdict": "survives"}), encoding="utf-8"
    )

    result = er_adapter.ingest_er_output(conn, "INFY")
    assert result["interpretation_ledger_entries"] == 2
    assert result["redteam_verdict"] == "survives"
    sources = result["note"]["sources"]
    assert any(s.endswith("interpretation_ledger.json") for s in sources)
    assert any(s.endswith("thesis_redteam.json") for s in sources)


def test_ingest_er_output_sources_unchanged_without_interpretation_artifacts(conn, _redirect_dirs):
    # The pre-existing contract: sources[1] is the handoff path. Nothing may
    # shift it (an earlier test indexes it), and an older run reports None
    # rather than zero — absent is not "computed and empty".
    _seed_infy(conn)
    _drop_workspace_fixture(_redirect_dirs["workspace_dir"])
    result = er_adapter.ingest_er_output(conn, "INFY")
    assert len(result["note"]["sources"]) == 2
    assert result["interpretation_ledger_entries"] is None
    assert result["redteam_verdict"] is None
