"""Orchestration for the Phase 7 cycle engine: run all live cycles for a
scope (or --all scopes), write cycle_assessments rows (narrative fields
NULL until the narrative_intensity agent ingests), compute the composite
allocation decision, and write composite_decisions.

CLI:
    python -m afund.cycles.assess --scope "NIFTY 50"
    python -m afund.cycles.assess --all
    python -m afund.cycles.assess --scope "NIFTY 50" --date 2026-07-03

Called by orchestrator/router.py's weekly_cycle_assessment trigger as
"py:afund.cycles.assess.run_all" (first step) and
"py:afund.cycles.assess.finalize" (last step, after narrative_intensity
ingestion — recomputes composite_decisions picking up the newly-ingested
narrative_intensity_score/reconciliation fields).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afund.config import load_settings
from afund.cycles import anchors, classify, composite, parabolic
from afund.cycles.framework import CycleFramework, load as load_framework
from afund.db.connection import get_conn

try:
    from knowledge.loader import load as load_knowledge
except ImportError:  # pragma: no cover
    load_knowledge = None  # type: ignore

MARKET_SCOPES = ["NIFTY 50", "NIFTY 500"]


def _sector_scopes() -> list[str]:
    settings = load_settings()
    sector_index_map = settings.get("sector_index_map", {})
    # Exclude 'generic' and the '_secondary' entries from the primary sector
    # scope loop — 'generic' maps to NIFTY 500 (already a market scope) and
    # '_secondary' entries are supplementary indices, not distinct sectors.
    return [
        slug for slug in sector_index_map
        if slug != "generic" and not slug.endswith("_secondary")
    ]


def all_scopes() -> list[str]:
    return MARKET_SCOPES + _sector_scopes()


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _reading_from_anchor(
    framework: CycleFramework,
    anchor: "anchors.AnchorSeries",
) -> tuple[classify.DirectionReading | None, float | None]:
    """Reduce an AnchorSeries to (DirectionReading, percentile), or
    (None, None) if data_pending or history too thin."""
    if anchor.data_pending or anchor.current is None or len(anchor.history) < 10:
        return None, None

    history_values = [v for _, v in anchor.history]
    percentile = classify.percentile_rank(anchor.current, history_values)
    if percentile is None:
        return None, None

    direction_cfg = framework.direction

    def _value_n_months_ago(months: int) -> float | None:
        target_date = (dt.date.fromisoformat(anchor.as_of_date) - dt.timedelta(days=round(months * 30.4375))).isoformat()
        candidates = [(d, v) for d, v in anchor.history if d <= target_date]
        if not candidates:
            return None
        return candidates[-1][1]

    roc_3m = classify.roc_pct(anchor.current, _value_n_months_ago(3)) if _value_n_months_ago(3) is not None else None
    roc_6m = classify.roc_pct(anchor.current, _value_n_months_ago(6)) if _value_n_months_ago(6) is not None else None
    roc_12m = classify.roc_pct(anchor.current, _value_n_months_ago(12)) if _value_n_months_ago(12) is not None else None

    direction = classify.classify_direction(roc_3m, roc_6m, roc_12m, direction_cfg.flat_threshold_pct)

    # momentum-of-momentum: compare the most recent 3m RoC against the 3m
    # RoC measured one window (3 months) earlier.
    value_6m_ago = _value_n_months_ago(6)
    value_3m_ago = _value_n_months_ago(3)
    roc_prior = classify.roc_pct(value_3m_ago, value_6m_ago) if (value_3m_ago is not None and value_6m_ago is not None) else None
    momentum_state = classify.classify_momentum_of_momentum(
        roc_3m, roc_prior, direction_cfg.momentum_of_momentum.stable_threshold_pct
    )

    reading = classify.DirectionReading(
        roc_3m=roc_3m, roc_6m=roc_6m, roc_12m=roc_12m,
        direction=direction, momentum_state=momentum_state,
    )
    return reading, percentile


def _assess_sentiment(
    conn: sqlite3.Connection,
    framework: CycleFramework,
    scope: str,
    as_of: str,
) -> dict:
    """Sentiment/behavioral cycle: breadth (pct_above_200dma) blended with
    INDIA_VIX (Phase 8). india_vix is fear_type, so it is INVERTED at
    scoring time (knowledge/references/kpi_interpretation/
    sentiment_cycle.md: 'Fear-type: INVERT before scoring' — high VIX =
    capitulation = LOW sentiment percentile; the kpi yaml stores the raw,
    non-inverted series and delegates inversion to this scoring layer via
    orientation: fear_type).

    Combination rules (DRAFT judgment call, disclosed in the row note):
      - both available: percentile = mean(breadth_pct, 100 - vix_pct);
        direction/momentum from the breadth series (the primary trend
        gauge, unchanged from Phase 7 behavior)
      - breadth only: Phase 7 behavior exactly
      - VIX only: classify on the NEGATED VIX series (negation flips both
        the percentile and the RoC direction coherently)
      - neither: honest data_pending naming both
    """
    catalog_cycle_id = anchors.CATALOG_CYCLE_MAP["sentiment_breadth"]
    breadth = anchors.sentiment_breadth_anchor(conn, scope=scope, as_of=as_of)
    vix = anchors.india_vix_anchor(conn, scope=scope, as_of=as_of)

    base_row = {
        "cycle_id": catalog_cycle_id,
        "scope": scope,
        "as_of_date": as_of,
        "framework_version": framework.content_version,
        "created_at": _now_iso(),
    }

    breadth_reading, breadth_pct = _reading_from_anchor(framework, breadth)
    breadth_ok = breadth_reading is not None and breadth_pct is not None

    vix_pct = None
    if not vix.data_pending and vix.current is not None and len(vix.history) >= 10:
        vix_pct = classify.percentile_rank(vix.current, [v for _, v in vix.history])

    if not breadth_ok and vix_pct is None:
        missing = list(dict.fromkeys((breadth.missing_kpis or ["breadth_200dma"])
                                     + (vix.missing_kpis or ["india_vix"])))
        base_row.update({
            "percentile": None, "direction": None, "momentum_state": None,
            "phase_id": None, "directional_lean": None, "quant_score": None,
            "data_pending": 1,
            "missing_kpis_json": json.dumps(missing),
            "contributing_kpis": json.dumps([]),
            "note": f"breadth: {breadth.note}; india_vix: {vix.note}",
        })
        return base_row

    if breadth_ok and vix_pct is not None:
        percentile = (breadth_pct + (100.0 - vix_pct)) / 2.0
        reading = breadth_reading
        contributing = ["pct_above_200dma", "india_vix"]
        note = (
            f"blended: breadth pct {breadth_pct:.1f} + inverted INDIA_VIX "
            f"(vix {vix.current:.2f}, pct {vix_pct:.1f} -> inverted {100.0 - vix_pct:.1f}, "
            f"fear_type) -> {percentile:.1f}; direction/momentum from breadth; {breadth.note}"
        )
    elif breadth_ok:
        percentile = breadth_pct
        reading = breadth_reading
        contributing = ["pct_above_200dma"]
        note = f"{breadth.note}; india_vix unavailable for blending ({vix.note})"
    else:
        # VIX only: negate the series so the generic reduction yields a
        # sentiment-oriented percentile AND direction (VIX falling ->
        # sentiment rising).
        inverted = anchors.AnchorSeries(
            cycle_id=catalog_cycle_id,
            scope=scope,
            metric_name="india_vix_inverted",
            as_of_date=as_of,
            current=-vix.current,
            history=[(d, -v) for d, v in vix.history],
            data_pending=False,
            note=vix.note,
        )
        reading, percentile = _reading_from_anchor(framework, inverted)
        if reading is None or percentile is None:
            base_row.update({
                "percentile": None, "direction": None, "momentum_state": None,
                "phase_id": None, "directional_lean": None, "quant_score": None,
                "data_pending": 1,
                "missing_kpis_json": json.dumps(["breadth_200dma"]),
                "contributing_kpis": json.dumps([]),
                "note": f"breadth pending ({breadth.note}); inverted-VIX reduction also failed ({vix.note})",
            })
            return base_row
        contributing = ["india_vix"]
        note = (
            f"breadth pending ({breadth.note}); sentiment read from inverted INDIA_VIX alone "
            f"(vix {vix.current:.2f}, fear_type inverted)"
        )

    phase = classify.classify_phase(framework, percentile, reading)
    base_row.update({
        "percentile": percentile,
        "direction": reading.direction,
        "momentum_state": reading.momentum_state,
        "phase_id": phase.phase_id,
        "directional_lean": phase.directional_lean,
        "quant_score": phase.directional_lean * 100.0,
        "data_pending": 0,
        "missing_kpis_json": json.dumps([]),
        "contributing_kpis": json.dumps(contributing),
        "note": note,
    })
    return base_row


def assess_live_cycle(
    conn: sqlite3.Connection,
    framework: CycleFramework,
    engine_cycle_name: str,
    scope: str,
    as_of: str,
) -> dict:
    """Run one of the 5 live cycles for one scope, returning a dict ready
    for cycle_assessments upsert. Never fabricates: if the anchor is
    data_pending, the returned dict carries data_pending=1 honestly."""
    catalog_cycle_id = anchors.CATALOG_CYCLE_MAP[engine_cycle_name]

    if engine_cycle_name == "valuation":
        anchor = anchors.valuation_anchor(conn, scope, as_of=as_of)
    elif engine_cycle_name == "earnings":
        anchor = anchors.earnings_anchor(conn, scope, as_of=as_of)
    elif engine_cycle_name == "sentiment_breadth":
        # Sentiment blends breadth + INDIA_VIX (fear_type) — handled by a
        # dedicated path since it combines two anchors.
        return _assess_sentiment(conn, framework, scope, as_of)
    elif engine_cycle_name == "commodity":
        anchor = anchors.commodity_anchor(conn, scope=scope, as_of=as_of)
    elif engine_cycle_name == "global_risk_dollar":
        anchor = anchors.global_risk_dollar_anchor(scope=scope, as_of=as_of)
    elif engine_cycle_name == "rate_liquidity":
        anchor = anchors.rate_liquidity_anchor(conn, scope=scope, as_of=as_of)
    elif engine_cycle_name == "credit":
        anchor = anchors.credit_anchor(conn, scope=scope, as_of=as_of)
    elif engine_cycle_name == "currency":
        anchor = anchors.currency_anchor(conn, scope=scope, as_of=as_of)
    elif engine_cycle_name == "inflation":
        anchor = anchors.inflation_anchor(conn, scope=scope, as_of=as_of)
    elif engine_cycle_name == "flows":
        anchor = anchors.flows_anchor(conn, scope=scope, as_of=as_of)
    else:
        raise ValueError(f"unknown live cycle {engine_cycle_name!r}")

    base_row = {
        "cycle_id": catalog_cycle_id,
        "scope": scope,
        "as_of_date": as_of,
        "framework_version": framework.content_version,
        "created_at": _now_iso(),
    }

    if anchor.data_pending:
        base_row.update({
            "percentile": None, "direction": None, "momentum_state": None,
            "phase_id": None, "directional_lean": None, "quant_score": None,
            "data_pending": 1,
            "missing_kpis_json": json.dumps(anchor.missing_kpis),
            "contributing_kpis": json.dumps([]),
            "note": anchor.note,
        })
        return base_row

    reading, percentile = _reading_from_anchor(framework, anchor)
    if reading is None or percentile is None:
        base_row.update({
            "percentile": None, "direction": None, "momentum_state": None,
            "phase_id": None, "directional_lean": None, "quant_score": None,
            "data_pending": 1,
            "missing_kpis_json": json.dumps([anchor.metric_name]),
            "contributing_kpis": json.dumps([]),
            "note": f"insufficient history to classify ({len(anchor.history)} points): {anchor.note}",
        })
        return base_row

    phase = classify.classify_phase(framework, percentile, reading)
    base_row.update({
        "percentile": percentile,
        "direction": reading.direction,
        "momentum_state": reading.momentum_state,
        "phase_id": phase.phase_id,
        "directional_lean": phase.directional_lean,
        "quant_score": phase.directional_lean * 100.0,
        "data_pending": 0,
        "missing_kpis_json": json.dumps([]),
        "contributing_kpis": json.dumps([anchor.metric_name]),
        "note": anchor.note,
    })
    return base_row


def assess_data_pending_cycles(scope: str, as_of: str, framework_version: str) -> list[dict]:
    """Honest data_pending rows for the 11 non-live catalog cycles."""
    live_catalog_ids = set(anchors.CATALOG_CYCLE_MAP.values())
    rows = []
    for catalog_cycle_id in anchors.ALL_CATALOG_CYCLE_IDS:
        if catalog_cycle_id in live_catalog_ids:
            continue
        anchor = anchors.data_pending_anchor(catalog_cycle_id, scope, as_of=as_of)
        rows.append({
            "cycle_id": catalog_cycle_id,
            "scope": scope,
            "as_of_date": as_of,
            "framework_version": framework_version,
            "percentile": None, "direction": None, "momentum_state": None,
            "phase_id": None, "directional_lean": None, "quant_score": None,
            "data_pending": 1,
            "missing_kpis_json": json.dumps(anchor.missing_kpis),
            "contributing_kpis": json.dumps([]),
            "note": anchor.note,
            "created_at": _now_iso(),
        })
    return rows


def upsert_cycle_assessment(conn: sqlite3.Connection, row: dict) -> None:
    """Idempotent upsert keyed on (cycle_id, scope, as_of_date). Narrative
    fields are left NULL on insert and untouched on conflict (they're only
    ever written by _ingest_narrative_intensity in orchestrator/run.py, via
    a separate UPDATE, never here)."""
    conn.execute(
        """
        INSERT INTO cycle_assessments (
            cycle_id, scope, as_of_date, framework_version,
            percentile, direction, momentum_state, phase_id, directional_lean,
            quant_score, data_pending, missing_kpis_json, contributing_kpis,
            note, created_at
        ) VALUES (
            :cycle_id, :scope, :as_of_date, :framework_version,
            :percentile, :direction, :momentum_state, :phase_id, :directional_lean,
            :quant_score, :data_pending, :missing_kpis_json, :contributing_kpis,
            :note, :created_at
        )
        ON CONFLICT(cycle_id, scope, as_of_date) DO UPDATE SET
            framework_version = excluded.framework_version,
            percentile = excluded.percentile,
            direction = excluded.direction,
            momentum_state = excluded.momentum_state,
            phase_id = excluded.phase_id,
            directional_lean = excluded.directional_lean,
            quant_score = excluded.quant_score,
            data_pending = excluded.data_pending,
            missing_kpis_json = excluded.missing_kpis_json,
            contributing_kpis = excluded.contributing_kpis,
            note = excluded.note,
            updated_at = :updated_at
        """,
        {**row, "updated_at": _now_iso()},
    )


def _row_to_phase_reading(row: dict, framework: CycleFramework) -> composite.CyclePhaseReading:
    return composite.CyclePhaseReading(
        cycle_id=row["cycle_id"],
        scope=row["scope"],
        phase_id=row.get("phase_id"),
        directional_lean=row.get("directional_lean"),
        percentile=row.get("percentile"),
        data_pending=bool(row.get("data_pending")),
        missing_kpis=json.loads(row.get("missing_kpis_json") or "[]"),
    )


def compute_and_upsert_composite(
    conn: sqlite3.Connection,
    framework: CycleFramework,
    scope: str,
    as_of: str,
    knowledge=None,
) -> dict:
    """Read back all cycle_assessments rows for (scope, as_of) written by
    assess_scope(), group them by functional_group, compute the composite,
    alignment, and EVI, then upsert composite_decisions. requires_human_review
    is always 1 per cycle_framework.yaml governance (HITL by default —
    nothing in this engine is intended to auto-execute)."""
    rows = conn.execute(
        "SELECT * FROM cycle_assessments WHERE scope = ? AND as_of_date = ?",
        (scope, as_of),
    ).fetchall()
    row_dicts = [dict(r) for r in rows]

    if knowledge is None and load_knowledge is not None:
        try:
            knowledge = load_knowledge()
        except Exception:
            knowledge = None

    # Map cycle_id -> functional_group via the knowledge catalog when
    # available; fall back to the framework's own functional_groups mapping
    # (which lists cycles by group) if knowledge/ can't be loaded.
    cycle_to_group: dict[str, str] = {}
    if knowledge is not None:
        for c in knowledge.catalog.cycles:
            cycle_to_group[c.cycle_id] = c.functional_group
    else:
        for group_id, group in framework.functional_groups.items():
            for cycle_id in group.cycles:
                cycle_to_group[cycle_id] = group_id

    readings_by_group: dict[str, list[composite.CyclePhaseReading]] = {
        "macro_regime": [], "market_structure": [], "external": [], "idiosyncratic": [],
    }
    all_readings: list[composite.CyclePhaseReading] = []
    for row in row_dicts:
        reading = _row_to_phase_reading(row, framework)
        all_readings.append(reading)
        group = cycle_to_group.get(row["cycle_id"])
        if group in readings_by_group:
            readings_by_group[group].append(reading)

    composite_result = composite.compute_composite(framework, readings_by_group)
    alignment_result = composite.compute_alignment(all_readings)

    # EVI (evi.yaml: each component is percentile-ranked over its own
    # history before averaging):
    #   index_pe        — the valuation_cycle reading's percentile (live)
    #   gsec_yield_x_pe — Phase 8: percentile of the current yield_gap
    #                     within its own history, ranked over evi.yaml's
    #                     10y lookback (the yield_gap anchor itself uses
    #                     yield_gap.yaml's 15y window for band selection)
    #   index_pb        — percentile of the scope-resolved index's latest
    #                     P/B over its own 10y pb history in index_data
    #                     (anchors.index_pb_percentile);
    #   mcap_gdp        — still missing (no GDP series).
    # Partial EVI is disclosed via components_missing, never silently full.
    valuation_row = next((r for r in row_dicts if r["cycle_id"] == "valuation_cycle"), None)

    yg_anchor = anchors.yield_gap_anchor(conn, scope, as_of=as_of)
    gsec_yield_x_pe_pct = None
    if not yg_anchor.data_pending and yg_anchor.current is not None:
        evi_cutoff = (dt.date.fromisoformat(as_of) - dt.timedelta(days=round(10 * 365.25))).isoformat()
        evi_window = [v for d, v in yg_anchor.history if d >= evi_cutoff]
        if len(evi_window) >= 10:
            gsec_yield_x_pe_pct = classify.percentile_rank(yg_anchor.current, evi_window)

    component_values = {
        "index_pe": valuation_row["percentile"] if valuation_row and not valuation_row["data_pending"] else None,
        "index_pb": anchors.index_pb_percentile(conn, scope, as_of=as_of),
        "gsec_yield_x_pe": gsec_yield_x_pe_pct,
        "mcap_gdp": None,
    }
    evi_result = composite.compute_evi(framework, component_values)

    # recommended_action / allocation band: only when the yield_gap KPI is
    # genuinely available (Phase 8 sourced the 10Y G-Sec yield) AND the
    # anchor actually produced a value for this scope. Never fabricated.
    recommended_action = "data_pending"
    allocation_band_json = None
    yield_gap_kpi_status = "missing"
    if knowledge is not None:
        try:
            yield_gap_kpi_status = knowledge.kpis["yield_gap"].source_status
        except Exception:
            pass
    if yield_gap_kpi_status == "available" and not yg_anchor.data_pending and yg_anchor.current is not None:
        valuation_phase_id = (
            valuation_row["phase_id"]
            if valuation_row and not valuation_row["data_pending"]
            else None
        )
        band, basis = composite.select_allocation_band(framework, yg_anchor.current, valuation_phase_id)
        recommended_action = (
            f"allocation band: {band.regime_label} "
            f"(equity {band.equity_pct.min:.0f}-{band.equity_pct.max:.0f}%, "
            f"debt {band.debt_pct.min:.0f}-{band.debt_pct.max:.0f}%, "
            f"gold/REITs {band.gold_reits_pct.min:.0f}-{band.gold_reits_pct.max:.0f}%, "
            f"cash {band.cash_pct.min:.0f}-{band.cash_pct.max:.0f}%)"
        )
        allocation_band_json = json.dumps({
            "yield_gap": round(yg_anchor.current, 4),
            "yield_gap_note": yg_anchor.note,
            "valuation_phase_id": valuation_phase_id,
            "basis": basis,
            "band": band.model_dump(),
        })

    now = _now_iso()
    conn.execute(
        """
        INSERT INTO composite_decisions (
            scope, as_of_date, framework_version, regime_cluster, regime_unknown,
            composite_score, alignment_score, group_scores_json, group_weights_json,
            evi_value, evi_components_used_json, evi_components_missing_json,
            recommended_action, allocation_band_json, contributing_kpis,
            requires_human_review, note, created_at
        ) VALUES (
            :scope, :as_of_date, :framework_version, :regime_cluster, :regime_unknown,
            :composite_score, :alignment_score, :group_scores_json, :group_weights_json,
            :evi_value, :evi_components_used_json, :evi_components_missing_json,
            :recommended_action, :allocation_band_json, :contributing_kpis,
            :requires_human_review, :note, :created_at
        )
        ON CONFLICT(scope, as_of_date) DO UPDATE SET
            framework_version = excluded.framework_version,
            regime_cluster = excluded.regime_cluster,
            regime_unknown = excluded.regime_unknown,
            composite_score = excluded.composite_score,
            alignment_score = excluded.alignment_score,
            group_scores_json = excluded.group_scores_json,
            group_weights_json = excluded.group_weights_json,
            evi_value = excluded.evi_value,
            evi_components_used_json = excluded.evi_components_used_json,
            evi_components_missing_json = excluded.evi_components_missing_json,
            recommended_action = excluded.recommended_action,
            allocation_band_json = excluded.allocation_band_json,
            contributing_kpis = excluded.contributing_kpis,
            requires_human_review = excluded.requires_human_review,
            note = excluded.note
        """,
        {
            "scope": scope,
            "as_of_date": as_of,
            "framework_version": framework.content_version,
            "regime_cluster": composite_result.regime_cluster.cluster,
            "regime_unknown": int(composite_result.regime_cluster.unknown),
            "composite_score": composite_result.composite_score,
            "alignment_score": alignment_result.alignment_score,
            "group_scores_json": json.dumps(composite_result.group_scores),
            "group_weights_json": json.dumps(composite_result.group_weights_used),
            "evi_value": evi_result.value,
            "evi_components_used_json": json.dumps(evi_result.components_used),
            "evi_components_missing_json": json.dumps(evi_result.components_missing),
            "recommended_action": recommended_action,
            "allocation_band_json": allocation_band_json,
            "contributing_kpis": json.dumps([r.cycle_id for r in all_readings if not r.data_pending]),
            "requires_human_review": 1,
            "note": f"{composite_result.note}; alignment: {alignment_result.note}",
            "created_at": now,
        },
    )

    return {
        "scope": scope,
        "as_of_date": as_of,
        "regime_cluster": composite_result.regime_cluster.cluster,
        "regime_unknown": composite_result.regime_cluster.unknown,
        "composite_score": composite_result.composite_score,
        "alignment_score": alignment_result.alignment_score,
        "evi_value": evi_result.value,
        "evi_components_missing": evi_result.components_missing,
        "yield_gap": None if yg_anchor.data_pending else yg_anchor.current,
        "recommended_action": recommended_action,
    }


def assess_scope(conn: sqlite3.Connection, framework: CycleFramework, scope: str, as_of: str) -> dict:
    """Run all 5 live cycles + honest data_pending rows for the other 11
    catalog cycles, upsert cycle_assessments, then compute + upsert the
    composite decision. Returns a summary dict for CLI printing."""
    live_rows = []
    for engine_cycle_name in sorted(anchors.LIVE_CYCLE_IDS):
        row = assess_live_cycle(conn, framework, engine_cycle_name, scope, as_of)
        upsert_cycle_assessment(conn, row)
        live_rows.append(row)

    pending_rows = assess_data_pending_cycles(scope, as_of, framework.content_version)
    for row in pending_rows:
        upsert_cycle_assessment(conn, row)

    conn.commit()

    composite_summary = compute_and_upsert_composite(conn, framework, scope, as_of)
    conn.commit()

    return {
        "scope": scope,
        "as_of_date": as_of,
        "live_cycles": live_rows,
        "n_pending_cycles": len(pending_rows),
        "composite": composite_summary,
    }


def run_all(conn: sqlite3.Connection | None = None, as_of: str | None = None) -> list[dict]:
    """Entry point for the weekly_cycle_assessment router trigger's first
    step ('py:afund.cycles.assess.run_all'): assess every scope (market +
    all sectors)."""
    owns_conn = conn is None
    conn = conn or get_conn()
    try:
        framework = load_framework()
        as_of = as_of or dt.date.today().isoformat()
        results = []
        for scope in all_scopes():
            results.append(assess_scope(conn, framework, scope, as_of))
        return results
    finally:
        if owns_conn:
            conn.close()


def finalize(conn: sqlite3.Connection | None = None, as_of: str | None = None) -> list[dict]:
    """Entry point for the weekly_cycle_assessment router trigger's last
    step ('py:afund.cycles.assess.finalize'): after narrative_intensity has
    ingested (see orchestrator/run.py _ingest_narrative_intensity, which
    UPDATEs cycle_assessments' narrative_* columns), recompute
    composite_decisions so reconciliation/narrative fields are reflected."""
    owns_conn = conn is None
    conn = conn or get_conn()
    try:
        framework = load_framework()
        as_of = as_of or dt.date.today().isoformat()
        results = []
        for scope in all_scopes():
            results.append(compute_and_upsert_composite(conn, framework, scope, as_of))
            conn.commit()
        return results
    finally:
        if owns_conn:
            conn.close()


def _print_scope_result(result: dict) -> None:
    print(f"\n=== {result['scope']} (as_of {result['as_of_date']}) ===")
    for row in result["live_cycles"]:
        if row["data_pending"]:
            print(f"  {row['cycle_id']:<32} data_pending  missing={json.loads(row['missing_kpis_json'])}  note={row['note']}")
        else:
            print(
                f"  {row['cycle_id']:<32} pct={row['percentile']:.1f} dir={row['direction']:<8} "
                f"mom={row['momentum_state']:<13} phase={row['phase_id']:<18} lean={row['directional_lean']:+d}"
            )
    print(f"  ({result['n_pending_cycles']} other catalog cycles recorded as data_pending)")
    c = result["composite"]
    if c["regime_unknown"]:
        print(f"  composite: regime=UNKNOWN (macro_regime data_pending), composite_score=None, "
              f"alignment_score={c['alignment_score']}")
    else:
        print(
            f"  composite: regime={c['regime_cluster']}, composite_score={c['composite_score']}, "
            f"alignment_score={c['alignment_score']}"
        )
    print(f"  EVI: value={c['evi_value']}, components_missing={c['evi_components_missing']}")
    if c.get("yield_gap") is not None:
        print(f"  yield_gap: {c['yield_gap']:.3f}")
    print(f"  recommended_action: {c['recommended_action']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7 cycle engine assessment CLI")
    parser.add_argument("--scope", type=str, default=None, help='e.g. "NIFTY 50" or a sector slug like "bfsi"')
    parser.add_argument("--all", action="store_true", help="assess market + all sector scopes")
    parser.add_argument("--date", type=str, default=None, help="as-of date, YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)

    if not args.scope and not args.all:
        parser.error("must pass --scope SCOPE or --all")

    conn = get_conn()
    try:
        framework = load_framework()
        print(f"cycle_framework.yaml version={framework.content_version} status={framework.status}")
        as_of = args.date or dt.date.today().isoformat()

        scopes = all_scopes() if args.all else [args.scope]
        for scope in scopes:
            result = assess_scope(conn, framework, scope, as_of)
            _print_scope_result(result)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
