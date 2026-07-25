"""Console helpers for Windows-safe strategy output."""

from __future__ import annotations

import sys
from typing import Any, TextIO


def safe_print(value: Any = "", *, file: TextIO | None = None) -> None:
    """Print text after replacing characters unsupported by the console."""
    stream = file or sys.stdout
    encoding = stream.encoding or "utf-8"
    text = str(value).encode(encoding, errors="replace").decode(encoding)
    stream.write(text + "\n")


__all__ = ["safe_print"]
