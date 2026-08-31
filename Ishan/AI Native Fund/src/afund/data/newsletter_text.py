"""Newsletter PDF text extraction (pure python, pypdf — no LLM, no network).

Feeds the macro_digest agent: the monthly_newsletter_digest pipeline
extracts each unparsed newsletter's text here, sanitizes it
(afund.agents.sanitize), and embeds it in the agent's context packet.
"""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

DEFAULT_MAX_CHARS = 15000

TRUNCATION_SUFFIX = "...[truncated]"


def extract_newsletter_text(local_path: str | Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Extract plain text from a newsletter PDF, capped at max_chars.

    Uses pypdf's per-page text extraction, joining pages with blank lines.
    Note on source quality: DSP Netra is chart-heavy — many of its pages are
    images with little or no extractable text layer, so the extracted text
    may be sparse; extract what exists rather than failing. Aequitas
    ("Top Down Bottom Up") is mostly prose and extracts well.

    Raises FileNotFoundError if the path doesn't exist; pypdf errors on a
    corrupt PDF propagate to the caller (which treats a single bad PDF as
    non-fatal for the batch).
    """
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"newsletter PDF not found: {path}")

    reader = PdfReader(str(path))
    pages_text: list[str] = []
    total = 0
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        pages_text.append(text)
        total += len(text)
        if total >= max_chars:
            break

    combined = "\n\n".join(pages_text)
    if len(combined) > max_chars:
        keep = max(max_chars - len(TRUNCATION_SUFFIX), 0)
        combined = combined[:keep] + TRUNCATION_SUFFIX
    return combined
