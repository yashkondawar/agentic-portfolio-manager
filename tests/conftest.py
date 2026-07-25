import os
import tempfile
from pathlib import Path

import pytest

_TEST_HISTORY = Path(tempfile.gettempdir()) / "trader_workbench_pytest.sqlite3"
os.environ["TRADER_WORKBENCH_DB"] = str(_TEST_HISTORY)


@pytest.fixture(scope="session", autouse=True)
def clean_test_history():
    _TEST_HISTORY.unlink(missing_ok=True)
    yield
    _TEST_HISTORY.unlink(missing_ok=True)
