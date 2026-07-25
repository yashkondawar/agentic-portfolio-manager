from pathlib import Path

from core.run_history import get_run, list_runs, sanitize, save_run
from core.strategy import StrategyResult


def test_sanitize_redacts_nested_credentials():
    value = {
        "api_key": "secret",
        "nested": {"access_token": "token", "symbols": ["TCS"]},
    }
    assert sanitize(value) == {
        "api_key": "[REDACTED]",
        "nested": {"access_token": "[REDACTED]", "symbols": ["TCS"]},
    }


def test_run_history_round_trip(tmp_path: Path):
    db_path = tmp_path / "runs.sqlite3"
    result = StrategyResult(
        strategy_id="parallel_agents",
        status="completed",
        report="# Report",
        data={"decisions": {"TCS": {"action": "BUY"}}},
    )
    run_id = save_run(
        result,
        {"symbols": ["TCS"], "api_key": "never-store"},
        duration_ms=42,
        db_path=db_path,
    )

    rows = list_runs(db_path=db_path)
    assert rows[0]["id"] == run_id
    record = get_run(run_id, db_path=db_path)
    assert record is not None
    assert record["params"]["api_key"] == "[REDACTED]"
    assert record["data"] == result.data
