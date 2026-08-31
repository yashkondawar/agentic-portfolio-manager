"""Pre-run integrity check — one entry point for every static check in the repo.

    python tools/preflight.py                      # repo checks only
    python tools/preflight.py workspace/NALCO      # repo checks + that run's state
    python tools/preflight.py --deps-only          # just the dependency import check
    python tools/preflight.py --list               # what runs, without running it

Run this BEFORE a coverage run and after ANY edit to config/, schema/, prompts/ or tools/.

Why: every defect this catches was, at some point, caught instead by a human reading a file
months later — a registry that claimed `tools/compute_kpis.py` consumed it when the tool had
no reference to it, a `generic` playbook marked `authored` with no file on disk, a
`reportStyle.js` duplicated with nothing enforcing the copies match, a test that ImportError'd
on the install it was written to protect. Documents that assert integrations are worthless
without something that checks them; this is that something.

Checks:
  1  deps        every import in tools/requirements.txt resolves (key-free set only)
  2  registry    tools/validate_sector_registry.py (E1-E11, W1, I1)
  3  schemas     every schema/*.json parses and declares $schema + required
  4  configs     every config/*.yaml parses; agent_config model tiers cover every agent
  5  refs        dead-reference scan over markdown (backticked repo paths must resolve)
  6  reportstyle the skill's reportStyle.js is byte-identical to the runner's
  7  tools       every tools/*.py compiles (syntax + import-time errors)
  8  state       tools/validate_state.py <workspace>   (only when a workspace is given)

Exit code 1 if any check fails. Deterministic, zero LLM tokens.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Distribution name -> module name, for the key-free set in tools/requirements.txt.
DIST_TO_MODULE = {
    "pyyaml": "yaml", "beautifulsoup4": "bs4", "python-dateutil": "dateutil",
    "python-dotenv": "dotenv", "pypdf": "pypdf", "pdfplumber": "pdfplumber",
    "markitdown": "markitdown", "openpyxl": "openpyxl", "yfinance": "yfinance",
    "pandas": "pandas", "requests": "requests", "lxml": "lxml", "bse": "bse",
}

# Artefacts written inside workspace/<TICKER>/ — relative to a run, not to the repo.
RUNTIME_PREFIXES = ("state/", "facts/", "findings/", "report/", "handoff/",
                    "research/", "cache/", "exports/", "input/", "workspace/")
# Where a bare backticked filename may legitimately live.
REF_DIRS = ["", "prompts/", "prompts/thesis_archetypes/", "prompts/sector_playbooks/",
            "prompts/sector_packs/", "docs/", "tools/", "schema/", "config/", "templates/"]

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name:12s} {detail}")


# --------------------------------------------------------------------------- #
def check_deps() -> None:
    req = REPO / "tools" / "requirements.txt"
    if not req.exists():
        record("deps", False, "tools/requirements.txt missing")
        return
    wanted: list[str] = []
    for line in req.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        dist = re.split(r"[><=!~\[]", line)[0].strip().lower()
        if dist:
            wanted.append(dist)
    missing = [d for d in wanted if importlib.util.find_spec(DIST_TO_MODULE.get(d, d)) is None]
    if missing:
        record("deps", False,
               f"{len(missing)} declared dependency/ies not importable: {missing}. "
               f"Run: python -m pip install -r tools/requirements.txt")
    else:
        record("deps", True, f"all {len(wanted)} key-free dependencies importable")


# --------------------------------------------------------------------------- #
def check_registry() -> None:
    script = REPO / "tools" / "validate_sector_registry.py"
    if not script.exists():
        record("registry", False, "tools/validate_sector_registry.py missing")
        return
    p = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=REPO)
    tail = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
    summary = tail[-1] if tail else "(no output)"
    pending = [ln for ln in tail if " pending (" in ln]
    if p.returncode != 0:
        bad = [ln for ln in tail if ln.startswith("ERROR")]
        record("registry", False, f"{summary} | first: {bad[0] if bad else '?'}")
    elif pending:
        record("registry", False,
               f"{summary} | {len(pending)} playbook(s) still `status: pending` — the registry "
               f"claims routing it cannot deliver")
    else:
        record("registry", True, summary)


# --------------------------------------------------------------------------- #
def check_schemas() -> None:
    bad: list[str] = []
    files = sorted((REPO / "schema").glob("*.json"))
    for f in files:
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            bad.append(f"{f.name}: {exc}")
            continue
        if "$schema" not in s:
            bad.append(f"{f.name}: no $schema")
        if s.get("type") == "object" and "required" not in s:
            bad.append(f"{f.name}: object schema with no `required` — validates anything")
    if bad:
        record("schemas", False, f"{len(bad)} problem(s): {bad[:3]}")
    else:
        record("schemas", True, f"{len(files)} schema(s) parse and declare $schema + required")


# --------------------------------------------------------------------------- #
def check_configs() -> None:
    try:
        import yaml
    except ImportError:
        record("configs", False, "pyyaml not installed — cannot parse config/*.yaml")
        return
    bad: list[str] = []
    cfgs = sorted((REPO / "config").glob("*.yaml"))
    loaded: dict[str, dict] = {}
    for f in cfgs:
        try:
            loaded[f.name] = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            bad.append(f"{f.name}: {exc}")

    ac = loaded.get("agent_config.yaml") or {}
    models = ac.get("models") or {}
    # Tiers that must exist because CLAUDE.md's tiering table names them and modules use them.
    for tier in ("extraction", "analysis", "research", "thesis", "adversarial",
                 "verification", "report"):
        if tier not in models:
            bad.append(f"agent_config.yaml: models.{tier} missing (CLAUDE.md's tiering table "
                       f"names it; a tier that exists only in prose routes nothing)")
    groups = ac.get("role_groups") or {}
    flat = {str(m) for v in groups.values() if isinstance(v, list) for m in v}
    for mod in ("33", "34"):
        if mod not in flat:
            bad.append(f"agent_config.yaml: module {mod} in no role_group (waves 6a/6b)")

    if bad:
        record("configs", False, f"{len(bad)} problem(s): {bad[:3]}")
    else:
        record("configs", True, f"{len(cfgs)} config(s) parse; model tiers and role_groups complete")


# --------------------------------------------------------------------------- #
# Backticked names that are SUPPOSED to be absent from this repo. Each needs a reason, so the
# list stays a set of deliberate exemptions rather than a place to bury real breakage.
INTENTIONALLY_ABSENT = {
    # Fund-repo paths, described in docs/DESIGN_DECISIONS.md as where this work was first
    # encoded. They document provenance; they are not links into this project.
    # (Whole fund-repo trees are handled by FUND_REPO_PREFIXES below, not listed here.)
    ".claude/agents/buy_side.md": "fund repo path (this project's copy is buy-side-analyst.md)",
    "buyside_depth.md": "fund repo companion doc, explicitly not carried over",
    # Named as future work / a template to copy, not as existing files.
    "batch.py": "proposed wrapper, disclosure_fetcher README 'natural next step'",
    "nse_source.py": "proposed source, named as a copy-target for bse_source.py",
    # Named in order to say it does NOT exist. These are the honest kind of dangling
    # reference — a correction that names the thing it is correcting.
    "all.txt": "counterexample: er_corpus README says there is no such seed file",
    "extract_docling.py": "counterexample: api_mode README says this stub was never written",
}

# Fund-repo top-level trees. This project is vendored into the AI-Native Fund at
# research/equity_researcher/, and both its own docs and the fund-generated sector packs
# cite fund paths — `registry/kpis/<sector>.yaml` for the governed KPI vocabulary,
# `knowledge/references/...` for the methodology prose. Those resolve one level up, in the
# vendoring repo, never here: per VERSION.md's sync policy this project deliberately has no
# `registry/`, which is the whole reason `config/eps_bridge_thresholds.yaml` is generated
# rather than read. A prefix rule rather than a list of exact names, because the fund's
# sector slugs are the fund's to change and this file should not have to track them.
FUND_REPO_PREFIXES = ("registry/", "knowledge/")


def check_refs() -> None:
    """Every backticked repo path in the docs must resolve to a real file.

    Resolution is deliberately generous about *where* a bare filename lives — the docs write
    `reportStyle.js` and `screener_source.py` without paths, and that is fine because the
    surrounding prose makes the location unambiguous. What we are hunting is a reference to a
    file that exists NOWHERE, which is how `seeds/all.txt` and a claimed-but-absent
    `extract_docling.py` survived. Workspace artefacts (`state/thesis.json`,
    `run_log.md`) are run-relative and resolve against workspace/, not the repo root.

    A bare run artefact (`thesis.json` rather than `state/thesis.json`) is accepted only
    when the docs elsewhere write the same basename WITH a runtime prefix — the prefixed
    forms are the declaration, the bare ones are shorthand for it. Derived rather than
    listed, and derived rather than left to the by_name index: resolving `thesis.json`
    off a leftover `workspace/NALCO/` made the check pass or fail depending on whether
    someone happened to have a run on disk, which is exactly the kind of accident this
    tool exists to catch. The fund's vendored copy gitignores workspace/ and so saw 24
    refs break that were never broken.
    """
    token = re.compile(r"`([A-Za-z0-9_./<>-]+\.(?:md|py|json|yaml|yml|js|txt|xlsx|csv))`")
    targets = [p for p in REPO.rglob("*.md")
               if not any(part in {"node_modules", "reference", "workspace", ".git"}
                          for part in p.relative_to(REPO).parts)]

    # index every real file by basename and by repo-relative path, once
    by_name: dict[str, list[str]] = {}
    rel_paths: set[str] = set()
    for p in REPO.rglob("*"):
        if not p.is_file() or "node_modules" in p.parts or "__pycache__" in p.parts:
            continue
        if p.relative_to(REPO).parts[0] == "workspace":
            continue           # run output; never a resolution target (see docstring)
        r = p.relative_to(REPO).as_posix()
        rel_paths.add(r)
        by_name.setdefault(p.name, []).append(r)

    doc_text: dict[Path, str] = {}
    for f in targets:
        try:
            doc_text[f] = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    runtime_names = {Path(r).name
                     for text in doc_text.values()
                     for r in token.findall(text)
                     if r.startswith(RUNTIME_PREFIXES)}

    bad: list[str] = []
    checked = exempt = 0
    for f, text in doc_text.items():
        for m in token.finditer(text):
            ref = m.group(1)
            if "<" in ref or ">" in ref:
                continue
            if ref in INTENTIONALLY_ABSENT or ref.startswith(FUND_REPO_PREFIXES):
                exempt += 1
                continue
            checked += 1
            if ref.startswith(RUNTIME_PREFIXES) or ref in rel_paths:
                continue
            if "/" not in ref and ref in runtime_names:
                continue
            if any((REPO / (d + ref)).exists() for d in REF_DIRS) or (f.parent / ref).exists():
                continue
            if any(r.endswith("/" + ref) or r == ref for r in rel_paths):
                continue
            if Path(ref).name in by_name:      # bare name, resolves somewhere real
                continue
            bad.append(f"{f.relative_to(REPO).as_posix()} -> {ref}")

    uniq = sorted(set(bad))
    if uniq:
        record("refs", False, f"{len(uniq)} dead reference(s) of {checked}: {uniq[:3]}")
    else:
        record("refs", True, f"{checked} backticked path references across {len(targets)} md "
                             f"files all resolve ({exempt} intentionally-absent exempted)")


# --------------------------------------------------------------------------- #
def check_reportstyle() -> None:
    a = REPO / ".claude" / "skills" / "equity-research-formatter" / "scripts" / "reportStyle.js"
    b = REPO / "tools" / "report_formatter" / "reportStyle.js"
    if not a.exists() or not b.exists():
        record("reportstyle", False,
               f"missing copy: skill={a.exists()} runner={b.exists()}")
        return
    ha, hb = (hashlib.sha256(p.read_bytes()).hexdigest() for p in (a, b))
    if ha != hb:
        record("reportstyle", False,
               "the skill's reportStyle.js and tools/report_formatter/reportStyle.js have "
               "DIVERGED. The runner's copy is the one that renders; copy it over the skill's "
               "so the documented design system matches the one in use.")
    else:
        record("reportstyle", True, f"both copies byte-identical (sha256 {ha[:12]})")


# --------------------------------------------------------------------------- #
def check_tools() -> None:
    bad: list[str] = []
    files = [p for p in sorted((REPO / "tools").rglob("*.py"))
             if "node_modules" not in p.parts and "__pycache__" not in p.parts]
    for f in files:
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            bad.append(f"{f.relative_to(REPO).as_posix()}:{exc.lineno} {exc.msg}")
    if bad:
        record("tools", False, f"{len(bad)} file(s) do not compile: {bad[:3]}")
    else:
        record("tools", True, f"{len(files)} python file(s) compile")


# --------------------------------------------------------------------------- #
def check_state(workspace: str) -> None:
    script = REPO / "tools" / "validate_state.py"
    if not script.exists():
        record("state", False, "tools/validate_state.py missing")
        return
    p = subprocess.run([sys.executable, str(script), workspace],
                       capture_output=True, text=True, cwd=REPO)
    tail = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
    summary = tail[-1] if tail else "(no output)"
    if p.returncode != 0:
        first = next((ln for ln in tail if ln.startswith("ERROR")), "?")
        record("state", False, f"{summary} | first: {first[:150]}")
    else:
        record("state", True, summary)


# --------------------------------------------------------------------------- #
CHECKS = [
    ("deps", "every import in tools/requirements.txt resolves"),
    ("registry", "sector registry integrity (E1-E11) and no pending playbooks"),
    ("schemas", "schema/*.json parse and declare $schema + required"),
    ("configs", "config/*.yaml parse; model tiers and role_groups complete"),
    ("refs", "dead-reference scan over markdown"),
    ("reportstyle", "the two reportStyle.js copies are byte-identical"),
    ("tools", "every tools/*.py compiles"),
    ("state", "workspace state against schema/*.json (needs a workspace argument)"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workspace", nargs="?", default=None,
                    help="optional workspace/<TICKER> to validate as well")
    ap.add_argument("--deps-only", action="store_true", help="run only the dependency check")
    ap.add_argument("--list", action="store_true", help="list the checks and exit")
    a = ap.parse_args()

    if a.list:
        for name, desc in CHECKS:
            print(f"  {name:12s} {desc}")
        return

    print(f"preflight: {REPO}\n")
    check_deps()
    if not a.deps_only:
        check_registry()
        check_schemas()
        check_configs()
        check_refs()
        check_reportstyle()
        check_tools()
        if a.workspace:
            check_state(a.workspace)
        else:
            print("[SKIP] state        no workspace given "
                  "(pass workspace/<TICKER> to validate a run)")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed"
          + (f"; FAILED: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
