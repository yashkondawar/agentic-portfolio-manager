"""Offline tests for orchestrator --ingest-output: contract validation,
agent_runs status transitions, and role-specific DB side effects.

All against a tmp-path SQLite DB (run.get_conn monkeypatched); no network,
no LLM.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from afund.orchestrator import run as run_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "afund_test.db"
    conn = _connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _patch_run_module(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "get_conn", lambda: _connect(db_path))
    monkeypatch.setattr(run_mod, "PACKETS_DIR", tmp_path / "packets")


def _insert_agent_run(db_path: Path, role: str, batch_id: str = "test_batch") -> int:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO agent_runs (run_batch_id, role, model, backend, trigger, status, started_at)
            VALUES (?, ?, 'sonnet', 'claude_code', 'test_trigger', 'PREPARED', ?)
            """,
            (batch_id, role, dt.datetime.now(dt.timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _ingest(agent_runs_id: int, output_file: Path) -> None:
    args = argparse.Namespace(ingest_output=agent_runs_id, file=str(output_file))
    run_mod.cmd_ingest_output(args)


def test_news_processor_output_updates_staged_rows(db_path, tmp_path):
    conn = _connect(db_path)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    for i in range(3):
        conn.execute(
            """
            INSERT INTO news_items (event_scope, tag, impact, event_date, source, url, raw_title, raw_hash, fetched_at, processed)
            VALUES ('NA', NULL, 'NA', NULL, 'test_source', ?, ?, ?, ?, 0)
            """,
            (f"http://example.com/{i}", f"Headline {i}", f"hash{i}", now_iso),
        )
    conn.commit()
    conn.close()

    run_id = _insert_agent_run(db_path, "news_processor")
    output = {
        "items": [
            {
                "news_item_id": 1,
                "event_scope": "MICRO",
                "tag": "TCS",
                "impact": "POSITIVE",
                "description": "TCS wins large deal.",
                "event_date": "2026-07-01",
                "source": "test_source",
                "url": "http://example.com/0",
            },
            {
                # No id -> matched by url fallback.
                "news_item_id": None,
                "event_scope": "MACRO",
                "tag": "NA",
                "impact": "NA",
                "description": "RBI holds rates steady.",
                "event_date": "2026-07-02",
                "source": "test_source",
                "url": "http://example.com/1",
            },
        ],
        "injection_flags": [],
    }
    out_file = tmp_path / "np_output.json"
    out_file.write_text(json.dumps(output), encoding="utf-8")

    _ingest(run_id, out_file)

    conn = _connect(db_path)
    row1 = conn.execute("SELECT * FROM news_items WHERE id = 1").fetchone()
    assert row1["processed"] == 1
    assert row1["event_scope"] == "MICRO"
    assert row1["tag"] == "TCS"
    assert row1["impact"] == "POSITIVE"
    assert row1["description"] == "TCS wins large deal."
    assert row1["event_date"] == "2026-07-01"

    row2 = conn.execute("SELECT * FROM news_items WHERE url = 'http://example.com/1'").fetchone()
    assert row2["processed"] == 1
    assert row2["event_scope"] == "MACRO"

    row3 = conn.execute("SELECT * FROM news_items WHERE url = 'http://example.com/2'").fetchone()
    assert row3["processed"] == 0  # untouched — not in the agent output

    status = conn.execute("SELECT status, finished_at FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    assert status["status"] == "COMPLETED"
    assert status["finished_at"] is not None
    conn.close()


def test_fund_manager_new_creates_decision_thesis_and_escalates(db_path, tmp_path, capsys):
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector) VALUES (1, 'INFY', 'STOCK', 'Information Technology')"
    )
    conn.commit()
    conn.close()

    run_id = _insert_agent_run(db_path, "fund_manager")
    output = {
        "instrument": "INFY",
        "action": "NEW",
        "strategy_tag": "cycle_contrarian",
        "conviction": 0.7,
        "thesis_restatement": "Cyclical recovery underpriced.",
        "strongest_counter_and_response": "GenAI deflation; countered by deal-win data.",
        "invalidation_condition": "Two consecutive quarters of sub-5% growth.",
        "evidence_chain": ["Q1 results"],
        "size_or_weight_pct": 4.0,
        "calibration_note": None,
    }
    out_file = tmp_path / "fm_output.json"
    out_file.write_text(json.dumps(output), encoding="utf-8")

    _ingest(run_id, out_file)
    printed = capsys.readouterr().out

    conn = _connect(db_path)
    decision = conn.execute("SELECT * FROM decision_log").fetchone()
    assert decision is not None
    assert decision["action"] == "NEW"
    assert decision["human_decision"] == "PENDING"
    assert decision["instrument_id"] == 1
    assert decision["strategy_tag"] == "cycle_contrarian"
    # Reproducibility stamp: every decision carries the registry version
    # (git short SHA / registry-content hash) in force when it was recorded.
    assert decision["registry_version"], "decision_log.registry_version must be non-null"

    thesis = conn.execute("SELECT * FROM thesis_tracker").fetchone()
    assert thesis is not None
    assert thesis["status"] == "ACTIVE"
    assert thesis["instrument_id"] == 1
    assert thesis["decision_id"] == decision["id"]
    assert thesis["invalidation_condition"] == "Two consecutive quarters of sub-5% growth."
    conn.close()

    assert "ESCALATION" in printed  # NEW requires human approval


def test_fund_manager_hold_no_thesis_no_hard_escalation(db_path, tmp_path, capsys):
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector) VALUES (1, 'INFY', 'STOCK', 'Information Technology')"
    )
    conn.commit()
    conn.close()

    run_id = _insert_agent_run(db_path, "fund_manager")
    output = {
        "instrument": "INFY",
        "action": "HOLD",
        "strategy_tag": "cycle_contrarian",
        "conviction": 0.5,
        "thesis_restatement": "Thesis intact, no action.",
        "strongest_counter_and_response": "Momentum fading; not yet at invalidation.",
        "invalidation_condition": "Close below 200DMA for 10 sessions.",
        "evidence_chain": [],
        "size_or_weight_pct": None,
        "calibration_note": None,
    }
    out_file = tmp_path / "fm_hold.json"
    out_file.write_text(json.dumps(output), encoding="utf-8")

    _ingest(run_id, out_file)
    printed = capsys.readouterr().out

    conn = _connect(db_path)
    assert conn.execute("SELECT COUNT(*) c FROM decision_log").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM thesis_tracker").fetchone()["c"] == 0  # no NEW -> no thesis
    conn.close()
    assert "ESCALATION" not in printed
    assert "Light review" in printed


def test_macro_digest_output_adds_notes_and_marks_parsed(db_path, tmp_path):
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO newsletters (publisher, title, period, url, local_path, fetched_at, parsed)
        VALUES ('DSP_NETRA', 'DSP Netra 2026-06', '2026-06', 'http://x/n.pdf', 'data/raw/n.pdf', ?, 0)
        """,
        (dt.datetime.now(dt.timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()

    run_id = _insert_agent_run(db_path, "macro_digest")
    output = {
        "publisher": "DSP_NETRA",
        "period": "2026-06",
        "macro_notes": [
            {
                "tag_value": "india_liquidity",
                "content": "Liquidity surplus at 14-month high.",
                "source_ref": "newsletter:DSP_NETRA:2026-06",
            },
            {
                "tag_value": "global_rates",
                "content": "Fed cut expectations pushed to Q4.",
                "source_ref": "newsletter:DSP_NETRA:2026-06",
            },
        ],
        "regime_read": "Liquidity easing, valuations stretched.",
        "injection_flags": [],
    }
    out_file = tmp_path / "md_output.json"
    out_file.write_text(json.dumps(output), encoding="utf-8")

    _ingest(run_id, out_file)

    conn = _connect(db_path)
    notes = conn.execute("SELECT * FROM knowledge_base WHERE tag_type = 'MACRO' ORDER BY id").fetchall()
    assert len(notes) == 3  # 2 macro_notes + 1 regime_read
    tag_values = {n["tag_value"] for n in notes}
    assert {"india_liquidity", "global_rates", "regime_read"} == tag_values
    assert all(n["source_ref"] for n in notes)

    newsletter = conn.execute(
        "SELECT parsed FROM newsletters WHERE publisher = 'DSP_NETRA' AND period = '2026-06'"
    ).fetchone()
    assert newsletter["parsed"] == 1
    conn.close()


def test_invalid_output_marks_agent_run_failed(db_path, tmp_path):
    run_id = _insert_agent_run(db_path, "critique")
    out_file = tmp_path / "bad_output.json"
    out_file.write_text('{"instrument": "INFY"}', encoding="utf-8")  # missing required fields

    with pytest.raises(SystemExit) as excinfo:
        _ingest(run_id, out_file)
    assert excinfo.value.code == 1

    conn = _connect(db_path)
    row = conn.execute("SELECT status, error, finished_at FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "FAILED"
    assert row["error"]  # pydantic error summary recorded
    assert row["finished_at"] is not None
    conn.close()


def test_non_json_output_marks_agent_run_failed(db_path, tmp_path):
    run_id = _insert_agent_run(db_path, "synthesis")
    out_file = tmp_path / "junk.json"
    out_file.write_text("not json {{{", encoding="utf-8")

    with pytest.raises(SystemExit):
        _ingest(run_id, out_file)

    conn = _connect(db_path)
    row = conn.execute("SELECT status FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "FAILED"
    conn.close()


def test_fenced_output_file_accepted(db_path, tmp_path):
    run_id = _insert_agent_run(db_path, "synthesis")
    payload = {
        "instrument": "INFY",
        "house_view": "Constructive.",
        "supporting_logic": ["Deal wins"],
        "confidence_tier": "MEDIUM",
        "load_bearing_assumptions": ["Budgets recover"],
    }
    out_file = tmp_path / "fenced.json"
    out_file.write_text("```json\n" + json.dumps(payload) + "\n```", encoding="utf-8")

    _ingest(run_id, out_file)

    conn = _connect(db_path)
    row = conn.execute("SELECT status FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "COMPLETED"
    conn.close()


def test_stored_output_written_under_packet_outputs_dir(db_path, tmp_path):
    run_id = _insert_agent_run(db_path, "synthesis", batch_id="batchX")
    payload = {
        "instrument": "INFY",
        "house_view": "Constructive.",
        "supporting_logic": [],
        "confidence_tier": "LOW",
        "load_bearing_assumptions": [],
    }
    out_file = tmp_path / "s.json"
    out_file.write_text(json.dumps(payload), encoding="utf-8")

    _ingest(run_id, out_file)

    dest = tmp_path / "packets" / "batchX" / "outputs" / f"{run_id}_synthesis_output.json"
    assert dest.exists()
    stored = json.loads(dest.read_text(encoding="utf-8"))
    assert stored["instrument"] == "INFY"
