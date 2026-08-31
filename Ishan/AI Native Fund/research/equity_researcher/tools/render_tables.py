"""Deterministic markdown table renderer — tables come from the facts store, not from prose.

Usage:
  python tools/render_tables.py workspace/TICKER --table income_summary --basis consolidated
  python tools/render_tables.py workspace/TICKER --spec path/to/custom_spec.json

Built-in table specs: income_summary, balance_summary, cashflow_summary, ratio_summary.
A spec is: {"title": str, "rows": [{"metric": str, "label": str, "unit": str}], "periods": "auto"}
Renders: metric rows x FY columns, each cell `value [S#]`, followed by the sectional legend
generated from the registry. Reported facts (method=reported) win over computed for the same
metric/period per the citation standard.
"""
import argparse, json
from pathlib import Path

SPECS = {
    "income_summary": {
        "title": "Income statement summary",
        "rows": [
            {"metric": "revenue_from_operations", "label": "Revenue from operations"},
            {"metric": "revenue_from_operations_yoy", "label": "Revenue growth YoY %"},
            {"metric": "ebitda", "label": "EBITDA"},
            {"metric": "ebitda_margin", "label": "EBITDA margin %"},
            {"metric": "depreciation_amortization", "label": "Depreciation & amortization"},
            {"metric": "finance_costs", "label": "Finance costs"},
            {"metric": "other_income", "label": "Other income"},
            {"metric": "pbt", "label": "PBT"},
            {"metric": "tax", "label": "Tax"},
            {"metric": "pat", "label": "PAT"},
            {"metric": "net_margin", "label": "PAT margin %"},
            {"metric": "eps_diluted", "label": "EPS (diluted)"}]},
    "balance_summary": {
        "title": "Balance sheet summary",
        "rows": [
            {"metric": "total_assets", "label": "Total assets"},
            {"metric": "total_equity", "label": "Total equity"},
            {"metric": "borrowings_noncurrent", "label": "Borrowings (non-current)"},
            {"metric": "borrowings_current", "label": "Borrowings (current)"},
            {"metric": "net_debt", "label": "Net debt"},
            {"metric": "inventories", "label": "Inventories"},
            {"metric": "trade_receivables", "label": "Trade receivables"},
            {"metric": "trade_payables", "label": "Trade payables"},
            {"metric": "cash_and_bank", "label": "Cash & bank"}]},
    "cashflow_summary": {
        "title": "Cash flow & FCF",
        "rows": [
            {"metric": "cfo", "label": "Cash flow from operations"},
            {"metric": "net_capex", "label": "Net capex"},
            {"metric": "fcf", "label": "Free cash flow"},
            {"metric": "cfo_to_ebitda", "label": "CFO/EBITDA %"}]},
    "ratio_summary": {
        "title": "Key ratios",
        "rows": [
            {"metric": "gross_margin", "label": "Gross margin %"},
            {"metric": "ebitda_margin", "label": "EBITDA margin %"},
            {"metric": "net_margin", "label": "PAT margin %"},
            {"metric": "roe", "label": "ROE %"},
            {"metric": "roce", "label": "ROCE %"},
            {"metric": "asset_turnover", "label": "Asset turnover (x)"},
            {"metric": "dso_days", "label": "Receivable days"},
            {"metric": "inventory_days", "label": "Inventory days"},
            {"metric": "payable_days", "label": "Payable days"},
            {"metric": "ccc_days", "label": "Cash conversion cycle (days)"},
            {"metric": "debt_equity", "label": "Debt/Equity (x)"},
            {"metric": "interest_coverage", "label": "Interest coverage (x)"},
            {"metric": "net_debt_ebitda", "label": "Net debt/EBITDA (x)"}]},
}


def load_facts(ws):
    recs = []
    for name in ("financials.json", "derived_metrics.json", "estimates.json", "market_data.json"):
        p = Path(ws) / "facts" / name
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            recs += d.get("facts", d) if isinstance(d, dict) else d
    return recs


def sref(sid):
    if not sid or sid == "DERIVED":
        return ""
    tail = sid.rsplit("-", 1)[-1]
    return f" [S{int(tail)}]" if tail.isdigit() else f" [{sid}]"


def render(ws, spec, basis):
    facts = load_facts(ws)
    # index: metric -> period -> best record (reported beats computed; non-superseded only)
    idx = {}
    for r in facts:
        if r.get("basis") not in (basis, "na"):
            continue
        if "superseded" in (r.get("flags") or []):
            continue
        m, p = r.get("metric"), r.get("period")
        cur = idx.get((m, p))
        if cur is None or (cur.get("method") != "reported" and r.get("method") == "reported"):
            idx[(m, p)] = r

    periods = sorted({p for (m, p) in idx if p.startswith("FY") and len(p) == 6})
    if not periods:
        return f"*{spec['title']}: no FY facts found for basis={basis}*", set()

    used = set()
    lines = [f"**{spec['title']}** ({basis})", "",
             "| Metric | " + " | ".join(periods) + " |",
             "|---" * (len(periods) + 1) + "|"]
    for row in spec["rows"]:
        cells = []
        for p in periods:
            r = idx.get((row["metric"], p))
            if r is None:
                cells.append("N/A")
            else:
                v = r.get("value")
                v = f"{v:,.1f}" if isinstance(v, (int, float)) else str(v)
                sid = (r.get("source") or {}).get("src_id")
                if sid and sid != "DERIVED":
                    used.add(sid)
                cells.append(v + sref(sid))
        lines.append(f"| {row['label']} | " + " | ".join(cells) + " |")
    return "\n".join(lines), used


def legend(ws, used):
    reg = {}
    p = Path(ws) / "state" / "source_registry.json"
    if p.exists():
        reg = json.loads(p.read_text(encoding="utf-8"))
    md = Path(ws) / "facts" / "market_data.json"
    if md.exists():
        reg.update(json.loads(md.read_text(encoding="utf-8")).get("source_registry_entry", {}))
    lines = ["", "*Sources:*"]
    for sid in sorted(used):
        e = reg.get(sid, {})
        tail = sid.rsplit("-", 1)[-1]
        tag = f"S{int(tail)}" if tail.isdigit() else sid
        desc = ", ".join(str(x) for x in (e.get("doc"), f"p.{e.get('page')}" if e.get("page") else None,
                                          e.get("locator")) if x)
        lines.append(f"- [{tag}] {desc or 'UNKNOWN — registry gap'}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace")
    ap.add_argument("--table", choices=sorted(SPECS), default=None)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--basis", default="consolidated")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    spec = SPECS[a.table] if a.table else json.loads(Path(a.spec).read_text(encoding="utf-8"))
    body, used = render(a.workspace, spec, a.basis)
    text = body + ("\n" + legend(a.workspace, used) if used else "")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"OK -> {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
