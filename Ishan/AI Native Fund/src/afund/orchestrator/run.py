"""Orchestrator CLI: `python -m afund.orchestrator.run`.

This is the deterministic rail the (future, Phase 4) automated agent
invocation rides on. It never calls an LLM itself: `agent:` steps stop
after writing a context packet and an agent_runs='PREPARED' row, printing
the exact instruction block a human (or a future automation layer) needs to
actually run the Claude Code agent and feed its output back in via
--ingest-output.

Flags:
  --list-due [--date YYYY-MM-DD]
  --show-pipeline <trigger>
  --job <trigger> [--date D] [--symbol S] [--step N] [--prior-output <file>]
  --record-human-decision <decision_id> --decision APPROVE|REJECT|MODIFY [--notes ...]
  --ingest-output <agent_runs_id> --file <output.json>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
import uuid
from pathlib import Path

from afund.agents import runner
from afund.agents.contracts import ContractViolation, validate_output
from afund.config import REPO_ROOT
from afund.db.connection import get_conn
from afund.memory import stores
from afund.orchestrator import escalation, scheduler
from afund.orchestrator.context import build_packet
from afund.orchestrator.router import TRIGGERS, show_pipeline
from afund.orchestrator.monitoring import check_invalidations

PACKETS_DIR = REPO_ROOT / "data" / "packets"
PROPOSALS_DIR = REPO_ROOT / "data" / "proposals"

# Phase 9: cmd_job()'s step loop is a straight-line, single-threaded walk over
# one trigger's steps within one process invocation — there is never more
# than one "in-flight" packet at a time. sector_research and buy_side_analysis
# both build their agent's packet in a preceding py: step (sector_assembler /
# er_adapter) rather than via the generic build_packet() path, so the
# following agent: step needs that exact path, not a freshly (and wrongly)
# built one. A module-level dict — reset at the top of every cmd_job() call —
# is the simplest way to thread that path across the two steps without
# reshaping every helper's signature for a two-step-only need.
LAST_PACKET_RESULT: dict[str, str | None] = {"path": None}

# meta_research may only PROPOSE changes to registry rules/prompts or agent
# definitions — never to application code, schema, or anything else. A
# proposal targeting a path outside these two roots is a contract-level
# invariant violation, not a soft warning: the ingest is refused outright.
META_PROPOSAL_ALLOWED_ROOTS = ("registry/", "registry\\", ".claude/agents/", ".claude\\agents\\")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _last_run_map(conn: sqlite3.Connection) -> dict[str, str]:
    """job_name -> most recent SUCCESS started_at, from job_runs."""
    rows = conn.execute(
        """
        SELECT job_name, MAX(started_at) AS last_started
          FROM job_runs
         WHERE status = 'SUCCESS'
         GROUP BY job_name
        """
    ).fetchall()
    return {row["job_name"]: row["last_started"] for row in rows if row["last_started"]}


def cmd_list_due(args: argparse.Namespace) -> None:
    on_date = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    conn = get_conn()
    try:
        last_run = _last_run_map(conn)
    finally:
        conn.close()
    due = scheduler.due_jobs(on_date, last_run=last_run)
    print(f"Due jobs for {on_date.isoformat()}:")
    for job in due:
        print(f"  - {job}")
    if not due:
        print("  (none)")


def cmd_show_pipeline(args: argparse.Namespace) -> None:
    try:
        steps = show_pipeline(args.show_pipeline)
    except KeyError as exc:
        print(str(exc))
        sys.exit(1)
    print(f"Pipeline for trigger '{args.show_pipeline}':")
    for i, step in enumerate(steps, start=1):
        print(f"  {i}. {step}")


def _import_pipeline_class(path: str):
    """'afund.data.universe.UniversePipeline' -> the class object."""
    module_path, class_name = path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _resolve_py_step(step: str, conn: sqlite3.Connection, *, args: argparse.Namespace, batch_id: str | None = None) -> None:
    """Run a 'py:' step. Two shapes are supported:
      - 'py:module.path.ClassName' — a Pipeline subclass; instantiate(conn).run().
      - 'py:module.path.function_name' — a plain callable(conn) -> dict/int, printed.
    """
    target_path = step.split("py:", 1)[1]

    # Special-case: universe pipeline only actually fetches on Mondays (mirrors
    # afund.data.run_daily's existing behavior) unless explicitly forced via --date.
    if target_path == "afund.data.universe.UniversePipeline":
        on_date = dt.date.fromisoformat(args.date) if getattr(args, "date", None) else dt.date.today()
        if on_date.weekday() != 0:
            print(f"  [SKIPPED] {target_path}: not Monday ({on_date.isoformat()})")
            return

    # Special-case: daily_nav takes an explicit `date` and already logs its
    # own job_runs row internally (see afund.portfolio.nav.run_daily_nav) —
    # skip the generic function wrapper's own (redundant) job_runs insert.
    if target_path == "afund.portfolio.nav.run_daily_nav":
        from afund.portfolio.nav import run_daily_nav

        on_date = args.date if getattr(args, "date", None) else None
        try:
            result = run_daily_nav(conn, date=on_date)
            print(f"  [SUCCESS] {target_path}: {json.dumps(result, default=str)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAILED] {target_path}: {exc}")
        return

    # Special-case: Phase 9 research bridge steps take extra CLI-supplied
    # arguments (ticker/sector) beyond the generic `function(conn)` shape —
    # each writes its own PREPARED agent_runs row (equity_research_kickoff)
    # or persists its own packet file (sector_research) rather than routing
    # through build_packet()/runner.prepare_invocation(), so they're resolved
    # here directly instead of falling through to the generic wrapper below.
    if target_path == "afund.research.er_adapter.prepare_kickoff":
        from afund.research.er_adapter import prepare_kickoff

        if not getattr(args, "ticker", None):
            print(f"  [FAILED] {target_path}: --ticker is required for this trigger")
            return
        try:
            result = prepare_kickoff(conn, args.ticker)
            print(f"  [SUCCESS] {target_path}: agent_runs_id={result['agent_runs_id']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAILED] {target_path}: {exc}")
        return

    if target_path == "afund.research.er_adapter.ingest_er_output":
        from afund.research.er_adapter import ingest_er_output

        if not getattr(args, "ticker", None):
            print(f"  [FAILED] {target_path}: --ticker is required for this trigger")
            return
        try:
            result = ingest_er_output(conn, args.ticker)
            print(f"  [SUCCESS] {target_path}: rating={result['rating']} -> {result['note_json_path']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAILED] {target_path}: {exc}")
        return

    if target_path == "afund.research.sector_assembler.build_sector_packet":
        from afund.research.sector_assembler import build_sector_packet

        if not getattr(args, "sector", None):
            print(f"  [FAILED] {target_path}: --sector is required for this trigger")
            return
        try:
            result = build_sector_packet(conn, args.sector, batch_id=batch_id)
            print(f"  [SUCCESS] {target_path}: packet -> {result['path']} (approx_tokens={result['approx_tokens']})")
            LAST_PACKET_RESULT["path"] = result["path"]
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAILED] {target_path}: {exc}")
        return

    if target_path == "afund.research.er_adapter.build_buy_side_packet":
        from afund.research.er_adapter import build_buy_side_packet

        if not getattr(args, "ticker", None):
            print(f"  [FAILED] {target_path}: --ticker is required for this trigger")
            return
        try:
            result = build_buy_side_packet(conn, args.ticker, batch_id=batch_id)
            print(f"  [SUCCESS] {target_path}: packet -> {result['path']} (approx_tokens={result['approx_tokens']})")
            LAST_PACKET_RESULT["path"] = result["path"]
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAILED] {target_path}: {exc}")
        return

    # Special-case: the Phase 10 funnel step returns a full per-candidate
    # gate breakdown (potentially large) — print a compact summary instead
    # of the generic json.dumps(result) dump below, mirroring how the
    # screener/other rich-output steps stay readable on the CLI.
    if target_path == "afund.cycles.funnel.run_funnel":
        from afund.cycles.funnel import run_funnel

        try:
            result = run_funnel(conn)
            candidates = result["candidates"]
            passed_both = sum(1 for c in candidates if c["gates_passed"] == 2)
            print(
                f"  [SUCCESS] {target_path}: as_of={result['as_of']} "
                f"universe_scanned={result['universe_scanned']} candidates={len(candidates)} "
                f"(gate1+gate4 both PASS: {passed_both})"
            )
            for c in candidates[:5]:
                g1 = c["gates"]["gate1_quant_cycle"]["result"]
                g3 = c["gates"]["gate3_idiosyncratic"]["percentile"]
                g4 = c["gates"]["gate4_neglect"]["result"]
                g3_str = f"{g3:.0f}" if g3 is not None else "n/a"
                print(f"      {c['symbol']:<12} gate1={g1:<4} gate3_pct={g3_str:>4} gate4={g4}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAILED] {target_path}: {exc}")
        return

    target = _import_pipeline_class(target_path)

    if isinstance(target, type):
        pipeline = target(conn=conn)
        result = pipeline.run()
        status_line = f"  [{result.status}] {result.job_name}: rows_written={result.rows_written}"
        if result.error:
            status_line += f" error={result.error.splitlines()[0]}"
        print(status_line)
    else:
        # Plain function step, e.g. afund.orchestrator.monitoring.check_invalidations
        started_at = _now_iso()
        try:
            result = target(conn)
            finished_at = _now_iso()
            print(f"  [SUCCESS] {target_path}: {json.dumps(result, default=str)}")
            from afund.data.base import log_job_run

            log_job_run(conn, target_path, "SUCCESS", 0, started_at, finished_at, None)
        except Exception as exc:  # noqa: BLE001
            finished_at = _now_iso()
            print(f"  [FAILED] {target_path}: {exc}")
            from afund.data.base import log_job_run

            log_job_run(conn, target_path, "FAILED", 0, started_at, finished_at, str(exc))


def _resolve_agent_step(
    role: str, conn: sqlite3.Connection, *, trigger: str, batch_id: str,
    instrument_id: int | None, symbol: str | None, prior_output: dict | None,
    newsletter_text: str | None = None, publisher: str | None = None, period: str | None = None,
    scope: str | None = None,
) -> dict:
    """Build the packet, log a PREPARED agent_runs row (via
    runner.prepare_invocation — the single owner of that insert), print the
    invocation instruction block. Returns the packet build result plus
    agent_runs_id/instruction."""
    packet_result = build_packet(
        conn,
        role=role,
        trigger=trigger,
        instrument_id=instrument_id,
        symbol=symbol,
        prior_output=prior_output,
        batch_id=batch_id,
        newsletter_text=newsletter_text,
        publisher=publisher,
        period=period,
        scope=scope,
    )

    invocation = runner.prepare_invocation(
        conn, role=role, packet_path=packet_result["path"], batch_id=batch_id, trigger=trigger,
    )
    print(invocation["instruction"])
    return {**invocation, **packet_result}


def _resolve_macro_digest_steps(conn: sqlite3.Connection, *, trigger: str, batch_id: str) -> list[dict]:
    """One macro_digest packet + PREPARED agent_runs row per unparsed
    newsletter (newsletters.parsed=0 with a local PDF). The PDF text is
    extracted here (pure python, pypdf) and sanitized inside build_packet."""
    from afund.data.newsletter_text import extract_newsletter_text

    rows = conn.execute(
        """
        SELECT id, publisher, period, local_path
          FROM newsletters
         WHERE parsed = 0 AND local_path IS NOT NULL
         ORDER BY period ASC, id ASC
        """
    ).fetchall()

    if not rows:
        print("  [SKIPPED] agent:macro_digest: no unparsed newsletters")
        return []

    results = []
    for row in rows:
        try:
            text = extract_newsletter_text(row["local_path"])
        except Exception as exc:  # noqa: BLE001 — one bad PDF must not abort the others
            print(f"  [FAILED] extract text for {row['publisher']} {row['period']}: {exc}")
            continue
        result = _resolve_agent_step(
            "macro_digest", conn, trigger=trigger, batch_id=batch_id,
            instrument_id=None, symbol=None, prior_output=None,
            newsletter_text=text, publisher=row["publisher"], period=row["period"],
        )
        results.append(result)
    return results


def _resolve_narrative_intensity_steps(conn: sqlite3.Connection, *, trigger: str, batch_id: str, scope: str | None) -> list[dict]:
    """One narrative_intensity packet + PREPARED agent_runs row per scope
    that has a cycle_assessments row for today (i.e. every scope run_all
    just assessed in this weekly_cycle_assessment pipeline) — unless a
    single --scope was passed on the CLI, in which case only that scope
    gets a packet. Mirrors _resolve_macro_digest_steps' fan-out shape."""
    if scope:
        scopes = [scope]
    else:
        as_of = dt.date.today().isoformat()
        rows = conn.execute(
            "SELECT DISTINCT scope FROM cycle_assessments WHERE as_of_date = ? ORDER BY scope ASC",
            (as_of,),
        ).fetchall()
        scopes = [row["scope"] for row in rows]

    if not scopes:
        print("  [SKIPPED] agent:narrative_intensity: no cycle_assessments rows for today (run "
              "py:afund.cycles.assess.run_all first)")
        return []

    results = []
    for one_scope in scopes:
        result = _resolve_agent_step(
            "narrative_intensity", conn, trigger=trigger, batch_id=batch_id,
            instrument_id=None, symbol=None, prior_output=None, scope=one_scope,
        )
        results.append(result)
    return results


def cmd_job(args: argparse.Namespace) -> None:
    trigger = args.job
    if trigger not in TRIGGERS:
        print(f"Unknown trigger: {trigger!r}. Known triggers: {sorted(TRIGGERS)}")
        sys.exit(1)

    steps = show_pipeline(trigger)

    # --step N: run only the Nth (1-based) step of the pipeline. This is how
    # the orchestrator chains agent steps across separate invocations:
    # ingest step N's output, then run step N+1 with --prior-output <file>.
    if args.step is not None:
        if not (1 <= args.step <= len(steps)):
            print(f"--step {args.step} out of range for trigger {trigger!r} ({len(steps)} steps)")
            sys.exit(1)
        steps = [steps[args.step - 1]]

    batch_id = f"{trigger}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    LAST_PACKET_RESULT["path"] = None

    conn = get_conn()
    prior_output: dict | None = None
    instrument_id: int | None = None
    symbol = args.symbol

    if args.prior_output:
        prior_path = Path(args.prior_output)
        try:
            prior_output = json.loads(prior_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"FAILED to parse --prior-output file {prior_path}: {exc}")
            sys.exit(1)

    if symbol:
        row = conn.execute(
            "SELECT id FROM instruments WHERE symbol = ? ORDER BY id LIMIT 1", (symbol,)
        ).fetchone()
        instrument_id = row["id"] if row else None

    try:
        print(f"Running job '{trigger}' (batch {batch_id})")
        for step in steps:
            if step.startswith("py:"):
                if step == "py:afund.orchestrator.monitoring.check_invalidations":
                    result = check_invalidations(conn)
                    print(f"  [SUCCESS] invalidation check: checked={result['checked']} breaches={len(result['breaches'])}")
                    if not result["breaches"]:
                        continue
                    # Breach found -> the next agent:fund_manager step should run;
                    # otherwise the pipeline logic below will still process it,
                    # but we annotate prior_output so it's visible in the packet.
                    prior_output = {"invalidation_check": result}
                else:
                    _resolve_py_step(step, conn, args=args, batch_id=batch_id)

            elif step.startswith("agent:"):
                role = step.split("agent:", 1)[1]

                # Conditional step: in position_monitoring, fund_manager only
                # runs if the preceding invalidation check found a breach.
                if trigger == "position_monitoring" and role == "fund_manager":
                    breaches = (prior_output or {}).get("invalidation_check", {}).get("breaches", [])
                    if not breaches:
                        print("  [SKIPPED] agent:fund_manager: no invalidation breaches this cycle")
                        continue

                if role == "macro_digest":
                    # Fan-out step: one packet + PREPARED row per unparsed newsletter.
                    _resolve_macro_digest_steps(conn, trigger=trigger, batch_id=batch_id)
                    prior_output = None
                    continue

                if role == "narrative_intensity":
                    # Fan-out step: one packet + PREPARED row per scope assessed
                    # today (or just --scope, if the CLI caller passed one).
                    _resolve_narrative_intensity_steps(
                        conn, trigger=trigger, batch_id=batch_id, scope=getattr(args, "scope", None),
                    )
                    prior_output = None
                    continue

                if role in ("sector_researcher", "buy_side"):
                    # Phase 9: the preceding py: step (sector_assembler.build_sector_packet
                    # or er_adapter.build_buy_side_packet) already built and persisted
                    # this role's packet — a role-specific shape build_packet() cannot
                    # produce. Skip build_packet() entirely and log the PREPARED
                    # agent_runs row directly against that packet path; both roles have
                    # real .claude/agents/<role>.md files, so prepare_invocation()'s
                    # generic instruction text resolves correctly.
                    packet_path = LAST_PACKET_RESULT["path"]
                    if not packet_path:
                        print(
                            f"  [FAILED] agent:{role}: no packet was built by the preceding "
                            f"py: step (expected one before agent:{role} in this trigger's pipeline)"
                        )
                        prior_output = None
                        continue
                    invocation = runner.prepare_invocation(
                        conn, role=role, packet_path=packet_path, batch_id=batch_id, trigger=trigger,
                    )
                    print(invocation["instruction"])
                    prior_output = None
                    continue

                agent_result = _resolve_agent_step(
                    role, conn, trigger=trigger, batch_id=batch_id,
                    instrument_id=instrument_id, symbol=symbol, prior_output=prior_output,
                    period=getattr(args, "period", None),
                )
                # The actual agent invocation happens outside this process
                # (claude_code backend); we keep iterating remaining steps so
                # the operator sees the full pipeline shape and every
                # PREPARED packet in one run.
                prior_output = None  # unknown until --ingest-output runs

            elif step == "HUMAN":
                pending = conn.execute(
                    "SELECT id, decision_date, instrument_id, sector, action FROM decision_log "
                    "WHERE human_decision = 'PENDING' ORDER BY created_at DESC"
                ).fetchall()
                print("HUMAN checkpoint reached. Pending decisions awaiting --record-human-decision:")
                if not pending:
                    print("  (none pending)")
                for row in pending:
                    print(
                        f"  - decision_id={row['id']} date={row['decision_date']} "
                        f"instrument_id={row['instrument_id']} sector={row['sector']} action={row['action']}"
                    )
            else:
                print(f"  [SKIPPED] unrecognized step: {step}")
    finally:
        conn.close()


def cmd_record_human_decision(args: argparse.Namespace) -> None:
    conn = get_conn()
    try:
        stores.record_human_decision(conn, args.record_human_decision, args.decision, args.notes)
        print(f"Recorded human decision {args.decision} for decision_id={args.record_human_decision}")
    finally:
        conn.close()


def _ingest_news_processor(conn: sqlite3.Connection, validated) -> None:
    """Apply a validated NewsProcessorOutput: update each staged news_items
    row (matched by news_item_id, falling back to url) with the structured
    fields and mark it processed=1."""
    updated = 0
    unmatched = 0
    for item in validated.items:
        target_id = None
        if item.news_item_id is not None:
            row = conn.execute("SELECT id FROM news_items WHERE id = ?", (item.news_item_id,)).fetchone()
            target_id = row["id"] if row else None
        if target_id is None and item.url:
            row = conn.execute("SELECT id FROM news_items WHERE url = ?", (item.url,)).fetchone()
            target_id = row["id"] if row else None
        if target_id is None:
            unmatched += 1
            continue
        conn.execute(
            """
            UPDATE news_items
               SET event_scope = ?, tag = ?, impact = ?, description = ?, event_date = ?, processed = 1
             WHERE id = ?
            """,
            (item.event_scope, item.tag, item.impact, item.description, item.event_date, target_id),
        )
        updated += 1
    conn.commit()
    print(f"news_processor: updated {updated} news_items row(s) to processed=1"
          + (f"; {unmatched} item(s) had no matching staged row" if unmatched else ""))
    if validated.injection_flags:
        print(f"news_processor: agent flagged {len(validated.injection_flags)} injection attempt(s): "
              f"{validated.injection_flags}")


def _ingest_macro_digest(conn: sqlite3.Connection, validated) -> None:
    """Apply a validated MacroDigestOutput: one knowledge_base MACRO note per
    macro_note, then mark the source newsletter parsed=1."""
    source_ref = f"newsletter:{validated.publisher}:{validated.period}"
    for note in validated.macro_notes:
        stores.add_note(
            conn, tag_type="MACRO", tag_value=note.tag_value, content=note.content,
            source_ref=note.source_ref or source_ref,
        )
    if validated.regime_read:
        stores.add_note(
            conn, tag_type="MACRO", tag_value="regime_read", content=validated.regime_read,
            source_ref=source_ref,
        )
    conn.execute(
        "UPDATE newsletters SET parsed = 1 WHERE publisher = ? AND period = ?",
        (validated.publisher, validated.period),
    )
    conn.commit()
    n_notes = len(validated.macro_notes) + (1 if validated.regime_read else 0)
    print(f"macro_digest: added {n_notes} MACRO knowledge_base note(s); "
          f"marked newsletter {validated.publisher} {validated.period} parsed=1")
    if validated.injection_flags:
        print(f"macro_digest: agent flagged {len(validated.injection_flags)} injection attempt(s): "
              f"{validated.injection_flags}")


def _ingest_narrative_intensity(conn: sqlite3.Connection, validated) -> None:
    """Apply a validated NarrativeIntensityOutput: UPDATE the matching
    cycle_assessments rows for (scope, as_of_date) — narrative fields only,
    the quant fields are owned by afund.cycles.assess and never touched here
    — then recompute the scope's composite_decisions row so the ingested
    narrative is reflected downstream. The reconciliation quadrant is
    computed HERE, in Python (composite.apply_reconciliation), never by the
    agent: the agent only supplies the -100..+100 score + narratives."""
    from afund.cycles import composite
    from afund.cycles.assess import compute_and_upsert_composite
    from afund.cycles.framework import load as load_framework

    framework = load_framework()
    scope = validated.scope
    as_of = validated.as_of_date

    rows = conn.execute(
        "SELECT id, cycle_id, directional_lean, data_pending FROM cycle_assessments "
        "WHERE scope = ? AND as_of_date = ?",
        (scope, as_of),
    ).fetchall()

    if not rows:
        # Agent output dated after the assessment run (e.g. run_all ran
        # Monday, the agent ingested Tuesday): fall back to the most recent
        # assessment on-or-before the output date, and say so.
        fallback = conn.execute(
            "SELECT as_of_date FROM cycle_assessments WHERE scope = ? AND as_of_date <= ? "
            "ORDER BY as_of_date DESC LIMIT 1",
            (scope, as_of),
        ).fetchone()
        if fallback is None:
            print(
                f"narrative_intensity: no cycle_assessments rows for scope={scope!r} on or before "
                f"{as_of} — nothing updated (run py:afund.cycles.assess.run_all first)."
            )
            return
        as_of = fallback["as_of_date"]
        print(f"narrative_intensity: no rows for {validated.as_of_date}; applying to latest assessment {as_of}")
        rows = conn.execute(
            "SELECT id, cycle_id, directional_lean, data_pending FROM cycle_assessments "
            "WHERE scope = ? AND as_of_date = ?",
            (scope, as_of),
        ).fetchall()

    summary_parts = []
    if validated.permanence_narratives:
        summary_parts.append("permanence: " + " | ".join(validated.permanence_narratives))
    if validated.impairment_narratives:
        summary_parts.append("impairment: " + " | ".join(validated.impairment_narratives))
    if validated.divergence_note:
        summary_parts.append("divergence: " + validated.divergence_note)
    summary_parts.append(f"confidence={validated.confidence}")
    narrative_summary = "; ".join(summary_parts)

    now = _now_iso()
    updated = 0
    for row in rows:
        if row["data_pending"] or row["directional_lean"] is None:
            # No quant lean -> no reconciliation possible; still record the
            # scope-level score + summary so the row is not silently blank.
            conn.execute(
                """
                UPDATE cycle_assessments
                   SET narrative_intensity_score = ?, narrative_summary = ?, updated_at = ?
                 WHERE id = ?
                """,
                (validated.narrative_intensity_score, narrative_summary, now, row["id"]),
            )
        else:
            recon = composite.apply_reconciliation(
                framework, row["directional_lean"], validated.narrative_intensity_score,
            )
            conn.execute(
                """
                UPDATE cycle_assessments
                   SET narrative_intensity_score = ?, narrative_summary = ?,
                       reconciliation_quadrant = ?, reconciliation_flags_json = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    validated.narrative_intensity_score, narrative_summary,
                    recon.outcome, json.dumps(recon.flags), now, row["id"],
                ),
            )
        updated += 1
    conn.commit()

    composite_summary = compute_and_upsert_composite(conn, framework, scope, as_of)
    conn.commit()

    print(
        f"narrative_intensity: updated {updated} cycle_assessments row(s) for scope={scope!r} "
        f"as_of={as_of} (score={validated.narrative_intensity_score:+.1f}); "
        f"recomputed composite_decisions (regime={composite_summary['regime_cluster']}, "
        f"alignment={composite_summary['alignment_score']})"
    )
    if validated.injection_flags:
        print(f"narrative_intensity: agent flagged {len(validated.injection_flags)} injection attempt(s): "
              f"{validated.injection_flags}")


def _target_file_allowed(target_file: str) -> bool:
    """True if target_file falls under registry/ or .claude/agents/ (the only
    two roots meta_research may propose changes to). Normalizes both '/' and
    Windows '\\' separators; rejects absolute paths and '..' escapes."""
    normalized = target_file.replace("\\", "/").lstrip("/")
    if ".." in Path(normalized).parts:
        return False
    return normalized.startswith("registry/") or normalized.startswith(".claude/agents/")


def _git_status_porcelain(path: str, *, cwd: Path) -> str:
    """Return `git status --porcelain -- <path>` output (empty string if
    clean or if git is unavailable/not a repo — callers treat that the same
    as 'nothing to report' rather than crashing the ingest)."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", path],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return ""
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _write_meta_proposal_artifacts(validated, output_json: dict) -> tuple[Path, Path]:
    """Write data/proposals/{period}_meta_proposal.json (raw validated
    output) and the human-readable .md companion (rationale + proposed_diff
    per proposal). Returns (json_path, md_path). Pure filesystem write — no
    registry/ or agent-definition file is EVER touched here."""
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    safe_period = validated.period.replace("/", "_").replace("\\", "_")

    json_path = PROPOSALS_DIR / f"{safe_period}_meta_proposal.json"
    json_path.write_text(json.dumps(output_json, indent=2, default=str), encoding="utf-8")

    lines = [f"# Meta-research proposal — {validated.period}", ""]
    lines.append("## Patterns found")
    if validated.patterns_found:
        for p in validated.patterns_found:
            lines.append(f"- {p}")
    else:
        lines.append("(none — no systematic pattern judged worth changing)")
    lines.append("")
    lines.append("## Calibration summary")
    lines.append(validated.calibration_summary or "(none provided)")
    lines.append("")
    lines.append("## Proposals")
    if not validated.proposals:
        lines.append("(none)")
    for i, proposal in enumerate(validated.proposals, start=1):
        lines.append(f"### {i}. {proposal.target_file} ({proposal.change_type})")
        lines.append("")
        lines.append(f"**Rationale:** {proposal.rationale}")
        lines.append("")
        lines.append("```diff")
        lines.append(proposal.proposed_diff)
        lines.append("```")
        lines.append("")
    lines.append("---")
    lines.append(
        "HUMAN REVIEW REQUIRED — meta-research proposes, it never applies. "
        "To stage these changes for review: "
        f".venv\\Scripts\\python scripts\\apply_meta_proposal.py {json_path.name}"
    )

    md_path = PROPOSALS_DIR / f"{safe_period}_meta_proposal.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return json_path, md_path


def _ingest_meta_research(conn: sqlite3.Connection, validated, output_json: dict) -> None:
    """Apply a validated MetaResearchOutput: NEVER touches registry/ or any
    target_file — meta_research proposes, it never applies (the invariant
    this whole role exists to prove). Refuses (raises, caller marks the
    agent_runs row FAILED) if any proposal's target_file is outside
    registry/ or .claude/agents/. On success: writes the JSON + Markdown
    proposal artifacts under data/proposals/, prints a one-line-per-proposal
    summary table, and verifies+prints that `git status --porcelain --
    registry/` is still empty afterward."""
    for proposal in validated.proposals:
        if not _target_file_allowed(proposal.target_file):
            raise ContractViolation(
                f"meta_research proposal target_file {proposal.target_file!r} is outside the allowed "
                f"scope (registry/ or .claude/agents/ only) — meta-research may only propose changes "
                f"to registry rules/prompts/agent definitions, never to application code or schema."
            )

    json_path, md_path = _write_meta_proposal_artifacts(validated, output_json)

    print(f"meta_research: wrote proposal artifacts -> {json_path}, {md_path}")
    print(f"meta_research: {len(validated.proposals)} proposal(s) for period {validated.period}")
    if validated.proposals:
        print(f"  {'target_file':<45} {'change_type':<16} rationale")
        for p in validated.proposals:
            one_line = p.rationale.splitlines()[0][:80] if p.rationale else ""
            print(f"  {p.target_file:<45} {p.change_type:<16} {one_line}")
    else:
        print("  (no proposals this cycle)")

    status = _git_status_porcelain("registry/", cwd=REPO_ROOT)
    if status.strip():
        print(f"WARNING: registry/ has uncommitted changes (pre-existing, not caused by this ingest):\n{status}")
    else:
        print("Confirmed: git status --porcelain -- registry/ is clean (meta_research made no registry/ edits).")


def _ingest_fund_manager(conn: sqlite3.Connection, validated, output_json: dict) -> None:
    """Apply a validated FundManagerOutput: decision_log PENDING row, an
    ACTIVE thesis_tracker row when action=NEW (and the instrument is known),
    and the escalation notice.

    Phase 10: merges the mechanical checklist (computed here, in Python,
    from live DB state via escalation.mechanical_checklist — size/cash/
    sector/alignment/first-time/anchor items) with the agent's own
    checklist_status (the judgment-only items it can self-assess) into a
    single "checklist" block persisted inside fund_manager_rec_json, and
    feeds the combined dict into escalation.requires_human() so any FAIL —
    mechanical or judgment — forces a human checkpoint even for an action
    that wouldn't otherwise hard-escalate.
    """
    instrument_row = None
    if validated.instrument:
        instrument_row = conn.execute(
            "SELECT id, sector FROM instruments WHERE symbol = ? ORDER BY id LIMIT 1",
            (validated.instrument,),
        ).fetchone()

    checklist_event = {
        "instrument_id": instrument_row["id"] if instrument_row else None,
        "sector": instrument_row["sector"] if instrument_row else None,
        "size_or_weight_pct": validated.size_or_weight_pct,
    }
    mechanical = escalation.mechanical_checklist(conn, checklist_event)
    judgment = validated.checklist_status or {}
    combined_checklist = {**mechanical, **judgment}
    output_json = {**output_json, "checklist": combined_checklist}

    # Every decision must be reproducible against the exact rules in force:
    # stamp the registry version (git short SHA at load time). None only if
    # the registry itself fails to load — never silently by default.
    try:
        from registry.registry import Registry

        registry_version = Registry.load().version
    except Exception:
        registry_version = None

    decision_id = stores.record_recommendation(
        conn,
        instrument_id=instrument_row["id"] if instrument_row else None,
        sector=instrument_row["sector"] if instrument_row else None,
        action=validated.action,
        strategy_tag=validated.strategy_tag,
        invalidation_condition=validated.invalidation_condition,
        fund_manager_rec_json=output_json,
        registry_version=registry_version,
    )
    print(f"Recorded decision_log row decision_id={decision_id} action={validated.action}")

    if validated.action == "NEW":
        if instrument_row is not None:
            thesis_id = stores.open_thesis(
                conn,
                instrument_id=instrument_row["id"],
                decision_id=decision_id,
                thesis_text=validated.thesis_restatement,
                invalidation_condition=validated.invalidation_condition,
            )
            print(f"Opened thesis_tracker row thesis_id={thesis_id} (ACTIVE) for {validated.instrument}")
        else:
            print(
                f"WARNING: action=NEW but instrument {validated.instrument!r} not found in instruments "
                f"table — no thesis_tracker row opened (open it manually once the instrument exists)."
            )

    event = {"type": "recommendation", "action": validated.action}
    failed_items = [k for k, v in combined_checklist.items() if v == "FAIL"]
    if escalation.requires_human(event, checklist=combined_checklist):
        print(
            f"ESCALATION: action={validated.action} requires human approval. "
            f"Run: .venv\\Scripts\\python -m afund.orchestrator.run "
            f"--record-human-decision {decision_id} --decision APPROVE|REJECT|MODIFY"
        )
        if failed_items:
            print(f"  Checklist FAILs forcing/reinforcing escalation: {', '.join(failed_items)}")
    else:
        print(f"Light review only (action={validated.action}); logged for digest, no hard gate.")
        if failed_items:
            # Shouldn't happen given rule 5 of requires_human(), but print
            # defensively so a future change to that rule's precedence can't
            # silently hide a FAIL from the digest.
            print(f"  NOTE: checklist has FAILs despite light-review action: {', '.join(failed_items)}")


def _ingest_sector_researcher(conn: sqlite3.Connection, validated) -> None:
    """Apply a validated SectorResearchNote: upsert a research_reports row
    (report_type='SECTOR', ticker=the sector slug — there is no single
    instrument for a sector-level note, so instrument_id stays NULL and
    ticker carries the sector slug instead). final_note_path/handoff_path
    are both NULL: the note itself is the packets/outputs JSON already
    written by cmd_ingest_output above, not a separate file this function
    needs to track."""
    created_at = _now_iso()
    conn.execute(
        """
        INSERT INTO research_reports
            (instrument_id, ticker, report_type, final_note_path, handoff_path,
             rating, as_of_date, status, created_at)
        VALUES (NULL, ?, 'SECTOR', NULL, NULL, NULL, ?, 'OK', ?)
        ON CONFLICT(ticker, report_type, as_of_date) DO UPDATE SET
            status = excluded.status,
            created_at = excluded.created_at
        """,
        (validated.sector, validated.as_of_date, created_at),
    )
    conn.commit()
    print(
        f"Recorded research_reports row (SECTOR) for sector={validated.sector} "
        f"as_of={validated.as_of_date} (cycle_phase={validated.cycle_phase}, "
        f"top_picks={validated.top_picks}, avoid_list={validated.avoid_list})"
    )


def _ingest_buy_side(conn: sqlite3.Connection, validated) -> None:
    """Apply a validated BuySideRecommendation: upsert a research_reports row
    (report_type='BUYSIDE') and print the computed EPS x PE sensitivity grid
    (afund.research.sensitivity — pure Python, never the agent's own
    arithmetic) plus % upside against the latest known price, if any."""
    from afund.research.sensitivity import grid as sensitivity_grid
    from afund.research.sensitivity import pct_upside

    instrument_row = conn.execute(
        "SELECT id FROM instruments WHERE symbol = ? ORDER BY id LIMIT 1", (validated.ticker,)
    ).fetchone()
    instrument_id = instrument_row["id"] if instrument_row else None

    as_of_date = dt.date.today().isoformat()
    created_at = _now_iso()
    conn.execute(
        """
        INSERT INTO research_reports
            (instrument_id, ticker, report_type, final_note_path, handoff_path,
             rating, as_of_date, status, created_at)
        VALUES (?, ?, 'BUYSIDE', NULL, NULL, ?, ?, 'OK', ?)
        ON CONFLICT(ticker, report_type, as_of_date) DO UPDATE SET
            instrument_id = COALESCE(excluded.instrument_id, research_reports.instrument_id),
            rating = excluded.rating,
            status = excluded.status,
            created_at = excluded.created_at
        """,
        (instrument_id, validated.ticker, validated.recommendation, as_of_date, created_at),
    )
    conn.commit()

    price_grid = sensitivity_grid(validated.eps_scenarios, validated.pe_scenarios)
    print(
        f"Recorded research_reports row (BUYSIDE) for ticker={validated.ticker} "
        f"recommendation={validated.recommendation} conviction={validated.conviction:.2f}"
    )
    print(f"  EPS x PE target-price grid: {price_grid}")

    price_row = conn.execute(
        "SELECT close FROM daily_prices WHERE instrument_id = ? ORDER BY date DESC LIMIT 1",
        (instrument_id,),
    ).fetchone() if instrument_id is not None else None
    if price_row and price_row["close"]:
        upside_grid = pct_upside(price_grid, price_row["close"])
        print(f"  % upside vs last close ({price_row['close']}): {upside_grid}")


def cmd_ingest_output(args: argparse.Namespace) -> None:
    conn = get_conn()
    try:
        output_path = Path(args.file)
        try:
            raw_text = output_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"FAILED to read output file {output_path}: {exc}")
            sys.exit(1)

        row = conn.execute(
            "SELECT * FROM agent_runs WHERE id = ?", (args.ingest_output,)
        ).fetchone()
        if row is None:
            print(f"No agent_runs row with id={args.ingest_output}")
            sys.exit(1)

        role = row["role"]
        try:
            validated = validate_output(role, raw_text)
        except ContractViolation as exc:
            finished_at = _now_iso()
            conn.execute(
                "UPDATE agent_runs SET status = 'FAILED', error = ?, finished_at = ? WHERE id = ?",
                (str(exc), finished_at, args.ingest_output),
            )
            conn.commit()
            print(
                f"CONTRACT VIOLATION for agent_runs_id={args.ingest_output} role={role}: {exc}\n"
                f"agent_runs row marked FAILED. Fix the agent output (see .claude/agents/) and re-ingest."
            )
            sys.exit(1)

        output_json = validated.model_dump()

        # meta_research's scope check (target_file must be under registry/ or
        # .claude/agents/) is a contract-level invariant, checked BEFORE the
        # agent_runs row is marked COMPLETED — a scope violation must FAIL
        # the run, exactly like a pydantic contract violation does above.
        if role == "meta_research":
            try:
                _ingest_meta_research(conn, validated, output_json)
            except ContractViolation as exc:
                finished_at = _now_iso()
                conn.execute(
                    "UPDATE agent_runs SET status = 'FAILED', error = ?, finished_at = ? WHERE id = ?",
                    (str(exc), finished_at, args.ingest_output),
                )
                conn.commit()
                print(
                    f"FAILED for agent_runs_id={args.ingest_output} role={role}: {exc}\n"
                    f"agent_runs row marked FAILED. No proposal artifacts were written; registry/ untouched."
                )
                sys.exit(1)

        finished_at = _now_iso()
        conn.execute(
            "UPDATE agent_runs SET status = 'COMPLETED', finished_at = ? WHERE id = ?",
            (finished_at, args.ingest_output),
        )
        conn.commit()

        out_dir = PACKETS_DIR / row["run_batch_id"] / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{args.ingest_output}_{role}_output.json"
        dest.write_text(json.dumps(output_json, indent=2, default=str), encoding="utf-8")
        print(f"Ingested output for agent_runs_id={args.ingest_output} role={role} -> {dest}")

        if role == "news_processor":
            _ingest_news_processor(conn, validated)
        elif role == "macro_digest":
            _ingest_macro_digest(conn, validated)
        elif role == "narrative_intensity":
            _ingest_narrative_intensity(conn, validated)
        elif role == "fund_manager":
            _ingest_fund_manager(conn, validated, output_json)
        elif role == "sector_researcher":
            _ingest_sector_researcher(conn, validated)
        elif role == "buy_side":
            _ingest_buy_side(conn, validated)
        # meta_research's side effect already ran above (before the COMPLETED
        # stamp, so a scope violation can still fail the run). idea_gen /
        # synthesis / critique / risk_mgmt / allocator: no DB side effects —
        # their outputs chain via --prior-output.
    finally:
        conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="afund deterministic orchestrator")
    parser.add_argument("--list-due", action="store_true", help="List jobs due on --date (default today)")
    parser.add_argument("--show-pipeline", metavar="TRIGGER", help="Print the ordered step list for a trigger")
    parser.add_argument("--job", metavar="TRIGGER", help="Run a trigger's pipeline")
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="Override 'today' for --list-due / --job")
    parser.add_argument("--symbol", metavar="SYMBOL", help="Instrument symbol to scope a --job run to")
    parser.add_argument("--ticker", metavar="TICKER", default=None,
                        help="Instrument ticker for equity_research_kickoff / buy_side_analysis triggers "
                             "(afund.research.er_adapter steps)")
    parser.add_argument("--sector", metavar="SECTOR", default=None,
                        help="Registry sector slug (e.g. it_technology, bfsi) for the sector_research trigger "
                             "(afund.research.sector_assembler.build_sector_packet)")
    parser.add_argument("--scope", metavar="SCOPE", default=None,
                        help='Cycle-assessment scope (e.g. "NIFTY 50" or a sector slug like "bfsi") — '
                             "narrative_intensity steps only; omit to fan out over every scope assessed today")
    parser.add_argument("--period", metavar="PERIOD", default=None,
                        help="Period to scope a --job run to, e.g. 2026-Q2 (meta_research_cycle only)")
    parser.add_argument("--step", metavar="N", type=int, default=None,
                        help="Run only the Nth (1-based) step of the --job trigger's pipeline")
    parser.add_argument("--prior-output", metavar="FILE", default=None,
                        help="JSON file with the prior agent step's (ingested) output, embedded in the packet as prior_output — for chaining agent steps across separate --job --step invocations")
    parser.add_argument("--record-human-decision", metavar="DECISION_ID", type=int, help="decision_log id to record a human call for")
    parser.add_argument("--decision", choices=["APPROVE", "REJECT", "MODIFY"], help="Human decision value")
    parser.add_argument("--notes", default=None, help="Optional human notes for --record-human-decision")
    parser.add_argument("--ingest-output", metavar="AGENT_RUNS_ID", type=int, help="agent_runs id to ingest output for")
    parser.add_argument("--file", metavar="OUTPUT_JSON", help="Path to the agent's output JSON (for --ingest-output)")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_due:
        cmd_list_due(args)
    elif args.show_pipeline:
        cmd_show_pipeline(args)
    elif args.job:
        cmd_job(args)
    elif args.record_human_decision is not None:
        if not args.decision:
            parser.error("--record-human-decision requires --decision")
        cmd_record_human_decision(args)
    elif args.ingest_output is not None:
        if not args.file:
            parser.error("--ingest-output requires --file")
        cmd_ingest_output(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
