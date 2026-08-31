"""Offline tests for the Phase 5 meta-research proposal loop:

  - context.build_packet(role="meta_research") on empty vs. seeded DBs
  - run.py --ingest-output side effects for role="meta_research"
  - scripts/apply_meta_proposal.py staging flow on a throwaway tmp git repo

No LLM calls; no network. apply_meta_proposal tests spin up a real (tmp,
isolated) git repo since the script's whole job is git branch plumbing that
can't be meaningfully faked with a mock.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from afund.orchestrator import context
from afund.orchestrator import run as run_mod
from afund.memory import stores


# ---------------------------------------------------------------------------
# shared fixtures
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


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
def _redirect_packets_dir(tmp_path, monkeypatch):
    packets_dir = tmp_path / "packets"
    monkeypatch.setattr(context, "PACKETS_DIR", packets_dir)
    yield packets_dir


def _seed_decisions_and_calibration(conn):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector) VALUES (1, 'INFY', 'STOCK', 'Information Technology')"
    )
    conn.commit()

    decision_ids = []
    for i in range(8):
        did = stores.record_recommendation(
            conn, instrument_id=1, sector="Information Technology",
            action="NEW" if i % 2 == 0 else "HOLD", strategy_tag="cycle_contrarian",
            invalidation_condition="cond", fund_manager_rec_json=None, registry_version="v1",
        )
        conn.execute("UPDATE decision_log SET decision_date = ? WHERE id = ?", (f"2026-05-{i + 1:02d}", did))
        decision_ids.append(did)
    conn.commit()
    stores.record_human_decision(conn, decision_ids[0], "APPROVE")
    stores.record_human_decision(conn, decision_ids[1], "REJECT")

    for i in range(3):
        cid = stores.record_prediction(conn, decision_id=decision_ids[i], predicted_outcome="up", predicted_prob=0.7)
        if i < 2:
            stores.record_outcome(conn, cid, "up" if i == 0 else "down", realized_at="2026-05-20")

    return decision_ids


# ---------------------------------------------------------------------------
# context.build_packet(role="meta_research")
# ---------------------------------------------------------------------------


def test_meta_research_packet_empty_db_has_all_sections_and_insufficient_flag(conn):
    result = context.build_packet(
        conn, role="meta_research", trigger="meta_research_cycle", batch_id="b1", period="2026-Q2"
    )
    packet = result["packet"]

    assert packet["insufficient_episodic_data"] is True
    assert packet["episodic_summary"] == []
    assert packet["calibration"] == {"brier_score": None, "n_predictions": 0, "n_resolved": 0, "n_pending": 0}
    assert packet["open_theses_summary"] == {
        "active_count": 0, "watch_count": 0, "breached_count": 0, "oldest_unchecked": None,
    }
    assert packet["lessons_current"] == []
    assert packet["agent_quality"] == {"by_role": {}, "pipeline_failure_counts": {}}
    assert set(packet["registry_inventory"].keys()) == {
        "registry_version", "kpi_files", "strategy_files", "rule_files",
        "prompt_files", "agent_definition_files",
    }
    assert packet["human_decision_patterns"] == {}
    assert packet["period"] == "2026-Q2"
    assert packet["period_start"] == "2026-04-01"
    assert packet["period_end"] == "2026-06-30"


def test_meta_research_packet_seeded_db_correct_counts(conn):
    _seed_decisions_and_calibration(conn)

    result = context.build_packet(
        conn, role="meta_research", trigger="meta_research_cycle", batch_id="b1", period="2026-Q2"
    )
    packet = result["packet"]

    assert packet["insufficient_episodic_data"] is False
    assert len(packet["episodic_summary"]) == 8
    assert packet["calibration"]["brier_score"] is not None
    assert packet["calibration"]["n_predictions"] == 3
    assert packet["calibration"]["n_resolved"] == 2
    assert packet["calibration"]["n_pending"] == 1
    assert packet["human_decision_patterns"]["NEW"]["APPROVE"] == 1
    assert packet["human_decision_patterns"]["HOLD"]["REJECT"] == 1

    row = packet["episodic_summary"][0]
    assert set(row.keys()) == {
        "decision_id", "decision_date", "action", "instrument", "strategy_tag",
        "human_decision", "human_notes",
    }


def test_meta_research_packet_caps_episodic_rows_at_50(conn):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector) VALUES (1, 'INFY', 'STOCK', 'Information Technology')"
    )
    conn.commit()
    for i in range(60):
        did = stores.record_recommendation(
            conn, instrument_id=1, sector="Information Technology", action="HOLD",
            strategy_tag="t", invalidation_condition="c", fund_manager_rec_json=None, registry_version="v1",
        )
        conn.execute("UPDATE decision_log SET decision_date = ? WHERE id = ?", (f"2026-05-{(i % 28) + 1:02d}", did))
    conn.commit()

    result = context.build_packet(
        conn, role="meta_research", trigger="meta_research_cycle", batch_id="b1", period="2026-Q2"
    )
    packet = result["packet"]
    assert len(packet["episodic_summary"]) <= 50
    assert packet["insufficient_episodic_data"] is False


def test_meta_research_packet_defaults_period_to_current_quarter(conn):
    result = context.build_packet(conn, role="meta_research", trigger="meta_research_cycle", batch_id="b1")
    packet = result["packet"]
    assert packet["period"]  # non-empty, derived from today's date


def test_parse_period_quarter_month_year():
    assert context.parse_period("2026-Q2") == ("2026-04-01", "2026-06-30")
    assert context.parse_period("2026-Q1") == ("2026-01-01", "2026-03-31")
    assert context.parse_period("2026-06") == ("2026-06-01", "2026-06-30")
    assert context.parse_period("2026") == ("2026-01-01", "2026-12-31")


def test_parse_period_invalid_raises():
    with pytest.raises(ValueError):
        context.parse_period("not-a-period")
    with pytest.raises(ValueError):
        context.parse_period("2026-Q9")


# ---------------------------------------------------------------------------
# run.py --ingest-output for role="meta_research"
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "afund_test.db"
    c = _connect(path)
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    c.commit()
    c.close()
    return path


@pytest.fixture(autouse=True)
def _patch_run_module(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "get_conn", lambda: _connect(db_path))
    monkeypatch.setattr(run_mod, "PACKETS_DIR", tmp_path / "packets")
    monkeypatch.setattr(run_mod, "PROPOSALS_DIR", tmp_path / "proposals")


def _insert_agent_run(db_path: Path, role: str, batch_id: str = "test_batch") -> int:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO agent_runs (run_batch_id, role, model, backend, trigger, status, started_at)
            VALUES (?, ?, 'opus', 'claude_code', 'meta_research_cycle', 'PREPARED', ?)
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


def _valid_meta_output(target_file: str = "registry/rules/risk_limits.yaml") -> dict:
    return {
        "period": "2026-Q2",
        "patterns_found": ["Fund Manager overweights conviction on turnaround theses vs. calibration."],
        "proposals": [
            {
                "target_file": target_file,
                "change_type": "RULE_CHANGE",
                "rationale": "Turnaround theses have a higher realized miss rate than stated conviction implies.",
                "proposed_diff": "--- a/registry/rules/risk_limits.yaml\n+++ b/registry/rules/risk_limits.yaml\n@@\n-  note: null\n+  note: added conviction haircut\n",
            }
        ],
        "calibration_summary": "Brier score 0.29 over 2 resolved predictions this period.",
    }


def test_ingest_meta_research_writes_proposal_artifacts_and_leaves_registry_untouched(db_path, tmp_path, capsys):
    run_id = _insert_agent_run(db_path, "meta_research")
    out_file = tmp_path / "meta_output.json"
    out_file.write_text(json.dumps(_valid_meta_output()), encoding="utf-8")

    # Snapshot registry/'s git status BEFORE the ingest: the invariant is
    # that ingest changes NOTHING under registry/, not that the working tree
    # is pristine (legitimate in-flight registry work, e.g. an uncommitted
    # DRAFT strategy file awaiting human review, must not fail this test).
    status_before = subprocess.run(
        ["git", "status", "--porcelain", "--", "registry/"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    ).stdout

    _ingest(run_id, out_file)
    printed = capsys.readouterr().out

    proposals_dir = tmp_path / "proposals"
    json_path = proposals_dir / "2026-Q2_meta_proposal.json"
    md_path = proposals_dir / "2026-Q2_meta_proposal.md"
    assert json_path.exists()
    assert md_path.exists()

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["period"] == "2026-Q2"
    assert len(saved["proposals"]) == 1

    md_text = md_path.read_text(encoding="utf-8")
    assert "risk_limits.yaml" in md_text
    assert "RULE_CHANGE" in md_text
    assert "```diff" in md_text

    assert "target_file" in printed  # summary table header
    assert "risk_limits.yaml" in printed

    conn = _connect(db_path)
    status = conn.execute("SELECT status FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    assert status["status"] == "COMPLETED"
    conn.close()

    # The real repo's registry/ must never be touched by ingest (only the
    # proposal artifacts under the tmp proposals dir were written): the git
    # status of registry/ must be EXACTLY what it was before the ingest.
    status_after = subprocess.run(
        ["git", "status", "--porcelain", "--", "registry/"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    ).stdout
    assert status_after == status_before


def test_ingest_meta_research_refuses_target_outside_scope(db_path, tmp_path):
    run_id = _insert_agent_run(db_path, "meta_research")
    out_file = tmp_path / "meta_bad.json"
    out_file.write_text(json.dumps(_valid_meta_output(target_file="src/afund/db/schema.sql")), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        _ingest(run_id, out_file)
    assert excinfo.value.code == 1

    conn = _connect(db_path)
    row = conn.execute("SELECT status, error FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "FAILED"
    assert "outside the allowed scope" in row["error"]
    conn.close()

    proposals_dir = tmp_path / "proposals"
    assert not proposals_dir.exists() or not any(proposals_dir.iterdir())


def test_ingest_meta_research_empty_proposals_still_writes_artifacts(db_path, tmp_path):
    run_id = _insert_agent_run(db_path, "meta_research")
    output = {
        "period": "2026-Q2",
        "patterns_found": ["No systematic pattern found this cycle."],
        "proposals": [],
        "calibration_summary": "Insufficient data to score calibration this period.",
    }
    out_file = tmp_path / "meta_empty.json"
    out_file.write_text(json.dumps(output), encoding="utf-8")

    _ingest(run_id, out_file)

    proposals_dir = tmp_path / "proposals"
    assert (proposals_dir / "2026-Q2_meta_proposal.json").exists()
    assert (proposals_dir / "2026-Q2_meta_proposal.md").exists()


# ---------------------------------------------------------------------------
# scripts/apply_meta_proposal.py — real tmp git repo
# ---------------------------------------------------------------------------


def _init_tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "tmp_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)

    (repo / "registry" / "rules").mkdir(parents=True)
    (repo / "registry" / "rules" / "risk_limits.yaml").write_text("max_single_position_pct:\n  value: 10\n", encoding="utf-8")
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "fund_manager.md").write_text("---\nname: fund_manager\n---\nBody text.\n", encoding="utf-8")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")

    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=str(repo), check=True)
    return repo


def _load_apply_meta_proposal_module(repo_root: Path):
    """Import scripts/apply_meta_proposal.py with its REPO_ROOT monkeypatched
    to a tmp git repo. Re-imports fresh each time since the module computes
    REPO_ROOT at import time from __file__, not from cwd."""
    import importlib

    if "apply_meta_proposal" in sys.modules:
        del sys.modules["apply_meta_proposal"]
    module = importlib.import_module("apply_meta_proposal")
    importlib.reload(module)
    module.REPO_ROOT = repo_root
    return module


def test_apply_meta_proposal_creates_branch_and_leaves_main_untouched(tmp_path):
    repo = _init_tmp_repo(tmp_path)
    module = _load_apply_meta_proposal_module(repo)

    proposal = {
        "period": "2026-Q2",
        "proposals": [
            {
                "target_file": "registry/rules/risk_limits.yaml",
                "change_type": "RULE_CHANGE",
                "rationale": "test",
                "proposed_diff": "not a real unified diff, just free text guidance",
            }
        ],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    before_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True
    ).stdout.strip()
    before_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), capture_output=True, text=True
    ).stdout.strip()

    summary = module.apply_proposal(proposal_path)

    assert summary["branch"] == "meta/2026-Q2"
    assert summary["original_branch"] == before_branch

    after_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), capture_output=True, text=True
    ).stdout.strip()
    after_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True
    ).stdout.strip()
    assert after_branch == before_branch
    assert after_head == before_head  # main's HEAD commit unchanged

    working_tree_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(repo), capture_output=True, text=True
    ).stdout
    assert working_tree_status.strip() == ""  # main's working tree is clean

    branches = subprocess.run(
        ["git", "branch", "--list", "meta/2026-Q2"], cwd=str(repo), capture_output=True, text=True
    ).stdout
    assert "meta/2026-Q2" in branches

    # The fallback .proposed file should exist ON the branch, not on main.
    assert not (repo / "registry" / "rules" / "risk_limits.yaml.proposed").exists()
    show = subprocess.run(
        ["git", "show", "meta/2026-Q2:registry/rules/risk_limits.yaml.proposed"],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert show.returncode == 0
    assert "free text guidance" in show.stdout


def test_apply_meta_proposal_refuses_on_dirty_registry(tmp_path):
    repo = _init_tmp_repo(tmp_path)
    module = _load_apply_meta_proposal_module(repo)

    (repo / "registry" / "rules" / "risk_limits.yaml").write_text("dirty change\n", encoding="utf-8")

    proposal = {"period": "2026-Q2", "proposals": []}
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(module.ApplyProposalError, match="Refusing to run"):
        module.apply_proposal(proposal_path)


def test_apply_meta_proposal_refuses_target_outside_scope(tmp_path):
    repo = _init_tmp_repo(tmp_path)
    module = _load_apply_meta_proposal_module(repo)

    proposal = {
        "period": "2026-Q2",
        "proposals": [
            {"target_file": "README.md", "change_type": "RULE_CHANGE", "rationale": "x", "proposed_diff": "y"}
        ],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(module.ApplyProposalError, match="outside registry"):
        module.apply_proposal(proposal_path)

    # No branch should have been created for a rejected proposal set.
    branches = subprocess.run(
        ["git", "branch", "--list", "meta/2026-Q2"], cwd=str(repo), capture_output=True, text=True
    ).stdout
    assert "meta/2026-Q2" not in branches
