import json
import logging
from pathlib import Path

from core.storage import (
    database_summary,
    export_artifact_group,
    get_artifact,
    get_cache,
    get_document,
    list_logs,
    migrate_legacy_storage,
    put_cache,
    save_artifacts,
    set_document,
)
from logging_config import SQLiteLogHandler


def test_storage_round_trips_documents_caches_and_artifacts(tmp_path: Path):
    db_path = tmp_path / "portfolio.sqlite3"

    set_document("strategy", "settings", {"enabled": True}, db_path=db_path)
    put_cache("prices", "TCS", b"payload", format="test", db_path=db_path)
    group_id, references = save_artifacts(
        "analysis",
        "test-run",
        {"report.md": "# Report", "data.json": {"symbol": "TCS"}},
        db_path=db_path,
    )

    assert get_document("strategy", "settings", db_path=db_path) == {"enabled": True}
    assert get_cache("prices", "TCS", db_path=db_path).payload == b"payload"
    assert references["report.md"].startswith(f"sqlite://artifacts/{group_id}/")
    assert get_artifact(group_id, "report.md", db_path=db_path).text == "# Report"

    exported = export_artifact_group(group_id, tmp_path / "export", db_path=db_path)
    assert {path.name for path in exported} == {"report.md", "data.json"}
    assert json.loads((tmp_path / "export" / "data.json").read_text()) == {
        "symbol": "TCS"
    }
    assert database_summary(db_path=db_path)["artifacts"] == 2


def test_migrate_legacy_storage_imports_state_and_artifacts(tmp_path: Path):
    repo = tmp_path / "repo"
    state = repo / "qtr_results" / "state"
    results = repo / "backtesting" / "swing_trading" / "results" / "run-1"
    state.mkdir(parents=True)
    results.mkdir(parents=True)
    (state / "ledger.json").write_text('[{"symbol": "TCS"}]', encoding="utf-8")
    (results / "summary.txt").write_text("complete", encoding="utf-8")
    db_path = tmp_path / "portfolio.sqlite3"

    imported = migrate_legacy_storage(repo, db_path=db_path)

    assert imported["documents"] == 1
    assert imported["artifact_groups"] == 1
    assert get_document("qtr_results", "ledger", db_path=db_path) == [
        {"symbol": "TCS"}
    ]

    second = migrate_legacy_storage(repo, db_path=db_path)
    assert second["documents"] == 0
    assert second["artifact_groups"] == 0


def test_sqlite_log_handler_persists_structured_logs(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "portfolio.sqlite3"))
    handler = SQLiteLogHandler()
    record = logging.LogRecord(
        "storage-test", logging.ERROR, __file__, 1, "failed %s", ("cleanly",), None
    )
    record.session_id = "session-1"
    record.agent_id = "agent-1"

    handler.emit(record)
    handler.close()

    rows = list_logs(level="ERROR")
    assert rows[0]["message"] == "failed cleanly"
    assert rows[0]["session_id"] == "session-1"
