"""
Small stand-alone helpers used across the pipeline. Kept dependency-light
and unit-testable without any network access.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

# Matches phrases BSE/company filings commonly use to state the period a
# result covers, e.g. "quarter ended 30th September, 2024", "year ended
# March 31, 2024", "half year ended September 30 2024".
_PERIOD_END_RE = re.compile(
    r"(?:ended|ending)\s+(?:on\s+)?"
    r"([0-3]?\d(?:st|nd|rd|th)?\s+\w+,?\s+\d{4}|\w+\s+[0-3]?\d,?\s+\d{4})",
    re.IGNORECASE,
)


def indian_fy_quarter(d: date) -> tuple[int, int]:
    """Return (quarter_number, fy_end_year) for an Indian fiscal year (Apr-Mar).

    e.g. 2024-07-15 -> (2, 2025)  meaning Q2 of FY ending March 2025 ("Q2 FY25")
         2025-02-01 -> (4, 2025)  meaning Q4 of FY ending March 2025 ("Q4 FY25")
    """
    shifted_month = (d.month - 4) % 12   # 0 for April ... 11 for March
    quarter = shifted_month // 3 + 1
    fy_end_year = d.year + 1 if d.month >= 4 else d.year
    return quarter, fy_end_year


def indian_fy_half(d: date) -> tuple[int, int]:
    """Return (half_number [1 or 2], fy_end_year)."""
    quarter, fy_end_year = indian_fy_quarter(d)
    half = 1 if quarter <= 2 else 2
    return half, fy_end_year


def quarter_label(d: date) -> str:
    q, fy = indian_fy_quarter(d)
    return f"Q{q} FY{str(fy)[-2:]}"


def half_year_label(d: date) -> str:
    h, fy = indian_fy_half(d)
    return f"H{h} FY{str(fy)[-2:]}"


def annual_label(d: date) -> str:
    """Annual reports/full-year results are labelled by the FY they close."""
    _, fy = indian_fy_quarter(d)
    return f"FY{str(fy)[-2:]}"


def quarter_sort_key(d: date) -> str:
    q, fy = indian_fy_quarter(d)
    return f"{fy}-Q{q}"


def half_sort_key(d: date) -> str:
    h, fy = indian_fy_half(d)
    return f"{fy}-H{h}"


def annual_sort_key(d: date) -> str:
    _, fy = indian_fy_quarter(d)
    return f"{fy}-FY"


def quarter_start_date(quarter: int, fy_end_year: int) -> date:
    """First calendar day of the given fiscal quarter."""
    month = {1: 4, 2: 7, 3: 10, 4: 1}[quarter]
    year = fy_end_year - 1 if quarter != 4 else fy_end_year
    return date(year, month, 1)


def prev_quarter(quarter: int, fy_end_year: int) -> tuple[int, int]:
    if quarter == 1:
        return 4, fy_end_year - 1
    return quarter - 1, fy_end_year


def half_start_date(half: int, fy_end_year: int) -> date:
    """First calendar day of the given fiscal half (1=Apr-Sep, 2=Oct-Mar)."""
    month = 4 if half == 1 else 10
    return date(fy_end_year - 1, month, 1)


def prev_half(half: int, fy_end_year: int) -> tuple[int, int]:
    if half == 1:
        return 2, fy_end_year - 1
    return 1, fy_end_year


def recent_quarters(
    n: int, as_of: Optional[date] = None, buffer_days: int = 20
) -> list[tuple[str, str]]:
    """Last n *completed* quarters as of `as_of`, most recent first.

    Returns a list of (period_label, period_sort_key) tuples, e.g.
    [("Q1 FY26", "2026-Q1"), ("Q4 FY25", "2025-Q4"), ...]

    A quarter only counts as "completed" (worth expecting a result for)
    once `buffer_days` have passed since its end, since companies get up
    to 45 days post quarter-end to file results under SEBI LODR. This
    walks backward one quarter at a time until it has collected n valid
    quarters - robust no matter how many recent quarters get skipped by
    the buffer near a quarter boundary (fixes an earlier off-by-one where
    collecting a fixed n+1 window under-returned near quarter edges).
    """
    as_of = as_of or date.today()
    q, fy = indian_fy_quarter(as_of)
    out: list[tuple[str, str]] = []
    guard = 0
    while len(out) < n and guard < n + 20:
        guard += 1
        end = quarter_start_date(q, fy) + relativedelta(months=3, days=-1)
        if (as_of - end).days >= buffer_days:
            out.append((quarter_label(end), quarter_sort_key(end)))
        q, fy = prev_quarter(q, fy)
    return out


def recent_halves(
    n: int, as_of: Optional[date] = None, buffer_days: int = 20
) -> list[tuple[str, str]]:
    """Last n *completed* fiscal halves as of `as_of`, most recent first."""
    as_of = as_of or date.today()
    h, fy = indian_fy_half(as_of)
    out: list[tuple[str, str]] = []
    guard = 0
    while len(out) < n and guard < n + 10:
        guard += 1
        end = half_start_date(h, fy) + relativedelta(months=6, days=-1)
        if (as_of - end).days >= buffer_days:
            out.append((half_year_label(end), half_sort_key(end)))
        h, fy = prev_half(h, fy)
    return out


def recent_annual_years(n: int, as_of: Optional[date] = None) -> list[tuple[str, str]]:
    """Last n fiscal years whose annual report should plausibly be public.

    Annual reports/AGMs typically land 4-6 months after FY close (e.g. FY24,
    ending March 2024, gets its AGM + annual report around July-Sept 2024).
    A 90-day buffer is used since annual reports trail further behind the
    FY-end than quarterly results do.
    """
    as_of = as_of or date.today()
    _, current_fy = indian_fy_quarter(as_of)
    out: list[tuple[str, str]] = []
    fy = current_fy
    guard = 0
    while len(out) < n and guard < n + 5:
        guard += 1
        fy_end = date(fy, 3, 31)
        if (as_of - fy_end).days >= 90:
            out.append((f"FY{str(fy)[-2:]}", f"{fy}-FY"))
        fy -= 1
    return out


def extract_period_end_date(text: str) -> Optional[date]:
    """Best-effort extraction of the period-end date from a filing's title."""
    m = _PERIOD_END_RE.search(text)
    if not m:
        return None
    try:
        return dateparser.parse(m.group(1), dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def safe_filename(text: str, max_len: int = 80) -> str:
    keep = "".join(c if c.isalnum() or c in " -_." else "_" for c in text)
    keep = re.sub(r"_+", "_", keep).strip("_ ")
    return keep[:max_len] or "file"


# Windows refuses paths over MAX_PATH (260) unless LongPathsEnabled is set, and it
# is off by default. safe_filename() bounds the *filename* at 80 chars but nothing
# bounded the *full path*, so a deep output directory produced a FileNotFoundError
# from write_bytes/open — which reads like a missing directory and is actually a
# too-long path. Hit for real by tests/test_offline.py at a 184-char output dir
# (268-char total). A user pointing --output-dir at a deep tree would hit the same.
_MAX_PATH = 260
_PATH_SAFETY_MARGIN = 12  # room for the "_1", "_2" … de-duplication suffixes below


def bounded_dest(doc_dir: Path, stem: str, ext: str, max_path: int = _MAX_PATH) -> Path:
    """`doc_dir / (stem + ext)`, with `stem` shortened just enough that the absolute
    path fits the platform limit. Shortens rather than fails: a truncated filename
    is recoverable, a crashed fetch loop is not. Returns the path unchanged on
    platforms without the limit, or when it already fits.
    """
    dest = doc_dir / f"{stem}{ext}"
    if os.name != "nt":
        return dest
    budget = max_path - _PATH_SAFETY_MARGIN - len(str(doc_dir.resolve())) - len(os.sep) - len(ext)
    if budget >= len(stem):
        return dest
    if budget < 8:
        # Directory alone is near the limit — a readable name is impossible, so use a
        # short stable hash and let the caller's manifest carry the real title.
        short = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8]
        return doc_dir / f"{short}{ext}"
    return doc_dir / f"{stem[:budget].rstrip('_ ')}{ext}"
