"""Regression tests for discovery prioritisation in the live qtr_results engine.

On a busy earnings day NSE returns 100+ result-declarers, mostly illiquid
micro-caps, but only ``max_analyze`` get verified. ``_prioritize_declarers``
must reorder them so watchlist + liquid index names are verified first, so a
notable large/mid-cap (the GESHIP regression) is never truncated behind
same-day micro-caps. These tests pin that ordering without hitting the network.
"""

from __future__ import annotations

import qtr_results.engine as engine


def _declarer(symbol, sources=None, result_date="2026-08-03"):
    return {"symbol": symbol, "sources": sources or ["nse"], "result_date": result_date}


def test_liquid_names_are_promoted_ahead_of_microcaps(monkeypatch):
    liquid = {"GESHIP", "MARICO"}
    monkeypatch.setattr(engine, "is_liquid", lambda s: s in liquid)

    # 40 micro-caps, then the liquid name last (raw calendar order = recency).
    declarers = [_declarer(f"MICRO{i}") for i in range(40)] + [_declarer("GESHIP")]
    ranked = [d["symbol"] for d in engine._prioritize_declarers(declarers)]

    # GESHIP was at index 40 (would be cut at max_analyze=40); now it is first.
    assert ranked[0] == "GESHIP"
    assert ranked.index("GESHIP") < 40


def test_watchlist_beats_liquid_beats_rest(monkeypatch):
    liquid = {"LIQ"}
    monkeypatch.setattr(engine, "is_liquid", lambda s: s in liquid)

    declarers = [
        _declarer("PLAIN", sources=["nse"]),
        _declarer("LIQ", sources=["nse"]),
        _declarer("WATCHED", sources=["watchlist"]),
    ]
    ranked = [d["symbol"] for d in engine._prioritize_declarers(declarers)]

    assert ranked == ["WATCHED", "LIQ", "PLAIN"]


def test_sort_is_stable_within_a_tier(monkeypatch):
    monkeypatch.setattr(engine, "is_liquid", lambda s: True)

    declarers = [_declarer("A"), _declarer("B"), _declarer("C")]
    ranked = [d["symbol"] for d in engine._prioritize_declarers(declarers)]

    # All same tier -> original (recency) order preserved.
    assert ranked == ["A", "B", "C"]


def test_prioritize_is_non_destructive(monkeypatch):
    monkeypatch.setattr(engine, "is_liquid", lambda s: s == "GESHIP")

    declarers = [_declarer("MICRO"), _declarer("GESHIP")]
    ranked = engine._prioritize_declarers(declarers)

    # Nothing dropped, and original list object is not mutated in place.
    assert {d["symbol"] for d in ranked} == {"MICRO", "GESHIP"}
    assert [d["symbol"] for d in declarers] == ["MICRO", "GESHIP"]
