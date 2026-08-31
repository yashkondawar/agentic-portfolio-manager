"""Phase 10 — 4-gate idea funnel, wired at the start of weekly_idea_cycle.

Reduces the bottom-up contrarian screen (derive/screener.py) to a ranked,
per-gate-annotated candidate list before idea_gen ever sees it. Every
candidate carries its full gate breakdown (never silently dropped without
a reason recorded) so idea_gen/synthesis/critique can see WHY a name did or
didn't clear.

Gates (per the Phase 10 task spec — this repo's cycle_framework.yaml has no
separate top-level "funnel:" section; these gate definitions are implemented
directly against the framework's existing alignment/reconciliation/phase
machinery and the screener's existing output, per the task's own explicit
spec):

  gate1 quant_cycle    — sector cycle phase favorable. Looks up the latest
                         cycle_assessments row for cycle_id='valuation_cycle'
                         at the candidate's sector scope (registry slug via
                         orchestrator.context.SECTOR_TO_KPI_KEY), falling
                         back to NIFTY 500 then NIFTY 50 if the sector scope
                         has no assessment yet (mirrors
                         context._build_cycle_context's own fallback order).
                         PASS if directional_lean in (+1, 0) i.e. phase_id in
                         cycle_framework.yaml alignment.directional_lean_map's
                         "+1"/"0" buckets (deep_value/attractive_growth/
                         momentum/value/optimism); FAIL if -1
                         (euphoria/distribution/denial — the whole point of
                         this gate is blocking late-cycle-phase entries);
                         UNKNOWN if no assessment exists for any fallback
                         scope (never silently defaults to PASS).

  gate2 quality        — ROE/ROCE stability, cash/assets, FCF where available
                         (derived_ratios / financials_quarterly). This repo's
                         data today has at most ONE as_of_date per instrument
                         for roe/roce (no time series yet -> "stability"
                         literally cannot be computed) and financials_quarterly
                         has no cash/assets/FCF fields at all yet — so quality
                         is realistically "partial" (single-point ROE/ROCE
                         only) or "unknown" (nothing) for virtually the whole
                         universe today. This gate NEVER fails a candidate on
                         missing data (per spec: "flag don't fail") — it only
                         reports quality: full|partial|unknown as informational
                         metadata alongside the roe/roce values used.

  gate3 idiosyncratic  — own-history percentile of the stock's P/E
                         (derived_ratios metric_name containing "p_e"), if
                         at least 2 distinct as_of_date points exist to rank
                         against (a single point can't produce a percentile).
                         Today's data has at most 1 point per instrument, so
                         this virtually always falls back to the documented
                         52w-position proxy: pct_from_52w_low (0% = at the
                         52w low, cheap on this proxy; 100% = at the 52w
                         high) from the screener's already-computed field.
                         Always informational (never a hard PASS/FAIL) —
                         gate3's "result" is a percentile numeric + the
                         proxy_used label, since neither proxy has a
                         universally agreed pass/fail cutoff (DRAFT).

  gate4 neglect        — reuses the screener's own flags directly: PASS if
                         the candidate carries "panic_buy", "long_term_neglect",
                         or "deep_drawdown" (the screener's own contrarian
                         flags) AND does NOT carry "euphoria_avoid". FAIL if
                         euphoria_avoid is present (excluded per spec: "NOT
                         euphoria"). This gate is otherwise a pure passthrough
                         of run_screen()'s existing vectorized computation —
                         no new SQL/pandas pass needed.

Ranking: candidates are ordered by (gate1 PASS first, then gate4 score
descending, then gate3 percentile ascending [cheaper first]) — see
rank_candidates(). Nothing here calls an LLM or writes to the database.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from afund.derive.screener import run_screen

# Canonical mapping lives in afund.sectors (dependency-free module — keeps
# cycles/ free of any orchestrator-layer import).
from afund.sectors import SECTOR_TO_KPI_KEY

# Per cycle_framework.yaml alignment.directional_lean_map: phases where
# directional_lean is +1 or 0 are gate1-favorable; -1 phases
# (euphoria/distribution/denial) fail gate1.
_FAVORABLE_LEANS = (1, 0)

_PE_METRIC_HINTS = ("p_e", "pe_ratio", "price_to_earnings")


def _kpi_key_for_sector(raw_sector: str | None) -> str:
    if not raw_sector:
        return "generic"
    return SECTOR_TO_KPI_KEY.get(raw_sector, "generic")


def _latest_valuation_phase(conn: sqlite3.Connection, scope: str) -> dict | None:
    row = conn.execute(
        """
        SELECT scope, as_of_date, phase_id, directional_lean, data_pending
          FROM cycle_assessments
         WHERE cycle_id = 'valuation_cycle' AND scope = ? AND data_pending = 0
         ORDER BY as_of_date DESC
         LIMIT 1
        """,
        (scope,),
    ).fetchone()
    return dict(row) if row else None


def gate1_quant_cycle(conn: sqlite3.Connection, sector: str | None) -> dict:
    """Sector cycle phase favorable. Falls back sector scope -> NIFTY 500 ->
    NIFTY 50, same order as orchestrator.context._build_cycle_context."""
    kpi_key = _kpi_key_for_sector(sector)
    candidate_scopes = [kpi_key, "NIFTY 500", "NIFTY 50"]
    seen: set[str] = set()
    scopes = [s for s in candidate_scopes if s and not (s in seen or seen.add(s))]

    for scope in scopes:
        reading = _latest_valuation_phase(conn, scope)
        if reading is None:
            continue
        lean = reading["directional_lean"]
        result = "PASS" if lean in _FAVORABLE_LEANS else "FAIL"
        return {
            "result": result,
            "scope_used": scope,
            "phase_id": reading["phase_id"],
            "directional_lean": lean,
            "as_of_date": reading["as_of_date"],
        }

    return {
        "result": "UNKNOWN",
        "scope_used": None,
        "phase_id": None,
        "directional_lean": None,
        "as_of_date": None,
        "note": f"no valuation_cycle assessment for any fallback scope ({', '.join(scopes)})",
    }


def gate2_quality(roe: float | None, roce: float | None, debt_to_equity: float | None) -> dict:
    """Quality signal: full|partial|unknown, never a hard fail. 'full' would
    require ROE/ROCE stability across multiple periods plus cash/assets/FCF
    (financials_quarterly has no such fields yet in this repo, and
    derived_ratios has at most one as_of_date per instrument today) — so in
    practice this reports 'partial' when at least one of roe/roce is present,
    else 'unknown'. Never blocks a candidate."""
    have_any = roe is not None or roce is not None
    quality = "partial" if have_any else "unknown"
    return {
        "quality": quality,
        "roe": roe,
        "roce": roce,
        "debt_to_equity": debt_to_equity,
        "note": (
            "single-snapshot ROE/ROCE only (no multi-period stability check possible with "
            "current data); cash/assets/FCF not sourced (financials_quarterly has no such "
            "columns yet)" if have_any else
            "no ROE/ROCE/derived_ratios data for this instrument"
        ),
    }


def gate3_idiosyncratic(
    conn: sqlite3.Connection,
    instrument_id: int,
    pct_from_52w_low: float | None,
    pct_from_52w_high: float | None,
) -> dict:
    """Own-history P/E percentile if >= 2 distinct as_of_date points exist;
    else the documented 52w-position proxy (pct_from_52w_low, 0=at the low)."""
    rows = conn.execute(
        """
        SELECT as_of_date, metric_value FROM derived_ratios
         WHERE instrument_id = ?
           AND (lower(metric_name) LIKE '%p_e%' OR lower(metric_name) LIKE '%pe_ratio%'
                OR lower(metric_name) LIKE '%price_to_earnings%')
         ORDER BY as_of_date ASC
        """,
        (instrument_id,),
    ).fetchall()
    distinct_dates = {r["as_of_date"] for r in rows}

    if len(distinct_dates) >= 2:
        history = [r["metric_value"] for r in rows if r["metric_value"] is not None]
        current = rows[-1]["metric_value"]
        if current is not None and history:
            n = len(history)
            count_le = sum(1 for v in history if v <= current)
            percentile = count_le / n * 100.0
            return {
                "proxy_used": "own_pe_history",
                "percentile": percentile,
                "note": f"P/E percentile over {n} own-history points",
            }

    # Fallback: 52-week position proxy. pct_from_52w_low is 0 at the 52w
    # low (cheapest on this proxy) and grows as price moves away from the
    # low; we report it directly as a 0-100-scaled "cheapness" percentile
    # by re-basing pct_from_52w_low/pct_from_52w_high into a 0-100 band
    # (0 = at 52w low, 100 = at 52w high).
    if pct_from_52w_low is not None and pct_from_52w_high is not None:
        # pct_from_52w_low >= 0 (price - low)/low; pct_from_52w_high <= 0
        # (price - high)/high. Position = low.../(low... - high...) rescale.
        span = pct_from_52w_low - pct_from_52w_high
        position_pct = (pct_from_52w_low / span * 100.0) if span else None
        return {
            "proxy_used": "52w_position",
            "percentile": position_pct,
            "note": "insufficient own-history P/E points (<2); using 52w price-position proxy "
                    "(0=at 52w low, 100=at 52w high)",
        }

    return {
        "proxy_used": None,
        "percentile": None,
        "note": "no own-history P/E series and no 52w price-position data available",
    }


def gate4_neglect(flags: list[str], score: int) -> dict:
    """Passthrough of the screener's own contrarian flags. PASS on any of
    panic_buy/long_term_neglect/deep_drawdown, EXCLUDING euphoria_avoid."""
    if "euphoria_avoid" in flags:
        return {"result": "FAIL", "reason": "euphoria_avoid", "flags": flags, "score": score}
    neglect_flags = [f for f in flags if f in ("panic_buy", "long_term_neglect", "deep_drawdown")]
    if neglect_flags:
        return {"result": "PASS", "reason": ",".join(neglect_flags), "flags": flags, "score": score}
    return {"result": "FAIL", "reason": "no contrarian/neglect flag", "flags": flags, "score": score}


def run_funnel(conn: sqlite3.Connection, as_of: str | None = None, top_n: int = 15) -> dict:
    """Run the screener, then annotate every candidate with all 4 gates.

    Returns:
        {
          "as_of": str,
          "candidates": [ {..screener fields.., "gates": {...}, "gates_passed": int}, ... ],
          "universe_scanned": int,
        }
    Candidates are the screener's own top_n pool (gate4 is near-tautological
    with screener membership since every screener candidate already has a
    contrarian/neglect flag by construction) re-ranked by gate1 PASS first,
    then gate4 PASS, then gate3 percentile ascending (cheaper-on-proxy first).
    """
    screen = run_screen(conn, as_of=as_of, top_n=top_n)
    candidates = []

    for c in screen["candidates"]:
        gate1 = gate1_quant_cycle(conn, c.get("sector"))
        gate2 = gate2_quality(c.get("roe"), c.get("roce"), c.get("debt_to_equity"))
        gate3 = gate3_idiosyncratic(
            conn, c["instrument_id"], c.get("pct_from_52w_low"), c.get("pct_from_52w_high")
        )
        gate4 = gate4_neglect(c.get("flags", []), c.get("score", 0))

        gates = {"gate1_quant_cycle": gate1, "gate2_quality": gate2, "gate3_idiosyncratic": gate3, "gate4_neglect": gate4}
        gates_passed = sum(1 for g in (gate1, gate4) if g.get("result") == "PASS")

        candidates.append({**c, "gates": gates, "gates_passed": gates_passed})

    def _sort_key(c: dict) -> tuple:
        gate1_pass = 0 if c["gates"]["gate1_quant_cycle"]["result"] == "PASS" else 1
        gate4_pass = 0 if c["gates"]["gate4_neglect"]["result"] == "PASS" else 1
        gate3_pct = c["gates"]["gate3_idiosyncratic"]["percentile"]
        gate3_sort = gate3_pct if gate3_pct is not None else 50.0
        return (gate1_pass, gate4_pass, gate3_sort)

    candidates.sort(key=_sort_key)

    return {
        "as_of": screen["as_of"],
        "candidates": candidates,
        "euphoria_list": screen["euphoria_list"],
        "universe_scanned": screen["universe_scanned"],
    }


def _print_table(funnel: dict) -> None:
    candidates = funnel["candidates"]
    print(f"4-gate funnel — as_of={funnel['as_of']}  universe_scanned={funnel['universe_scanned']}")
    print(f"{len(candidates)} candidates\n")

    header = f"{'symbol':<12}{'gate1':<8}{'gate2':<9}{'gate3':>8}  {'gate4':<7}{'passed':>7}"
    print(header)
    print("-" * len(header))
    for c in candidates:
        g1 = c["gates"]["gate1_quant_cycle"]["result"]
        g2 = c["gates"]["gate2_quality"]["quality"]
        g3 = c["gates"]["gate3_idiosyncratic"]["percentile"]
        g3_str = f"{g3:.0f}" if g3 is not None else "n/a"
        g4 = c["gates"]["gate4_neglect"]["result"]
        print(f"{c['symbol']:<12}{g1:<8}{g2:<9}{g3_str:>8}  {g4:<7}{c['gates_passed']:>7}")


def main() -> None:
    from afund.db.connection import get_conn

    conn = get_conn()
    try:
        funnel = run_funnel(conn)
        _print_table(funnel)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
