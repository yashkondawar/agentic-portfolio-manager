"""Pure escalation rules: does a given event require a human checkpoint?

Reads registry/rules/risk_limits.yaml directly (raw YAML, not the strict
Registry pydantic model — light_review is an orchestrator-level routing
hint layered onto the escalation rule, not a mandate risk parameter, so it
doesn't need a Registry schema change) for:
  - escalation.value          — actions that ALWAYS require human approval
                                 (default: NEW, ADD, REDUCE, EXIT).
  - escalation.light_review   — actions that are logged + surfaced in the
                                 digest but do NOT hard-gate on a human
                                 (default: HOLD, MONITOR_ONLY).

requires_human(event) is intentionally a single pure function with no I/O
beyond the one-time YAML read, so it's trivially unit-testable and safe to
call from anywhere in the orchestrator (router steps, run.py, monitoring.py).

Event shape (all keys optional — a caller passes what's relevant):
    {
      "type": "recommendation" | "thesis_status" | "risk_violation",
      "action": "NEW" | "ADD" | "REDUCE" | "EXIT" | "HOLD" | "MONITOR_ONLY",
      "thesis_status": "ACTIVE" | "WATCH" | "INVALIDATED" | "CLOSED",
      "risk_violation": bool,
    }
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yaml

from afund.config import REPO_ROOT

RISK_LIMITS_PATH = REPO_ROOT / "registry" / "rules" / "risk_limits.yaml"

DEFAULT_HARD_ESCALATE_ACTIONS = ["NEW", "ADD", "REDUCE", "EXIT"]
DEFAULT_LIGHT_REVIEW_ACTIONS = ["HOLD", "MONITOR_ONLY"]

# Phase 10: |z-score|-like threshold for the "anchor beyond ~3 SD" mechanical
# check (cycle_framework.yaml governance.hitl_triggers: "Any anchor metric
# reads beyond roughly +/-3 standard deviations"). We proxy this with the
# cycle_assessments.percentile field (0-100, from classify.percentile_rank):
# a normal distribution's +/-3 SD tail is roughly below the 0.15th / above
# the 99.85th percentile — DRAFT approximation, since percentile_rank is a
# rank statistic, not a z-score, but it's the only per-cycle extremity
# measure this engine already computes.
ANCHOR_EXTREME_LOW_PERCENTILE = 0.15
ANCHOR_EXTREME_HIGH_PERCENTILE = 99.85


def _load_escalation_config(path: Path | None = None) -> dict[str, Any]:
    risk_limits_path = path or RISK_LIMITS_PATH
    data = yaml.safe_load(risk_limits_path.read_text(encoding="utf-8"))
    escalation = (data or {}).get("escalation", {}) or {}
    return {
        "hard_escalate_actions": escalation.get("value") or DEFAULT_HARD_ESCALATE_ACTIONS,
        "light_review_actions": escalation.get("light_review") or DEFAULT_LIGHT_REVIEW_ACTIONS,
    }


def requires_human(
    event: dict, *, config_path: Path | None = None, checklist: dict[str, str] | None = None
) -> bool:
    """True if `event` must stop at a human checkpoint before proceeding.

    Rules (any one match is sufficient):
      1. A recommendation whose action is in risk_limits.yaml's
         escalation.value list (default NEW/ADD/REDUCE/EXIT) -> True.
      2. A thesis_status event of INVALIDATED, or any "WATCH-breach" event
         (thesis_status == "WATCH") -> True.
      3. Any risk_violation event (risk_violation truthy) -> True.
      4. An action in escalation.light_review (default HOLD/MONITOR_ONLY) is
         explicitly NOT a hard escalation -> False, unless another rule above
         also matches.
      5. (Phase 10) Any FAIL in a `checklist` dict passed by the caller
         (typically afund.orchestrator.escalation.mechanical_checklist()'s
         output) -> True. `checklist` is an optional caller-supplied dict
         rather than computed here, since this function stays DB-free/pure
         (mechanical_checklist needs a sqlite3.Connection); passing None
         (the default) preserves this rule's prior pure-event-dict behavior
         exactly for every existing caller.

    Anything not matching any rule (e.g. an event with no recognized action
    and no thesis/risk flags) defaults to False — escalation is opt-in, not
    opt-out, so an unrecognized/empty event never blocks silently by
    accident, but also never proceeds past a real gate by accident since
    every actual action-bearing recommendation must supply a recognized
    action string.
    """
    config = _load_escalation_config(config_path)

    action = event.get("action")
    if action is not None and action in config["hard_escalate_actions"]:
        return True

    thesis_status = event.get("thesis_status")
    if thesis_status in ("INVALIDATED", "WATCH"):
        return True

    if event.get("risk_violation"):
        return True

    if checklist and any(v == "FAIL" for v in checklist.values()):
        return True

    return False


def _load_risk_limits_raw(config_path: Path | None = None) -> dict[str, Any]:
    risk_limits_path = config_path or RISK_LIMITS_PATH
    return yaml.safe_load(risk_limits_path.read_text(encoding="utf-8")) or {}


def mechanical_checklist(conn: sqlite3.Connection, event: dict, *, config_path: Path | None = None) -> dict[str, str]:
    """The MECHANICAL subset of cycle_framework.yaml's governance.checklist
    (items 1/2/4/5/6/9/10 are tagged type: mechanical in the YAML; items
    3/7/8 are type: judgment and are NOT computed here — those need a human
    or an agent, not a deterministic rule) reduced to concrete, checkable
    conditions this engine can actually evaluate today:

      size_vs_cycle_adjusted_limit — event["size_or_weight_pct"] (if given)
        <= portfolio.risk.cycle_adjusted_limit()'s adjusted_limit_pct for
        event's instrument_id/sector. NA if no size given.
      cash_floor — (only meaningful for a cash-consuming action) NA here;
        this repo's cash floor is portfolio-level and already checked by
        portfolio/risk.py's own concentration/positions machinery, not
        re-derived from this event shape alone, so this item reports NA
        unless event supplies "resulting_cash_pct" explicitly.
      sector_cap — event["sector_weight_pct_after"] (if given) <=
        risk_limits.yaml max_sector_pct.value. NA if not given.
      alignment_vs_size — cycle_framework.yaml governance.hitl_triggers'
        "low-alignment-large-size": FAIL if event["alignment_score"] (0-100)
        is low (<40, DRAFT cutoff) AND event["size_or_weight_pct"] is large
        (>= half the cycle-adjusted limit). NA if either input is missing.
      first_time_exposure — cycle_framework.yaml's hitl_trigger is "a new
        sector/country exposure is being initiated for THE FIRST TIME", i.e.
        only meaningful for an exposure-initiating/-changing action. FAIL
        (i.e. the trigger fires, human must look) if event["action"] is one
        of NEW/ADD/REDUCE/EXIT (any capital-moving action per risk_limits.
        yaml escalation.value) AND there is NO prior decision_log row for
        this instrument_id (a genuinely new name for the portfolio). PASS if
        a prior row exists for a capital-moving action. NA if no
        instrument_id given, OR if event["action"] is HOLD/MONITOR_ONLY/
        absent — those don't initiate exposure, so "first time" doesn't
        apply regardless of decision_log history.
      anchor_extreme — FAIL if the resolved scope's latest valuation_cycle
        percentile is beyond the ~3SD-equivalent tail (see module-level
        ANCHOR_EXTREME_*_PERCENTILE). NA if no assessment available.

    Every item is PASS, FAIL, or NA — never silently omitted, so a caller
    can print "N items FAILED" and enumerate them without special-casing
    missing keys.
    """
    from afund.portfolio.risk import _resolve_sector_scope, cycle_adjusted_limit

    result: dict[str, str] = {}

    instrument_id = event.get("instrument_id")
    sector = event.get("sector")
    size_pct = event.get("size_or_weight_pct")

    # size_vs_cycle_adjusted_limit
    limit_info = cycle_adjusted_limit(conn, instrument_id=instrument_id, sector=sector)
    if size_pct is None:
        result["size_vs_cycle_adjusted_limit"] = "NA"
    else:
        result["size_vs_cycle_adjusted_limit"] = (
            "PASS" if size_pct <= limit_info["adjusted_limit_pct"] else "FAIL"
        )

    # cash_floor
    resulting_cash_pct = event.get("resulting_cash_pct")
    if resulting_cash_pct is None:
        result["cash_floor"] = "NA"
    else:
        risk_limits = _load_risk_limits_raw(config_path)
        floor = (risk_limits.get("cash_floor_pct") or {}).get("value", 5)
        result["cash_floor"] = "PASS" if resulting_cash_pct >= floor else "FAIL"

    # sector_cap
    sector_weight_after = event.get("sector_weight_pct_after")
    if sector_weight_after is None:
        result["sector_cap"] = "NA"
    else:
        risk_limits = _load_risk_limits_raw(config_path)
        cap = (risk_limits.get("max_sector_pct") or {}).get("value", 25)
        result["sector_cap"] = "PASS" if sector_weight_after <= cap else "FAIL"

    # alignment_vs_size (low-alignment-large-size hitl_trigger)
    alignment_score = event.get("alignment_score")
    if alignment_score is None or size_pct is None:
        result["alignment_vs_size"] = "NA"
    else:
        half_limit = limit_info["adjusted_limit_pct"] / 2.0
        low_alignment = alignment_score < 40
        large_size = size_pct >= half_limit
        result["alignment_vs_size"] = "FAIL" if (low_alignment and large_size) else "PASS"

    # first_time_exposure — only applicable to a capital-moving action; a
    # HOLD/MONITOR_ONLY (or an event with no action at all, e.g. risk_mgmt's
    # pre-sizing check) isn't "initiating" anything, so it's NA there
    # regardless of decision_log history.
    action = event.get("action")
    exposure_initiating_actions = {"NEW", "ADD", "REDUCE", "EXIT"}
    if instrument_id is None or action not in exposure_initiating_actions:
        result["first_time_exposure"] = "NA"
    else:
        prior = conn.execute(
            "SELECT 1 FROM decision_log WHERE instrument_id = ? LIMIT 1", (instrument_id,)
        ).fetchone()
        result["first_time_exposure"] = "FAIL" if prior is None else "PASS"

    # anchor_extreme (+/-3 SD-equivalent)
    resolved_scope = _resolve_sector_scope(conn, instrument_id=instrument_id, sector=sector)
    candidate_scopes = [s for s in [resolved_scope, "NIFTY 500", "NIFTY 50"] if s]
    seen: set[str] = set()
    scopes = [s for s in candidate_scopes if not (s in seen or seen.add(s))]
    percentile = None
    for scope in scopes:
        row = conn.execute(
            """
            SELECT percentile FROM cycle_assessments
             WHERE cycle_id = 'valuation_cycle' AND scope = ? AND data_pending = 0
             ORDER BY as_of_date DESC LIMIT 1
            """,
            (scope,),
        ).fetchone()
        if row is not None and row["percentile"] is not None:
            percentile = row["percentile"]
            break
    if percentile is None:
        result["anchor_extreme"] = "NA"
    else:
        extreme = percentile <= ANCHOR_EXTREME_LOW_PERCENTILE or percentile >= ANCHOR_EXTREME_HIGH_PERCENTILE
        result["anchor_extreme"] = "FAIL" if extreme else "PASS"

    return result
