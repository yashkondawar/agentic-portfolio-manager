"""Offline tests for the Phase 9 wiring inside afund.orchestrator.run:

- cmd_job's LAST_PACKET_RESULT hand-off for agent:sector_researcher /
  agent:buy_side (the design gap this phase closed -- these two agent:
  steps must use the packet the *preceding* py: step already built, never
  a freshly-built generic build_packet() packet).
- --ticker / --sector CLI args reach the py: steps that need them.
- cmd_ingest_output's new sector_researcher / buy_side research_reports
  side effects.

get_conn() is monkeypatched to a temp SQLite DB built from schema.sql so
these tests never touch the real configured database. No network, no LLM
calls -- agent steps only get as far as the PREPARED-row + printed
instruction (the claude_code backend never executes here).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from afund.orchestrator import context, run
from afund.research import er_adapter, sector_assembler

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "er_workspace_sample"

AS_OF = dt.date(2026, 7, 5)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    connection.close()
    return path


@pytest.fixture(autouse=True)
def _redirect_everything(tmp_path, monkeypatch, db_path):
    packets_dir = tmp_path / "data" / "packets"
    er_root = tmp_path / "research" / "equity_researcher"

    monkeypatch.setattr(run, "get_conn", lambda: _connect(db_path))
    monkeypatch.setattr(run, "PACKETS_DIR", packets_dir)
    monkeypatch.setattr(context, "PACKETS_DIR", packets_dir)
    monkeypatch.setattr(sector_assembler, "PACKETS_DIR", packets_dir)
    monkeypatch.setattr(er_adapter, "PACKETS_DIR", packets_dir)
    monkeypatch.setattr(er_adapter, "ER_ROOT", er_root)
    monkeypatch.setattr(er_adapter, "ER_INPUT_DIR", er_root / "input")
    monkeypatch.setattr(er_adapter, "ER_WORKSPACE_DIR", er_root / "workspace")
    monkeypatch.setattr(er_adapter, "RESEARCH_PACKETS_DIR", tmp_path / "data" / "packets" / "research")
    # prepare_kickoff defaults to fetch_documents=True, which calls
    # fetch_er_documents -> a real disclosure_fetcher.pipeline.run_pipeline
    # network call. This file is offline by design (see module docstring),
    # so stub it out -- see tests/test_research/test_disclosure_fetcher.py
    # for fetch_er_documents' own dedicated offline tests.
    monkeypatch.setattr(
        er_adapter,
        "fetch_er_documents",
        lambda ticker, company_name=None: {
            "status": "ok",
            "counts": {},
            "manifest_path": None,
            "raw_dir": "",
            "warning": None,
        },
    )
    yield {"packets_dir": packets_dir, "er_root": er_root}


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _base_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        job=None, date=None, symbol=None, ticker=None, sector=None, scope=None,
        period=None, step=None, prior_output=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _seed_instrument(db_path, instrument_id, symbol, sector):
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector, active) VALUES (?, ?, 'STOCK', ?, 1)",
        (instrument_id, symbol, sector),
    )
    conn.commit()
    conn.close()


# --- sector_research trigger: agent:sector_researcher must use the py: step's packet ---


def test_sector_research_agent_step_uses_sector_assembler_packet(db_path, capsys):
    args = _base_args(job="sector_research", sector="it_technology")
    run.cmd_job(args)
    captured = capsys.readouterr()

    # The py: step's packet path must appear in the agent: step's printed
    # instruction -- proof that agent:sector_researcher did NOT fall through
    # to the generic build_packet() path (which would build a different,
    # instrument/regime-shaped packet and never mention this exact file).
    packet_lines = [l for l in captured.out.splitlines() if "packet ->" in l]
    assert len(packet_lines) == 1
    packet_path = packet_lines[0].split("packet -> ")[1].split(" (approx_tokens")[0]
    assert Path(packet_path).exists()
    assert f"packet file {packet_path}" in captured.out
    assert "sector_researcher" in captured.out


def test_sector_research_missing_sector_flag_fails_py_step(db_path, capsys):
    args = _base_args(job="sector_research", sector=None)
    run.cmd_job(args)
    captured = capsys.readouterr()
    assert "--sector is required" in captured.out
    # agent: step must not have silently built a wrong packet either.
    assert "packet ->" not in captured.out


def test_sector_research_logs_prepared_agent_run(db_path):
    args = _base_args(job="sector_research", sector="it_technology")
    run.cmd_job(args)

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT role, status FROM agent_runs WHERE role = 'sector_researcher' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["status"] == "PREPARED"


# --- equity_research_kickoff trigger --------------------------------------------


def test_equity_research_kickoff_requires_ticker(db_path, capsys):
    args = _base_args(job="equity_research_kickoff", ticker=None)
    run.cmd_job(args)
    captured = capsys.readouterr()
    assert "--ticker is required" in captured.out


def test_equity_research_kickoff_with_ticker(db_path, capsys):
    _seed_instrument(db_path, 1, "INFY", "Information Technology")
    args = _base_args(job="equity_research_kickoff", ticker="INFY")
    run.cmd_job(args)
    captured = capsys.readouterr()
    assert "READY: equity_researcher kickoff prepared for INFY" in captured.out


# --- buy_side_analysis trigger: three-step pipeline, agent step uses 2nd py: step's packet ---


def _drop_workspace_fixture(er_root: Path, ticker: str = "INFY") -> None:
    ticker_dir = er_root / "workspace" / ticker
    (ticker_dir / "report").mkdir(parents=True, exist_ok=True)
    (ticker_dir / "handoff").mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_DIR / "final_note.md", ticker_dir / "report" / "final_note.md")
    shutil.copy(FIXTURE_DIR / "valuation_handoff.json", ticker_dir / "handoff" / "valuation_handoff.json")


def test_buy_side_analysis_full_pipeline(db_path, capsys, _redirect_everything):
    _seed_instrument(db_path, 1, "INFY", "Information Technology")
    _drop_workspace_fixture(_redirect_everything["er_root"])

    args = _base_args(job="buy_side_analysis", ticker="INFY")
    run.cmd_job(args)
    captured = capsys.readouterr()

    # Step 1: ingest_er_output succeeded.
    assert "rating=BULLISH" in captured.out
    # Step 2: build_buy_side_packet succeeded and wrote a packet.
    packet_lines = [l for l in captured.out.splitlines() if "packet ->" in l]
    assert len(packet_lines) == 1
    packet_path = packet_lines[0].split("packet -> ")[1].split(" (approx_tokens")[0]
    # Step 3: agent:buy_side's instruction references that exact packet path.
    assert f"packet file {packet_path}" in captured.out
    assert "'buy_side'" in captured.out

    on_disk = json.loads(Path(packet_path).read_text(encoding="utf-8"))
    assert on_disk["role"] == "buy_side"
    assert on_disk["ticker"] == "INFY"


def test_buy_side_analysis_without_prior_ingest_fails_cleanly(db_path, capsys):
    # No workspace fixture dropped -> step 1 (ingest_er_output) fails with
    # FileNotFoundError (caught, printed as [FAILED]) -> step 2
    # (build_buy_side_packet) then fails with LookupError (also caught) --
    # neither should raise out of cmd_job, and no agent: instruction should
    # be printed since no packet was ever built.
    args = _base_args(job="buy_side_analysis", ticker="INFY")
    run.cmd_job(args)
    captured = capsys.readouterr()
    assert "[FAILED]" in captured.out
    assert "packet file" not in captured.out


# --- cmd_ingest_output side effects for the two new roles -----------------------


def test_ingest_output_sector_researcher_writes_research_reports_row(db_path, tmp_path):
    args = _base_args(job="sector_research", sector="it_technology")
    run.cmd_job(args)

    conn = _connect(db_path)
    prepared = conn.execute(
        "SELECT id, run_batch_id FROM agent_runs WHERE role = 'sector_researcher' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert prepared is not None

    output_payload = {
        "sector": "it_technology",
        "as_of_date": AS_OF.isoformat(),
        "cycle_phase": "expansion",
        "cycle_confidence": 0.6,
        "competitive_landscape": "Test landscape.",
        "value_chain_note": "Test value chain note.",
        "comparison_table": [],
        "top_picks": ["INFY"],
        "avoid_list": [],
        "key_risks": ["Test risk."],
        "sources": ["test"],
    }
    output_file = tmp_path / "sector_researcher_output.json"
    output_file.write_text(json.dumps(output_payload), encoding="utf-8")

    ingest_args = argparse.Namespace(ingest_output=prepared["id"], file=str(output_file))
    run.cmd_ingest_output(ingest_args)

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT ticker, report_type, status FROM research_reports WHERE report_type = 'SECTOR'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["ticker"] == "it_technology"
    assert row["status"] == "OK"


def test_ingest_output_buy_side_writes_research_reports_row_and_grid(db_path, tmp_path, capsys, _redirect_everything):
    _seed_instrument(db_path, 1, "INFY", "Information Technology")
    _drop_workspace_fixture(_redirect_everything["er_root"])

    args = _base_args(job="buy_side_analysis", ticker="INFY")
    run.cmd_job(args)

    conn = _connect(db_path)
    prepared = conn.execute(
        "SELECT id FROM agent_runs WHERE role = 'buy_side' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert prepared is not None

    output_payload = {
        "ticker": "INFY",
        "recommendation": "ACCUMULATE",
        "conviction": 0.65,
        "rerating_narrative": "Test narrative grounded in handoff numbers.",
        "catalysts": ["Test catalyst"],
        "eps_scenarios": [80.0, 85.0, 90.0, 95.0, 100.0],
        "pe_scenarios": [20.0, 22.0, 24.0, 26.0, 28.0],
        "scenario_reasoning": "Test reasoning.",
        "base_target_price": 2160.0,
        "invalidation_condition": "Two consecutive quarters of sub-5% YoY growth.",
    }
    output_file = tmp_path / "buy_side_output.json"
    output_file.write_text(json.dumps(output_payload), encoding="utf-8")

    ingest_args = argparse.Namespace(ingest_output=prepared["id"], file=str(output_file))
    run.cmd_ingest_output(ingest_args)
    captured = capsys.readouterr()

    assert "EPS x PE target-price grid" in captured.out
    # center cell: eps[2]=90 * pe[2]=24 == 2160 (matches base_target_price)
    assert "2160" in captured.out

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT ticker, report_type, rating FROM research_reports WHERE report_type = 'BUYSIDE'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["ticker"] == "INFY"
    assert row["rating"] == "ACCUMULATE"
