"""
kronos/gate_eval.py
===================

**Separation test** — the honest, cheap way to answer one question:

    *"On the stocks a strategy already picked, do the trades Kronos would KEEP
     win more often than the trades it would VETO?"*

This is a far lower bar than price prediction. A gate does not need Kronos to be
*calibrated* (accurate absolute prices); it only needs Kronos' opinion to
**separate** eventual winners from losers on the strategy's own picks. So instead
of a full portfolio A/B (which conflates the gate with sizing / capacity / timing),
we measure separation directly:

  * take the strategy's realised trades (symbol + entry date + booked P&L),
  * compute Kronos' point-in-time signal **as of each entry date**,
  * bucket trades into KEPT vs VETOED (and into score quintiles),
  * compare realised win-rate / average return across the buckets, and
  * report a rank information-coefficient (Spearman) between Kronos' score and the
    realised outcome.

Two outcomes are measured per trade so we can tell *skill* from *horizon mismatch*:
  * ``strat_pnl_pct`` — what the strategy actually booked (the thing we gate), and
  * ``fwd_pnl_pct``   — the raw N-day forward return from entry, N = Kronos'
    forecast horizon (Kronos' *native* horizon, isolating its own predictive edge).

Calibration fix baked in
------------------------
The strategies feed Kronos **adjusted** prices (``auto_adjust=True``), which is the
prime suspect for the implausible downward-biased forecasts we observed. This module
forecasts from **raw** (unadjusted) candles — what Kronos was trained on — via its
own :class:`RawPriceCache`, and defaults to a short 5-session horizon to limit bias
compounding.

Everything except :class:`RawPriceCache` (network) and the Kronos forecaster (torch)
is pure and unit-testable with hand-built inputs.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from statistics import fmean
from typing import Dict, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger("kronos.gate_eval")


# ── trade + evaluation records ───────────────────────────────────────────────
@dataclass
class TradeRecord:
    """One realised trade from a strategy backtest."""

    symbol: str
    entry_date: date
    strat_pnl_pct: float  # what the strategy booked on this trade (%)

    @property
    def strat_win(self) -> bool:
        return self.strat_pnl_pct > 0.0


@dataclass
class TradeEval:
    """A trade annotated with Kronos' as-of opinion and realised outcomes."""

    symbol: str
    entry_date: date
    strat_pnl_pct: float
    strat_win: bool

    has_signal: bool
    allowed: Optional[bool] = None       # would the gate KEEP this trade?
    prob_up: Optional[float] = None
    expected_return: Optional[float] = None
    direction: Optional[str] = None
    fwd_pnl_pct: Optional[float] = None   # raw N-day forward return from entry (%)


# ── raw (unadjusted) point-in-time price cache ───────────────────────────────
def _yf_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s.endswith((".NS", ".BO")):
        s = f"{s}.NS"
    return s


def _plain_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".NS", "").replace(".BO", "")


class RawPriceCache:
    """Download RAW (``auto_adjust=False``) daily OHLCV once per symbol and serve
    leak-free as-of slices plus fixed-horizon forward returns.

    Raw candles matter here: Kronos was trained on raw traded prices, and feeding
    it split/dividend-*adjusted* levels is the likely cause of the biased forecasts
    seen when reusing the strategies' adjusted data.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.frames: Dict[str, pd.DataFrame] = {}

    def load_or_download(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        *,
        warmup_days: int = 500,
        forward_days: int = 40,
        use_cache: bool = True,
        chunk_size: int = 40,
    ) -> None:
        import yfinance as yf

        dl_start = start - timedelta(days=warmup_days)
        dl_end = end + timedelta(days=forward_days)
        plains = sorted({_plain_symbol(s) for s in symbols})
        tag = f"raw_{len(plains)}_{hash(tuple(plains)) & 0xffffffff:x}_{dl_start}_{dl_end}"
        cache_path = self.cache_dir / f"{tag}.pkl"

        if use_cache and cache_path.exists():
            logger.info("Loading cached RAW prices from %s", cache_path.name)
            with open(cache_path, "rb") as fh:
                self.frames = pickle.load(fh)
            return

        yf_map = {_yf_symbol(s): _plain_symbol(s) for s in plains}
        tickers = list(yf_map.keys())
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            logger.info("Downloading RAW %d-%d / %d", i + 1, min(i + chunk_size, len(tickers)), len(tickers))
            try:
                data = yf.download(
                    chunk, start=dl_start, end=dl_end, interval="1d",
                    auto_adjust=False, progress=False, group_by="ticker", threads=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("RAW chunk download failed (%s); skipping.", exc)
                continue
            for yf_sym in chunk:
                plain = yf_map[yf_sym]
                try:
                    sub = data[yf_sym] if len(chunk) > 1 else data
                except (KeyError, TypeError):
                    continue
                df = self._normalise(sub)
                if df is not None and len(df) >= 60:
                    self.frames[plain] = df

        with open(cache_path, "wb") as fh:
            pickle.dump(self.frames, fh)
        logger.info("Cached RAW prices to %s (%d symbols)", cache_path.name, len(self.frames))

    @staticmethod
    def _normalise(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        # With auto_adjust=False yfinance yields Open/High/Low/Close/Adj Close/Volume.
        rename = {c: c.title() for c in df.columns}
        df = df.rename(columns=rename)
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        if "Close" not in keep:
            return None
        df = df[keep].dropna(subset=["Close"])
        idx = pd.to_datetime(df.index)
        try:
            idx = idx.tz_localize(None)
        except (TypeError, AttributeError):
            pass
        df.index = idx.normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df

    def as_of(self, symbol: str, day: date, lookback_rows: Optional[int] = None) -> Optional[pd.DataFrame]:
        df = self.frames.get(_plain_symbol(symbol))
        if df is None:
            return None
        sliced = df.loc[: pd.Timestamp(day).normalize()]
        if sliced.empty:
            return None
        return sliced.tail(lookback_rows) if lookback_rows else sliced

    def forward_return_pct(self, symbol: str, entry_day: date, horizon: int) -> Optional[float]:
        """Raw close-to-close return from the entry session to ``horizon`` sessions later."""
        df = self.frames.get(_plain_symbol(symbol))
        if df is None:
            return None
        ts = pd.Timestamp(entry_day).normalize()
        past = df.loc[:ts]
        future = df.loc[ts:]
        if past.empty or len(future) < horizon + 1:
            return None
        entry_close = float(past["Close"].iloc[-1])
        exit_close = float(future["Close"].iloc[horizon])
        if entry_close <= 0:
            return None
        return (exit_close / entry_close - 1.0) * 100.0


# ── trade ingestion ──────────────────────────────────────────────────────────
def load_trades_csv(path: str | Path) -> List[TradeRecord]:
    """Parse a strategy backtest ``trades.csv`` (qtr_results / swing format).

    Requires ``symbol``, ``entry_date`` and a P&L column (``pnl_pct``).
    """
    df = pd.read_csv(path)
    return records_from_dicts(df.to_dict("records"))


def records_from_dicts(rows: Sequence[dict]) -> List[TradeRecord]:
    """Build TradeRecords from a list of trade dicts (from a CSV or a backtest).

    Tolerant of column casing and a few P&L aliases; skips malformed rows.
    """
    out: List[TradeRecord] = []
    for raw in rows:
        r = {str(k).lower(): v for k, v in raw.items()}
        sym = r.get("symbol")
        entry = r.get("entry_date")
        pnl = r.get("pnl_pct", r.get("pnl_percent", r.get("return_pct")))
        if sym is None or entry is None or pnl is None:
            continue
        try:
            out.append(
                TradeRecord(
                    symbol=str(sym).strip().upper(),
                    entry_date=pd.to_datetime(entry).date(),
                    strat_pnl_pct=float(pnl),
                )
            )
        except (ValueError, TypeError):
            continue
    return out


# ── evaluation ───────────────────────────────────────────────────────────────
def evaluate_gate(
    trades: Sequence[TradeRecord],
    forecaster,
    raw_cache: RawPriceCache,
    *,
    pred_len: int = 5,
    sample_paths: int = 10,
    lookback: int = 256,
    min_prob_up: float = 0.50,
    block_avoid: bool = True,
    gate_mode: str = "rank",
    keep_fraction: float = 0.5,
    min_rows: int = 60,
) -> List[TradeEval]:
    """Annotate each trade with Kronos' as-of opinion and its realised outcomes.

    Point-in-time: the forecast only ever sees raw rows dated ``<= entry_date``.
    The forward return uses sessions AFTER entry purely as an outcome label.

    Gate modes (how ``allowed`` is set):
      * ``absolute`` — KEEP when P(up) ≥ ``min_prob_up`` (and not AVOID if
        ``block_avoid``). Simple, but sensitive to Kronos' large downward drift on
        NSE bars, so it tends to veto almost everything.
      * ``rank`` (default) — KEEP the top ``keep_fraction`` of trades by Kronos
        expected-return **rank** across the evaluated set. Robust to a constant
        drift bias: it asks "of these picks, do Kronos' relatively-more-bullish
        ones win more?" — the honest gate question for a miscalibrated model.
    """
    from kronos.service import prepare_inputs
    from kronos.signals import derive_signal

    evals: List[TradeEval] = []
    for t in trades:
        fwd = raw_cache.forward_return_pct(t.symbol, t.entry_date, pred_len)
        df_asof = raw_cache.as_of(t.symbol, t.entry_date, lookback_rows=lookback)
        if df_asof is None or len(df_asof) < min_rows:
            evals.append(
                TradeEval(
                    symbol=t.symbol, entry_date=t.entry_date,
                    strat_pnl_pct=t.strat_pnl_pct, strat_win=t.strat_win,
                    has_signal=False, fwd_pnl_pct=fwd,
                )
            )
            continue

        d = df_asof.rename(columns=str.lower)
        x_df, x_ts, y_ts = prepare_inputs(d, pred_len)
        paths = forecaster.predict_paths(
            x_df, x_ts, y_ts, pred_len=pred_len, sample_paths=sample_paths
        )
        sig = derive_signal(t.symbol, float(d["close"].iloc[-1]), paths, horizon=pred_len)

        allowed = _allows(sig, min_prob_up=min_prob_up, block_avoid=block_avoid)
        evals.append(
            TradeEval(
                symbol=t.symbol, entry_date=t.entry_date,
                strat_pnl_pct=t.strat_pnl_pct, strat_win=t.strat_win,
                has_signal=True, allowed=allowed,
                prob_up=sig.prob_up, expected_return=sig.expected_return,
                direction=sig.direction, fwd_pnl_pct=fwd,
            )
        )

    if gate_mode == "rank":
        _apply_rank_gate(evals, keep_fraction=keep_fraction)
    return evals


def _apply_rank_gate(evals: List[TradeEval], *, keep_fraction: float) -> None:
    """Overwrite ``allowed`` by cross-sectional expected-return rank (in place).

    KEEP the top ``keep_fraction`` of signalled trades; veto the rest. This makes
    the gate relative, so a constant forecast drift cancels out.
    """
    scored = [e for e in evals if e.has_signal and e.expected_return is not None]
    if len(scored) < 2:
        return
    scored.sort(key=lambda e: e.expected_return, reverse=True)
    keep_n = max(1, min(len(scored) - 1, round(len(scored) * keep_fraction)))
    for i, e in enumerate(scored):
        e.allowed = i < keep_n


def _allows(sig, *, min_prob_up: float, block_avoid: bool) -> bool:
    if block_avoid and sig.direction == "AVOID":
        return False
    if sig.prob_up < min_prob_up:
        return False
    return True


# ── separation statistics ────────────────────────────────────────────────────
def _bucket(evals: Sequence[TradeEval], allowed: bool) -> Dict[str, float]:
    rows = [e for e in evals if e.has_signal and e.allowed is allowed]
    n = len(rows)
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_pnl": None, "avg_fwd": None}
    wins = sum(1 for e in rows if e.strat_win)
    fwds = [e.fwd_pnl_pct for e in rows if e.fwd_pnl_pct is not None]
    return {
        "n": n,
        "win_rate": round(wins / n * 100.0, 1),
        "avg_pnl": round(fmean(e.strat_pnl_pct for e in rows), 2),
        "avg_fwd": round(fmean(fwds), 2) if fwds else None,
    }


def _spearman_ic(evals: Sequence[TradeEval], score: str, outcome: str) -> Optional[float]:
    """Rank correlation between a Kronos score and a realised outcome."""
    xs, ys = [], []
    for e in evals:
        if not e.has_signal:
            continue
        s = getattr(e, score)
        o = getattr(e, outcome)
        if s is None or o is None:
            continue
        xs.append(s)
        ys.append(o)
    if len(xs) < 5:
        return None
    s = pd.Series(xs).corr(pd.Series(ys), method="spearman")
    return None if pd.isna(s) else round(float(s), 3)


def _quintiles(evals: Sequence[TradeEval], score: str = "prob_up") -> List[Dict[str, float]]:
    rows = [e for e in evals if e.has_signal and getattr(e, score) is not None]
    if len(rows) < 5:
        return []
    df = pd.DataFrame(
        {
            "score": [getattr(e, score) for e in rows],
            "win": [1 if e.strat_win else 0 for e in rows],
            "pnl": [e.strat_pnl_pct for e in rows],
        }
    )
    try:
        df["q"] = pd.qcut(df["score"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    except ValueError:
        return []
    out = []
    for q, g in df.groupby("q", observed=True):
        out.append(
            {
                "quintile": int(q),
                "n": int(len(g)),
                "score_lo": round(float(g["score"].min()), 3),
                "score_hi": round(float(g["score"].max()), 3),
                "win_rate": round(float(g["win"].mean()) * 100.0, 1),
                "avg_pnl": round(float(g["pnl"].mean()), 2),
            }
        )
    return out


def separation_report(evals: Sequence[TradeEval]) -> Dict[str, object]:
    signalled = [e for e in evals if e.has_signal]
    total = len(evals)
    n_sig = len(signalled)
    base_wins = sum(1 for e in evals if e.strat_win)
    baseline_win = round(base_wins / total * 100.0, 1) if total else None

    kept = _bucket(evals, True)
    vetoed = _bucket(evals, False)

    lift = None
    if kept["win_rate"] is not None and baseline_win is not None:
        lift = round(kept["win_rate"] - baseline_win, 1)

    return {
        "n_trades": total,
        "n_signalled": n_sig,
        "n_no_signal": total - n_sig,
        "baseline_win_rate": baseline_win,
        "kept": kept,
        "vetoed": vetoed,
        "win_rate_lift_vs_baseline": lift,
        "ic_probup_vs_strat": _spearman_ic(signalled, "prob_up", "strat_pnl_pct"),
        "ic_probup_vs_fwd": _spearman_ic(signalled, "prob_up", "fwd_pnl_pct"),
        "ic_expret_vs_fwd": _spearman_ic(signalled, "expected_return", "fwd_pnl_pct"),
        "quintiles": _quintiles(signalled, "prob_up"),
        "verdict": _verdict(kept, vetoed, baseline_win),
    }


def _verdict(kept: Dict, vetoed: Dict, baseline_win: Optional[float]) -> str:
    if kept["n"] == 0 or vetoed["n"] == 0:
        return (
            "INCONCLUSIVE — one bucket is empty (gate kept or vetoed ~everything). "
            "Use gate_mode='rank' (keep top fraction) or adjust min_prob_up so both "
            "buckets have trades."
        )
    sep = kept["win_rate"] - vetoed["win_rate"]
    if sep >= 8.0 and kept["win_rate"] >= (baseline_win or 0):
        return (
            f"PASS — kept trades win {kept['win_rate']}% vs vetoed {vetoed['win_rate']}% "
            f"(+{round(sep,1)} pts). Kronos separates winners from losers on these picks."
        )
    if sep >= 3.0:
        return (
            f"WEAK — modest separation ({round(sep,1)} pts). Some signal, but confirm on "
            "more trades / windows before trusting it as a gate."
        )
    if sep <= -3.0:
        return (
            f"INVERTED — kept trades win LESS than vetoed ({round(sep,1)} pts). Kronos is "
            "anti-predictive here; do NOT gate with it as-is."
        )
    return (
        f"FAIL — no meaningful separation ({round(sep,1)} pts). Kronos adds no gating edge "
        "on these picks; a fixed threshold gate is not worthwhile."
    )


# ── reporting ────────────────────────────────────────────────────────────────
def render_separation_report(rep: Dict[str, object], *, title: str, meta: str) -> str:
    def wr(b: Dict) -> str:
        if b["n"] == 0:
            return "— (0 trades)"
        fwd = f", fwd {b['avg_fwd']}%" if b.get("avg_fwd") is not None else ""
        return f"{b['win_rate']}% win · avg {b['avg_pnl']}%{fwd} · n={b['n']}"

    lines = [
        f"# 🧪 Kronos Gate — Separation Test ({title})",
        "",
        meta,
        "",
        f"**Verdict: {rep['verdict']}**",
        "",
        f"Trades analysed: **{rep['n_trades']}** "
        f"(Kronos scored {rep['n_signalled']}, {rep['n_no_signal']} lacked history)",
        f"Baseline win rate (all picks): **{rep['baseline_win_rate']}%**",
        "",
        "| Bucket | Outcome |",
        "|---|---|",
        f"| ✅ Kronos KEEP | {wr(rep['kept'])} |",
        f"| ⛔ Kronos VETO | {wr(rep['vetoed'])} |",
        "",
        f"**Win-rate lift of kept trades vs baseline: "
        f"{_fmt_pts(rep['win_rate_lift_vs_baseline'])}**",
        "",
        "### Rank information coefficient (Spearman)",
        "> IC > 0 means a higher Kronos score → better realised outcome. "
        "|IC| ≥ 0.1 is a usable signal; ~0 is noise; < 0 is anti-predictive.",
        "",
        f"- P(up) vs strategy P&L: **{_fmt_ic(rep['ic_probup_vs_strat'])}**",
        f"- P(up) vs {'{}-day'.format('N')} forward return (Kronos' native horizon): "
        f"**{_fmt_ic(rep['ic_probup_vs_fwd'])}**",
        f"- Expected-return vs forward return: **{_fmt_ic(rep['ic_expret_vs_fwd'])}**",
    ]

    quints = rep.get("quintiles") or []
    if quints:
        lines += [
            "",
            "### Win rate by Kronos P(up) quintile",
            "> A monotonic rise from Q1→Q5 is the signature of a real gating signal.",
            "",
            "| Quintile | P(up) range | Trades | Win rate | Avg P&L |",
            "|---|---|---|---|---|",
        ]
        for q in quints:
            lines.append(
                f"| Q{q['quintile']} | {q['score_lo']:.2f}–{q['score_hi']:.2f} | "
                f"{q['n']} | {q['win_rate']}% | {q['avg_pnl']}% |"
            )

    lines += [
        "",
        "> Point-in-time: forecasts use only RAW (unadjusted) candles dated ≤ entry. "
        "One strategy/window is indicative, not proof — confirm across periods before "
        "wiring the gate live.",
    ]
    return "\n".join(lines)


def _fmt_pts(v: Optional[float]) -> str:
    if v is None:
        return "—"
    arrow = " ✅" if v > 0.5 else (" ⚠️" if v < -0.5 else "")
    return f"{v:+.1f} pts{arrow}"


def _fmt_ic(v: Optional[float]) -> str:
    if v is None:
        return "— (too few trades)"
    if v >= 0.1:
        return f"{v:+.3f} ✅ usable"
    if v <= -0.1:
        return f"{v:+.3f} ⚠️ anti-predictive"
    return f"{v:+.3f} (noise)"


__all__ = [
    "TradeRecord",
    "TradeEval",
    "RawPriceCache",
    "load_trades_csv",
    "records_from_dicts",
    "evaluate_gate",
    "separation_report",
    "render_separation_report",
    "run_gate_eval",
]


# ── orchestration ────────────────────────────────────────────────────────────
def run_gate_eval(
    trades: Sequence[TradeRecord],
    *,
    cache_dir: Path,
    model: str,
    tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base",
    pred_len: int = 5,
    sample_paths: int = 10,
    lookback: int = 256,
    min_prob_up: float = 0.50,
    block_avoid: bool = True,
    gate_mode: str = "rank",
    keep_fraction: float = 0.5,
    use_cache: bool = True,
    title: str = "",
) -> Dict[str, object]:
    """End-to-end: build a raw-price cache over the trades' symbols/window, run
    Kronos as-of each entry, and return the separation report + markdown.

    Raises :class:`kronos.predictor.KronosUnavailable` if torch/Kronos are missing.
    """
    from kronos.config import KronosConfig
    from kronos.predictor import KronosForecaster

    if not trades:
        raise ValueError("no trades to evaluate")

    symbols = sorted({t.symbol for t in trades})
    start = min(t.entry_date for t in trades)
    end = max(t.entry_date for t in trades)

    raw_cache = RawPriceCache(Path(cache_dir))
    raw_cache.load_or_download(
        symbols, start, end,
        warmup_days=max(lookback * 2, 500),
        forward_days=max(pred_len * 3, 40),
        use_cache=use_cache,
    )

    cfg = KronosConfig(
        model=model, tokenizer=tokenizer,
        pred_len=pred_len, sample_paths=sample_paths, lookback=lookback,
    )
    forecaster = KronosForecaster(cfg)

    evals = evaluate_gate(
        trades, forecaster, raw_cache,
        pred_len=pred_len, sample_paths=sample_paths, lookback=lookback,
        min_prob_up=min_prob_up, block_avoid=block_avoid,
        gate_mode=gate_mode, keep_fraction=keep_fraction,
    )
    rep = separation_report(evals)
    if gate_mode == "rank":
        gate_desc = f"**rank** (keep top {keep_fraction:.0%} by Kronos score)"
    else:
        gate_desc = f"**absolute** (min P(up) {min_prob_up:.0%}, block AVOID {block_avoid})"
    meta = (
        f"Model `{model}` · horizon **{pred_len}** sessions · paths **{sample_paths}** · "
        f"gate {gate_desc} · prices **RAW (unadjusted)**"
    )
    rep["markdown"] = render_separation_report(rep, title=title or "picks", meta=meta)
    return rep
