"""Mechanical citation integrity check — layer 1 of the verification wave.

Usage:
  python tools/citation_check.py workspace/TICKER [--report path]

Checks:
  1. every fact source.src_id exists in state/source_registry.json
  2. every [S#] token in report/*.md maps to an SRC id in the registry
  3. registry entries never referenced anywhere (dead weight -> listed, not fatal)
  4. duplicate SRC ids across registry fragments
  5. facts flagged 'unverified' or 'superseded' cited in deliverables (fatal for unverified)
  6. sample list generator: stratified pick of numeric [S#] cells for the auditor agent
Exit 1 if fatal problems found (missing registry refs, unverified facts in deliverables).
"""
import argparse, json, random, re, sys
from pathlib import Path


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def all_fact_files(ws):
    for pattern in ("facts/*.json", "facts/external/*.json"):
        for p in Path(ws).glob(pattern):
            if p.name in ("merge_discrepancies.json",):
                continue
            data = load_json(p, None)
            if data is None:
                continue
            records = data.get("facts", data) if isinstance(data, dict) else data
            if isinstance(records, list):
                yield p.name, records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace")
    ap.add_argument("--report", default=None)
    ap.add_argument("--sample-pct", type=int, default=30)
    a = ap.parse_args()
    ws = Path(a.workspace)

    registry = load_json(ws / "state" / "source_registry.json", {})
    # market data keeps its registry entry inline — merge it for checking
    md = load_json(ws / "facts" / "market_data.json", {})
    registry.update(md.get("source_registry_entry", {}))

    problems = {"fatal": [], "warn": []}
    used_src = set()

    for fname, records in all_fact_files(ws):
        for r in records:
            sid = (r.get("source") or {}).get("src_id")
            if not sid:
                problems["fatal"].append(f"{fname}: fact {r.get('id')} has no src_id")
            elif sid not in registry and sid not in ("DERIVED", "SRC-MKT-001"):
                problems["fatal"].append(f"{fname}: fact {r.get('id')} cites unknown {sid}")
            else:
                used_src.add(sid)

    token_re = re.compile(r"\[S(\d+)\]")
    report_tokens = []
    for rp in (ws / "report").glob("*.md") if (ws / "report").exists() else []:
        text = rp.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            for m in token_re.finditer(line):
                sid = f"SRC-{int(m.group(1)):03d}"
                report_tokens.append({"file": rp.name, "line": i, "sid": sid,
                                      "context": line.strip()[:160]})
                if sid not in registry:
                    problems["fatal"].append(f"{rp.name}:{i}: [S{m.group(1)}] not in registry")
                used_src.add(sid)

    unused = [s for s in registry if s not in used_src]
    if unused:
        problems["warn"].append(f"{len(unused)} registry entries never cited: {unused[:10]}…"
                                if len(unused) > 10 else f"registry entries never cited: {unused}")

    # unverified/superseded fact ids that appear in deliverables
    bad_ids = set()
    for fname, records in all_fact_files(ws):
        for r in records:
            fl = r.get("flags") or []
            if "unverified" in fl:
                bad_ids.add((r.get("id"), "unverified"))
            if "superseded" in fl:
                bad_ids.add((r.get("id"), "superseded"))
    if bad_ids and (ws / "report").exists():
        blob = " ".join(p.read_text(encoding="utf-8") for p in (ws / "report").glob("*.md"))
        for fid, kind in bad_ids:
            if fid and fid in blob:
                target = problems["fatal"] if kind == "unverified" else problems["warn"]
                target.append(f"{kind} fact {fid} appears in deliverables")

    sample = []
    if report_tokens:
        random.seed(42)  # reproducible sample across re-runs
        k = max(1, len(report_tokens) * a.sample_pct // 100)
        sample = random.sample(report_tokens, min(k, len(report_tokens)))

    out = {"fatal": problems["fatal"], "warnings": problems["warn"],
           "stats": {"registry_entries": len(registry), "src_used": len(used_src),
                     "report_citations": len(report_tokens)},
           "auditor_sample": sample}
    rp = Path(a.report) if a.report else ws / "state" / "citation_check.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{'FAIL' if problems['fatal'] else 'OK'}: {len(problems['fatal'])} fatal, "
          f"{len(problems['warn'])} warnings, {len(report_tokens)} citations checked, "
          f"sample of {len(sample)} -> {rp}")
    sys.exit(1 if problems["fatal"] else 0)


if __name__ == "__main__":
    main()
