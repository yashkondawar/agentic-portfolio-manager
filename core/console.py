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


def safe_write(chunk: Any = "", *, file: TextIO | None = None) -> None:
    """Stream text to the console without a newline, dropping unsupported chars.

    Streaming callbacks cannot use :func:`safe_print` because it appends a
    newline to every chunk. Windows consoles default to cp1252, so raw
    ``sys.stdout.write`` raises ``UnicodeEncodeError`` the moment a model emits
    a rupee sign or an emoji.
    """
    stream = file or sys.stdout
    encoding = stream.encoding or "utf-8"
    stream.write(str(chunk).encode(encoding, errors="replace").decode(encoding))
    stream.flush()


__all__ = ["safe_print", "safe_write"]
