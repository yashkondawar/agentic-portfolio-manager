import json
import logging
from pathlib import Path

import pytest

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


def test_migrate_can_explicitly_replace_changed_mutable_state(tmp_path: Path):
    repo = tmp_path / "repo"
    state = repo / "qtr_results" / "state"
    state.mkdir(parents=True)
    ledger = state / "ledger.json"
    ledger.write_text('[{"symbol": "TCS"}]', encoding="utf-8")
    db_path = tmp_path / "portfolio.sqlite3"
    migrate_legacy_storage(repo, db_path=db_path)
    ledger.write_text('[{"symbol": "INFY"}]', encoding="utf-8")

    unchanged = migrate_legacy_storage(repo, db_path=db_path)
    replaced = migrate_legacy_storage(repo, replace_state=True, db_path=db_path)
    repeated = migrate_legacy_storage(repo, replace_state=True, db_path=db_path)

    assert unchanged["documents"] == 0
    assert replaced["documents"] == 1
    assert repeated["documents"] == 0
    assert get_document("qtr_results", "ledger", db_path=db_path) == [
        {"symbol": "INFY"}
    ]


def test_migrate_deduplicates_identical_reports_from_different_roots(
    tmp_path: Path,
):
    first_repo = tmp_path / "first"
    second_repo = tmp_path / "second"
    first_repo.mkdir()
    second_repo.mkdir()
    for repo in (first_repo, second_repo):
        (repo / "forensic_test.md").write_text("# Same report", encoding="utf-8")
    db_path = tmp_path / "portfolio.sqlite3"

    first = migrate_legacy_storage(first_repo, db_path=db_path)
    second = migrate_legacy_storage(second_repo, db_path=db_path)

    assert first["artifact_groups"] == 1
    assert second["artifact_groups"] == 0
    assert database_summary(db_path=db_path)["artifact_groups"] == 1


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


# ---------------------------------------------------------------------------
# Sharing market history
#
# The whole application - bars, bhavcopy, filings, reports, schedules, the
# Zerodha token - lives in ONE SQLite file. Scraping years of history takes
# hours, so sharing it is genuinely useful; sharing the file itself would hand
# over a live broker token and the owner's holdings.
# ---------------------------------------------------------------------------


def _seed_shareable_and_private(db_path: Path) -> None:
    import scraper.bhavcopy as bhavcopy
    from core.storage import connect

    bhavcopy.open_store(db_path).close()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO bhavcopy_days(trade_date, rows, source, fetched_at) "
            "VALUES ('2024-01-01', 42, 'udiff', '2024-01-02T00:00:00Z')"
        )
        conn.commit()

    # Exactly what zerodha/client.py and qtr_results/portfolio.py write.
    set_document("credentials", "zerodha_access_token", {"access_token": "SECRET"}, db_path=db_path)
    set_document("qtr_results", "portfolio", {"TCS": {"qty": 100}}, db_path=db_path)


def test_shared_copy_carries_market_history(tmp_path: Path):
    from core.storage import export_market_data

    db_path = tmp_path / "portfolio.sqlite3"
    _seed_shareable_and_private(db_path)

    counts = export_market_data(tmp_path / "share.sqlite3", db_path=db_path)
    assert counts["bhavcopy_days"] == 1


def test_shared_copy_cannot_leak_the_broker_token_or_holdings(tmp_path: Path):
    """The point of the allow-list. If this fails, do not ship."""
    import sqlite3

    from core.storage import export_market_data

    db_path = tmp_path / "portfolio.sqlite3"
    shared = tmp_path / "share.sqlite3"
    _seed_shareable_and_private(db_path)
    export_market_data(shared, db_path=db_path)

    conn = sqlite3.connect(shared)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "documents" not in tables
    assert "runs" not in tables
    assert "application_logs" not in tables
    conn.close()

    # Belt and braces: the secret must not appear anywhere in the bytes.
    assert b"SECRET" not in shared.read_bytes()


def test_shared_copy_refuses_to_overwrite(tmp_path: Path):
    from core.storage import export_market_data

    db_path = tmp_path / "portfolio.sqlite3"
    _seed_shareable_and_private(db_path)
    target = tmp_path / "share.sqlite3"
    target.write_bytes(b"precious")

    with pytest.raises(FileExistsError):
        export_market_data(target, db_path=db_path)
    assert target.read_bytes() == b"precious"


def test_importing_shared_history_onto_a_fresh_machine(tmp_path: Path):
    """The recipient has never scraped, so the tables do not exist yet."""
    from core.storage import export_market_data, import_market_data

    sender = tmp_path / "sender.sqlite3"
    shared = tmp_path / "share.sqlite3"
    receiver = tmp_path / "receiver.sqlite3"
    _seed_shareable_and_private(sender)
    export_market_data(shared, db_path=sender)

    added = import_market_data(shared, db_path=receiver)
    assert added["bhavcopy_days"] == 1


def test_importing_twice_adds_nothing_the_second_time(tmp_path: Path):
    from core.storage import export_market_data, import_market_data

    sender = tmp_path / "sender.sqlite3"
    shared = tmp_path / "share.sqlite3"
    receiver = tmp_path / "receiver.sqlite3"
    _seed_shareable_and_private(sender)
    export_market_data(shared, db_path=sender)

    import_market_data(shared, db_path=receiver)
    again = import_market_data(shared, db_path=receiver)
    assert sum(again.values()) == 0
