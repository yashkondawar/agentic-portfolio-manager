import os
import logging
import tempfile
import uuid
from pathlib import Path

import pytest

_TEST_STORAGE = (
    Path(tempfile.gettempdir()) / f"agentic_portfolio_pytest_{uuid.uuid4().hex}.sqlite3"
)
os.environ["PORTFOLIO_DB_PATH"] = str(_TEST_STORAGE)


def _remove_test_storage() -> None:
    for path in (
        _TEST_STORAGE,
        Path(f"{_TEST_STORAGE}-shm"),
        Path(f"{_TEST_STORAGE}-wal"),
    ):
        path.unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def clean_test_history():
    yield
    logging.shutdown()
    _remove_test_storage()
