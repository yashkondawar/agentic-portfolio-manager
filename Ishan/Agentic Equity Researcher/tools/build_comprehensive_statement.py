"""Comprehensive statement builder — deterministic, zero tokens.

Reads the merged facts store (output of tools/merge_facts.py, i.e.
facts/financials.json — optionally also facts/derived_metrics.json for
computed ratios) and assembles a single authoritative multi-period view:

  workspace/<TICKER>/state/comprehensive_statement.json
      For each statement (income_statement / balance_sheet / cash_flow): a
      line-item TREE (level 1 -> level 2 -> level 3 children) x all fiscal
      years and available quarters/halves. Each node:
        {"label": str, "metric": str, "level": int,
         "values": {period: {"value": ..., "unit": ..., "basis": ...,
                              "fact_id": ..., "method": ...}, ...},
         "fact_ids": [...], "children": [...]}

  workspace/<TICKER>/state/comprehensive_statement.md
      Rendered indented multi-year table per statement (one table per
      basis found: consolidated / standalone).

Statement assignment: each Level-1 metric is classified into
income_statement / balance_sheet / cash_flow via a keyword heuristic aligned
with prompts/10's Part 1/2/3 vocabulary; anything genuinely outside the three
statements (production and capacity volumes, dividends, buybacks, share counts)
lands in the fourth bucket, which is a legitimate destination and not a failure.
Level 2/3 records inherit their parent's statement.

ONLY LEVEL 1 BECOMES A ROOT. This used to read "level 1 OR no resolvable
parent", which promoted every unparented record to a root. Extraction labels
`level` reliably but `parent` rarely — 79 of 1,220 facts on the NALCO run — so
that rule flattened the tree: 117 roots on a ~12-line income statement, max
depth 2, and duplicate-looking sibling rows in the Excel export. The advertised
three-level decomposition was not being built.

A level-2/3 record without a parent is now ATTACHED, not promoted, in this
order: (1) explicit `parent` (fact id or metric name); (2) the longest
metric-name prefix shared with a shallower metric in the same statement, since
this vocabulary names breakdowns by extending the parent's stem
(revenue_alumina_export -> revenue_alumina -> revenue); (3) a per-statement,
per-level bucket node labelled "Level-N items whose parent line was not captured
by extraction". Every inferred edge is counted and the split is printed, so a
largely-reconstructed tree announces itself instead of passing as disclosed.

Prior-year comparative aliases are folded: `<metric>_prior` merges onto
`<metric>`, because the `_prior` record already carries the correct earlier
period and the separate name was duplicating the line item.

Missing levels are still handled gracefully: Level 3 without a Level 2 nests
under Level 1 flagged `orphan_level: true`, never dropped. Nodes whose parent
edge was inferred rather than disclosed carry `inferred_parent: true`.

Usage:
  python tools/build_comprehensive_statement.py workspace/TICKER/facts/financials.json \
      --out-json workspace/TICKER/state/comprehensive_statement.json \
      --out-md workspace/TICKER/state/comprehensive_statement.md \
      [--derived workspace/TICKER/facts/derived_metrics.json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# --- statement classification (Level-1 / root metrics only) ---------------

# Keyword lists aligned with prompts/10's Part 1/2/3 vocabulary.
#
# EXPANDED 2026-08-03. The original lists left 204 of NALCO's line items in `unclassified`,
# including obvious face lines — `total_income`, `profit_for_the_year`, `intangible_assets`,
# `other_equity`, `total_liabilities`, `cash_from_operating_activities`. Two causes: singular vs
# plural stems (`intangibles` never matches `intangible_assets`) and Ind-AS Indian statement
# wording the lists did not cover (`total_comprehensive_income`, `other_financial_assets_current`).
#
# ORDER MATTERS: classify_root() tests cash flow, then balance sheet, then income statement. So
# cash-flow keys must stay specific — a bare "cash" here would capture the balance sheet's
# `cash_and_cash_equivalents`.
INCOME_STATEMENT_KEYWORDS = (
    "revenue", "other_income", "total_income", "total_expenses", "ebitda", "ebit",
    "depreciation", "amortization", "amortisation", "finance_costs", "pbt", "tax", "pat",
    "profit_for_the", "profit_before", "profit_after", "comprehensive_income", "tci",
    "minority_interest", "eps", "weighted_shares", "cost_of_materials",
    "cost_of_raw_materials", "purchases_stock_in_trade", "changes_in_inventories",
    "employee_benefits", "power_fuel", "power_and_fuel", "freight", "sub_contracting",
    "other_expenses", "exceptional_item", "share_of_profit",
)
BALANCE_SHEET_KEYWORDS = (
    "total_assets", "total_equity", "total_liabilities", "ppe",
    "property_plant", "cwip", "capital_work", "intangible", "goodwill",
    "investments", "inventories", "trade_receivables", "trade_payables",
    "cash_and_bank", "cash_and_cash_equivalents", "cash_and_equivalents",
    "bank_balances", "borrowings", "lease_liabilit", "provisions",
    "contingent_liabilities", "deferred_tax", "current_assets",
    "current_liabilities", "net_debt", "net_worth", "gross_receivables",
    "allowance_doubtful_accounts", "equity_share_capital", "other_equity",
    "share_capital", "reserves", "loans_noncurrent", "loans_current",
    "other_financial_assets", "other_financial_liabilities",
    "other_noncurrent", "other_current_assets", "other_current_liabilities",
    "right_of_use", "capital_employed",
)
CASH_FLOW_KEYWORDS = (
    "cfo", "cfi", "cff", "purchase_of_ppe", "purchase_of_intangibles",
    "sale_of_ppe", "net_capex", "capex", "fcf", "working_capital_movement",
    "cash_flow", "cash_from_operating", "cash_from_investing",
    "cash_from_financing", "cash_used_in", "cash_generated",
    "proceeds_from", "repayment_of", "dividend_paid", "interest_paid",
)

STATEMENT_LABELS = {
    "income_statement": "Income Statement",
    "balance_sheet": "Balance Sheet",
    "cash_flow": "Cash Flow",
    # Not a failure bucket. After the 2026-08-03 keyword expansion, what lands here is
    # genuinely outside the three statements: production and capacity volumes, dividends and
    # buybacks, share counts, the auditor's opinion. Those are exactly the operating metrics
    # compute_kpis.py needs, so the name should not read as "we could not classify these".
    "unclassified": "Operating & other metrics (outside the three statements)",
}


def classify_root(metric: str) -> str:
    m = metric.lower()
    # Derived percentages are not statement lines - see is_derived_analytic().
    if is_derived_analytic(m):
        return "unclassified"
    if any(k in m for k in CASH_FLOW_KEYWORDS):
        return "cash_flow"
    if any(k in m for k in BALANCE_SHEET_KEYWORDS):
        return "balance_sheet"
    if any(k in m for k in INCOME_STATEMENT_KEYWORDS):
        return "income_statement"
    return "unclassified"


# --- loading ----------------------------------------------------------------

def load_facts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    recs = data.get("facts", data) if isinstance(data, dict) else data
    return [r for r in recs if isinstance(r, dict)]


def is_live(rec: dict) -> bool:
    return "superseded" not in (rec.get("flags") or [])


# --- tree assembly ------------------------------------------------------

class Node:
    __slots__ = ("label", "metric", "level", "values", "fact_ids", "children", "orphan_level",
                 "inferred_parent")

    def __init__(self, metric: str, label: str, level: int):
        self.metric = metric
        self.label = label
        self.level = level
        self.values: dict[str, dict] = {}
        self.fact_ids: list[str] = []
        self.children: dict[str, "Node"] = {}
        self.orphan_level = False
        self.inferred_parent = False   # True when this node's parent edge was inferred, not disclosed

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "metric": self.metric,
            "level": self.level,
            "values": self.values,
            "fact_ids": sorted(set(self.fact_ids)),
            "orphan_level": self.orphan_level,
            "inferred_parent": self.inferred_parent,
            "children": [c.to_dict() for c in self.children.values()],
        }


# Period qualifiers baked into a metric NAME while the record's `period` field already carries the
# same information. Folding these reunites one line item's history instead of showing it as several
# sibling rows. Measured on NALCO: 97 such metrics, every one with its base metric present.
_PERIOD_SUFFIX_RE = re.compile(
    r"_(?:h[12]|q[1-4]|fy20\d{2}(?:_full_year)?|full_year|"
    r"fy20\d{2}q[1-4]|prior)$"
)

# Derived percentages. Real facts, but not statement lines: a percentage in a currency column breaks
# the common-size base, and tools/export_financials_xlsx.py now computes YoY itself.
_DERIVED_RE = re.compile(r"_(?:yoy|qoq)(?:_pct)?$")


def is_derived_analytic(metric: str) -> bool:
    return bool(_DERIVED_RE.search(metric or ""))


def canonical_metric(metric: str) -> str:
    """Fold prior-year comparative aliases onto the base line item.

    Extractors emit a statement's prior-year column as a SEPARATE metric — `revenue_from_operations`
    for FY2021 and `revenue_from_operations_prior` for FY2020 — even though the `_prior` record
    already carries the correct earlier period. That is pure duplication of the line item, and it
    doubled the statement face: on the NALCO run, all 88 `_prior` metrics had their base metric
    present too, which is what produced apparent duplicate sibling rows in the Excel export
    (`Cost of power and fuel` twice, with different period coverage each).

    Folding is safe precisely BECAUSE the period is already right — the two records differ only in
    name, so merging them by name loses nothing and reunites one line item's history.
    """
    if not metric:
        return metric
    folded = _PERIOD_SUFFIX_RE.sub("", metric)
    # Never fold a name down to nothing, and never fold a derived percentage onto a currency line.
    return folded if folded and not is_derived_analytic(metric) else metric


def build_trees(facts: list[dict]) -> dict[str, dict[str, Node]]:
    """Returns {statement: {metric: root_node}} — root_node subtrees hold
    level-2/3 children keyed by metric name."""
    live = [f for f in facts if is_live(f)]
    folded = 0
    for r in live:
        m = r.get("metric")
        if not m:
            continue
        canon = canonical_metric(m)
        if canon != m:
            r["metric"] = canon
            r.setdefault("flags", []).append("period_alias_folded")
            folded += 1
    if folded:
        build_comprehensive_statement_edge_stats["prior_aliases_folded"] = folded
    by_metric_fact_ids: dict[str, str] = {}  # metric -> a representative fact id (any period) for parent-chain lookups
    parent_of: dict[str, str | None] = {}    # metric -> parent metric (from any record carrying that metric)
    level_of: dict[str, int] = {}
    label_of: dict[str, str] = {}

    for r in live:
        metric = r.get("metric")
        if not metric:
            continue
        level_of.setdefault(metric, r.get("level", 1) or 1)
        label_of.setdefault(metric, r.get("label") or metric)
        parent_metric = r.get("parent")
        # `parent` in fact records is documented as a fact id, but extractors in
        # practice may emit either a fact id or a metric name; resolve by metric
        # name when possible, else keep the raw value for id-based lookups below.
        if parent_metric:
            parent_of.setdefault(metric, parent_metric)
        by_metric_fact_ids.setdefault(metric, r.get("id"))

    # map fact id -> metric, for resolving parent fields that are fact ids
    id_to_metric = {r.get("id"): r.get("metric") for r in live if r.get("id")}

    def resolve_parent_metric(metric: str) -> str | None:
        p = parent_of.get(metric)
        if not p:
            return None
        if p in level_of:  # already a metric name
            return p
        return id_to_metric.get(p)  # else treat as fact id

    # roots = LEVEL-1 metrics only.
    #
    # This used to read `if lvl == 1 or resolve_parent_metric(metric) is None`, i.e. any metric
    # without a resolvable parent was promoted to a root whatever its level. Extractors populate
    # `level` reliably but `parent` rarely — on the NALCO run, 79 of 1,220 facts (6%) carried a
    # parent — so the promotion rule flattened the tree: 117 "roots" on an income statement that
    # has ~12 face lines, max depth 2, and the same label appearing as several sibling rows in
    # the Excel export. The three-level decomposition CLAUDE.md advertises was not being built.
    #
    # A level-2 or level-3 metric with no parent is now ATTACHED rather than promoted, by
    # _infer_parent() below. Nothing is invented: a name-prefix match is used where one exists,
    # and everything else lands in a clearly-labelled per-statement bucket so the missing
    # disclosure is visible in the output instead of silently restructuring the statement.
    roots: dict[str, str] = {}  # metric -> statement
    for metric, lvl in level_of.items():
        if lvl == 1:
            roots[metric] = classify_root(metric)
    if not roots:
        # No level-1 records at all (a very sparse extraction). Fall back to the old behaviour so
        # the tool still produces something, and say so.
        for metric in level_of:
            if resolve_parent_metric(metric) is None:
                roots[metric] = classify_root(metric)

    trees: dict[str, dict[str, Node]] = {s: {} for s in STATEMENT_LABELS}

    def get_or_create(statement: str, metric: str, level: int) -> Node:
        bucket = trees[statement]
        if metric not in bucket:
            bucket[metric] = Node(metric, label_of.get(metric, metric), level)
        return bucket[metric]

    # build node registry across all metrics first (flat), then link parent->child
    all_nodes: dict[str, Node] = {}
    metric_statement: dict[str, str] = {}

    def statement_for(metric: str, _seen=None) -> str:
        if metric in metric_statement:
            return metric_statement[metric]
        _seen = _seen or set()
        if metric in _seen:
            return "unclassified"
        _seen.add(metric)
        if metric in roots:
            stmt = roots[metric]
        else:
            p = resolve_parent_metric(metric)
            stmt = statement_for(p, _seen) if p else classify_root(metric)
        metric_statement[metric] = stmt
        return stmt

    for metric, level in level_of.items():
        stmt = statement_for(metric)
        node = Node(metric, label_of.get(metric, metric), level)
        all_nodes[metric] = node
        metric_statement[metric] = stmt

    # attach values + fact_ids from every live record onto its node
    for r in live:
        metric = r.get("metric")
        if not metric or metric not in all_nodes:
            continue
        node = all_nodes[metric]
        period = r.get("period")
        if period:
            incoming = {
                "value": r.get("value"),
                "unit": r.get("unit"),
                "basis": r.get("basis"),
                "fact_id": r.get("id"),
                "method": r.get("method"),
            }
            existing = node.values.get(period)
            if existing is None:
                node.values[period] = incoming
            else:
                # Same line item, same period, two bases. This used to be last-writer-wins, which
                # made a node's basis vary BY PERIOD - so a single-basis column filter blanked most
                # of the statement. Prefer consolidated (the basis a reader expects); keep the
                # other on the entry rather than discarding it.
                rank = {"consolidated": 2, "standalone": 1}
                keep, drop = ((incoming, existing)
                              if rank.get(incoming.get("basis"), 0) > rank.get(existing.get("basis"), 0)
                              else (existing, incoming))
                if drop.get("basis") != keep.get("basis"):
                    keep = dict(keep)
                    keep["alt_basis"] = {"basis": drop.get("basis"), "value": drop.get("value"),
                                         "fact_id": drop.get("fact_id")}
                node.values[period] = keep
        if r.get("id"):
            node.fact_ids.append(r["id"])

    # ---- parent inference for records that carry `level` but no `parent` -------------------
    # Extraction labels levels far more reliably than it wires edges, so the tree has to be
    # reconstructable from levels alone. Order of preference, most trustworthy first:
    #   1. explicit `parent` (a fact id or a metric name) — always wins
    #   2. longest metric-name prefix shared with a shallower metric in the same statement,
    #      e.g. revenue_alumina_export -> revenue_alumina -> revenue. This is a real signal in
    #      this fact vocabulary, where breakdowns are named by extending the parent's stem.
    #   3. a per-statement, per-level bucket node, explicitly labelled as un-attributed
    # Every inferred edge is counted and reported; nothing is silently invented.
    edge_stats = {"explicit": 0, "prefix_inferred": 0, "bucketed": 0, "root": 0,
                  "prior_aliases_folded": build_comprehensive_statement_edge_stats.get(
                      "prior_aliases_folded", 0)}
    BUCKET_PREFIX = "_unattributed_level"

    def _infer_parent(metric: str, node: Node, stmt: str) -> str | None:
        """Best shallower metric in the same statement whose name is a prefix of `metric`."""
        best, best_len = None, 0
        stem = metric
        for cand, cand_lvl in level_of.items():
            if cand == metric or cand_lvl >= node.level:
                continue
            if metric_statement.get(cand) != stmt:
                continue
            # require a token-boundary prefix so `revenue_x` matches `revenue` but not `rev`
            if stem.startswith(cand + "_") and len(cand) > best_len:
                best, best_len = cand, len(cand)
        return best

    def _bucket_for(stmt: str, level: int) -> Node:
        key = f"{BUCKET_PREFIX}{level}"
        bucket = trees[stmt].get(key)
        if bucket is None:
            bucket = Node(key,
                          f"Level-{level} items whose parent line was not captured by extraction",
                          level - 1)
            bucket.orphan_level = True
            trees[stmt][key] = bucket
        return bucket

    # link children to parents; roots go into `trees[statement]`
    for metric, node in all_nodes.items():
        stmt = metric_statement[metric]
        parent_metric = resolve_parent_metric(metric)
        source = "explicit" if (parent_metric and parent_metric in all_nodes
                               and parent_metric != metric) else None

        if source is None and node.level > 1:
            inferred = _infer_parent(metric, node, stmt)
            if inferred and inferred in all_nodes:
                parent_metric, source = inferred, "prefix_inferred"
                node.inferred_parent = True

        if source:
            parent_node = all_nodes[parent_metric]
            # graceful missing-level handling: if this is level 3 but parent is
            # level 1 (no level-2 in between), mark it an orphan child rather
            # than dropping it.
            if node.level == 3 and parent_node.level == 1:
                node.orphan_level = True
            parent_node.children[metric] = node
            edge_stats[source] += 1
        elif node.level > 1:
            # Level 2/3 with nothing to attach to: bucket it rather than promote it to a root,
            # so the statement's face keeps only its real face lines.
            _bucket_for(stmt, node.level).children[metric] = node
            node.orphan_level = True
            edge_stats["bucketed"] += 1
        else:
            trees[stmt][metric] = node
            edge_stats["root"] += 1

    build_comprehensive_statement_edge_stats.clear()
    build_comprehensive_statement_edge_stats.update(edge_stats)
    return trees


# Populated by build_trees() so main() can report how much of the tree was inferred rather than
# disclosed. Kept module-level because build_trees()'s return type is part of the public shape.
build_comprehensive_statement_edge_stats: dict[str, int] = {}


# --- rendering ------------------------------------------------------------

def all_periods(trees: dict[str, dict[str, Node]]) -> list[str]:
    periods: set[str] = set()

    def walk(node: Node):
        periods.update(node.values.keys())
        for c in node.children.values():
            walk(c)

    for bucket in trees.values():
        for root in bucket.values():
            walk(root)
    return sorted(periods, key=lambda p: (0 if p.startswith("FY") else 1, p))


def fmt_value(v) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, (int, float)):
        return f"{v:,.1f}"
    return str(v)


def render_node(node: Node, periods: list[str], basis: str, indent: int, lines: list[str]):
    cells = []
    for p in periods:
        entry = node.values.get(p)
        if entry is None or (entry.get("basis") not in (basis, "na")):
            cells.append("")
        else:
            cells.append(fmt_value(entry.get("value")))
    prefix = "  " * indent + ("- " if indent else "")
    lines.append(f"| {prefix}{node.label} | " + " | ".join(cells) + " |")
    for child in sorted(node.children.values(), key=lambda n: n.label):
        render_node(child, periods, basis, indent + 1, lines)


def render_markdown(trees: dict[str, dict[str, Node]]) -> str:
    periods = all_periods(trees)
    bases: set[str] = set()

    def collect_bases(node: Node):
        for entry in node.values.values():
            b = entry.get("basis")
            if b and b != "na":
                bases.add(b)
        for c in node.children.values():
            collect_bases(c)

    for bucket in trees.values():
        for root in bucket.values():
            collect_bases(root)
    if not bases:
        bases = {"consolidated"}

    out = ["# Comprehensive Statement (3-level, all periods)", ""]
    if not periods:
        out.append("*No periods found in facts store.*")
        return "\n".join(out)

    for statement, label in STATEMENT_LABELS.items():
        bucket = trees.get(statement, {})
        if not bucket:
            continue
        out.append(f"## {label}")
        out.append("")
        for basis in sorted(bases):
            out.append(f"### Basis: {basis}")
            out.append("")
            lines = ["| Line item | " + " | ".join(periods) + " |",
                     "|---" * (len(periods) + 1) + "|"]
            for root in sorted(bucket.values(), key=lambda n: n.label):
                render_node(root, periods, basis, 0, lines)
            out.extend(lines)
            out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("facts_file", help="merged facts store, e.g. workspace/TICKER/facts/financials.json")
    ap.add_argument("--derived", default=None, help="optional derived_metrics.json to include computed ratios")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    a = ap.parse_args()

    facts = load_facts(Path(a.facts_file))
    if a.derived:
        facts += load_facts(Path(a.derived))

    trees = build_trees(facts)

    json_out = {
        statement: {metric: node.to_dict() for metric, node in bucket.items()}
        for statement, bucket in trees.items()
    }

    out_json_path = Path(a.out_json)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(json_out, indent=2, ensure_ascii=False), encoding="utf-8")

    md = render_markdown(trees)
    out_md_path = Path(a.out_md)
    out_md_path.parent.mkdir(parents=True, exist_ok=True)
    out_md_path.write_text(md, encoding="utf-8")

    counts = {s: len(b) for s, b in trees.items()}
    es = build_comprehensive_statement_edge_stats
    total_edges = es.get("explicit", 0) + es.get("prefix_inferred", 0) + es.get("bucketed", 0)
    print(f"OK: comprehensive statement -> {out_json_path} + {out_md_path}; root counts: {counts}")
    if es.get("prior_aliases_folded"):
        print(f"    folded {es['prior_aliases_folded']} period-alias metric(s) onto their base line "
              f"item (_prior, _h1, _q1..q4, _fy20XX_full_year). Extraction baked the period into the "
              f"metric NAME while the record's `period` field already carried it, so one line item "
              f"was appearing as several sibling rows in the statement.")
    if total_edges:
        pct = 100.0 * es.get("explicit", 0) / total_edges
        print(f"    tree edges: {es.get('explicit', 0)} disclosed by extraction ({pct:.0f}%), "
              f"{es.get('prefix_inferred', 0)} inferred from the metric-name hierarchy, "
              f"{es.get('bucketed', 0)} un-attributable (see the "
              f"'Level-N items whose parent line was not captured' nodes)")
        if pct < 50:
            print(f"    NOTE: under half the tree edges were disclosed. Extraction is labelling "
                  f"`level` but not `parent` — see prompts/10, which now requires `parent` on "
                  f"every level-2/3 record. The tree above is largely reconstructed.")


if __name__ == "__main__":
    main()
