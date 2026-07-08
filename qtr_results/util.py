"""Small shared helpers: number parsing and json-block extraction."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

_NUM_CLEAN_RE = re.compile(r"[,%₹\s]")
_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def parse_number(raw: Any) -> Optional[float]:
    """Parse a screener/CLI cell like '1,234', '12.5%', '-45', '' into a float.

    Returns ``None`` when the value is missing or non-numeric.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s or s in {"-", "--", "N/A", "NA"}:
        return None
    s = _NUM_CLEAN_RE.sub("", s)
    if s in {"", "-", "."}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pct_change(latest: Optional[float], base: Optional[float]) -> Optional[float]:
    """Percentage change from ``base`` to ``latest`` (guards divide-by-zero)."""
    if latest is None or base is None or base == 0:
        return None
    return (latest - base) / abs(base) * 100.0


def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Extract the last ```json {...}``` block from LLM output, if any."""
    if not text:
        return None
    matches = _JSON_BLOCK_RE.findall(text)
    for candidate in reversed(matches):
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            continue
    return None


def fmt_pct(value: Optional[float]) -> str:
    return f"{value:+.1f}%" if isinstance(value, (int, float)) else "n/a"


def fmt_price(value: Optional[float]) -> str:
    return f"Rs {value:,.2f}" if isinstance(value, (int, float)) else "n/a"


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def dedupe_preserve(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        key = it.strip().upper()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out
