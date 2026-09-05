"""Minimal Streamlit script that renders only the schedules page.

Used by ``tests/test_schedules_page.py`` through ``streamlit.testing.v1``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ui.pages import schedules_page  # noqa: E402

schedules_page()
