"""File-based bridge to the external Equity Researcher subsystem
(research/equity_researcher/ — its own CLAUDE.md, its own Claude Code
session; see that folder's "Fund integration" section).

Four entry points, all manual-first (per CLAUDE.md's hard rule: nothing
here invokes an LLM or crosses into the subsystem's own process):

  prepare_kickoff(conn, ticker, docs_paths=None, fetch_documents=True)
      Writes research/equity_researcher/input/<TICKER>/fund_context.json,
      logs a PREPARED agent_runs row (role='equity_researcher',
      backend='claude_code'), and prints the instruction telling the
      operator to open a Claude Code session inside
      research/equity_researcher/ and run the pipeline for <TICKER>. When
      fetch_documents=True (default), also invokes fetch_er_documents()
      first so input/<TICKER>/ is pre-populated with BSE+Screener
      disclosures before the operator ever opens that session — see
      fetch_er_documents below. Failure-tolerant: a fetch error never
      blocks kickoff from completing.

  fetch_er_documents(ticker, company_name=None)
      Runs research/disclosure_fetcher (BSE + Screener primary sources,
      key-free, web-search/Gemini fallback OFF) for `ticker`, landing raw
      downloads under data/raw/disclosures/<TICKER>/ (gitignored), then
      copies/renames the results into
      research/equity_researcher/input/<TICKER>/ following that folder's
      README naming conventions (AR_/Q_/TR_/PPT_ prefixes). Never raises —
      any failure is caught and returned as a warning string so a kickoff
      that calls this always completes.

  ingest_er_output(conn, ticker)
      Reads back workspace/<TICKER>/report/final_note.md and
      workspace/<TICKER>/handoff/valuation_handoff.json once a run
      completes, maps the handoff's rating.value into an EquityResearchNote
      (BUY/ADD -> BULLISH, HOLD -> NEUTRAL, REDUCE/SELL/AVOID -> BEARISH),
      validates it via afund.agents.contracts, upserts a research_reports
      row, and stores the note JSON under data/packets/research/.

  build_buy_side_packet(conn, ticker, batch_id=None)
      Assembles the buy_side agent's context packet from the latest ingested
      EQUITY research_reports row's valuation_handoff.json plus the fund's
      cycle context, the buyside_depth.md reference pointer, and the
      interpretation frame/ledger for the name (which multiple the sector is
      judged on, and which facts the ER run found genuinely contested) —
      used by the buy_side_analysis trigger's second py: step, after
      ingest_er_output has run.

Nothing here calls an LLM (fetch_er_documents runs the disclosure fetcher
with enable_web_fallback=False, so it never touches Gemini/Tavily either —
see research/disclosure_fetcher/README.md "Fund integration"). equity_researcher
has no fund-side .claude/agents/*.md — the actual research work happens in a
separate Claude Code session governed by research/equity_researcher/CLAUDE.md,
so prepare_kickoff bypasses afund.agents.runner.prepare_invocation()'s generic
instruction text (which assumes a .claude/agents/<role>.md file exists) and
writes its own PREPARED row + a kickoff-specific instruction directly.
sector_researcher and buy_side DO have real .claude/agents/*.md files, so
their agent: steps in run.py use prepare_invocation() normally, pointed at
the packet path this module (or sector_assembler) already wrote.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

from afund.agents.contracts import ContractViolation, validate_output
from afund.config import REPO_ROOT
from afund.orchestrator.context import PACKETS_DIR
from afund.research.interpretation import (
    FACTS_VS_INTERPRETATION_REF,
    resolve_frame,
)

ER_ROOT = REPO_ROOT / "research" / "equity_researcher"
ER_INPUT_DIR = ER_ROOT / "input"
ER_WORKSPACE_DIR = ER_ROOT / "workspace"
RESEARCH_PACKETS_DIR = REPO_ROOT / "data" / "packets" / "research"

DISCLOSURE_FETCHER_DIR = REPO_ROOT / "research" / "disclosure_fetcher"
RAW_DISCLOSURES_DIR = REPO_ROOT / "data" / "raw" / "disclosures"

BUYSIDE_DEPTH_REF = "methodology/buyside_depth.md"

# disclosure_fetcher doc_type (downloads/<company>/<doc_type>/) -> ER
# input/README.md naming prefix. half_yearly_result and special_disclosure
# have no dedicated ER pattern; half-yearly lands alongside quarterlies
# under the Q_ prefix (SEBI LODR quarterly reporting means most main-board
# companies have zero of these anyway - see disclosure_fetcher's README),
# special_disclosure falls through to the README's "anything else" bucket
# and is copied under its original filename, unprefixed. earnings_transcript
# maps to TR here for reference, but fetch_er_documents special-cases its
# filename to a date (TR_2026-05-12.pdf per the README), not a period
# suffix like the other three.
_DOC_TYPE_TO_ER_PREFIX = {
    "annual_report": "AR",
    "quarterly_result": "Q",
    "half_yearly_result": "Q",
    "earnings_transcript": "TR",
    "investor_presentation": "PPT",
}

# disclosure_fetcher source subdirectory names (downloader._DOC_TYPE_DIRS)
_DOC_TYPE_SUBDIRS = {
    "annual_report": "annual_reports",
    "quarterly_result": "quarterly_results",
    "half_yearly_result": "half_yearly_results",
    "earnings_transcript": "transcripts",
    "investor_presentation": "presentations",
    "special_disclosure": "special_disclosures",
}

_PERIOD_LABEL_RE = re.compile(r"^(?:Q(?P<q>\d)\s+)?FY(?P<yy>\d{2})$")

_knowledge_added = False


def _load_knowledge():
    global _knowledge_added
    if not _knowledge_added:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        _knowledge_added = True
    from knowledge.loader import Knowledge

    return Knowledge

# ER's handoff rating.value (schema/valuation_handoff.schema.json) -> the
# fund's EquityResearchNote.rating enum. Any value not listed here (e.g. an
# unexpected string) is treated as unmapped and left as rating=None with a
# note flag, rather than guessing — never fabricate a rating the source
# document didn't actually support.
RATING_MAP: dict[str, str] = {
    "BUY": "BULLISH",
    "ADD": "BULLISH",
    "HOLD": "NEUTRAL",
    "REDUCE": "BEARISH",
    "SELL": "BEARISH",
    "AVOID": "BEARISH",
}

_registry_added = False


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sector_for_ticker(conn: sqlite3.Connection, ticker: str) -> tuple[int | None, str | None]:
    row = conn.execute(
        "SELECT id, sector FROM instruments WHERE symbol = ? ORDER BY id LIMIT 1", (ticker,)
    ).fetchone()
    if row is None:
        return None, None
    return row["id"], row["sector"]


def _kpi_key_for_sector(raw_sector: str | None) -> str:
    # Local import to avoid a hard import-time dependency loop between
    # orchestrator.context and this module; context.py owns the canonical
    # SECTOR_TO_KPI_KEY mapping.
    from afund.orchestrator.context import _kpi_key_for_sector as _map

    return _map(raw_sector)


def _sector_cycle_phase(conn: sqlite3.Connection, kpi_key: str | None) -> dict | None:
    from afund.orchestrator.context import _build_cycle_context

    if not kpi_key:
        return None
    return _build_cycle_context(conn, scope=kpi_key, sector=kpi_key)


def _portfolio_position(conn: sqlite3.Connection, instrument_id: int | None) -> dict | None:
    if instrument_id is None:
        return None
    row = conn.execute(
        "SELECT instrument_id, qty, avg_cost, realized_pnl FROM positions WHERE instrument_id = ?",
        (instrument_id,),
    ).fetchone()
    if row is None or not row["qty"]:
        return None
    return {"qty": row["qty"], "avg_cost": row["avg_cost"], "realized_pnl": row["realized_pnl"]}


def _is_watchlisted(ticker: str) -> bool:
    from afund.config import load_settings

    settings = load_settings()
    watchlist = ((settings.get("universe") or {}).get("watchlist")) or []
    return ticker in watchlist


def _company_name_for_ticker(conn: sqlite3.Connection, ticker: str) -> str | None:
    row = conn.execute(
        "SELECT name FROM instruments WHERE symbol = ? ORDER BY id LIMIT 1", (ticker,)
    ).fetchone()
    if row is None:
        return None
    return row["name"] or None


def _period_to_er_suffix(period_label: str) -> str | None:
    """"Q4 FY26" -> "FY2026Q4"; "FY26" -> "FY2026" (ER input/README.md's
    AR_FY2025.pdf / Q_FY2026Q1.pdf naming). Returns None if period_label
    doesn't match the expected disclosure_fetcher format (e.g. a
    special_disclosure's "Disclosure (2026-02-14)" label, or a
    period-less "recent material disclosures" filler) - callers fall back
    to a sanitized-title filename in that case rather than fabricating a
    period.
    """
    m = _PERIOD_LABEL_RE.match(period_label.strip())
    if not m:
        return None
    yy = int(m.group("yy"))
    full_year = 2000 + yy
    q = m.group("q")
    return f"FY{full_year}Q{q}" if q else f"FY{full_year}"


def _safe_stem(text: str, max_len: int = 60) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in text)
    keep = re.sub(r"\s+", "_", keep.strip())
    return keep[:max_len] or "doc"


def fetch_er_documents(ticker: str, company_name: str | None = None) -> dict:
    """Run research/disclosure_fetcher for `ticker` (BSE + Screener only,
    web-search/Gemini fallback OFF — key-free) and map its output into
    research/equity_researcher/input/<TICKER>/ per that folder's README
    naming conventions.

    Raw downloads land under data/raw/disclosures/<TICKER>/ first
    (gitignored — see .gitignore); this function then copies (not moves,
    so the raw archive stays intact for re-runs/audits) the accepted
    documents into input/<TICKER>/ with README-convention filenames, plus
    manifest.csv unchanged.

    Never raises: any failure (missing `disclosure_fetcher`/`bse` package,
    network error, unresolved company, etc.) is caught and returned as
    {"status": "error", "warning": <str>} so callers (prepare_kickoff) can
    still complete the kickoff with a clear "documents not fetched" note
    rather than blocking on it.

    Returns a dict: {"status": "ok"|"error"|"unresolved", "counts": {...},
    "manifest_path": str|None, "raw_dir": str, "warning": str|None}.
    """
    raw_dir = RAW_DISCLOSURES_DIR / ticker
    query = company_name or ticker

    try:
        if str(DISCLOSURE_FETCHER_DIR) not in sys.path:
            sys.path.insert(0, str(DISCLOSURE_FETCHER_DIR))
        from disclosure_fetcher.config import FetchTargets
        from disclosure_fetcher.pipeline import run_pipeline
    except Exception as exc:  # pragma: no cover - environment/import issue
        return {
            "status": "error",
            "counts": {},
            "manifest_path": None,
            "raw_dir": str(raw_dir),
            "warning": f"disclosure_fetcher not importable ({exc}); documents not fetched.",
        }

    try:
        result = run_pipeline(
            company_query=query,
            targets=FetchTargets(),
            output_dir=raw_dir,
            enable_web_fallback=False,  # key-free BSE+Screener only, per CLAUDE.md hard rules
        )
    except Exception as exc:
        return {
            "status": "error",
            "counts": {},
            "manifest_path": None,
            "raw_dir": str(raw_dir),
            "warning": f"disclosure_fetcher run failed for {query!r}: {exc}; documents not fetched.",
        }

    if not result.company.is_resolved():
        return {
            "status": "unresolved",
            "counts": {},
            "manifest_path": None,
            "raw_dir": str(raw_dir),
            "warning": f"disclosure_fetcher could not resolve {query!r} to a BSE-listed company; "
            f"documents not fetched. Warnings: {'; '.join(result.warnings) or 'none'}",
        }

    ticker_input_dir = ER_INPUT_DIR / ticker
    ticker_input_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for candidate in result.downloaded:
        if not candidate.local_path:
            continue
        src = Path(candidate.local_path)
        if not src.exists():
            continue

        doc_type = candidate.doc_type.value
        prefix = _DOC_TYPE_TO_ER_PREFIX.get(doc_type)

        if doc_type == "earnings_transcript":
            # README wants a date, not a fiscal period, for transcripts:
            # TR_2026-05-12.pdf. Fall back to a sanitized period/title if
            # announced_on wasn't captured (rare - BSE candidates always
            # have it; a web-sourced one might not, though fallback is off
            # by default anyway).
            if candidate.announced_on:
                dest_name = f"TR_{candidate.announced_on.isoformat()}{src.suffix}"
            else:
                dest_name = f"TR_{_safe_stem(candidate.period_label)}{src.suffix}"
        elif prefix:
            suffix = _period_to_er_suffix(candidate.period_label)
            if suffix:
                dest_name = f"{prefix}_{suffix}{src.suffix}"
            else:
                # period_label didn't parse (shouldn't normally happen for
                # these doc types) - fall back to a sanitized title rather
                # than silently dropping the document.
                dest_name = f"{prefix}_{_safe_stem(candidate.period_label)}{src.suffix}"
        else:
            # special_disclosure (and anything else not mapped): README's
            # "anything else / Other disclosures" bucket - keep the
            # original descriptive filename, unprefixed.
            dest_name = src.name

        dest = ticker_input_dir / dest_name
        counter = 1
        while dest.exists():
            dest = ticker_input_dir / f"{dest.stem}_{counter}{dest.suffix}"
            counter += 1

        shutil.copy2(src, dest)
        counts[doc_type] = counts.get(doc_type, 0) + 1

    manifest_dest = None
    if result.manifest_path:
        manifest_src = Path(result.manifest_path)
        if manifest_src.exists():
            manifest_dest = ticker_input_dir / "manifest.csv"
            shutil.copy2(manifest_src, manifest_dest)

    return {
        "status": "ok",
        "counts": counts,
        "manifest_path": str(manifest_dest) if manifest_dest else None,
        "raw_dir": str(raw_dir),
        "company": {
            "name": result.company.name,
            "bse_scrip_code": result.company.bse_scrip_code,
            "nse_symbol": result.company.nse_symbol,
            "screener_url": result.company.screener_url,
        },
        "warnings": result.warnings,
        "warning": None,
    }


def prepare_kickoff(
    conn: sqlite3.Connection,
    ticker: str,
    docs_paths: list[str] | None = None,
    fetch_documents: bool = True,
) -> dict:
    """Write input/<TICKER>/fund_context.json for the ER subsystem, log a
    PREPARED agent_runs row (role='equity_researcher', backend='claude_code'),
    and print the manual-first kickoff instruction.

    Returns {"agent_runs_id": int, "fund_context_path": str, "instruction": str}.
    """
    instrument_id, raw_sector = _sector_for_ticker(conn, ticker)
    kpi_key = _kpi_key_for_sector(raw_sector)
    cycle_context = _sector_cycle_phase(conn, kpi_key)
    position = _portfolio_position(conn, instrument_id)
    watchlisted = _is_watchlisted(ticker)

    fetch_result: dict | None = None
    if fetch_documents:
        company_name = _company_name_for_ticker(conn, ticker)
        try:
            fetch_result = fetch_er_documents(ticker, company_name=company_name)
        except Exception as exc:  # pragma: no cover - fetch_er_documents already
            # catches its own errors; this is a last-resort net so a bug there
            # can never block kickoff from completing (failure-tolerant per spec).
            fetch_result = {
                "status": "error",
                "counts": {},
                "manifest_path": None,
                "raw_dir": str(RAW_DISCLOSURES_DIR / ticker),
                "warning": f"fetch_er_documents raised unexpectedly: {exc}; documents not fetched.",
            }

    fund_context = {
        "ticker": ticker,
        "generated_at": _now_iso(),
        "sector": raw_sector,
        "sector_kpi_key": kpi_key,
        "sector_cycle_phase": (
            {
                "phase_id": next(
                    (c["phase_id"] for c in cycle_context["cycles"] if c["phase_id"]), None
                ),
                "as_of_date": cycle_context["as_of_date"],
                "regime_cluster": cycle_context["regime_cluster"],
            }
            if cycle_context
            else None
        ),
        "portfolio_position": position,
        "watchlisted": watchlisted,
        "docs_paths": docs_paths or [],
        "documents_fetched": fetch_result,
    }

    ticker_input_dir = ER_INPUT_DIR / ticker
    ticker_input_dir.mkdir(parents=True, exist_ok=True)
    fund_context_path = ticker_input_dir / "fund_context.json"
    fund_context_path.write_text(json.dumps(fund_context, indent=2, default=str), encoding="utf-8")

    batch_id = f"equity_research_kickoff_{ticker}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    started_at = _now_iso()
    cur = conn.execute(
        """
        INSERT INTO agent_runs
            (run_batch_id, role, model, backend, trigger, input_tokens,
             output_tokens, cost_usd, status, error, started_at, finished_at)
        VALUES (?, 'equity_researcher', 'sonnet', 'claude_code', 'equity_research_kickoff',
                NULL, NULL, NULL, 'PREPARED', NULL, ?, NULL)
        """,
        (batch_id, started_at),
    )
    conn.commit()
    agent_runs_id = cur.lastrowid

    if fetch_result is None:
        fetch_note = "Document auto-fetch skipped (fetch_documents=False)."
    elif fetch_result["status"] == "ok":
        total = sum(fetch_result["counts"].values())
        fetch_note = (
            f"Document auto-fetch OK: {total} document(s) landed in "
            f"research/equity_researcher/input/{ticker}/ ({fetch_result['counts']})."
        )
    else:
        fetch_note = f"Document auto-fetch NOT completed: {fetch_result['warning']}"

    instruction = (
        f"READY: equity_researcher kickoff prepared for {ticker} "
        f"(agent_runs_id={agent_runs_id}). fund_context written to "
        f"{fund_context_path}.\n"
        f"{fetch_note}\n"
        f"MANUAL STEP: open a Claude Code session in research/equity_researcher/ "
        f"and run the pipeline for {ticker} (drop any source documents into "
        f"research/equity_researcher/input/{ticker}/ alongside fund_context.json "
        f"first). Once the run completes, ingest its output with:\n"
        f"  .venv\\Scripts\\python -m afund.orchestrator.run --ingest-output {agent_runs_id} "
        f"--file <output.json>\n"
        f"or call afund.research.er_adapter.ingest_er_output(conn, {ticker!r}) directly."
    )
    print(instruction)

    return {
        "agent_runs_id": agent_runs_id,
        "fund_context_path": str(fund_context_path),
        "instruction": instruction,
        "documents_fetched": fetch_result,
    }


def _parse_rating_from_handoff(handoff: dict) -> tuple[str | None, str | None]:
    """Returns (mapped_rating, raw_rating_value). mapped_rating is None if
    the handoff's rating.value doesn't match a known ER rating token — never
    guess a mapping the source document doesn't support."""
    raw_value = (handoff.get("rating") or {}).get("value")
    if raw_value is None:
        return None, None
    mapped = RATING_MAP.get(raw_value.strip().upper())
    return mapped, raw_value


def _parse_rating_from_final_note(final_note_text: str) -> str | None:
    """Fallback parse: the final note template's first rating-box row is
    `| **{RATING}** | {One-line thesis} |`. Only used if the handoff JSON
    lacks a rating (it shouldn't, per schema, but the note is a
    cross-check/fallback source, never the primary one)."""
    m = re.search(r"\|\s*\*\*(\w+)\*\*\s*\|\s*(.+?)\s*\|", final_note_text)
    if not m:
        return None
    return m.group(1).strip().upper()


def ingest_er_output(conn: sqlite3.Connection, ticker: str) -> dict:
    """Read back workspace/<TICKER>/report/final_note.md +
    handoff/valuation_handoff.json, map into an EquityResearchNote, validate
    it, upsert a research_reports row, and store the note JSON under
    data/packets/research/.

    Raises FileNotFoundError if either expected output file is missing, and
    ContractViolation if the mapped note fails EquityResearchNote validation
    (both are fail-loud conditions — an ER run must finish and validate
    before it's usable downstream).
    """
    workspace_dir = ER_WORKSPACE_DIR / ticker
    final_note_path = workspace_dir / "report" / "final_note.md"
    handoff_path = workspace_dir / "handoff" / "valuation_handoff.json"
    # Additive (Phase 11 — EPS-bridge doctrine): tools/export_financials_xlsx.py's
    # output, if the COMPUTE step produced one for this run. Optional — an
    # ER run predating this artifact, or one where the export step was
    # skipped, still ingests fine with xlsx_path left NULL.
    xlsx_path = workspace_dir / "exports" / f"{ticker}_financials.xlsx"

    if not final_note_path.exists():
        raise FileNotFoundError(f"final_note.md not found for {ticker}: {final_note_path}")
    if not handoff_path.exists():
        raise FileNotFoundError(f"valuation_handoff.json not found for {ticker}: {handoff_path}")

    final_note_text = final_note_path.read_text(encoding="utf-8")
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))

    mapped_rating, raw_rating_value = _parse_rating_from_handoff(handoff)
    if mapped_rating is None:
        raw_rating_value = raw_rating_value or _parse_rating_from_final_note(final_note_text)
        mapped_rating = RATING_MAP.get((raw_rating_value or "").upper())

    thesis = (handoff.get("rating") or {}).get("thesis_one_line")
    as_of_date = handoff.get("as_of") or dt.date.today().isoformat()

    # Additive (facts/interpretation layer): the two artifacts prompts/33 step
    # 6b and prompts/34 write. Recorded as sources so the note's provenance
    # names the adversarial pass, and returned so a caller can see at ingest
    # time whether the thesis was actually contested — an ER run that produced
    # neither is one where checks 16-18 never ran. Optional, like the xlsx
    # above: an older run ingests fine without them.
    ledger_path = workspace_dir / "state" / "interpretation_ledger.json"
    redteam_path = workspace_dir / "findings" / "thesis_redteam.json"
    ledger = _read_er_json(ticker, "state", "interpretation_ledger.json")
    redteam = _read_er_json(ticker, "findings", "thesis_redteam.json")

    extra_sources = [
        str(p) for p, present in ((ledger_path, ledger), (redteam_path, redteam)) if present
    ]

    note_payload = {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "status": "OK",
        "rating": mapped_rating,
        "conviction": None,
        "thesis": thesis,
        "key_drivers": handoff.get("growth_drivers") or [],
        "sector_kpi_readout": [],
        "valuation": {
            "pe_bands": handoff.get("pe_bands"),
            "scenario_seeds": handoff.get("scenario_seeds"),
        },
        "risks": handoff.get("key_risks_to_estimates") or [],
        "invalidation_condition": None,
        "sources": [str(final_note_path), str(handoff_path)] + extra_sources,
    }

    try:
        validated = validate_output("equity_researcher", note_payload)
    except ContractViolation:
        raise

    RESEARCH_PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    note_json_path = RESEARCH_PACKETS_DIR / f"{ticker}_{as_of_date}_equity.json"
    note_json_path.write_text(
        json.dumps(validated.model_dump(), indent=2, default=str), encoding="utf-8"
    )

    instrument_id, _ = _sector_for_ticker(conn, ticker)
    created_at = _now_iso()
    xlsx_path_value = str(xlsx_path) if xlsx_path.exists() else None
    conn.execute(
        """
        INSERT INTO research_reports
            (instrument_id, ticker, report_type, final_note_path, handoff_path,
             rating, as_of_date, status, created_at, xlsx_path)
        VALUES (?, ?, 'EQUITY', ?, ?, ?, ?, 'OK', ?, ?)
        ON CONFLICT(ticker, report_type, as_of_date) DO UPDATE SET
            instrument_id = COALESCE(excluded.instrument_id, research_reports.instrument_id),
            final_note_path = excluded.final_note_path,
            handoff_path = excluded.handoff_path,
            rating = COALESCE(excluded.rating, research_reports.rating),
            status = excluded.status,
            created_at = excluded.created_at,
            xlsx_path = COALESCE(excluded.xlsx_path, research_reports.xlsx_path)
        """,
        (instrument_id, ticker, str(final_note_path), str(handoff_path), mapped_rating, as_of_date, created_at, xlsx_path_value),
    )
    conn.commit()

    return {
        "ticker": ticker,
        "rating": mapped_rating,
        "raw_rating_value": raw_rating_value,
        "note_json_path": str(note_json_path),
        "note": validated.model_dump(),
        "interpretation_ledger_entries": len(ledger.get("entries") or []) if ledger else None,
        "redteam_verdict": (redteam or {}).get("verdict"),
    }


def _knowledge_reference_pointer(rel_path: str) -> dict | None:
    """Path + 1-line summary for a knowledge/references/<rel_path> doc — a
    pointer, never the prose itself (token frugality; CLAUDE.md hard rule).
    Returns None if no matching reference doc exists."""
    Knowledge = _load_knowledge()
    k = Knowledge.load()
    for ref in k.references:
        if ref.path == rel_path:
            return {"path": f"knowledge/references/{ref.path}", "summary": ref.summary}
    return None


def _comprehensive_statement_pointer(ticker: str) -> dict | None:
    """Path + 1-line description of the ER subsystem's
    state/comprehensive_statement.json for this ticker — a pointer only
    (token frugality; CLAUDE.md hard rule), never the tree contents inline.
    Returns None if the ER run for this ticker hasn't produced one yet (e.g.
    an older run predating this artifact, or COMPUTE step not yet re-run)."""
    path = ER_WORKSPACE_DIR / ticker / "state" / "comprehensive_statement.json"
    if not path.exists():
        return None
    return {
        "path": str(path),
        "summary": (
            "3-level line-item tree (IS/BS/CF) x all fiscal years/quarters "
            "with fact_ids per node — the authoritative multi-period view "
            "behind the valuation handoff; Read directly if deeper line-item "
            "detail than the handoff summary is needed."
        ),
    }


def _eps_bridge_check_block(ticker: str) -> dict | None:
    """Full contents of state/eps_bridge_check.json for this ticker —
    inlined (not a pointer) per plan section A.3: it IS the numeric
    skeleton buy_side reasons from, and is small (fixed set of ~9 rule_ids
    plus numbers), so token cost is negligible vs. the value of not making
    the agent Read a second file for its primary input. Returns None if
    tools/eps_bridge_check.py hasn't run for this ticker yet (older run,
    or COMPUTE step predates this artifact) — buy_side.md is written to
    degrade gracefully when this key is absent."""
    path = ER_WORKSPACE_DIR / ticker / "state" / "eps_bridge_check.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _xlsx_path_pointer(ticker: str) -> str | None:
    """Path to workspace/<TICKER>/exports/<TICKER>_financials.xlsx (written
    by tools/export_financials_xlsx.py) — a pointer only, never inlined
    (it's a binary workbook). Returns None if the export hasn't been
    produced for this ticker yet."""
    path = ER_WORKSPACE_DIR / ticker / "exports" / f"{ticker}_financials.xlsx"
    return str(path) if path.exists() else None


def _narrative_findings_pointer(ticker: str) -> dict | None:
    """Path + 1-line summary of the ER subsystem's findings/guidance.json
    for this ticker — the module that owns management-intent/delivery-
    track-record narrative (guidance ledger + contradiction list), i.e.
    the qualitative gate in eps_bridge.md section v. A pointer only (token
    frugality); Read if the packet's own guidance_ledger (already inlined
    inside valuation_handoff) isn't enough detail. Returns None if this ER
    run hasn't produced findings/guidance.json yet."""
    path = ER_WORKSPACE_DIR / ticker / "findings" / "guidance.json"
    if not path.exists():
        return None
    return {
        "path": str(path),
        "summary": (
            "Guidance-analyst findings: management-intent narrative, "
            "quote-grounded guidance ledger, and delivery-vs-promise "
            "contradiction list — the qualitative gate behind eps_bridge.md "
            "section v (management must be actively discussing the "
            "strategies the numeric bridge implies, with a track record of "
            "delivering on it)."
        ),
    }


def _read_er_json(ticker: str, *parts: str) -> dict | None:
    """Read one of the ER run's own JSON artifacts, or None if this run
    didn't produce it. Never raises on a malformed file — a half-written
    artifact must not take down a packet build; the caller records absence."""
    path = ER_WORKSPACE_DIR / ticker
    for part in parts:
        path = path / part
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _interpretation_frame(handoff: dict, kpi_key: str | None) -> dict | None:
    """Which multiple this name is judged on, and which conditioning
    variables make that judgement defensible — layered family-then-playbook
    (src/afund/research/interpretation.py::resolve_frame).

    Playbook first, because the ER run classified the business (32 tier-2
    playbooks, triage T2) while `kpi_key` is only a mapping off the NSE
    industry string — `life_insurance` is judged on P/EV, not on bfsi's P/B,
    and only the ER classification knows that. Falls back to the fund's own
    family slug when the handoff names no playbook, or names one this
    checkout's vendored registry doesn't carry (an ER run newer than the
    sync). Returns None when neither resolves: no frame is the honest answer
    for a sector nobody has authored one for, and the buy_side prompt is
    written to fall back to first principles rather than to a default
    multiple nobody chose.
    """
    playbook = (handoff.get("sector_playbook") or "").strip() or None
    if playbook:
        frame = resolve_frame(playbook=playbook)
        if frame is not None:
            return frame
    return resolve_frame(family=kpi_key)


def _interpretation_ledger(ticker: str, handoff: dict) -> dict | None:
    """The same-fact/divergent-readings ledger for this run.

    Prefers the copy the valuation handoff carries (that is the contract
    surface between the two systems — schema/valuation_handoff.schema.json
    `interpretation_ledger`), falling back to the ER run's own
    state/interpretation_ledger.json, which prompts/33 step 6b owns. Returns
    None when neither exists, and a consumer must read that as "not
    computed", never as "no divergence" — a P/E with no recorded divergence
    is usually one nobody contested, not one nobody could.
    """
    from_handoff = handoff.get("interpretation_ledger")
    if isinstance(from_handoff, list) and from_handoff:
        return {
            "source": "valuation_handoff.interpretation_ledger",
            "entries": from_handoff,
        }
    if isinstance(from_handoff, dict) and from_handoff.get("entries"):
        return {"source": "valuation_handoff.interpretation_ledger", **from_handoff}

    state = _read_er_json(ticker, "state", "interpretation_ledger.json")
    if state and state.get("entries"):
        return {
            "source": str(
                ER_WORKSPACE_DIR / ticker / "state" / "interpretation_ledger.json"
            ),
            **state,
        }
    return None


def _redteam_findings(ticker: str) -> dict | None:
    """The decision-relevant slice of findings/thesis_redteam.json.

    Sub-selected rather than inlined whole: prompts/34 Part 7 emits several
    long prose fields (`opposite_case`, `premortem`,
    `what_would_have_broken_it`) alongside the structured verdict, and the
    packet carries a pointer to the file for those (token frugality;
    CLAUDE.md hard rule). What stays inline is what changes a buy-side
    decision — the verdict, the interpretation audit (checks 16-18), the
    divergences the red team could not settle, and any banned-reasoning
    hits, which are binding under that prompt's "Consequences" section
    rather than advisory. `checks` is reduced to failures only: 18 passes
    carry no information, and a fail names the offending sentence.
    """
    data = _read_er_json(ticker, "findings", "thesis_redteam.json")
    if not data:
        return None

    checks = data.get("checks")
    failed = []
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict) and str(check.get("status", "")).lower() == "fail":
                failed.append(check)

    return {
        "path": str(ER_WORKSPACE_DIR / ticker / "findings" / "thesis_redteam.json"),
        "verdict": data.get("verdict"),
        "rating_change_recommended": data.get("rating_change_recommended"),
        "disconfirming_exhibit_present": data.get("disconfirming_exhibit_present"),
        "material_challenges": data.get("material_challenges") or [],
        "banned_reasoning_hits": data.get("banned_reasoning_hits") or [],
        "interpretation_audit": data.get("interpretation_audit"),
        "unresolved_divergences": data.get("unresolved_divergences") or [],
        "failed_checks": failed,
        "note": (
            "Sub-selected from the red-team findings; Read the path above for "
            "the full attack (opposite_case, premortem, peer-comparability "
            "audit). A high-severity material challenge must be answered in "
            "the recommendation, not dropped."
        ),
    }


def _opinion_audit_reference() -> dict:
    """Pointer to the doctrine the audit runs on — never the prose itself."""
    return {
        "fund_methodology": (
            _knowledge_reference_pointer(FACTS_VS_INTERPRETATION_REF)
            or {"path": f"knowledge/references/{FACTS_VS_INTERPRETATION_REF}"}
        ),
        "er_doctrine": str(ER_ROOT / "docs" / "OPINION_VS_ANALYSIS.md"),
        "summary": (
            "Fact vs reading vs discriminator: a fact is published, a reading "
            "is fact + conditioning variable + sector convention -> verdict, "
            "and only four discriminator types may settle a divergence "
            "(historical_distribution, peer_distribution, disclosed_mechanism, "
            "forward_observable). ER doc section 4 is the 18-check audit, "
            "section 5 the banned-reasoning list, section 7 the divergence rule."
        ),
    }


def build_buy_side_packet(conn: sqlite3.Connection, ticker: str, *, batch_id: str | None = None) -> dict:
    """Assemble, budget-cap, and persist the buy_side agent's context packet
    for one ticker: the latest ingested EQUITY research_reports row's
    valuation_handoff.json contents, the fund's cycle context for the
    ticker's sector, a pointer to buyside_depth.md, and the interpretation
    layer (sector playbook, layered multiple frame, divergence ledger,
    red-team findings).

    Requires ingest_er_output(conn, ticker) to have already run (there must
    be a research_reports row with report_type='EQUITY' and a non-null
    handoff_path) — raises LookupError otherwise, since buy_side has nothing
    to analyze without a completed equity_researcher handoff.

    Returns {"path": str, "approx_tokens": int, "packet": dict}, matching the
    shape orchestrator.context.build_packet() / sector_assembler.build_sector_packet()
    return, so run.py's step dispatch can treat all three the same way.
    """
    row = conn.execute(
        """
        SELECT ticker, handoff_path, final_note_path, rating, as_of_date
          FROM research_reports
         WHERE ticker = ? AND report_type = 'EQUITY' AND handoff_path IS NOT NULL
         ORDER BY as_of_date DESC, id DESC
         LIMIT 1
        """,
        (ticker,),
    ).fetchone()
    if row is None:
        raise LookupError(
            f"no EQUITY research_reports row with a handoff_path found for {ticker!r} — "
            f"run afund.research.er_adapter.ingest_er_output(conn, {ticker!r}) first"
        )

    handoff_path = Path(row["handoff_path"])
    if not handoff_path.exists():
        raise FileNotFoundError(f"handoff_path on record no longer exists for {ticker}: {handoff_path}")
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))

    instrument_id, raw_sector = _sector_for_ticker(conn, ticker)
    kpi_key = _kpi_key_for_sector(raw_sector)
    cycle_context = _sector_cycle_phase(conn, kpi_key)
    position = _portfolio_position(conn, instrument_id)

    as_of = dt.date.today().isoformat()
    packet: dict = {
        "role": "buy_side",
        "ticker": ticker,
        "as_of": as_of,
        "prior_equity_research": {
            "rating": row["rating"],
            "as_of_date": row["as_of_date"],
            "final_note_path": row["final_note_path"],
        },
        "valuation_handoff": handoff,
        "cycle_context": cycle_context,
        "portfolio_position": position,
        "buyside_depth_reference": _knowledge_reference_pointer(BUYSIDE_DEPTH_REF),
        "comprehensive_statement_reference": _comprehensive_statement_pointer(ticker),
        # Additive (Phase 11 — EPS-bridge doctrine): eps_bridge_check.json
        # inlined (it IS the numeric skeleton, see .claude/agents/buy_side.md
        # "EPS-bridge reasoning skeleton"); xlsx/narrative-findings stay
        # pointers (binary / can be large). All three are None gracefully
        # when the ER run predates these artifacts.
        "eps_bridge_check": _eps_bridge_check_block(ticker),
        "xlsx_path": _xlsx_path_pointer(ticker),
        "narrative_findings_reference": _narrative_findings_pointer(ticker),
        # Additive (facts/interpretation layer). eps_bridge_check says whether
        # the earnings can grow; these say what a given multiple on those
        # earnings MEANS, and who would read it the other way. Without them
        # an agent handed "P/E 30" has no governed way to judge 30 and reaches
        # for tone. sector_playbook is the ER tier-2 classification (32 of
        # them) that the handoff carries; interpretation_frame is the layered
        # family-then-playbook convention; the ledger is the contested facts;
        # redteam_findings is what checks 16-18 made of them. All None/absent
        # gracefully on runs predating these artifacts.
        "sector_playbook": (handoff.get("sector_playbook") or None),
        "interpretation_frame": _interpretation_frame(handoff, kpi_key),
        "interpretation_ledger": _interpretation_ledger(ticker, handoff),
        "redteam_findings": _redteam_findings(ticker),
        "opinion_audit_reference": _opinion_audit_reference(),
        "truncation_notes": [],
    }

    total_chars = len(json.dumps(packet, default=str))
    packet["approx_tokens"] = total_chars // 4

    batch_id = batch_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = PACKETS_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(batch_dir.glob("[0-9][0-9]_*.json"))
    seq = len(existing) + 1
    out_path = batch_dir / f"{seq:02d}_buy_side.json"
    out_path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")

    return {"path": str(out_path), "approx_tokens": packet["approx_tokens"], "packet": packet}
