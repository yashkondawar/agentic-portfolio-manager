"""Per-cycle anchor-metric series for the cycle engine's live cycles.

Ten cycles have genuinely live, non-fabricated data sources today (see
docs/SYSTEM_MAP.md data-availability table and knowledge/data/kpis/*.yaml
source_status fields). Five were live from Phase 7 day-1:

    valuation            index P/E percentile — market scope (NIFTY 50 /
                         NIFTY 500) and sector scope (via
                         config.settings.sector_index_map), per source doc
                         section 2.7's fractal application (the SAME cycle
                         computed at different scopes, not the separate
                         sector_thematic_cycle catalog entry, whose micro
                         KPI anchors like bfsi_price_to_book are not sourced
                         yet).
    earnings             index EPS = close / pe (monthly, YoY growth)
    sentiment_breadth    % of instruments above their 200-day moving
                         average (vectorized over daily_prices)
    commodity            gold_to_nifty = GOLDBEES/NIFTY 50,
                         gsr = GOLDBEES/SILVERBEES
    global_risk_dollar   DXY (ICE US Dollar Index) via yfinance ticker
                         "DX-Y.NYB", fetched live (not stored permanently
                         in daily_prices/index_data — this is the one
                         exception where anchors.py reaches out to a live
                         source directly, since DXY isn't in any pipeline
                         yet; see knowledge/data/kpis/dxy.yaml source_status:
                         missing at the KPI-pipeline level, but usable here
                         as a direct fetch for the cycle engine specifically)

Five more went live in Phase 8, backed by macro_series rows written by the
Phase 8 pipelines (afund.data.macro_fred / macro_bis / india_vix / fii_dii):

    rate_liquidity       GSEC_10Y level percentile (FRED INDIRLTLT01STM,
                         monthly) — the catalog's own anchors (curve_slope,
                         dxy) are not both sourced (1Y G-Sec confirmed
                         unavailable on FRED), so the 10Y level series is
                         the honest Phase 8 anchor
    credit               CREDIT_GDP_GAP (BIS credit-to-GDP gap, quarterly)
    currency             REER (India real effective exchange rate, monthly)
    inflation            CPI_YOY (FRED-derived, monthly) — goldilocks_type
                         per cpi_yoy.yaml; NOTE the FRED CPI series lags
                         ~12-15 months, so this anchor enforces a staleness
                         cutoff and reads data_pending (data_stale) until a
                         fresh CPI lands via the MOSPI manual route
                         (afund.data.macro_manual)
    flows                FII_NET monthly net-flow sums (NSE provisional
                         daily flows, forward-accumulating from 2026-07;
                         data_pending until >= 24 complete months exist)

sentiment_breadth additionally blends INDIA_VIX (fear_type, inverted per
knowledge/references/kpi_interpretation/sentiment_cycle.md) alongside
breadth — see india_vix_anchor + assess.py's sentiment special-case.
yield_gap_anchor() provides the valuation cycle's Yield Gap series
((10Y G-Sec yield / 100) x index P/E per knowledge/data/kpis/
yield_gap.yaml, consistent with the 1.40/1.70 allocation-band thresholds)
for assess.py's allocation-band selection + the EVI gsec_yield_x_pe
component.

Every other cycle in the 16-cycle catalog returns a `data_pending` reading
with the list of missing kpi_ids from knowledge.loader — never fabricated.

WORKSTREAM D note: gdp_business_cycle gained a genuine, computable
supplementary anchor (gdp_business_anchor(), blending GST_COLLECTIONS and
ICI_INDEX YoY from afund.data.macro_govt) but is deliberately NOT added
to LIVE_CYCLE_IDS/CATALOG_CYCLE_MAP — its catalog anchor_kpi_ids still
lists mcap_gdp first (source_status: missing), so the cycle as a whole
stays on the data_pending_anchor() path in the real assess.py pipeline
until mcap_gdp itself is sourced or a deliberate decision is made to
promote gdp_business to a fully live cycle (which would also need a new
assess.py assess_live_cycle() branch). data_pending_anchor()'s
available_unwired disclosure now correctly names gst_collections/
ici_index rather than reporting them as missing.

All functions here return raw (non-percentile) series/values; classify.py
does the percentile-rank + direction/momentum reduction. anchors.py's job
is ONLY "what is the honest raw number right now, and what's its history,"
never phase classification itself.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass, field

from afund.config import load_settings
from afund.derive.returns import _price_series

try:
    from knowledge.loader import load as load_knowledge
except ImportError:  # pragma: no cover - path setup fallback
    load_knowledge = None  # type: ignore

# Cycles with genuinely live data sources today. "Live" means the anchor
# has a real data source wired — a live cycle can still return an honest
# data_pending reading (e.g. flows until enough history accumulates, or
# inflation while the CPI series is stale).
LIVE_CYCLE_IDS = {
    "valuation",
    "earnings",
    "sentiment_breadth",
    "commodity",
    "global_risk_dollar",
    # Phase 8 additions (macro_series-backed):
    "rate_liquidity",
    "credit",
    "currency",
    "inflation",
    "flows",
}

# Map our internal "live cycle" names to the 16-cycle catalog's cycle_id +
# the kpi_ids they conceptually anchor on (used for missing_kpis reporting
# and for narrative packet tag-matching). valuation/earnings/sentiment_
# breadth/commodity/global_risk_dollar are engine-internal names distinct
# from catalog cycle_ids because valuation/earnings are fractal (same
# cycle, many scopes) while the catalog models them as single cycles.
CATALOG_CYCLE_MAP = {
    "valuation": "valuation_cycle",
    "earnings": "earnings_margin_cycle",
    "sentiment_breadth": "sentiment_behavioral_cycle",
    "commodity": "commodity_cycle",
    "global_risk_dollar": "global_risk_appetite_dollar_cycle",
    # Phase 8 additions:
    "rate_liquidity": "interest_rate_liquidity_cycle",
    "credit": "credit_debt_cycle",
    "currency": "currency_external_balance_cycle",
    "inflation": "inflation_cycle",
    "flows": "fii_dii_capital_flows_cycle",
}

# All 16 catalog cycle_ids this engine knows about (mirrors
# knowledge/data/cycles/catalog.yaml). Kept as a local constant so
# data_pending reporting doesn't require a knowledge/ load in hot paths
# (assess.py loads knowledge once and passes it down where needed).
ALL_CATALOG_CYCLE_IDS = [
    "valuation_cycle",
    "earnings_margin_cycle",
    "gdp_business_cycle",
    "inflation_cycle",
    "interest_rate_liquidity_cycle",
    "credit_debt_cycle",
    "currency_external_balance_cycle",
    "fii_dii_capital_flows_cycle",
    "sentiment_behavioral_cycle",
    "sector_thematic_cycle",
    "commodity_cycle",
    "real_estate_cycle",
    "capex_investment_cycle",
    "volatility_risk_regime_cycle",
    "global_risk_appetite_dollar_cycle",
    "policy_regulatory_cycle",
]


@dataclass
class AnchorSeries:
    """A single anchor metric's current value + full historical series,
    ready for classify.percentile_rank() + direction RoC computation.

    `data_pending` is True when the metric could not be computed from
    genuinely available data; in that case `current` and `history` are
    empty/None and `missing_kpis` names what's missing."""
    cycle_id: str          # engine-internal live-cycle name or catalog cycle_id
    scope: str              # e.g. "NIFTY 50", "bfsi", "market"
    metric_name: str
    as_of_date: str
    current: float | None
    history: list[tuple[str, float]] = field(default_factory=list)  # [(date, value)]
    data_pending: bool = False
    missing_kpis: list[str] = field(default_factory=list)
    note: str = ""


def _index_pe_series(conn: sqlite3.Connection, index_name: str) -> list[tuple[str, float]]:
    rows = conn.execute(
        """
        SELECT date, pe FROM index_data
         WHERE index_name = ? AND pe IS NOT NULL
         ORDER BY date ASC
        """,
        (index_name,),
    ).fetchall()
    return [(r["date"], r["pe"]) for r in rows]


def index_pb_percentile(
    conn: sqlite3.Connection, scope: str, as_of: str | None = None, lookback_years: int = 10
) -> float | None:
    """Latest index P/B percentile-ranked over its own lookback window, for
    the EVI's index_pb component (evi.yaml). Scope resolution mirrors
    valuation_anchor: literal index_name or registry sector slug via
    sector_index_map. Returns None when the pb series is absent/too thin —
    partial EVI discloses it via components_missing, never fabricates."""
    as_of = as_of or dt.date.today().isoformat()
    settings = load_settings()
    index_name = settings.get("sector_index_map", {}).get(scope, scope)
    rows = conn.execute(
        """
        SELECT date, pb FROM index_data
         WHERE index_name = ? AND pb IS NOT NULL AND date <= ?
         ORDER BY date ASC
        """,
        (index_name, as_of),
    ).fetchall()
    series = [(r["date"], r["pb"]) for r in rows]
    if not series:
        return None
    cutoff = (dt.date.fromisoformat(as_of) - dt.timedelta(days=round(lookback_years * 365.25))).isoformat()
    window = [v for d, v in series if d >= cutoff]
    if len(window) < 10:
        return None
    from afund.cycles import classify

    return classify.percentile_rank(series[-1][1], window)


def valuation_anchor(conn: sqlite3.Connection, scope: str, as_of: str | None = None) -> AnchorSeries:
    """Valuation cycle, fractal application (source doc section 2.7): same
    cycle, scoped either to the whole market (index_name literal, e.g.
    "NIFTY 50") or to a sector (via config.settings.sector_index_map,
    keyed by the registry sector slug, e.g. "bfsi" -> "NIFTY BANK").

    `scope` is either a literal index_name (market scope, e.g. "NIFTY 50",
    "NIFTY 500") or a registry sector slug present in sector_index_map
    (e.g. "bfsi", "it_technology", ...).
    """
    as_of = as_of or dt.date.today().isoformat()
    settings = load_settings()
    sector_index_map = settings.get("sector_index_map", {})

    index_name = sector_index_map.get(scope, scope)  # sector slug -> index name, else literal
    series = _index_pe_series(conn, index_name)
    series = [(d, v) for d, v in series if d <= as_of]

    if not series:
        return AnchorSeries(
            cycle_id="valuation_cycle",
            scope=scope,
            metric_name="index_pe",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["yield_gap", "evi"],
            note=f"no index_data.pe rows for index_name={index_name!r} as of {as_of}",
        )

    current = series[-1][1]
    return AnchorSeries(
        cycle_id="valuation_cycle",
        scope=scope,
        metric_name="index_pe",
        as_of_date=as_of,
        current=current,
        history=series,
        data_pending=False,
        note=f"index={index_name}",
    )


def earnings_anchor(conn: sqlite3.Connection, scope: str, as_of: str | None = None) -> AnchorSeries:
    """Earnings cycle: index EPS = close / pe (monthly cadence via the
    underlying daily series' own frequency; YoY growth is computed
    downstream by classify.roc_pct over a ~12m window on this raw EPS
    series). `scope` is an index_name or sector slug, same convention as
    valuation_anchor."""
    as_of = as_of or dt.date.today().isoformat()
    settings = load_settings()
    sector_index_map = settings.get("sector_index_map", {})
    index_name = sector_index_map.get(scope, scope)

    rows = conn.execute(
        """
        SELECT date, close, pe FROM index_data
         WHERE index_name = ? AND close IS NOT NULL AND pe IS NOT NULL AND pe > 0 AND date <= ?
         ORDER BY date ASC
        """,
        (index_name, as_of),
    ).fetchall()

    if not rows:
        return AnchorSeries(
            cycle_id="earnings_margin_cycle",
            scope=scope,
            metric_name="index_eps",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["index_eps_growth"],
            note=f"no index_data close+pe rows for index_name={index_name!r} as of {as_of}",
        )

    eps_series = [(r["date"], r["close"] / r["pe"]) for r in rows]
    current = eps_series[-1][1]
    return AnchorSeries(
        cycle_id="earnings_margin_cycle",
        scope=scope,
        metric_name="index_eps",
        as_of_date=as_of,
        current=current,
        history=eps_series,
        data_pending=False,
        note=f"index={index_name}, eps=close/pe",
    )


def sentiment_breadth_anchor(conn: sqlite3.Connection, scope: str = "market", as_of: str | None = None,
                              window_days: int = 200) -> AnchorSeries:
    """% of instruments trading above their own trailing `window_days`
    moving average, vectorized over daily_prices for performance (one SQL
    pull + pandas groupby, not one query per instrument).

    Historical series: recomputed at each date where at least
    `window_days` of trailing history exist for a reasonable subset of
    instruments — this is intentionally a lighter-weight approximation
    (breadth is computed on the LATEST date's full universe, and history is
    built by re-running the same computation on trailing month-end dates)
    rather than a true point-in-time-correct daily breadth series, to keep
    this cheap; documented here as a DRAFT simplification, not a bug."""
    as_of = as_of or dt.date.today().isoformat()

    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        return AnchorSeries(
            cycle_id="sentiment_behavioral_cycle",
            scope=scope,
            metric_name="pct_above_200dma",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["breadth_200dma"],
            note="pandas not available",
        )

    df = pd.read_sql_query(
        """
        SELECT instrument_id, date, close FROM daily_prices
         WHERE close IS NOT NULL AND date <= ?
         ORDER BY instrument_id, date
        """,
        conn,
        params=(as_of,),
    )
    if df.empty:
        return AnchorSeries(
            cycle_id="sentiment_behavioral_cycle",
            scope=scope,
            metric_name="pct_above_200dma",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["breadth_200dma"],
            note="no daily_prices rows",
        )

    df["date"] = pd.to_datetime(df["date"])

    def _pct_above_dma(frame: "pd.DataFrame") -> float | None:
        latest_date = frame["date"].max()
        latest = frame[frame["date"] == latest_date]
        above = 0
        total = 0
        for inst_id, grp in frame.groupby("instrument_id"):
            grp = grp.sort_values("date")
            if len(grp) < window_days:
                continue
            dma = grp["close"].tail(window_days).mean()
            last_close = grp.iloc[-1]["close"]
            total += 1
            if last_close > dma:
                above += 1
        if total == 0:
            return None
        return 100.0 * above / total

    current = _pct_above_dma(df)
    if current is None:
        return AnchorSeries(
            cycle_id="sentiment_behavioral_cycle",
            scope=scope,
            metric_name="pct_above_200dma",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["breadth_200dma"],
            note=f"no instrument has >= {window_days} trading days of history",
        )

    # Lightweight monthly-cadence history: recompute breadth at each
    # month-end over the available span (bounded to the last ~3 years to
    # keep this fast) so classify.py has a percentile/direction series.
    all_dates = sorted(df["date"].unique())
    month_ends: list = []
    seen_months = set()
    for d in reversed(all_dates):
        key = (d.year, d.month)
        if key not in seen_months:
            seen_months.add(key)
            month_ends.append(d)
        if len(month_ends) >= 36:
            break
    month_ends.reverse()

    history: list[tuple[str, float]] = []
    for d in month_ends:
        sub = df[df["date"] <= d]
        val = _pct_above_dma(sub)
        if val is not None:
            history.append((d.strftime("%Y-%m-%d"), val))

    return AnchorSeries(
        cycle_id="sentiment_behavioral_cycle",
        scope=scope,
        metric_name="pct_above_200dma",
        as_of_date=as_of,
        current=current,
        history=history,
        data_pending=False,
        note=f"window_days={window_days}, universe breadth (all instruments with sufficient history)",
    )


def _etf_close_series(conn: sqlite3.Connection, symbol: str, as_of: str) -> list[tuple[str, float]]:
    inst = conn.execute(
        "SELECT id FROM instruments WHERE symbol = ? AND instrument_type = 'ETF'",
        (symbol,),
    ).fetchone()
    if inst is None:
        return []
    return [(d, v) for d, v in _price_series(conn, instrument_id=inst["id"]) if d <= as_of]


def commodity_anchor(conn: sqlite3.Connection, scope: str = "market", as_of: str | None = None) -> AnchorSeries:
    """Commodity cycle: two ratio anchors —
      gold_to_nifty = GOLDBEES close / NIFTY 50 close
      gsr           = GOLDBEES close / SILVERBEES close  (Gold-Silver Ratio)

    Returns gold_to_nifty as the primary `current`/`history` series (the
    doc's own value_type anchor for this cycle); gsr is exposed via `note`
    plus a second AnchorSeries is available through commodity_gsr_anchor()
    for callers wanting both independently."""
    as_of = as_of or dt.date.today().isoformat()

    gold_series = _etf_close_series(conn, "GOLDBEES", as_of)
    nifty_rows = conn.execute(
        "SELECT date, close FROM index_data WHERE index_name = 'NIFTY 50' AND close IS NOT NULL AND date <= ? ORDER BY date ASC",
        (as_of,),
    ).fetchall()
    nifty_series = {r["date"]: r["close"] for r in nifty_rows}

    if not gold_series or not nifty_series:
        return AnchorSeries(
            cycle_id="commodity_cycle",
            scope=scope,
            metric_name="gold_to_nifty",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["gold_to_nifty", "gsr"],
            note="missing GOLDBEES prices or NIFTY 50 index_data",
        )

    ratio_series = [(d, v / nifty_series[d]) for d, v in gold_series if d in nifty_series and nifty_series[d]]
    if not ratio_series:
        return AnchorSeries(
            cycle_id="commodity_cycle",
            scope=scope,
            metric_name="gold_to_nifty",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["gold_to_nifty", "gsr"],
            note="no overlapping dates between GOLDBEES and NIFTY 50",
        )

    return AnchorSeries(
        cycle_id="commodity_cycle",
        scope=scope,
        metric_name="gold_to_nifty",
        as_of_date=as_of,
        current=ratio_series[-1][1],
        history=ratio_series,
        data_pending=False,
        note="gold_to_nifty = GOLDBEES/NIFTY 50",
    )


def commodity_gsr_anchor(conn: sqlite3.Connection, scope: str = "market", as_of: str | None = None) -> AnchorSeries:
    """Gold-Silver Ratio: GOLDBEES/SILVERBEES, the commodity cycle's
    secondary anchor (source doc section 3 catalog: `gsr`)."""
    as_of = as_of or dt.date.today().isoformat()
    gold_series = dict(_etf_close_series(conn, "GOLDBEES", as_of))
    silver_series = dict(_etf_close_series(conn, "SILVERBEES", as_of))

    if not gold_series or not silver_series:
        return AnchorSeries(
            cycle_id="commodity_cycle",
            scope=scope,
            metric_name="gsr",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["gsr"],
            note="missing GOLDBEES or SILVERBEES prices",
        )

    common_dates = sorted(set(gold_series) & set(silver_series))
    ratio_series = [(d, gold_series[d] / silver_series[d]) for d in common_dates if silver_series[d]]
    if not ratio_series:
        return AnchorSeries(
            cycle_id="commodity_cycle",
            scope=scope,
            metric_name="gsr",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["gsr"],
            note="no overlapping dates between GOLDBEES and SILVERBEES",
        )

    return AnchorSeries(
        cycle_id="commodity_cycle",
        scope=scope,
        metric_name="gsr",
        as_of_date=as_of,
        current=ratio_series[-1][1],
        history=ratio_series,
        data_pending=False,
        note="gsr = GOLDBEES/SILVERBEES",
    )


_DXY_TICKER = "DX-Y.NYB"


def global_risk_dollar_anchor(scope: str = "market", as_of: str | None = None,
                               years: int = 10) -> AnchorSeries:
    """Global Risk Appetite / Dollar cycle: DXY (ICE US Dollar Index) via a
    direct, live yfinance fetch (ticker DX-Y.NYB). This is the one anchor
    that reaches an external source directly rather than reading from
    afund's own DB tables — DXY isn't in any pipeline/table yet
    (knowledge/data/kpis/dxy.yaml source_status: missing at the
    pipeline level), but the raw series is cheap and safe to pull live for
    this read-only cycle-engine purpose. Nothing is written back to the DB
    from here (no fabrication, no silent persistence of an unvetted
    source) — assess.py decides whether/how to record the resulting
    reading."""
    as_of = as_of or dt.date.today().isoformat()

    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover
        return AnchorSeries(
            cycle_id="global_risk_appetite_dollar_cycle",
            scope=scope,
            metric_name="dxy",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["dxy"],
            note="yfinance not available",
        )

    try:
        ticker = yf.Ticker(_DXY_TICKER)
        hist = ticker.history(period=f"{years}y")
    except Exception as exc:  # pragma: no cover - network dependent
        return AnchorSeries(
            cycle_id="global_risk_appetite_dollar_cycle",
            scope=scope,
            metric_name="dxy",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["dxy"],
            note=f"yfinance fetch failed: {exc}",
        )

    if hist is None or hist.empty:
        return AnchorSeries(
            cycle_id="global_risk_appetite_dollar_cycle",
            scope=scope,
            metric_name="dxy",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["dxy"],
            note=f"empty history from yfinance ticker {_DXY_TICKER}",
        )

    series = [(idx.strftime("%Y-%m-%d"), float(row["Close"])) for idx, row in hist.iterrows()
              if row["Close"] == row["Close"]]  # NaN guard
    series = [(d, v) for d, v in series if d <= as_of]
    if not series:
        return AnchorSeries(
            cycle_id="global_risk_appetite_dollar_cycle",
            scope=scope,
            metric_name="dxy",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["dxy"],
            note="no DXY rows on/before as_of",
        )

    return AnchorSeries(
        cycle_id="global_risk_appetite_dollar_cycle",
        scope=scope,
        metric_name="dxy",
        as_of_date=as_of,
        current=series[-1][1],
        history=series,
        data_pending=False,
        note=f"yfinance ticker={_DXY_TICKER}",
    )


# ---------------------------------------------------------------------------
# Phase 8: macro_series-backed anchors
# ---------------------------------------------------------------------------

def _macro_series_history(conn: sqlite3.Connection, series_code: str, as_of: str,
                           lookback_years: float | None = None) -> list[tuple[str, float]]:
    """[(date, value)] from macro_series for `series_code`, dates <= as_of,
    optionally limited to the trailing `lookback_years` window before as_of
    (percentiles are ranked within the cycle's own catalog lookback, per
    the Phase 8 plan — 'respect each cycle's catalog lookback')."""
    rows = conn.execute(
        """
        SELECT date, value FROM macro_series
         WHERE series_code = ? AND value IS NOT NULL AND date <= ?
         ORDER BY date ASC
        """,
        (series_code, as_of),
    ).fetchall()
    series = [(r["date"], r["value"]) for r in rows]
    if lookback_years is not None and series:
        cutoff = (dt.date.fromisoformat(as_of)
                  - dt.timedelta(days=round(lookback_years * 365.25))).isoformat()
        series = [(d, v) for d, v in series if d >= cutoff]
    return series


def _months_stale(latest_date: str, as_of: str) -> float:
    return (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(latest_date)).days / 30.4375


def _macro_level_anchor(
    conn: sqlite3.Connection,
    *,
    catalog_cycle_id: str,
    scope: str,
    as_of: str | None,
    series_code: str,
    metric_name: str,
    missing_kpi_id: str,
    lookback_years: float,
    max_stale_months: float,
    note: str = "",
    stale_note: str = "",
) -> AnchorSeries:
    """Shared plumbing for the 'single macro_series level series' anchors:
    pull the series within the cycle's lookback, refuse (data_pending, with
    a data_stale note) when the latest point is older than max_stale_months
    relative to as_of — stale macro data must never be silently classified
    as if it were current."""
    as_of = as_of or dt.date.today().isoformat()
    series = _macro_series_history(conn, series_code, as_of, lookback_years)

    if not series:
        return AnchorSeries(
            cycle_id=catalog_cycle_id,
            scope=scope,
            metric_name=metric_name,
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=[missing_kpi_id],
            note=f"no macro_series rows for {series_code} as of {as_of}",
        )

    stale_months = _months_stale(series[-1][0], as_of)
    if stale_months > max_stale_months:
        return AnchorSeries(
            cycle_id=catalog_cycle_id,
            scope=scope,
            metric_name=metric_name,
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=[missing_kpi_id],
            note=(
                f"data_stale: latest {series_code} point ({series[-1][0]}) is "
                f"{stale_months:.1f} months old (> {max_stale_months:g}-month threshold)"
                + (f"; {stale_note}" if stale_note else "")
            ),
        )

    return AnchorSeries(
        cycle_id=catalog_cycle_id,
        scope=scope,
        metric_name=metric_name,
        as_of_date=as_of,
        current=series[-1][1],
        history=series,
        data_pending=False,
        note=note or f"{series_code} level, {lookback_years:g}y lookback",
    )


def rate_liquidity_anchor(conn: sqlite3.Connection, scope: str = "market",
                           as_of: str | None = None) -> AnchorSeries:
    """Interest-rate/liquidity cycle: 10Y India G-Sec yield LEVEL percentile
    (macro_series GSEC_10Y, FRED INDIRLTLT01STM via afund.data.macro_fred,
    monthly). The catalog's own anchor KPIs (curve_slope, dxy) are not both
    sourced — the 1Y G-Sec needed for curve_slope was confirmed unavailable
    on FRED (INDIRLTST01STM 404s; see config/sources.yaml) — so the 10Y
    level is the honest Phase 8 anchor. Lookback 15y = the lower bound of
    the catalog's '15-20' range (only ~14.5y of GSEC_10Y exists anyway)."""
    return _macro_level_anchor(
        conn,
        catalog_cycle_id="interest_rate_liquidity_cycle",
        scope=scope,
        as_of=as_of,
        series_code="GSEC_10Y",
        metric_name="gsec_10y_yield",
        missing_kpi_id="gsec_10y",
        lookback_years=15,
        max_stale_months=6,  # monthly series; FRED publishes ~1-2 months in arrears
        note="GSEC_10Y level (FRED INDIRLTLT01STM, monthly); catalog anchors "
             "curve_slope/dxy not both sourced — level percentile is the Phase 8 anchor",
    )


def credit_anchor(conn: sqlite3.Connection, scope: str = "market",
                   as_of: str | None = None) -> AnchorSeries:
    """Credit/debt cycle: BIS credit-to-GDP gap (macro_series
    CREDIT_GDP_GAP via afund.data.macro_bis, quarterly). Lookback 20y per
    the catalog's short-cycle guidance ('15-20 (short cycle)'); the BIS
    supercycle framing (50-75y) is background context only. Staleness
    threshold 12 months: BIS publishes ~2 quarters in arrears, so a
    9-month-old latest quarter is normal, not stale."""
    return _macro_level_anchor(
        conn,
        catalog_cycle_id="credit_debt_cycle",
        scope=scope,
        as_of=as_of,
        series_code="CREDIT_GDP_GAP",
        metric_name="credit_gdp_gap",
        missing_kpi_id="credit_to_gdp_gap",
        lookback_years=20,
        max_stale_months=12,
        note="BIS credit-to-GDP gap (actual minus HP trend, pct pts), 20y lookback; "
             ">+10 pct pts is the BIS early-warning threshold",
    )


def currency_anchor(conn: sqlite3.Connection, scope: str = "market",
                     as_of: str | None = None) -> AnchorSeries:
    """Currency/external-balance cycle: India REER (macro_series REER,
    FRED RBINBIS via afund.data.macro_fred, monthly). Lookback 10y per
    reer.yaml (catalog range '10-15')."""
    return _macro_level_anchor(
        conn,
        catalog_cycle_id="currency_external_balance_cycle",
        scope=scope,
        as_of=as_of,
        series_code="REER",
        metric_name="reer",
        missing_kpi_id="reer",
        lookback_years=10,
        max_stale_months=6,
        note="India REER (FRED RBINBIS, monthly), 10y lookback",
    )


# RBI inflation target band (cpi_yoy.yaml: 'scored against the RBI's
# inflation target band (4% +/- 2pp)').
RBI_CPI_TARGET_MID = 4.0
RBI_CPI_TARGET_HALF_WIDTH = 2.0


def inflation_anchor(conn: sqlite3.Connection, scope: str = "market",
                      as_of: str | None = None) -> AnchorSeries:
    """Inflation cycle: CPI YoY (macro_series CPI_YOY, derived from FRED
    INDCPIALLMINMEI by afund.data.macro_fred, monthly). Lookback 12y per
    cpi_yoy.yaml.

    STALENESS (live Phase 8 finding): the FRED India CPI series lags
    ~12-15 months (latest 2025-03 as of 2026-07), so this anchor reads
    data_pending (data_stale) rather than silently classifying on stale
    inflation data. The fresh-CPI route is the MOSPI manual import
    (afund.data.macro_manual, series_code CPI_YOY) — once a fresh point
    lands, this anchor goes live automatically.

    Goldilocks orientation (cpi_yoy.yaml orientation: goldilocks_type):
    the raw CPI_YOY level series is what gets percentile-ranked — for the
    inflation cycle's own wheel this is semantically right (high CPI
    percentile + rising = inflation peaking -> Overheating cluster; low
    percentile = disinflation trough) — and the anchor's note discloses
    the current reading's position vs the RBI 4% +/- 2pp target band so
    downstream consumers see the goldilocks context explicitly."""
    anchor = _macro_level_anchor(
        conn,
        catalog_cycle_id="inflation_cycle",
        scope=scope,
        as_of=as_of,
        series_code="CPI_YOY",
        metric_name="cpi_yoy",
        missing_kpi_id="cpi_yoy",
        lookback_years=12,
        max_stale_months=6,
        stale_note="FRED's INDCPIALLMINMEI lags ~12-15 months; fresh CPI requires the "
                   "MOSPI manual import route (afund.data.macro_manual)",
    )
    if not anchor.data_pending and anchor.current is not None:
        lo = RBI_CPI_TARGET_MID - RBI_CPI_TARGET_HALF_WIDTH
        hi = RBI_CPI_TARGET_MID + RBI_CPI_TARGET_HALF_WIDTH
        if anchor.current < lo:
            band_pos = f"BELOW the RBI target band ({lo:g}-{hi:g}%)"
        elif anchor.current > hi:
            band_pos = f"ABOVE the RBI target band ({lo:g}-{hi:g}%)"
        else:
            band_pos = f"inside the RBI target band ({lo:g}-{hi:g}%) — goldilocks"
        anchor.note = (
            f"CPI YoY {anchor.current:.2f}% is {band_pos}; 12y lookback "
            f"(goldilocks_type per cpi_yoy.yaml)"
        )
    return anchor


# flows_anchor: minimum complete months of FII_NET history before a
# distributional reading (percentile over monthly sums) is honest. The
# NSE provisional-flows source is forward-accumulating only (no free bulk
# history — see afund.data.fii_dii), so this stays data_pending for the
# first ~2 years of accumulation.
FLOWS_MIN_MONTHS = 24


def flows_anchor(conn: sqlite3.Connection, scope: str = "market",
                  as_of: str | None = None) -> AnchorSeries:
    """FII/DII capital-flows cycle: monthly net FII flow sums (macro_series
    FII_NET, INR crore, via afund.data.fii_dii), percentile-ranked over an
    8y lookback (fii_dii_flows.yaml). The kpi yaml frames the stat as a
    z-score against the flow distribution; the engine's uniform mechanism
    (classify.percentile_rank over the anchor's own history) is the same
    normalize-against-own-distribution idea, kept consistent with every
    other anchor rather than special-casing a z-score here.

    Only COMPLETE months are aggregated (the as_of month is excluded —
    a 2-day partial month sum is not comparable to full-month sums), and
    the anchor stays honestly data_pending until FLOWS_MIN_MONTHS complete
    months exist."""
    as_of = as_of or dt.date.today().isoformat()
    daily = _macro_series_history(conn, "FII_NET", as_of, lookback_years=8)

    monthly: dict[str, float] = {}
    current_month = as_of[:7]
    for d, v in daily:
        month = d[:7]
        if month >= current_month:
            continue  # exclude the (potentially partial) as_of month
        monthly[month] = monthly.get(month, 0.0) + v

    if len(monthly) < FLOWS_MIN_MONTHS:
        return AnchorSeries(
            cycle_id="fii_dii_capital_flows_cycle",
            scope=scope,
            metric_name="fii_net_monthly",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["fii_dii_flows"],
            note=(
                f"forward-accumulating: {len(monthly)} complete month(s) of FII_NET "
                f"accumulated so far (need >= {FLOWS_MIN_MONTHS}); NSE provisional "
                f"flows have no free bulk history (see afund.data.fii_dii)"
            ),
        )

    history = [(f"{m}-01", v) for m, v in sorted(monthly.items())]
    return AnchorSeries(
        cycle_id="fii_dii_capital_flows_cycle",
        scope=scope,
        metric_name="fii_net_monthly",
        as_of_date=as_of,
        current=history[-1][1],
        history=history,
        data_pending=False,
        note=f"monthly FII_NET sums (INR cr), {len(history)} complete months, 8y lookback",
    )


def india_vix_anchor(conn: sqlite3.Connection, scope: str = "market",
                      as_of: str | None = None) -> AnchorSeries:
    """India VIX (macro_series INDIA_VIX via afund.data.india_vix, daily,
    10y lookback per india_vix.yaml). Raw (non-inverted) series — the KPI
    is fear_type, and the INVERSION happens at scoring time in assess.py
    (high VIX percentile = fear = capitulation = LOW sentiment percentile,
    per knowledge/references/kpi_interpretation/sentiment_cycle.md:
    'Fear-type: INVERT before scoring'). anchors.py only reports the honest
    raw number, per this module's contract."""
    return _macro_level_anchor(
        conn,
        catalog_cycle_id="sentiment_behavioral_cycle",
        scope=scope,
        as_of=as_of,
        series_code="INDIA_VIX",
        metric_name="india_vix",
        missing_kpi_id="india_vix",
        lookback_years=10,
        max_stale_months=2,  # daily series; anything >2 months old means the pipeline stopped
        note="India VIX daily close (NSE), 10y lookback; fear_type — inverted at scoring time",
    )


def yield_gap_anchor(conn: sqlite3.Connection, scope: str, as_of: str | None = None,
                      lookback_years: float = 15) -> AnchorSeries:
    """Yield Gap for the valuation cycle / allocation bands / EVI:

        yield_gap = (10Y G-Sec yield % / 100) x index trailing P/E

    encoding knowledge/data/kpis/yield_gap.yaml's formula ('10Y G-Sec
    yield x Nifty trailing P/E') in the scaling consistent with its own
    1.40/1.70 thresholds — verified live: GSEC_10Y 7.02 (2026-05) x
    NIFTY 50 PE 20.92 (2026-07-03) / 100 = 1.469, inside the 1.40-1.70
    neutral zone (the raw product, 147, would be nonsensical vs those
    thresholds).

    History: monthly join — each GSEC_10Y month is paired with the last
    index P/E print on/before that month's end. Current: the latest
    G-Sec yield paired with the latest P/E as of `as_of` (the monthly
    yield lags the daily P/E by ~1-2 months; acceptable for a monthly-
    cadence macro series, and disclosed in the note). Lookback 15y per
    yield_gap.yaml. `scope` resolves through sector_index_map exactly
    like valuation_anchor (fractal application)."""
    as_of = as_of or dt.date.today().isoformat()
    settings = load_settings()
    sector_index_map = settings.get("sector_index_map", {})
    index_name = sector_index_map.get(scope, scope)

    gsec = _macro_series_history(conn, "GSEC_10Y", as_of, lookback_years + 1)
    pe_rows = conn.execute(
        """
        SELECT date, pe FROM index_data
         WHERE index_name = ? AND pe IS NOT NULL AND pe > 0 AND date <= ?
         ORDER BY date ASC
        """,
        (index_name, as_of),
    ).fetchall()
    pe_series = [(r["date"], r["pe"]) for r in pe_rows]

    if not gsec or not pe_series:
        return AnchorSeries(
            cycle_id="valuation_cycle",
            scope=scope,
            metric_name="yield_gap",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["yield_gap"],
            note=(
                f"missing {'GSEC_10Y macro_series rows' if not gsec else ''}"
                f"{' and ' if not gsec and not pe_series else ''}"
                f"{f'index_data.pe rows for {index_name!r}' if not pe_series else ''} as of {as_of}"
            ),
        )

    # Staleness guard on the yield leg (same 6-month threshold as
    # rate_liquidity_anchor — a yield_gap computed off a year-old yield
    # would be silently wrong).
    if _months_stale(gsec[-1][0], as_of) > 6:
        return AnchorSeries(
            cycle_id="valuation_cycle",
            scope=scope,
            metric_name="yield_gap",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["yield_gap"],
            note=f"data_stale: latest GSEC_10Y point ({gsec[-1][0]}) is more than 6 months old",
        )

    # Monthly join: last PE on/before each G-Sec month's end.
    history: list[tuple[str, float]] = []
    pe_idx = 0
    last_pe_on_or_before: list[tuple[str, float]] = []  # running pointer over pe_series
    for month_start, yield_pct in gsec:
        month_date = dt.date.fromisoformat(month_start)
        next_month = (month_date.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        month_end = (next_month - dt.timedelta(days=1)).isoformat()
        while pe_idx < len(pe_series) and pe_series[pe_idx][0] <= month_end:
            last_pe_on_or_before = [pe_series[pe_idx]]
            pe_idx += 1
        if last_pe_on_or_before:
            pe_date, pe = last_pe_on_or_before[0]
            # Only pair when the PE print is reasonably close (within the
            # same month or the prior one) — avoids joining a years-old PE
            # onto a G-Sec month at the start of the PE series.
            if _months_stale(pe_date, month_end) <= 2:
                history.append((month_start, (yield_pct / 100.0) * pe))

    latest_yield_date, latest_yield = gsec[-1]
    latest_pe_date, latest_pe = pe_series[-1]
    current = (latest_yield / 100.0) * latest_pe
    if not history or history[-1][0] < latest_pe_date:
        history.append((latest_pe_date, current))

    if len(history) < 10:
        return AnchorSeries(
            cycle_id="valuation_cycle",
            scope=scope,
            metric_name="yield_gap",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["yield_gap"],
            note=f"only {len(history)} joined GSEC_10Y x PE monthly points for {index_name!r} — too thin to rank",
        )

    return AnchorSeries(
        cycle_id="valuation_cycle",
        scope=scope,
        metric_name="yield_gap",
        as_of_date=as_of,
        current=current,
        history=history,
        data_pending=False,
        note=(
            f"yield_gap = (GSEC_10Y {latest_yield:.2f}% [{latest_yield_date}] / 100) x "
            f"{index_name} PE {latest_pe:.2f} [{latest_pe_date}] = {current:.3f}; "
            f"{len(history)} monthly points, {lookback_years:g}y lookback"
        ),
    )


def _yoy_from_level_series(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Derive a monthly YoY % series from a level series, matching each
    point against the value 12 rows back (both series are monthly,
    (date, value) sorted ascending — index-offset is correct as long as
    there are no gaps, which macro_govt's GST_COLLECTIONS/ICI_INDEX
    series don't currently have). Never fabricates: points with no
    same-month-prior-year comparator (first 12 months, or a gap) are
    simply omitted, not interpolated."""
    by_date = {d: v for d, v in series}
    out: list[tuple[str, float]] = []
    for i, (d, v) in enumerate(series):
        if i < 12:
            continue
        prior_date, prior_v = series[i - 12]
        # Guard against gaps: only trust the i-12 lookup if it's genuinely
        # ~12 months back (same calendar month, prior year).
        try:
            cur = dt.date.fromisoformat(d)
            prior = dt.date.fromisoformat(prior_date)
        except ValueError:
            continue
        if not (prior.year == cur.year - 1 and prior.month == cur.month):
            continue
        if prior_v in (0, None):
            continue
        out.append((d, (v - prior_v) / prior_v * 100.0))
    return out


def gdp_business_anchor(conn: sqlite3.Connection, scope: str = "market",
                         as_of: str | None = None) -> AnchorSeries:
    """GDP/Business cycle: WORKSTREAM D supplementary activity anchor,
    blending GST_COLLECTIONS YoY (nominal consumption/trade activity) and
    ICI_INDEX YoY (industrial output, ~40%-weight IIP proxy) into a
    simple average "activity YoY" reading, when both are available and
    fresh. This is deliberately NOT the catalog's primary anchor_kpi_id
    (mcap_gdp, still source_status: missing — see mcap_gdp.yaml) — it is
    a second, genuinely-available reading for the same cycle, following
    the same honest data_pending pattern as every other anchor here.

    NOT wired into LIVE_CYCLE_IDS/CATALOG_CYCLE_MAP/assess.py's
    assess_live_cycle() dispatch: gdp_business_cycle's catalog
    anchor_kpi_ids still lists mcap_gdp first and that KPI remains
    unsourced, so the cycle as a whole stays on the data_pending_anchor()
    path in the real assessment pipeline (assess.py's
    assess_data_pending_cycles() — see its available_unwired disclosure,
    which now correctly reports gst_collections/ici_index as available-
    but-unwired rather than missing). This function exists so the
    reading is computable directly (e.g. for ad hoc inspection or a
    future assess.py branch) without overclaiming the cycle is fully
    live end-to-end.

    Both GST_COLLECTIONS and ICI_INDEX arrive as monthly LEVEL series
    (afund.data.macro_govt) — YoY is derived here via
    _yoy_from_level_series, the same level->YoY derivation pattern as
    CPI_INDEX->CPI_YOY (afund.data.macro_fred), just done locally since
    these two don't have a pre-derived *_YOY macro_series row."""
    as_of = as_of or dt.date.today().isoformat()
    gst_levels = _macro_series_history(conn, "GST_COLLECTIONS", as_of, lookback_years=6)
    ici_levels = _macro_series_history(conn, "ICI_INDEX", as_of, lookback_years=6)
    gst_yoy = _yoy_from_level_series(gst_levels)
    ici_yoy = _yoy_from_level_series(ici_levels)

    missing_kpi_id = "gst_collections"
    if not gst_yoy and not ici_yoy:
        return AnchorSeries(
            cycle_id="gdp_business_cycle",
            scope=scope,
            metric_name="activity_yoy",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=["gst_collections", "ici_index"],
            note="neither GST_COLLECTIONS nor ICI_INDEX has >=13 months of "
                 "level history yet to derive a YoY reading",
        )

    # Blend on shared dates when both exist; fall back to whichever one
    # has data on a given month otherwise. Never fabricate a value for a
    # month where both are missing.
    gst_by_date = dict(gst_yoy)
    ici_by_date = dict(ici_yoy)
    all_dates = sorted(set(gst_by_date) | set(ici_by_date))
    blended: list[tuple[str, float]] = []
    for d in all_dates:
        vals = [v for v in (gst_by_date.get(d), ici_by_date.get(d)) if v is not None]
        if vals:
            blended.append((d, sum(vals) / len(vals)))

    if not blended:
        return AnchorSeries(
            cycle_id="gdp_business_cycle",
            scope=scope,
            metric_name="activity_yoy",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=[missing_kpi_id],
            note="GST_COLLECTIONS/ICI_INDEX YoY derivation produced no overlapping points",
        )

    stale_months = _months_stale(blended[-1][0], as_of)
    if stale_months > 4:  # both sources publish monthly, ~1-2 months in arrears
        return AnchorSeries(
            cycle_id="gdp_business_cycle",
            scope=scope,
            metric_name="activity_yoy",
            as_of_date=as_of,
            current=None,
            data_pending=True,
            missing_kpis=[missing_kpi_id],
            note=f"data_stale: latest activity_yoy point ({blended[-1][0]}) is "
                 f"{stale_months:.1f} months old (> 4-month threshold)",
        )

    n_gst = len(gst_yoy)
    n_ici = len(ici_yoy)
    return AnchorSeries(
        cycle_id="gdp_business_cycle",
        scope=scope,
        metric_name="activity_yoy",
        as_of_date=as_of,
        current=blended[-1][1],
        history=blended,
        data_pending=False,
        note=(
            f"activity_yoy = mean(GST_COLLECTIONS YoY, ICI_INDEX YoY) where both "
            f"available, else whichever exists ({n_gst} GST points, {n_ici} ICI "
            f"points); supplementary anchor alongside the still-missing mcap_gdp "
            f"primary anchor (value_type, per catalog orientation_note) — DRAFT, "
            f"not back-tested"
        ),
    )


def data_pending_anchor(catalog_cycle_id: str, scope: str, as_of: str | None = None) -> AnchorSeries:
    """Honest data_pending reading for any non-live catalog cycle. Looks up
    the cycle's own anchor_kpi_ids from knowledge/ so the reported
    missing_kpis list is accurate rather than guessed; falls back to an
    empty list if knowledge/ can't be loaded (never fabricated).

    KPIs whose source_status is already 'available' (data landed but this
    cycle's anchor logic isn't wired yet — e.g. india_vix for
    volatility_risk_regime_cycle after Phase 8) are excluded from
    missing_kpis (claiming they're missing would be false) and disclosed
    in the note instead."""
    as_of = as_of or dt.date.today().isoformat()
    missing: list[str] = []
    available_unwired: list[str] = []
    if load_knowledge is not None:
        try:
            k = load_knowledge()
            cycle_def = k.catalog.get(catalog_cycle_id)
            for kpi_id in cycle_def.anchor_kpi_ids:
                kpi = k.kpis.get(kpi_id)
                if kpi is not None and kpi.source_status == "available":
                    available_unwired.append(kpi_id)
                else:
                    missing.append(kpi_id)
        except Exception:
            missing = []
            available_unwired = []

    note = "no live data source wired yet for this cycle (Phase 8+ sourcing TODO)"
    if available_unwired:
        note = (
            f"anchor data for {available_unwired} IS available but this cycle's "
            f"anchor logic is not wired into the engine yet"
            + (f"; still missing: {missing}" if missing else "")
        )

    return AnchorSeries(
        cycle_id=catalog_cycle_id,
        scope=scope,
        metric_name="n/a",
        as_of_date=as_of,
        current=None,
        data_pending=True,
        missing_kpis=missing,
        note=note,
    )
