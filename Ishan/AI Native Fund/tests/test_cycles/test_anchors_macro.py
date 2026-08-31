"""Tests for the Phase 8 macro_series-backed anchors (rate_liquidity,
credit, currency, inflation w/ staleness, flows w/ forward-accumulation
gate, india_vix, yield_gap) plus allocation-band selection and the
sentiment breadth+VIX blend — all against a synthetic temp DB, no network."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from afund.cycles import anchors, assess, composite
from afund.cycles.framework import load as load_framework

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

AS_OF = "2026-07-05"


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_anchor_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def fw():
    return load_framework()


def _seed_monthly(conn, series_code, start_year, n_months, value_fn, source="TEST", freq="M"):
    dates = []
    y, m = start_year, 1
    for i in range(n_months):
        dates.append(f"{y}-{m:02d}-01")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    for i, d in enumerate(dates):
        conn.execute(
            "INSERT INTO macro_series (series_code, source, date, value, unit, freq) "
            "VALUES (?, ?, ?, ?, NULL, ?)",
            (series_code, source, d, value_fn(i), freq),
        )
    conn.commit()
    return dates


# ---------------------------------------------------------------------------
# level anchors
# ---------------------------------------------------------------------------

def test_rate_liquidity_anchor_live(conn):
    # 48 monthly GSEC_10Y points ending 2026-06 (fresh vs AS_OF).
    _seed_monthly(conn, "GSEC_10Y", 2022, 54, lambda i: 6.0 + 0.02 * i)
    anchor = anchors.rate_liquidity_anchor(conn, as_of=AS_OF)
    assert not anchor.data_pending
    assert anchor.metric_name == "gsec_10y_yield"
    assert anchor.cycle_id == "interest_rate_liquidity_cycle"
    # rising series -> current is the max -> last history point
    assert anchor.current == anchor.history[-1][1]


def test_rate_liquidity_anchor_pending_when_empty(conn):
    anchor = anchors.rate_liquidity_anchor(conn, as_of=AS_OF)
    assert anchor.data_pending
    assert anchor.missing_kpis == ["gsec_10y"]


def test_credit_anchor_quarterly_staleness_window(conn):
    # Quarterly series ending 2025-10 (~9 months before AS_OF): NOT stale
    # for the 12-month quarterly threshold (BIS publishes in arrears).
    dates = [f"{y}-{m:02d}-01" for y in range(2021, 2026) for m in (1, 4, 7, 10)]
    for i, d in enumerate(dates):
        conn.execute(
            "INSERT INTO macro_series (series_code, source, date, value, freq) "
            "VALUES ('CREDIT_GDP_GAP', 'BIS', ?, ?, 'Q')",
            (d, -10.0 + i),
        )
    conn.commit()
    anchor = anchors.credit_anchor(conn, as_of=AS_OF)
    assert not anchor.data_pending
    assert anchor.cycle_id == "credit_debt_cycle"
    assert anchor.history[-1][0] == "2025-10-01"


def test_inflation_anchor_marks_stale_data_pending(conn):
    # CPI_YOY ending 2025-03 — 15+ months before AS_OF (the live FRED lag):
    # must be data_pending with a data_stale note, never silently classified.
    _seed_monthly(conn, "CPI_YOY", 2023, 27, lambda i: 4.0 + 0.1 * i)  # ends 2025-03
    anchor = anchors.inflation_anchor(conn, as_of=AS_OF)
    assert anchor.data_pending
    assert "data_stale" in anchor.note
    assert "MOSPI" in anchor.note  # names the fresh-CPI route
    assert anchor.missing_kpis == ["cpi_yoy"]
    assert anchor.current is None


def test_inflation_anchor_live_with_fresh_data_and_goldilocks_note(conn):
    _seed_monthly(conn, "CPI_YOY", 2022, 54, lambda i: 3.0 + 0.05 * i)  # ends 2026-06
    anchor = anchors.inflation_anchor(conn, as_of=AS_OF)
    assert not anchor.data_pending
    # 3.0 + 0.05*53 = 5.65 -> inside the RBI 2-6% band.
    assert anchor.current == pytest.approx(5.65)
    assert "goldilocks" in anchor.note
    assert "RBI target band" in anchor.note


def test_currency_anchor_live(conn):
    _seed_monthly(conn, "REER", 2022, 54, lambda i: 100.0 - 0.1 * i)
    anchor = anchors.currency_anchor(conn, as_of=AS_OF)
    assert not anchor.data_pending
    assert anchor.cycle_id == "currency_external_balance_cycle"


# ---------------------------------------------------------------------------
# flows: forward-accumulation gate
# ---------------------------------------------------------------------------

def test_flows_anchor_pending_until_enough_complete_months(conn):
    # 3 days of FII_NET (the real day-1 situation): honest data_pending.
    for d, v in [("2026-07-01", 100.0), ("2026-07-02", -50.0), ("2026-07-03", 20.0)]:
        conn.execute(
            "INSERT INTO macro_series (series_code, source, date, value, freq) "
            "VALUES ('FII_NET', 'NSE', ?, ?, 'D')",
            (d, v),
        )
    conn.commit()
    anchor = anchors.flows_anchor(conn, as_of=AS_OF)
    assert anchor.data_pending
    assert "forward-accumulating" in anchor.note
    assert anchor.missing_kpis == ["fii_dii_flows"]


def test_flows_anchor_live_with_enough_months_and_excludes_partial_month(conn):
    # 30 complete months of two dailies each + a partial as_of month.
    y, m = 2024, 1
    for _ in range(30):
        conn.execute(
            "INSERT INTO macro_series (series_code, source, date, value, freq) "
            "VALUES ('FII_NET', 'NSE', ?, 100.0, 'D')",
            (f"{y}-{m:02d}-10",),
        )
        conn.execute(
            "INSERT INTO macro_series (series_code, source, date, value, freq) "
            "VALUES ('FII_NET', 'NSE', ?, 50.0, 'D')",
            (f"{y}-{m:02d}-20",),
        )
        m += 1
        if m > 12:
            m, y = 1, y + 1
    # partial as_of month (2026-07): must be EXCLUDED from the series
    conn.execute(
        "INSERT INTO macro_series (series_code, source, date, value, freq) "
        "VALUES ('FII_NET', 'NSE', '2026-07-01', 99999.0, 'D')"
    )
    conn.commit()

    anchor = anchors.flows_anchor(conn, as_of=AS_OF)
    assert not anchor.data_pending
    assert len(anchor.history) == 30
    assert all(v == pytest.approx(150.0) for _, v in anchor.history)  # monthly sums
    assert anchor.history[-1][0] == "2026-06-01"  # partial July excluded


# ---------------------------------------------------------------------------
# yield gap
# ---------------------------------------------------------------------------

def test_yield_gap_anchor_formula_and_join(conn):
    # 24 months of GSEC_10Y at a constant 7.0%, and daily-ish PE prints.
    gsec_dates = _seed_monthly(conn, "GSEC_10Y", 2024, 30, lambda i: 7.0)  # ends 2026-06
    for i, d in enumerate(gsec_dates):
        # one PE print per month, mid-month
        pe_date = d[:8] + "15"
        conn.execute(
            "INSERT INTO index_data (index_name, date, close, pe) VALUES ('NIFTY 50', ?, ?, ?)",
            (pe_date, 20000.0, 20.0 + 0.1 * i),
        )
    conn.commit()

    anchor = anchors.yield_gap_anchor(conn, "NIFTY 50", as_of=AS_OF)
    assert not anchor.data_pending
    # current = (7.0/100) x latest PE (20.0 + 0.1*29 = 22.9) = 1.603
    assert anchor.current == pytest.approx(0.07 * 22.9)
    # every joined history point = 0.07 x that month's PE
    assert anchor.history[0][1] == pytest.approx(0.07 * 20.0)
    assert len(anchor.history) >= 10


def test_yield_gap_anchor_pending_without_gsec(conn):
    conn.execute(
        "INSERT INTO index_data (index_name, date, close, pe) VALUES ('NIFTY 50', '2026-07-03', 24000, 21.0)"
    )
    conn.commit()
    anchor = anchors.yield_gap_anchor(conn, "NIFTY 50", as_of=AS_OF)
    assert anchor.data_pending
    assert anchor.missing_kpis == ["yield_gap"]


# ---------------------------------------------------------------------------
# allocation band selection
# ---------------------------------------------------------------------------

def test_select_allocation_band_extremes_and_middle(fw):
    deep, basis = composite.select_allocation_band(fw, 1.30)
    assert deep.regime_label == "Deep Value / Capitulation"
    assert "1.3" in basis

    euph, _ = composite.select_allocation_band(fw, 1.80)
    assert euph.regime_label == "Distribution / Euphoria"

    value_band, _ = composite.select_allocation_band(fw, 1.50, valuation_phase_id="value")
    assert value_band.regime_label == "Value / Early Recovery"

    momentum_band, _ = composite.select_allocation_band(fw, 1.50, valuation_phase_id="momentum")
    assert momentum_band.regime_label == "Momentum / Fair Value"

    # middle zone with an expensive-side phase or no phase -> Neutral
    # default (the extreme bands trigger only on yield_gap thresholds).
    neutral, _ = composite.select_allocation_band(fw, 1.69, valuation_phase_id="euphoria")
    assert neutral.regime_label == "Momentum / Fair Value"
    neutral2, _ = composite.select_allocation_band(fw, 1.50, valuation_phase_id=None)
    assert neutral2.regime_label == "Momentum / Fair Value"


# ---------------------------------------------------------------------------
# sentiment blend (VIX-only path — breadth needs 200d of daily_prices)
# ---------------------------------------------------------------------------

def test_sentiment_vix_only_path_classifies_inverted(conn, fw):
    # INDIA_VIX daily-ish history (2 prints/month for 3 years), falling —
    # falling fear = rising sentiment once inverted.
    y, m = 2023, 7
    i = 0
    while (y, m) <= (2026, 6):
        for day in (10, 20):
            conn.execute(
                "INSERT INTO macro_series (series_code, source, date, value, freq) "
                "VALUES ('INDIA_VIX', 'NSE', ?, ?, 'D')",
                (f"{y}-{m:02d}-{day:02d}", 30.0 - 0.2 * i),
            )
            i += 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    conn.commit()

    row = assess._assess_sentiment(conn, fw, "market", AS_OF)
    assert row["data_pending"] == 0
    assert json.loads(row["contributing_kpis"]) == ["india_vix"]
    assert "inverted" in row["note"]
    # VIX at its 10y low -> inverted percentile at/near 100 -> late-wheel
    # sentiment phase, and direction must read "rising" (negated series).
    assert row["percentile"] > 90
    assert row["direction"] == "rising"


def test_sentiment_pending_when_both_legs_missing(conn, fw):
    row = assess._assess_sentiment(conn, fw, "market", AS_OF)
    assert row["data_pending"] == 1
    missing = json.loads(row["missing_kpis_json"])
    assert "india_vix" in missing


# ---------------------------------------------------------------------------
# data_pending_anchor honesty after the Phase 8 status flips
# ---------------------------------------------------------------------------

def test_data_pending_anchor_discloses_available_but_unwired():
    # volatility_risk_regime_cycle anchors on india_vix, whose data IS
    # available since Phase 8 — claiming it "missing" would be false.
    anchor = anchors.data_pending_anchor("volatility_risk_regime_cycle", "market", as_of=AS_OF)
    assert anchor.data_pending
    assert "india_vix" not in anchor.missing_kpis
    assert "india_vix" in anchor.note
    assert "not wired" in anchor.note


def test_data_pending_anchor_still_lists_truly_missing():
    # gdp_business_cycle's catalog anchor_kpi_ids grew gst_collections/
    # ici_index (WORKSTREAM D, both now source_status: available) but
    # mcap_gdp — the catalog's primary value_type anchor — remains
    # genuinely unsourced, so it alone must still show up in missing_kpis.
    anchor = anchors.data_pending_anchor("gdp_business_cycle", "market", as_of=AS_OF)
    assert anchor.data_pending
    assert anchor.missing_kpis == ["mcap_gdp"]


def test_data_pending_anchor_gdp_business_discloses_workstream_d_series():
    anchor = anchors.data_pending_anchor("gdp_business_cycle", "market", as_of=AS_OF)
    assert "gst_collections" in anchor.note
    assert "ici_index" in anchor.note
    assert "not wired" in anchor.note


# ---------------------------------------------------------------------------
# gdp_business_anchor (WORKSTREAM D): GST_COLLECTIONS + ICI_INDEX YoY
# blended supplementary activity anchor. NOT part of LIVE_CYCLE_IDS /
# CATALOG_CYCLE_MAP — see anchors.py module docstring and
# gdp_business_anchor's own docstring for why the cycle as a whole still
# routes through data_pending_anchor() in assess.py.
# ---------------------------------------------------------------------------

def test_gdp_business_anchor_pending_when_empty(conn):
    anchor = anchors.gdp_business_anchor(conn, as_of=AS_OF)
    assert anchor.data_pending
    assert anchor.cycle_id == "gdp_business_cycle"
    assert set(anchor.missing_kpis) == {"gst_collections", "ici_index"}


def test_gdp_business_anchor_live_blends_both_series(conn):
    # 30 monthly GST_COLLECTIONS + ICI_INDEX level points ending 2026-06
    # (fresh vs AS_OF=2026-07-05) — enough for >=1 YoY point (needs 13+
    # months) with room to spare.
    _seed_monthly(conn, "GST_COLLECTIONS", 2024, 30, lambda i: 150000.0 + 500.0 * i)
    _seed_monthly(conn, "ICI_INDEX", 2024, 30, lambda i: 150.0 + 0.5 * i)
    anchor = anchors.gdp_business_anchor(conn, as_of=AS_OF)
    assert not anchor.data_pending
    assert anchor.cycle_id == "gdp_business_cycle"
    assert anchor.metric_name == "activity_yoy"
    assert anchor.current is not None
    # Both series grow monotonically -> YoY should be a small positive
    # number for both legs, so the blended current should be positive too.
    assert anchor.current > 0
    assert "GST_COLLECTIONS" in anchor.note
    assert "ICI_INDEX" in anchor.note


def test_gdp_business_anchor_uses_whichever_series_has_data(conn):
    # Only ICI_INDEX seeded — GST_COLLECTIONS entirely absent. Must not
    # fabricate a GST leg; blended reading falls back to ICI_INDEX alone.
    _seed_monthly(conn, "ICI_INDEX", 2024, 30, lambda i: 150.0 + 0.5 * i)
    anchor = anchors.gdp_business_anchor(conn, as_of=AS_OF)
    assert not anchor.data_pending
    assert anchor.current is not None


def test_gdp_business_anchor_stale_when_latest_point_too_old(conn):
    # Series ends 2025-12 — 7+ months before AS_OF=2026-07-05, past the
    # 4-month staleness threshold for a monthly-in-arrears series.
    _seed_monthly(conn, "GST_COLLECTIONS", 2023, 24, lambda i: 150000.0 + 500.0 * i)
    _seed_monthly(conn, "ICI_INDEX", 2023, 24, lambda i: 150.0 + 0.5 * i)
    anchor = anchors.gdp_business_anchor(conn, as_of=AS_OF)
    assert anchor.data_pending
    assert "data_stale" in anchor.note
