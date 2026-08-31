"""
Turns an accepted DocumentCandidate into a saved file on disk, plus a row
in a manifest so you can audit exactly what was downloaded, from where,
and how confident the (heuristic and/or LLM) classification was.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests

from disclosure_fetcher.config import INTER_REQUEST_DELAY, MAX_DOWNLOAD_BYTES, REQUEST_TIMEOUT
from disclosure_fetcher.models import DocumentCandidate
from disclosure_fetcher.utils import safe_filename

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_DOC_TYPE_DIRS = {
    "annual_report": "annual_reports",
    "quarterly_result": "quarterly_results",
    "half_yearly_result": "half_yearly_results",
    "earnings_transcript": "transcripts",
    "investor_presentation": "presentations",
    "special_disclosure": "special_disclosures",
}


def _guess_extension(url: str, content_type: str) -> str:
    for ext in (".pdf", ".pptx", ".ppt", ".docx", ".xlsx", ".zip"):
        if url.lower().endswith(ext):
            return ext
    if "pdf" in content_type:
        return ".pdf"
    if "presentation" in content_type or "powerpoint" in content_type:
        return ".pptx"
    return ".pdf"  # BSE/Screener filings are overwhelmingly PDFs


def _try_download(url: str, session: requests.Session) -> Optional[requests.Response]:
    try:
        resp = session.get(url, headers={"User-Agent": _UA}, timeout=REQUEST_TIMEOUT, stream=True)
    except requests.RequestException as exc:
        logger.info("Download request failed for %s: %s", url, exc)
        return None

    if resp.status_code != 200:
        return None

    content_type = resp.headers.get("Content-Type", "").lower()
    if "text/html" in content_type:
        # almost always a soft-404 / login page rather than the real file
        return None

    return resp


def download_candidate(
    candidate: DocumentCandidate,
    out_dir: Path,
    session: Optional[requests.Session] = None,
) -> bool:
    """Download `candidate.url` and, on success, set candidate.local_path.

    For BSE candidates specifically, tries the "AttachLive" URL first and
    falls back to "AttachHis" (older filings move between the two BSE
    storage buckets over time) - see candidate.raw["attachhis_url"].

    Returns True on success. Never raises; failures are logged and simply
    leave candidate.local_path as None so the pipeline can report a gap
    instead of crashing the whole run.
    """
    session = session or requests.Session()

    resp = _try_download(candidate.url, session)
    if resp is None and candidate.raw.get("attachhis_url"):
        time.sleep(INTER_REQUEST_DELAY)
        resp = _try_download(candidate.raw["attachhis_url"], session)

    if resp is None:
        logger.warning("Could not download %s (%s)", candidate.title, candidate.url)
        return False

    doc_dir = out_dir / _DOC_TYPE_DIRS.get(candidate.doc_type.value, "other")
    doc_dir.mkdir(parents=True, exist_ok=True)

    ext = _guess_extension(candidate.url, resp.headers.get("Content-Type", ""))
    stem = safe_filename(f"{candidate.period_label}__{candidate.source}__{candidate.title}")
    dest = doc_dir / f"{stem}{ext}"

    counter = 1
    while dest.exists():
        dest = doc_dir / f"{stem}_{counter}{ext}"
        counter += 1

    total = 0
    try:
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    logger.warning("Aborting download of %s - exceeded size cap", candidate.url)
                    fh.close()
                    dest.unlink(missing_ok=True)
                    return False
                fh.write(chunk)
    except OSError as exc:
        logger.warning("Could not write %s: %s", dest, exc)
        return False

    if total == 0:
        dest.unlink(missing_ok=True)
        return False

    candidate.local_path = str(dest)
    return True


def extract_first_page_text(path: str, max_pages: int = 2) -> str:
    """Best-effort text pull from the first couple of pages of a downloaded
    PDF, for an optional final sanity check. Returns "" for non-PDFs or on
    any extraction failure (encrypted/scanned/corrupt PDFs are common
    enough on these sites that this must never raise).
    """
    if not path.lower().endswith(".pdf"):
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = reader.pages[:max_pages]
        return " ".join((p.extract_text() or "") for p in pages)[:4000]
    except Exception as exc:
        logger.info("Could not extract text from %s: %s", path, exc)
        return ""


def write_manifest(candidates: list[DocumentCandidate], out_dir: Path) -> Path:
    """Write manifest.csv and manifest.json summarising every downloaded
    (or attempted) candidate, for auditing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "manifest.csv"
    json_path = out_dir / "manifest.json"

    rows = [
        {
            "doc_type": c.doc_type.value,
            "company": c.company,
            "period_label": c.period_label,
            "source": c.source,
            "title": c.title,
            "url": c.url,
            "announced_on": c.announced_on.isoformat() if c.announced_on else "",
            "heuristic_confidence": round(c.heuristic_confidence, 3),
            "llm_confidence": round(c.llm_confidence, 3) if c.llm_confidence is not None else "",
            "llm_reasoning": c.llm_reasoning,
            "local_path": c.local_path or "",
        }
        for c in candidates
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)

    return csv_path
