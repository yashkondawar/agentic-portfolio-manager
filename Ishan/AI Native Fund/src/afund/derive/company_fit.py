"""Phase 12 — universe screening: company-fit classification.

Classifies every active STOCK instrument into ONE `fit_bucket`, joining:
  - latest derived_ratios (mcap, pe, roce, roe...) — populated at scale by
    the batch screener.in scrape (afund.data.financials.scrape_universe),
    falling back to whatever a single instrument already has (e.g. the
    long-standing watchlist-scoped fetch) when the batch hasn't reached it.
  - sector + sector cycle phase: latest cycle_assessments.phase_id for the
    sector's registry KPI scope (afund.sectors.kpi_key_for_sector), same
    scope-name convention cycles/funnel.py uses (NOT the fallback-chased
    scope funnel.py resolves per-candidate — company_fit reports the
    sector's OWN scope reading only, honestly NULL if that exact scope has
    no assessment, since this module's job is "what do we know about this
    company's sector today", not "the funnel's best-available proxy").
  - derive/screener.py per-instrument metrics (ret_1y, cagr_5y, 52w
    position, panic/euphoria/neglect flags) via run_screen()'s own
    vectorized pass over the whole universe (one query, not one per
    instrument).
  - cycles/funnel.py gate1 (quant_cycle) + gate4 (neglect) results, reusing
    those gate functions directly rather than re-deriving the same logic.

Classification rules (module contract — DRAFT, unvalidated, not
back-tested; every fit_bucket/fit_score number here is a judgment call
until the user back-tests it, per CLAUDE.md's "all strategy/framework
thresholds are DRAFT" rule):

  Evaluated in this fixed priority order — the FIRST matching rule wins,
  so e.g. a euphoria-flagged instrument with strong quality metrics is
  bucketed euphoria_avoid, not quality_watch (euphoria/entry-timing risk is
  treated as the dominant signal over static quality here):

  1. data_gap             — pe, roce, and roe are ALL None (i.e. the batch
                             scrape never reached this instrument, or
                             screener.in had nothing parseable for it).
                             Honest "we don't know" bucket per CLAUDE.md's
                             never-fabricate-missing-data rule, not a
                             silent 0/None fallthrough into another bucket.
  2. euphoria_avoid        — "euphoria_avoid" in screener flags, OR
                             pct_52w (0-100 rebased 52w position, 0=at the
                             52w low, 100=at the 52w high) > 90 ("own-
                             history percentile >90" per the task spec,
                             approximated with the same 52w-position proxy
                             cycles/funnel.py's gate3 already uses when an
                             own-history P/E series isn't available, which
                             is virtually always true for this universe
                             today per funnel.py's own docstring).
  3. contrarian_candidate  — gate1 result == "PASS" AND at least one of
                             ("panic_buy","long_term_neglect","deep_drawdown")
                             in flags (i.e. gate4 would PASS too, but this
                             bucket doesn't require gate4's exact PASS/FAIL
                             computation, just the same underlying flags —
                             kept as a direct flag check so a candidate
                             that's already excluded from euphoria_avoid
                             above by construction never double-fails
                             gate4's separate euphoria exclusion).
  4. weak_avoid            — quality metrics present (roce or roe not None)
                             AND (roce < 8 OR roe < 8) — "leverage red
                             flags" per the task spec is left unimplemented
                             (financials_quarterly has no debt/equity
                             fields yet, same documented gap
                             cycles/funnel.py's gate2 already calls out) so
                             this rule is ROCE/ROE-only today, DRAFT.
  5. quality_watch         — quality metrics present AND roce > 15 AND
                             roe > 12, no entry signal (didn't already
                             match contrarian_candidate above).
  6. neutral               — none of the above; some data exists (not a
                             data_gap) but no fit signal either way.

fit_score (0-100, simple/DRAFT — documented here in full, not buried):
  Starts at 50 (neutral baseline). Additive adjustments, then clamped to
  [0, 100]:
    +20  gate1_quant_cycle PASS (favorable sector cycle phase)
    +15  any contrarian/neglect flag present (panic_buy, long_term_neglect,
         deep_drawdown)
    +10  roce > 15 (quality signal, if known)
    +10  roe > 12 (quality signal, if known)
    -25  euphoria_avoid flag present
    -15  pct_52w > 90 (near-52w-high, even without the explicit flag)
    -15  roce < 8 (if known)
    -15  roe < 8 (if known)
  data_gap rows get fit_score = None (an honest "can't score it" rather
  than a fabricated 50 — never fabricate per CLAUDE.md).

Nothing here calls an LLM; this module only computes, classifies, and
writes to `company_fit` (additive migration, see schema.sql).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from afund.config import REPO_ROOT
from afund.cycles.funnel import gate1_quant_cycle, gate4_neglect
from afund.derive.screener import run_screen
from afund.sectors import kpi_key_for_sector

EXPORTS_DIR = REPO_ROOT / "data" / "exports"

# fit_score adjustment weights — see module docstring for the full rationale.
_SCORE_BASELINE = 50.0
_SCORE_ADJUSTMENTS = {
    "gate1_pass": 20.0,
    "contrarian_flag": 15.0,
    "roce_strong": 10.0,
    "roe_strong": 10.0,
    "euphoria_flag": -25.0,
    "near_52w_high": -15.0,
    "roce_weak": -15.0,
    "roe_weak": -15.0,
}

_CONTRARIAN_FLAGS = ("panic_buy", "long_term_neglect", "deep_drawdown")
_PCT_52W_EUPHORIA_THRESHOLD = 90.0
_ROCE_STRONG = 15.0
_ROE_STRONG = 12.0
_ROCE_WEAK = 8.0
_ROE_WEAK = 8.0


def _active_stocks(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id AS instrument_id, symbol, sector
          FROM instruments
         WHERE active = 1 AND instrument_type = 'STOCK'
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _latest_derived_ratios(conn: sqlite3.Connection, instrument_ids: list[int]) -> dict[int, dict[str, float]]:
    """Latest (by as_of_date) value per (instrument_id, metric family) for
    mcap/pe/roce/roe, tolerant substring matching mirroring
    derive/screener.py's _tolerant_metric_lookup (derived_ratios.metric_name
    is not a controlled vocabulary in practice)."""
    if not instrument_ids:
        return {}
    placeholders = ",".join("?" for _ in instrument_ids)
    rows = conn.execute(
        f"""
        SELECT instrument_id, as_of_date, metric_name, metric_value
          FROM derived_ratios
         WHERE instrument_id IN ({placeholders})
         ORDER BY instrument_id ASC, as_of_date ASC
        """,
        instrument_ids,
    ).fetchall()

    hints = {
        "mcap": ("market_cap",),
        "pe": ("p_e", "pe_ratio", "price_to_earnings"),
        "roce": ("roce",),
        "roe": ("roe",),
    }

    # instrument_id -> field -> (as_of_date, value), kept as "latest wins"
    # since rows are ordered ascending by as_of_date per instrument.
    result: dict[int, dict[str, float]] = {}
    for row in rows:
        iid = row["instrument_id"]
        name_lower = row["metric_name"].lower()
        bucket = result.setdefault(iid, {})
        for field, field_hints in hints.items():
            if any(hint in name_lower for hint in field_hints):
                bucket[field] = row["metric_value"]
    return result


def _sector_phase(conn: sqlite3.Connection, kpi_sector: str) -> str | None:
    row = conn.execute(
        """
        SELECT phase_id FROM cycle_assessments
         WHERE cycle_id = 'valuation_cycle' AND scope = ? AND data_pending = 0
         ORDER BY as_of_date DESC
         LIMIT 1
        """,
        (kpi_sector,),
    ).fetchone()
    return row["phase_id"] if row else None


def _rebased_pct_52w(pct_from_52w_low: float | None, pct_from_52w_high: float | None) -> float | None:
    """Same 0-100 rebasing cycles/funnel.py's gate3 uses for its 52w-position
    proxy (0 = at the 52w low, 100 = at the 52w high)."""
    if pct_from_52w_low is None or pct_from_52w_high is None:
        return None
    span = pct_from_52w_low - pct_from_52w_high
    if not span:
        return None
    return pct_from_52w_low / span * 100.0


def classify_fit(
    *,
    pe: float | None,
    roce: float | None,
    roe: float | None,
    flags: list[str],
    gate1_result: str,
    pct_52w: float | None,
) -> tuple[str, float | None]:
    """Pure classification function — see module docstring for the full
    rule set and fit_score formula. Returns (fit_bucket, fit_score)."""
    if pe is None and roce is None and roe is None:
        return "data_gap", None

    score = _SCORE_BASELINE
    if gate1_result == "PASS":
        score += _SCORE_ADJUSTMENTS["gate1_pass"]
    has_contrarian_flag = any(f in flags for f in _CONTRARIAN_FLAGS)
    if has_contrarian_flag:
        score += _SCORE_ADJUSTMENTS["contrarian_flag"]
    if roce is not None and roce > _ROCE_STRONG:
        score += _SCORE_ADJUSTMENTS["roce_strong"]
    if roe is not None and roe > _ROE_STRONG:
        score += _SCORE_ADJUSTMENTS["roe_strong"]
    has_euphoria_flag = "euphoria_avoid" in flags
    near_52w_high = pct_52w is not None and pct_52w > _PCT_52W_EUPHORIA_THRESHOLD
    if has_euphoria_flag:
        score += _SCORE_ADJUSTMENTS["euphoria_flag"]
    if near_52w_high:
        score += _SCORE_ADJUSTMENTS["near_52w_high"]
    roce_weak = roce is not None and roce < _ROCE_WEAK
    roe_weak = roe is not None and roe < _ROE_WEAK
    if roce_weak:
        score += _SCORE_ADJUSTMENTS["roce_weak"]
    if roe_weak:
        score += _SCORE_ADJUSTMENTS["roe_weak"]
    score = max(0.0, min(100.0, score))

    if has_euphoria_flag or near_52w_high:
        return "euphoria_avoid", score

    if gate1_result == "PASS" and has_contrarian_flag:
        return "contrarian_candidate", score

    have_quality = roce is not None or roe is not None
    if have_quality and (roce_weak or roe_weak):
        return "weak_avoid", score

    if have_quality and roce is not None and roe is not None and roce > _ROCE_STRONG and roe > _ROE_STRONG:
        return "quality_watch", score

    return "neutral", score


def build_company_fit(conn: sqlite3.Connection, as_of: str | None = None) -> list[dict]:
    """Build the full company_fit row set for every active STOCK. Pure
    compute — does not write to the DB (see refresh_company_fit for the
    upsert wrapper). Returns the row list in the same shape written to
    `company_fit` (as_of_date/created_at added by the caller on write)."""
    as_of = as_of or dt.date.today().isoformat()
    stocks = _active_stocks(conn)
    if not stocks:
        return []

    instrument_ids = [s["instrument_id"] for s in stocks]
    ratios_by_instrument = _latest_derived_ratios(conn, instrument_ids)

    screen = run_screen(conn, as_of=as_of, top_n=len(stocks))
    screener_by_instrument = {c["instrument_id"]: c for c in screen["candidates"]}
    for c in screen.get("euphoria_list", []):
        screener_by_instrument.setdefault(c["instrument_id"], c)

    sector_phase_cache: dict[str, str | None] = {}
    rows: list[dict] = []

    for stock in stocks:
        iid = stock["instrument_id"]
        symbol = stock["symbol"]
        sector = stock["sector"]
        kpi_sector = kpi_key_for_sector(sector)

        if kpi_sector not in sector_phase_cache:
            sector_phase_cache[kpi_sector] = _sector_phase(conn, kpi_sector)
        sector_phase = sector_phase_cache[kpi_sector]

        ratios = ratios_by_instrument.get(iid, {})
        screener_row = screener_by_instrument.get(iid)

        flags = screener_row["flags"] if screener_row else []
        ret_1y = screener_row["ret_1y"] if screener_row else None
        pct_52w = (
            _rebased_pct_52w(screener_row["pct_from_52w_low"], screener_row["pct_from_52w_high"])
            if screener_row
            else None
        )
        # Prefer the screener's own tolerant pe/roce/roe lookup (already
        # computed in the run_screen pass) when this instrument was part of
        # the screener's flagged pool; otherwise fall back to the direct
        # derived_ratios lookup above so instruments with NO screener flags
        # (the vast majority) still get their fundamentals reported.
        def _prefer_screener(field: str) -> float | None:
            screener_value = screener_row.get(field) if screener_row else None
            return screener_value if screener_value is not None else ratios.get(field)

        pe = _prefer_screener("pe")
        roce = _prefer_screener("roce")
        roe = _prefer_screener("roe")

        gate1 = gate1_quant_cycle(conn, sector)
        gate4 = gate4_neglect(flags, screener_row["score"] if screener_row else 0)
        gates_passed = sum(1 for g in (gate1, gate4) if g["result"] == "PASS")

        fit_bucket, fit_score = classify_fit(
            pe=pe, roce=roce, roe=roe, flags=flags, gate1_result=gate1["result"], pct_52w=pct_52w,
        )

        rows.append(
            {
                "instrument_id": iid,
                "symbol": symbol,
                "sector": sector,
                "kpi_sector": kpi_sector,
                "sector_phase": sector_phase,
                "mcap": ratios.get("mcap"),
                "pe": pe,
                "roce": roce,
                "roe": roe,
                "ret_1y": ret_1y,
                "pct_52w": pct_52w,
                "flags": flags,
                "gates_passed": gates_passed,
                "fit_bucket": fit_bucket,
                "fit_score": fit_score,
            }
        )

    return rows


def refresh_company_fit(conn: sqlite3.Connection, as_of: str | None = None) -> dict:
    """Compute build_company_fit() and upsert into `company_fit`. Idempotent
    (ON CONFLICT(instrument_id, as_of_date) DO UPDATE). Returns a summary
    dict {"as_of", "rows_written", "bucket_counts"} for job_runs-style
    logging by the router step."""
    as_of = as_of or dt.date.today().isoformat()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    rows = build_company_fit(conn, as_of=as_of)
    bucket_counts: dict[str, int] = {}
    rows_written = 0

    for row in rows:
        bucket_counts[row["fit_bucket"]] = bucket_counts.get(row["fit_bucket"], 0) + 1
        conn.execute(
            """
            INSERT INTO company_fit
                (instrument_id, symbol, as_of_date, sector, kpi_sector, sector_phase,
                 mcap, pe, roce, roe, ret_1y, pct_52w, flags, gates_passed,
                 fit_bucket, fit_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument_id, as_of_date) DO UPDATE SET
                symbol = excluded.symbol,
                sector = excluded.sector,
                kpi_sector = excluded.kpi_sector,
                sector_phase = excluded.sector_phase,
                mcap = excluded.mcap,
                pe = excluded.pe,
                roce = excluded.roce,
                roe = excluded.roe,
                ret_1y = excluded.ret_1y,
                pct_52w = excluded.pct_52w,
                flags = excluded.flags,
                gates_passed = excluded.gates_passed,
                fit_bucket = excluded.fit_bucket,
                fit_score = excluded.fit_score,
                created_at = excluded.created_at
            """,
            (
                row["instrument_id"], row["symbol"], as_of, row["sector"], row["kpi_sector"],
                row["sector_phase"], row["mcap"], row["pe"], row["roce"], row["roe"],
                row["ret_1y"], row["pct_52w"], json.dumps(row["flags"]), row["gates_passed"],
                row["fit_bucket"], row["fit_score"], now_iso,
            ),
        )
        rows_written += 1

    conn.commit()
    return {"as_of": as_of, "rows_written": rows_written, "bucket_counts": bucket_counts}


def export_csv(conn: sqlite3.Connection, as_of: str | None = None, path: Path | None = None) -> Path:
    """Export the as_of company_fit snapshot to data/exports/company_fit_<date>.csv,
    sorted by mcap desc (NULLs last). Creates the exports directory if needed."""
    as_of = as_of or dt.date.today().isoformat()
    out_path = path or (EXPORTS_DIR / f"company_fit_{as_of}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = conn.execute(
        """
        SELECT instrument_id, symbol, as_of_date, sector, kpi_sector, sector_phase,
               mcap, pe, roce, roe, ret_1y, pct_52w, flags, gates_passed,
               fit_bucket, fit_score
          FROM company_fit
         WHERE as_of_date = ?
         ORDER BY (mcap IS NULL) ASC, mcap DESC
        """,
        (as_of,),
    ).fetchall()

    fieldnames = [
        "instrument_id", "symbol", "as_of_date", "sector", "kpi_sector", "sector_phase",
        "mcap", "pe", "roce", "roe", "ret_1y", "pct_52w", "flags", "gates_passed",
        "fit_bucket", "fit_score",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    return out_path


def _print_summary(summary: dict) -> None:
    print(f"company_fit refresh — as_of={summary['as_of']}  rows_written={summary['rows_written']}")
    for bucket, count in sorted(summary["bucket_counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {bucket:<22}{count:>5}")


def main() -> None:
    from afund.db.connection import get_conn

    conn = get_conn()
    try:
        summary = refresh_company_fit(conn)
        _print_summary(summary)
        csv_path = export_csv(conn, as_of=summary["as_of"])
        print(f"CSV exported: {csv_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
