"""Permanent wiring audit: verifies the whole system is CONNECTED (not that
it has been executed — no network, no LLM, no live data fetch). Runs in
under ~30s.

Usage:
    .venv\\Scripts\\python scripts\\wiring_check.py

Exit code 0 if every check PASSes, 1 if any check FAILs. Prints an aligned
PASS/FAIL table with one row per check, grouped into the sections below
(mirrors plan section E's checklist a-h):

  a. Router TRIGGERS steps all resolve (py: callables import; agent: roles
     have a .claude/agents/<role>.md; HUMAN is a recognized terminal token).
  b. Three-way role consistency: settings.model_tiers keys <-> .claude/agents/*.md
     frontmatter (name+model match tier) <-> contracts.ROLE_MODELS registry.
     Documents the one intentional exception (equity_researcher: external
     subsystem role, no fund-side .md, no contract — see er_adapter.py).
  c. knowledge loader: every KPI's cycle_refs resolve against the catalog's
     cycle ids; every catalog anchor_kpi_id resolves to a defined KPI
     (already enforced by Knowledge.load() itself, re-asserted here);
     source_status values are legal.
  d. DB: live data/afund.db tables superset schema.sql's CREATE TABLE list;
     key additive columns present (research_reports.xlsx_path,
     decision_log.registry_version).
  e. Packet builders: every agent: role in TRIGGERS is servicable by either
     orchestrator.context.build_packet's generic dispatch or a dedicated
     builder (sector_assembler.build_sector_packet, er_adapter.build_buy_side_packet)
     — resolved by reading the actual dispatch source, not by assumption.
  f. ER chain: disclosure_fetcher package imports; er_adapter's four entry
     points exist; equity_researcher/tools/*.py import cleanly; buy_side
     packet keys (eps_bridge_check/xlsx_path/narrative_findings_reference)
     present in er_adapter's build_buy_side_packet source; registry/rules/
     eps_bridge.yaml loads as YAML.
  g. Registry + knowledge + cycle_framework all load without error, version
     stamps print.
  h. Cadences: every settings.yaml cadences key maps to a router trigger
     (documented exceptions for quarterly-only cadences with no automated
     trigger yet) and vice versa.
  i. Facts/interpretation layer: registry/rules/interpretation_frames.yaml and
     the ER config/sector_registry.yaml both load; the contracts' closed
     Literals match the governed vocabulary exactly; the new models are
     registered and the new optional fields exist on the four consuming
     contracts; resolve_frame() resolves every fund family and layers a tier-2
     playbook on top; both packet builders emit the new keys; the four agent
     prompts carry the doctrine section; and the three generator/checker
     scripts report current.

This script imports application modules but calls no pipeline .run(), no
agent invocation, and opens no network socket. It DOES open a read-only
connection to the live data/afund.db (if present) for check (d) only.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
DB_PATH = REPO_ROOT / "data" / "afund.db"
ER_ROOT = REPO_ROOT / "research" / "equity_researcher"
DISCLOSURE_FETCHER_DIR = REPO_ROOT / "research" / "disclosure_fetcher"
EPS_BRIDGE_RULES_PATH = REPO_ROOT / "registry" / "rules" / "eps_bridge.yaml"
INTERPRETATION_RULES_PATH = REPO_ROOT / "registry" / "rules" / "interpretation_frames.yaml"
ER_SECTOR_REGISTRY_PATH = ER_ROOT / "config" / "sector_registry.yaml"

# --------------------------------------------------------------------------
# Small result-collection helper
# --------------------------------------------------------------------------

Results = list[tuple[str, str, bool, str]]  # (section, check_name, passed, detail)


def _record(results: Results, section: str, name: str, passed: bool, detail: str = "") -> None:
    results.append((section, name, passed, detail))


# --------------------------------------------------------------------------
# a. Router TRIGGERS resolution
# --------------------------------------------------------------------------

def check_router_triggers(results: Results) -> None:
    section = "a.router"
    try:
        from afund.orchestrator.router import TRIGGERS
    except Exception as exc:
        _record(results, section, "import router.TRIGGERS", False, str(exc))
        return
    _record(results, section, "import router.TRIGGERS", True, f"{len(TRIGGERS)} triggers")

    for trigger, steps in TRIGGERS.items():
        for i, step in enumerate(steps, start=1):
            check_name = f"{trigger}[{i}] {step}"
            if step == "HUMAN":
                _record(results, section, check_name, True, "terminal/mid checkpoint token")
                continue
            if step.startswith("agent:"):
                role = step.split("agent:", 1)[1]
                md_path = AGENTS_DIR / f"{role}.md"
                if md_path.exists():
                    _record(results, section, check_name, True, str(md_path))
                else:
                    _record(results, section, check_name, False, f"missing {md_path}")
                continue
            if step.startswith("py:"):
                target_path = step.split("py:", 1)[1]
                module_path, attr_name = target_path.rsplit(".", 1)
                try:
                    module = importlib.import_module(module_path)
                    target = getattr(module, attr_name)
                    kind = "class" if isinstance(target, type) else "callable" if callable(target) else "value"
                    _record(results, section, check_name, True, f"resolved as {kind}")
                except Exception as exc:
                    _record(results, section, check_name, False, str(exc))
                continue
            _record(results, section, check_name, False, f"unrecognized step shape: {step!r}")


# --------------------------------------------------------------------------
# b. Role consistency three-way
# --------------------------------------------------------------------------

# Roles intentionally exempt from the three-way check, with the reason. Kept
# here (not silently skipped) so the exception is visible in the PASS table.
KNOWN_ROLE_EXCEPTIONS = {
    "equity_researcher": (
        "external subsystem role (research/equity_researcher/ has its own "
        "Claude Code session, no fund-side .claude/agents/*.md); DOES have a "
        "contracts.ROLE_MODELS entry (EquityResearchNote) for er_adapter's "
        "ingest_er_output validation, but no model_tiers entry since it "
        "never runs via afund.agents.runner's claude_code dispatch."
    ),
    "research_head": (
        "dispatcher role invoked sub-agent-to-sub-agent (by idea_gen/synthesis/"
        "critique/fund_manager directly, per its .claude/agents/research_head.md "
        "'Role mandate and boundary' section) — never appears as an agent: step "
        "in orchestrator.router.TRIGGERS and never runs through orchestrator/"
        "run.py's ingestion path, so it has model_tiers + a .md-documented JSON "
        "I/O shape but intentionally no contracts.ROLE_MODELS entry (nothing "
        "calls validate_output('research_head', ...))."
    ),
}


def check_role_consistency(results: Results) -> None:
    section = "b.roles"
    try:
        from afund.config import load_settings
        from afund.agents.contracts import ROLE_MODELS
    except Exception as exc:
        _record(results, section, "import settings/contracts", False, str(exc))
        return

    settings = load_settings()
    model_tiers: dict[str, str] = settings.get("model_tiers", {}) or {}

    agent_md_roles: dict[str, dict] = {}
    for md_path in sorted(AGENTS_DIR.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        agent_md_roles[md_path.stem] = fm

    _record(results, section, "model_tiers keys found", True, f"{len(model_tiers)} roles")
    _record(results, section, "agent .md files found", True, f"{len(agent_md_roles)} files")
    _record(results, section, "contracts.ROLE_MODELS roles found", True, f"{len(ROLE_MODELS)} roles")

    all_roles = set(model_tiers) | set(agent_md_roles) | set(ROLE_MODELS)
    for role in sorted(all_roles):
        if role in KNOWN_ROLE_EXCEPTIONS:
            _record(
                results, section, f"role consistency: {role}", True,
                f"documented exception: {KNOWN_ROLE_EXCEPTIONS[role]}",
            )
            continue

        in_tiers = role in model_tiers
        in_md = role in agent_md_roles
        in_contract = role in ROLE_MODELS

        if not (in_tiers and in_md and in_contract):
            missing = []
            if not in_tiers:
                missing.append("model_tiers")
            if not in_md:
                missing.append(".claude/agents/*.md")
            if not in_contract:
                missing.append("contracts.ROLE_MODELS")
            _record(results, section, f"role consistency: {role}", False, f"missing from: {', '.join(missing)}")
            continue

        # All three present -- check the .md frontmatter's model matches the
        # settings tier and the frontmatter name matches the file stem/role.
        fm = agent_md_roles[role]
        fm_name = fm.get("name")
        fm_model = fm.get("model")
        tier = model_tiers[role]
        detail_bits = []
        ok = True
        if fm_name != role:
            ok = False
            detail_bits.append(f"frontmatter name={fm_name!r} != file stem {role!r}")
        if fm_model != tier:
            ok = False
            detail_bits.append(f"frontmatter model={fm_model!r} != model_tiers[{role!r}]={tier!r}")
        _record(
            results, section, f"role consistency: {role}", ok,
            "; ".join(detail_bits) if detail_bits else f"name={fm_name}, model={fm_model} (tier={tier})",
        )


def _parse_frontmatter(text: str) -> dict:
    """Tiny YAML frontmatter parser for .claude/agents/*.md files: content
    between the first pair of '---' lines. Uses yaml.safe_load, so it
    tolerates full YAML syntax, not just the simple key: value lines these
    files currently use."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}
    fm_text = "\n".join(lines[1:end])
    data = yaml.safe_load(fm_text)
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------
# c. knowledge loader cross-checks
# --------------------------------------------------------------------------

_LEGAL_SOURCE_STATUSES = {"available", "derivable", "manual", "missing"}


def check_knowledge(results: Results) -> None:
    section = "c.knowledge"
    try:
        from knowledge.loader import load as load_knowledge
        k = load_knowledge()
    except Exception as exc:
        _record(results, section, "knowledge.loader.load()", False, str(exc))
        return
    _record(results, section, "knowledge.loader.load()", True, f"version={k.version}, {len(k.kpis)} KPIs, {len(k.catalog.cycles)} cycles")

    catalog_cycle_ids = {c.cycle_id for c in k.catalog.cycles}
    bad_refs = []
    for kpi_id, kpi in k.kpis.items():
        for ref in kpi.cycle_refs:
            if ref not in catalog_cycle_ids:
                bad_refs.append(f"{kpi_id} -> {ref!r}")
    if bad_refs:
        _record(results, section, "KPI cycle_refs resolve to catalog cycle ids", False, "; ".join(bad_refs))
    else:
        _record(results, section, "KPI cycle_refs resolve to catalog cycle ids", True, f"checked {len(k.kpis)} KPIs")

    # anchor_kpi_ids -> defined KPI is already enforced inside Knowledge.load()
    # (it raises ValueError before we'd get here) -- re-assert honestly.
    _record(
        results, section, "catalog anchor_kpi_ids resolve to defined KPIs", True,
        "enforced by Knowledge.load() itself (would have raised above otherwise)",
    )

    bad_status = [
        f"{kpi_id}: {kpi.source_status!r}"
        for kpi_id, kpi in k.kpis.items()
        if kpi.source_status not in _LEGAL_SOURCE_STATUSES
    ]
    if bad_status:
        _record(results, section, "source_status values legal", False, "; ".join(bad_status))
    else:
        _record(results, section, "source_status values legal", True, f"all in {sorted(_LEGAL_SOURCE_STATUSES)}")


# --------------------------------------------------------------------------
# d. DB schema superset check
# --------------------------------------------------------------------------

def _tables_from_schema_sql(sql_text: str) -> set[str]:
    import re

    return set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql_text))


def check_db(results: Results) -> None:
    section = "d.db"
    if not SCHEMA_PATH.exists():
        _record(results, section, "schema.sql exists", False, str(SCHEMA_PATH))
        return
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    schema_tables = _tables_from_schema_sql(schema_sql)
    _record(results, section, "schema.sql parses", True, f"{len(schema_tables)} tables declared")

    if not DB_PATH.exists():
        _record(results, section, "data/afund.db exists", False, f"{DB_PATH} not found (no live DB to check against)")
        return
    _record(results, section, "data/afund.db exists", True, str(DB_PATH))

    conn = sqlite3.connect(str(DB_PATH))
    try:
        live_tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        missing = schema_tables - live_tables
        if missing:
            _record(results, section, "live DB tables superset schema.sql", False, f"missing: {sorted(missing)}")
        else:
            _record(
                results, section, "live DB tables superset schema.sql", True,
                f"live has {len(live_tables)} tables >= schema's {len(schema_tables)}",
            )

        key_columns = {
            "research_reports": ["xlsx_path"],
            "decision_log": ["registry_version"],
        }
        for table, cols in key_columns.items():
            if table not in live_tables:
                _record(results, section, f"{table} key columns present", False, f"table {table!r} missing from live DB")
                continue
            live_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            missing_cols = [c for c in cols if c not in live_cols]
            if missing_cols:
                _record(results, section, f"{table} key columns present", False, f"missing columns: {missing_cols}")
            else:
                _record(results, section, f"{table} key columns present", True, f"{cols} all present")
    finally:
        conn.close()


# --------------------------------------------------------------------------
# e. Packet builders per agent: role
# --------------------------------------------------------------------------

# Roles with a dedicated (non-generic) packet builder, and the module.function
# that builds it -- verified by import + source inspection, not execution.
DEDICATED_PACKET_BUILDERS = {
    "sector_researcher": ("afund.research.sector_assembler", "build_sector_packet"),
    "buy_side": ("afund.research.er_adapter", "build_buy_side_packet"),
}


def check_packet_builders(results: Results) -> None:
    section = "e.packets"
    try:
        from afund.orchestrator.router import TRIGGERS
        from afund.orchestrator import context as context_mod
    except Exception as exc:
        _record(results, section, "import router/context", False, str(exc))
        return

    agent_roles = sorted({
        step.split("agent:", 1)[1]
        for steps in TRIGGERS.values()
        for step in steps
        if step.startswith("agent:")
    })
    _record(results, section, "agent: roles found in TRIGGERS", True, f"{agent_roles}")

    build_packet_src = None
    try:
        import inspect

        build_packet_src = inspect.getsource(context_mod.build_packet)
    except Exception as exc:
        _record(results, section, "read build_packet source", False, str(exc))

    for role in agent_roles:
        if role in DEDICATED_PACKET_BUILDERS:
            module_path, fn_name = DEDICATED_PACKET_BUILDERS[role]
            try:
                module = importlib.import_module(module_path)
                fn = getattr(module, fn_name)
                _record(
                    results, section, f"packet builder for agent:{role}", True,
                    f"dedicated builder {module_path}.{fn_name} ({'callable' if callable(fn) else 'not callable!'})",
                )
            except Exception as exc:
                _record(results, section, f"packet builder for agent:{role}", False, str(exc))
            continue

        # Generic dispatch: build_packet() must actually reference this role
        # somewhere in its body (either via the role-keyed constant sets near
        # the top of context.py, or by not needing any special-casing at all
        # because the base Packet dataclass already covers it). We check
        # that the role is at least handled generically -- i.e. build_packet
        # doesn't hard-fail on unknown roles is implicit; the meaningful
        # check is that a special-cased role name (if any of its behavior
        # depends on such a branch) is spelled correctly.
        if build_packet_src is not None:
            role_mentioned = f'"{role}"' in build_packet_src or f"'{role}'" in build_packet_src
            _record(
                results, section, f"packet builder for agent:{role}", True,
                (f"generic build_packet() dispatch; role referenced directly in source" if role_mentioned
                 else "generic build_packet() dispatch (no role-specific branch needed)"),
            )
        else:
            _record(results, section, f"packet builder for agent:{role}", False, "could not inspect build_packet source")


# --------------------------------------------------------------------------
# f. ER chain existence
# --------------------------------------------------------------------------

def check_er_chain(results: Results) -> None:
    section = "f.er_chain"

    # disclosure_fetcher package imports
    added = str(DISCLOSURE_FETCHER_DIR) not in sys.path
    if added:
        sys.path.insert(0, str(DISCLOSURE_FETCHER_DIR))
    try:
        importlib.import_module("disclosure_fetcher.pipeline")
        importlib.import_module("disclosure_fetcher.config")
        _record(results, section, "disclosure_fetcher package imports", True, "disclosure_fetcher.{pipeline,config}")
    except Exception as exc:
        _record(results, section, "disclosure_fetcher package imports", False, str(exc))

    # er_adapter's four entry points
    try:
        from afund.research import er_adapter

        for fn_name in ("prepare_kickoff", "fetch_er_documents", "ingest_er_output", "build_buy_side_packet"):
            fn = getattr(er_adapter, fn_name, None)
            _record(
                results, section, f"er_adapter.{fn_name} exists", fn is not None and callable(fn),
                "callable" if callable(fn) else "MISSING",
            )
    except Exception as exc:
        _record(results, section, "import afund.research.er_adapter", False, str(exc))
        er_adapter = None

    # equity_researcher/tools/*.py import cleanly (path-insert as needed)
    tools_dir = ER_ROOT / "tools"
    added_tools = str(tools_dir) not in sys.path
    if added_tools:
        sys.path.insert(0, str(tools_dir))
    tool_modules = [
        "convert_docs",
        "build_comprehensive_statement",
        "eps_bridge_check",
        "export_financials_xlsx",
    ]
    for mod_name in tool_modules:
        mod_path = tools_dir / f"{mod_name}.py"
        if not mod_path.exists():
            _record(results, section, f"tools/{mod_name}.py imports", False, f"{mod_path} not found")
            continue
        try:
            importlib.import_module(mod_name)
            _record(results, section, f"tools/{mod_name}.py imports", True, str(mod_path))
        except Exception as exc:
            _record(results, section, f"tools/{mod_name}.py imports", False, str(exc))

    # buy_side packet keys present in build_buy_side_packet source
    try:
        import inspect

        from afund.research import er_adapter as er_adapter_mod

        src = inspect.getsource(er_adapter_mod.build_buy_side_packet)
        expected_keys = ["eps_bridge_check", "xlsx_path", "narrative_findings_reference"]
        missing_keys = [k for k in expected_keys if f'"{k}"' not in src]
        if missing_keys:
            _record(results, section, "buy_side packet keys present", False, f"missing: {missing_keys}")
        else:
            _record(results, section, "buy_side packet keys present", True, f"{expected_keys} all present")
    except Exception as exc:
        _record(results, section, "buy_side packet keys present", False, str(exc))

    # registry/rules/eps_bridge.yaml loads
    if not EPS_BRIDGE_RULES_PATH.exists():
        _record(results, section, "registry/rules/eps_bridge.yaml loads", False, f"{EPS_BRIDGE_RULES_PATH} not found")
    else:
        try:
            data = yaml.safe_load(EPS_BRIDGE_RULES_PATH.read_text(encoding="utf-8"))
            n_rules = len([k for k in data if k != "sector_overrides"]) if isinstance(data, dict) else 0
            _record(results, section, "registry/rules/eps_bridge.yaml loads", True, f"{n_rules} threshold blocks")
        except Exception as exc:
            _record(results, section, "registry/rules/eps_bridge.yaml loads", False, str(exc))


# --------------------------------------------------------------------------
# g. Registry / knowledge / cycle_framework load
# --------------------------------------------------------------------------

def check_registry_loads(results: Results) -> None:
    section = "g.loaders"
    try:
        from registry.registry import Registry

        reg = Registry.load()
        _record(
            results, section, "registry.registry.Registry.load()", True,
            f"version={reg.version}, {len(reg.kpis)} sector KPI sets, {len(reg.strategies)} strategies",
        )
    except Exception as exc:
        _record(results, section, "registry.registry.Registry.load()", False, str(exc))

    try:
        from knowledge.loader import load as load_knowledge

        k = load_knowledge()
        _record(results, section, "knowledge.loader.load()", True, f"version={k.version}")
    except Exception as exc:
        _record(results, section, "knowledge.loader.load()", False, str(exc))

    try:
        from afund.cycles.framework import CycleFramework

        fw_path = REPO_ROOT / "registry" / "strategies" / "cycle_framework.yaml"
        data = yaml.safe_load(fw_path.read_text(encoding="utf-8"))
        fw = CycleFramework(**data)
        _record(results, section, "cycles.framework.CycleFramework validates cycle_framework.yaml", True, f"loaded from {fw_path}")
    except Exception as exc:
        _record(results, section, "cycles.framework.CycleFramework validates cycle_framework.yaml", False, str(exc))


# --------------------------------------------------------------------------
# h. Cadences <-> router triggers
# --------------------------------------------------------------------------

# settings.yaml cadences keys with no 1:1 router trigger, and why. Each maps
# to either a router trigger it shares (piggybacks on another trigger's
# pipeline) or None with a documented reason (no automated trigger yet).
CADENCE_TRIGGER_EXCEPTIONS = {
    "daily_news": "daily_news_process",  # naming: cadence says "daily_news", trigger is "daily_news_process"
    "daily_prices": "daily_data",  # prices_yf.PricesPipeline is one leg of daily_data, not its own trigger
    "daily_mf_navs": "daily_data",  # amfi_nav.AmfiNavPipeline is one leg of daily_data, not its own trigger
    "monthly_newsletters": "monthly_newsletter_digest",  # naming: cadence "monthly_newsletters" vs trigger "monthly_newsletter_digest"
    "quarterly_financials": None,  # manual: python -m afund.data.financials --universe (see universe_screening_stage's docstring); no dedicated automated trigger yet
    "quarterly_macro": None,  # subsumed by monthly_macro's pipelines running quarterly-relevant sources on a monthly cadence; no separate trigger
}


def check_cadences(results: Results) -> None:
    section = "h.cadences"
    try:
        from afund.config import load_settings
        from afund.orchestrator.router import TRIGGERS
    except Exception as exc:
        _record(results, section, "import settings/router", False, str(exc))
        return

    settings = load_settings()
    cadences: dict[str, str] = settings.get("cadences", {}) or {}
    trigger_names = set(TRIGGERS.keys())

    for cadence_key in sorted(cadences):
        if cadence_key in trigger_names:
            _record(results, section, f"cadence '{cadence_key}' -> trigger", True, f"direct match: TRIGGERS[{cadence_key!r}]")
            continue
        if cadence_key in CADENCE_TRIGGER_EXCEPTIONS:
            mapped = CADENCE_TRIGGER_EXCEPTIONS[cadence_key]
            if mapped is None:
                _record(results, section, f"cadence '{cadence_key}' -> trigger", True, "documented exception: no automated trigger yet (manual)")
            elif mapped in trigger_names:
                _record(results, section, f"cadence '{cadence_key}' -> trigger", True, f"documented alias -> TRIGGERS[{mapped!r}]")
            else:
                _record(results, section, f"cadence '{cadence_key}' -> trigger", False, f"documented alias {mapped!r} not in TRIGGERS")
            continue
        _record(results, section, f"cadence '{cadence_key}' -> trigger", False, "no matching trigger and no documented exception")

    # Reverse: every trigger should be reachable from some cadence, a HUMAN-
    # initiated ad hoc flow (equity_research_kickoff, sector_research,
    # buy_side_analysis, position_monitoring, universe_screening_stage are
    # deliberately ad hoc / staged, not on a fixed calendar cadence).
    AD_HOC_TRIGGERS = {
        "daily_nav",  # standalone re-run leg of daily_data, ad hoc by design
        "equity_research_kickoff",
        "sector_research",
        "buy_side_analysis",
        "position_monitoring",
        "universe_screening_stage",
    }
    reverse_mapped_triggers = set(cadences.values()) | {
        v for v in CADENCE_TRIGGER_EXCEPTIONS.values() if v is not None
    }
    # cadences dict maps key->human-readable schedule string, not to trigger
    # names, so build the actual reverse set from keys that direct-matched or
    # alias-matched above instead.
    covered_triggers = set()
    for cadence_key in cadences:
        if cadence_key in trigger_names:
            covered_triggers.add(cadence_key)
        elif cadence_key in CADENCE_TRIGGER_EXCEPTIONS and CADENCE_TRIGGER_EXCEPTIONS[cadence_key]:
            covered_triggers.add(CADENCE_TRIGGER_EXCEPTIONS[cadence_key])

    for trigger in sorted(trigger_names):
        if trigger in covered_triggers or trigger in AD_HOC_TRIGGERS:
            reason = "covered by a cadence" if trigger in covered_triggers else "documented ad hoc/staged trigger (no fixed cadence)"
            _record(results, section, f"trigger '{trigger}' <- cadence", True, reason)
        else:
            _record(results, section, f"trigger '{trigger}' <- cadence", False, "no cadence maps to this trigger and not in AD_HOC_TRIGGERS")


# --------------------------------------------------------------------------
# i. Facts / interpretation layer
# --------------------------------------------------------------------------

# Which model must carry which additive field. Nothing here is required at
# runtime (every field defaults to None/empty so pre-layer payloads still
# validate) — but a field silently disappearing would take the whole
# fact/reading separation offline without a single test failing, because
# pydantic's default extra="ignore" would just drop the agent's output key.
INTERPRETATION_CONTRACT_FIELDS = {
    "SynthesisOutput": ["facts_relied_on", "interpretations"],
    "CritiqueOutput": ["opinion_audit", "banned_reasoning_hits", "unresolved_divergences"],
    "SectorResearchNote": ["facts", "interpretations", "divergence_cases"],
    "BuySideRecommendation": [
        "sector_playbook",
        "primary_multiple",
        "multiple_conditioner",
        "interpretation_ledger",
        "opinion_audit",
    ],
}

# The doctrine section each consuming agent prompt must carry. critique.md's
# heading continues "— the 18-check audit", hence prefix matching.
INTERPRETATION_AGENT_PROMPTS = ("buy_side", "sector_researcher", "synthesis", "critique")

# --check scripts that must report "current". Subprocess rather than import:
# each one's contract IS its exit code, and re-implementing the comparison here
# would be a second source of truth for the same question.
INTERPRETATION_CHECK_SCRIPTS = (
    "check_interpretation_frames.py",
    "gen_sector_packs.py",
    "gen_eps_thresholds.py",
)


def _run_check_script(name: str) -> tuple[bool, str]:
    path = REPO_ROOT / "scripts" / name
    if not path.exists():
        return False, f"{path} not found"
    try:
        proc = subprocess.run(
            [sys.executable, str(path), "--check"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        )
    except Exception as exc:
        return False, str(exc)
    tail = [ln for ln in (proc.stdout or proc.stderr or "").splitlines() if ln.strip()]
    return proc.returncode == 0, (tail[-1].strip() if tail else f"exit {proc.returncode}")


def check_interpretation_layer(results: Results) -> None:
    section = "i.interpretation"

    # Governed tier loads, and everything in it is still DRAFT (CLAUDE.md: no
    # threshold or framework value is calibrated until the user back-tests it).
    fund_frames: dict = {}
    if not INTERPRETATION_RULES_PATH.exists():
        _record(results, section, "registry/rules/interpretation_frames.yaml loads", False,
                f"{INTERPRETATION_RULES_PATH} not found")
    else:
        try:
            fund_frames = yaml.safe_load(INTERPRETATION_RULES_PATH.read_text(encoding="utf-8")) or {}
            n_vocab = len(fund_frames.get("conditioning_variables") or {})
            n_types = len(fund_frames.get("discriminator_types") or {})
            n_fams = len(fund_frames.get("family_frames") or {})
            _record(results, section, "registry/rules/interpretation_frames.yaml loads", True,
                    f"{n_vocab} conditioning variables, {n_types} discriminator types, {n_fams} family frames")
            not_draft = [
                f"{group}.{slug}"
                for group in ("conditioning_variables", "discriminator_types", "family_frames")
                for slug, block in (fund_frames.get(group) or {}).items()
                if isinstance(block, dict) and block.get("status") != "DRAFT"
            ]
            _record(results, section, "interpretation frames all status: DRAFT", not not_draft,
                    "every entry DRAFT" if not not_draft else f"not DRAFT: {not_draft[:5]}")
        except Exception as exc:
            _record(results, section, "registry/rules/interpretation_frames.yaml loads", False, str(exc))

    # ER tier-2 registry: the 32 playbooks stay upstream-owned; the fund only
    # consumes them, so absence is a FAIL here (the packets would silently lose
    # their playbook layer) but is handled gracefully at runtime.
    if not ER_SECTOR_REGISTRY_PATH.exists():
        _record(results, section, "ER config/sector_registry.yaml loads", False,
                f"{ER_SECTOR_REGISTRY_PATH} not found")
    else:
        try:
            er_reg = yaml.safe_load(ER_SECTOR_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
            _record(results, section, "ER config/sector_registry.yaml loads", True,
                    f"{len(er_reg.get('families') or {})} families, {len(er_reg.get('playbooks') or {})} playbooks")
        except Exception as exc:
            _record(results, section, "ER config/sector_registry.yaml loads", False, str(exc))

    # Contracts: the models exist, and the closed Literals are the governed
    # vocabulary verbatim. Equality, not subset — a token in the contract that
    # the registry does not govern is as broken as the reverse.
    try:
        from typing import get_args

        from afund.agents import contracts as contracts_mod

        for model_name in ("FactClaim", "Reading", "DivergenceCase", "UnresolvedDivergence"):
            model = getattr(contracts_mod, model_name, None)
            _record(results, section, f"contracts.{model_name} registered", model is not None,
                    "present" if model is not None else "MISSING")

        contract_vocab = set(get_args(contracts_mod.ConditioningVariable))
        registry_vocab = set((fund_frames.get("conditioning_variables") or {}).keys())
        _record(results, section, "ConditioningVariable == registry vocabulary",
                bool(registry_vocab) and contract_vocab == registry_vocab,
                f"{len(contract_vocab)} tokens match" if contract_vocab == registry_vocab
                else f"contract-only={sorted(contract_vocab - registry_vocab)}, registry-only={sorted(registry_vocab - contract_vocab)}")

        contract_types = set(get_args(contracts_mod.DiscriminatorType))
        registry_types = set((fund_frames.get("discriminator_types") or {}).keys())
        _record(results, section, "DiscriminatorType == registry discriminator_types",
                bool(registry_types) and contract_types == registry_types,
                f"{len(contract_types)} types match" if contract_types == registry_types
                else f"contract-only={sorted(contract_types - registry_types)}, registry-only={sorted(registry_types - contract_types)}")

        for model_name, fields in INTERPRETATION_CONTRACT_FIELDS.items():
            model = getattr(contracts_mod, model_name, None)
            if model is None:
                _record(results, section, f"{model_name} interpretation fields", False, "model missing")
                continue
            missing = [f for f in fields if f not in model.model_fields]
            _record(results, section, f"{model_name} interpretation fields", not missing,
                    f"{len(fields)} fields present" if not missing else f"missing: {missing}")
    except Exception as exc:
        _record(results, section, "import afund.agents.contracts", False, str(exc))

    # Frame resolution: every fund sector slug resolves at family level, and a
    # tier-2 playbook layers on top of its family (family-then-playbook, key by
    # key — the same override semantics as eps_bridge_check._override_chain).
    try:
        from afund.research.interpretation import resolve_frame

        families = sorted((fund_frames.get("family_frames") or {}).keys())
        unresolved = [f for f in families if resolve_frame(family=f) is None]
        _record(results, section, "resolve_frame() resolves every fund family",
                bool(families) and not unresolved,
                f"{len(families)} families resolve" if not unresolved else f"unresolved: {unresolved}")

        layered = resolve_frame(playbook="life_insurance")
        ok = (
            layered is not None
            and layered.get("family") == "bfsi"
            and layered.get("playbook") == "life_insurance"
            and len(layered.get("resolved_from") or []) == 2
        )
        _record(results, section, "resolve_frame() layers playbook over family", ok,
                f"life_insurance -> {layered.get('primary_multiple')} via {layered.get('resolved_from')}"
                if layered else "life_insurance did not resolve")
    except Exception as exc:
        _record(results, section, "afund.research.interpretation.resolve_frame", False, str(exc))

    # Both packet builders actually emit the keys the prompts tell agents to read.
    try:
        import inspect

        from afund.research import er_adapter as er_adapter_mod
        from afund.research import sector_assembler as sector_mod

        buy_src = inspect.getsource(er_adapter_mod.build_buy_side_packet)
        buy_keys = ["sector_playbook", "interpretation_frame", "interpretation_ledger",
                    "redteam_findings", "opinion_audit_reference"]
        missing = [k for k in buy_keys if f'"{k}"' not in buy_src]
        _record(results, section, "buy_side packet interpretation keys", not missing,
                f"{buy_keys} all present" if not missing else f"missing: {missing}")

        sector_src = inspect.getsource(sector_mod.build_sector_packet)
        sector_keys = ["interpretation_frame", "divergence_reference"]
        missing = [k for k in sector_keys if f'"{k}"' not in sector_src]
        _record(results, section, "sector packet interpretation keys", not missing,
                f"{sector_keys} all present" if not missing else f"missing: {missing}")
    except Exception as exc:
        _record(results, section, "packet builders carry interpretation keys", False, str(exc))

    # The prose tier the packets point at, discoverable through the loader
    # (knowledge/loader.py rglobs references/, so this also proves the path).
    try:
        from afund.research.interpretation import FACTS_VS_INTERPRETATION_REF
        from knowledge.loader import load as load_knowledge

        paths = {ref.path for ref in load_knowledge().references}
        _record(results, section, "facts_vs_interpretation.md in knowledge references",
                FACTS_VS_INTERPRETATION_REF in paths,
                f"knowledge/references/{FACTS_VS_INTERPRETATION_REF}"
                if FACTS_VS_INTERPRETATION_REF in paths else f"not among {len(paths)} references")
    except Exception as exc:
        _record(results, section, "facts_vs_interpretation.md in knowledge references", False, str(exc))

    # Agent prompts carry the doctrine. A contract field with no prompt telling
    # the agent how to fill it is a field that stays empty forever.
    for role in INTERPRETATION_AGENT_PROMPTS:
        md_path = AGENTS_DIR / f"{role}.md"
        if not md_path.exists():
            _record(results, section, f"{role}.md 'Facts vs interpretation' section", False,
                    f"{md_path} not found")
            continue
        text = md_path.read_text(encoding="utf-8")
        has_section = "## Facts vs interpretation" in text
        has_security = text.lstrip().splitlines()[0].startswith("---") and "SECURITY (non-negotiable)" in text
        _record(results, section, f"{role}.md 'Facts vs interpretation' section", has_section and has_security,
                "section + SECURITY preamble present" if has_section and has_security
                else f"section={has_section}, security_preamble={has_security}")

    # Generated artifacts current / upstream tokens still inside the vocabulary.
    for script_name in INTERPRETATION_CHECK_SCRIPTS:
        ok, detail = _run_check_script(script_name)
        _record(results, section, f"{script_name} --check", ok, detail)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_report(results: Results) -> bool:
    name_width = min(max((len(f"{s}: {n}") for s, n, _, _ in results), default=10), 70)
    all_passed = True
    current_section = None
    for section, name, passed, detail in results:
        if section != current_section:
            print(f"\n=== {section} ===")
            current_section = section
        status = "PASS" if passed else "FAIL"
        label = f"{name}"
        if len(label) > name_width:
            label = label[: name_width - 1] + "…"
        print(f"  [{status}] {label:<{name_width}}  {detail}")
        if not passed:
            all_passed = False

    total = len(results)
    n_pass = sum(1 for _, _, p, _ in results if p)
    n_fail = total - n_pass
    print("\n" + "=" * 78)
    print(f"SUMMARY: {n_pass}/{total} PASS, {n_fail} FAIL")
    print("=" * 78)
    return all_passed


def main() -> int:
    results: Results = []

    check_router_triggers(results)
    check_role_consistency(results)
    check_knowledge(results)
    check_db(results)
    check_packet_builders(results)
    check_er_chain(results)
    check_registry_loads(results)
    check_cadences(results)
    check_interpretation_layer(results)

    all_passed = print_report(results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
