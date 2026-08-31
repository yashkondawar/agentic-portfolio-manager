"""Merge per-document fact fragments into the canonical facts store, with precedence rules.

Usage:
  python tools/merge_facts.py workspace/TICKER/facts/fragments/ --out workspace/TICKER/facts/financials.json
      [--registry workspace/TICKER/state/source_registry.json]

Rules (prompts/00_citation_standard.md #2):
  - dedupe key: (metric, period, basis, level, parent)
  - annual report beats quarterly filing for the same FY period
  - later-dated document beats earlier for the same key (restatement); loser kept with flag
  - exact-duplicate values collapse silently; conflicting values produce a discrepancy entry
Outputs the merged store plus a discrepancy report the orchestrator turns into red-flag
candidates (category data_quality).
"""
import argparse, json, sys
from pathlib import Path

KIND_RANK = {"annual_report": 3, "quarterly_result": 2, "presentation": 1,
             "transcript": 1, "other": 0}


def load_fragments(folder):
    frags = []
    for p in sorted(Path(folder).glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN unreadable fragment {p.name}: {e}", file=sys.stderr)
            continue
        records = data["facts"] if isinstance(data, dict) and "facts" in data else data
        if not isinstance(records, list):
            print(f"WARN {p.name}: not a fact array, skipped", file=sys.stderr)
            continue
        for r in records:
            r.setdefault("_fragment", p.name)
            frags.append(r)
    return frags


def key(r):
    return (r.get("metric"), r.get("period"), r.get("basis"), r.get("level", 1),
            r.get("parent"))


def doc_meta(rec, registry):
    src = (rec.get("source") or {}).get("src_id")
    entry = registry.get(src, {}) if registry else {}
    return entry.get("kind", "other"), entry.get("doc", "")


def better(a, b, registry):
    """True if record a should win over record b."""
    ka, da = doc_meta(a, registry)
    kb, db = doc_meta(b, registry)
    if KIND_RANK.get(ka, 0) != KIND_RANK.get(kb, 0):
        return KIND_RANK.get(ka, 0) > KIND_RANK.get(kb, 0)
    return da >= db  # doc names embed period (AR_FY2025 > AR_FY2024); lexical works for our convention


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fragments_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--registry", default=None)
    a = ap.parse_args()

    registry = {}
    if a.registry and Path(a.registry).exists():
        registry = json.loads(Path(a.registry).read_text(encoding="utf-8"))

    frags = load_fragments(a.fragments_dir)
    merged, superseded, discrepancies = {}, [], []

    for rec in frags:
        k = key(rec)
        if k not in merged:
            merged[k] = rec
            continue
        cur = merged[k]
        same_value = str(cur.get("value")) == str(rec.get("value"))
        if same_value:
            continue  # exact duplicate from another doc — keep first, values agree
        winner, loser = (rec, cur) if better(rec, cur, registry) else (cur, rec)
        loser = dict(loser)
        loser.setdefault("flags", []).append("superseded")
        superseded.append(loser)
        discrepancies.append({
            "metric": k[0], "period": k[1], "basis": k[2],
            "kept": {"value": winner.get("value"), "src": (winner.get("source") or {}).get("src_id"),
                     "fragment": winner.get("_fragment")},
            "superseded": {"value": loser.get("value"), "src": (loser.get("source") or {}).get("src_id"),
                           "fragment": loser.get("_fragment")}})
        merged[k] = winner

    out_records = list(merged.values()) + superseded
    for r in out_records:
        r.pop("_fragment", None)

    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({"facts": out_records}, indent=2), encoding="utf-8")

    disc_path = outp.parent / "merge_discrepancies.json"
    disc_path.write_text(json.dumps(discrepancies, indent=2), encoding="utf-8")

    print(f"OK: {len(frags)} records in -> {len(merged)} canonical + {len(superseded)} superseded; "
          f"{len(discrepancies)} value conflicts -> {disc_path.name}")
    if discrepancies:
        print("NOTE: conflicts need red-flag candidates (category=data_quality); "
              "orchestrator should append them to state/red_flags.json")


if __name__ == "__main__":
    main()
