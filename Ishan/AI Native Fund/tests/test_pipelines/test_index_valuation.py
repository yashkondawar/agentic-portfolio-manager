"""Offline parser test for index_valuation.py's allIndices response shape.
No network — exercises the same field-extraction logic as
fetch_current_snapshot() but against a saved fixture instead of a live call.
"""
from __future__ import annotations

import json
from pathlib import Path

from afund.data.index_valuation import TARGET_INDICES, _float_or_none

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _extract_rows(payload: dict) -> list[dict]:
    """Mirrors fetch_current_snapshot()'s row-extraction loop, but operating
    on an already-parsed dict instead of a live requests.Response."""
    rows = []
    for entry in payload.get("data", []):
        if entry.get("index") in TARGET_INDICES:
            rows.append(
                {
                    "index_name": entry["index"],
                    "close": _float_or_none(entry.get("last")),
                    "pe": _float_or_none(entry.get("pe")),
                    "pb": _float_or_none(entry.get("pb")),
                    "div_yield": _float_or_none(entry.get("dy")),
                }
            )
    return rows


def test_extracts_all_four_target_indices():
    payload = json.loads((FIXTURES / "nse_all_indices_sample.json").read_text(encoding="utf-8"))
    rows = _extract_rows(payload)
    names = {r["index_name"] for r in rows}
    assert names == set(TARGET_INDICES)


def test_nifty_50_values():
    payload = json.loads((FIXTURES / "nse_all_indices_sample.json").read_text(encoding="utf-8"))
    rows = _extract_rows(payload)
    nifty50 = next(r for r in rows if r["index_name"] == "NIFTY 50")
    assert nifty50["close"] == 24270.85
    assert nifty50["pe"] == 20.92
    assert nifty50["pb"] == 3.17
    assert nifty50["div_yield"] == 1.25


def test_float_or_none_handles_blank_and_missing():
    assert _float_or_none("") is None
    assert _float_or_none(None) is None
    assert _float_or_none("20.92") == 20.92
    assert _float_or_none("not-a-number") is None
