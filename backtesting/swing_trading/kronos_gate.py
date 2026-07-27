"""
kronos_gate.py
==============

A **point-in-time** Kronos confirmation gate for the swing backtest.

The gate answers one question for each entry candidate the playbook produces:
*"does Kronos' near-term forecast confirm this long?"* It is used as an overlay —
candidates the gate vetoes are dropped before they become pending orders — so we
can A/B whether Kronos raises hit-rate / risk-adjusted return vs. the baseline.

Leak-free by construction
-------------------------
The gate is only ever handed an **as-of slice** (``PointInTimeData.as_of`` — rows
dated ``<= day``). Kronos forecasts *forward* from that day's close, and the
engine still fills the entry at the NEXT session's open. No future bar is ever
consulted, exactly like every other signal in the backtest.

Cost control
------------
Forecasting is the expensive step, so the gate:
  * only sees candidates that already passed the mechanical entry screen,
  * evaluates best-ranked candidates first and stops once enough survive,
  * memoises ``(symbol, day)`` decisions.

Kronos itself is an optional dependency; :meth:`KronosGate.from_config` raises
:class:`kronos.predictor.KronosUnavailable` (with install guidance) when torch /
the model repo are missing, so a gated run fails loudly rather than silently
degrading to the baseline.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger("backtest.kronos_gate")

_OHLCV = ["open", "high", "low", "close", "volume"]


class KronosGate:
    """Wraps a loaded Kronos forecaster and turns as-of price slices into a veto."""

    def __init__(
        self,
        forecaster,
        *,
        pred_len: int,
        sample_paths: int,
        lookback: int,
        min_prob_up: float,
        block_avoid: bool,
        min_reward_risk: float = 0.0,
        min_rows: int = 30,
    ):
        self.forecaster = forecaster
        self.pred_len = pred_len
        self.sample_paths = sample_paths
        self.lookback = lookback
        self.min_prob_up = min_prob_up
        self.block_avoid = block_avoid
        self.min_reward_risk = min_reward_risk
        self.min_rows = min_rows
        self._cache: Dict[Tuple[str, str], object] = {}

    # ── construction ─────────────────────────────────────────────────────────
    @classmethod
    def from_config(cls, cfg) -> "KronosGate":
        """Build a gate from a :class:`BacktestConfig` (loads Kronos lazily)."""
        from kronos.config import KronosConfig
        from kronos.predictor import KronosForecaster

        kcfg = KronosConfig(
            model=getattr(cfg, "kronos_model", "NeoQuasar/Kronos-base"),
            tokenizer=getattr(
                cfg, "kronos_tokenizer", "NeoQuasar/Kronos-Tokenizer-base"
            ),
            device=getattr(cfg, "kronos_device", "cpu"),
            lookback=getattr(cfg, "kronos_lookback", 256),
            pred_len=getattr(cfg, "kronos_pred_len", 10),
            sample_paths=getattr(cfg, "kronos_sample_paths", 10),
        )
        forecaster = KronosForecaster(kcfg)
        forecaster.load()  # eager load → fail fast if Kronos is unavailable
        return cls(
            forecaster,
            pred_len=kcfg.pred_len,
            sample_paths=kcfg.sample_paths,
            lookback=kcfg.clamped_lookback(),
            min_prob_up=float(getattr(cfg, "kronos_min_prob_up", 0.55)),
            block_avoid=bool(getattr(cfg, "kronos_block_avoid", True)),
            min_reward_risk=float(getattr(cfg, "kronos_min_reward_risk", 0.0)),
        )

    # ── inference ────────────────────────────────────────────────────────────
    def evaluate(self, symbol: str, df_asof: Optional[pd.DataFrame], day: date):
        """Return a :class:`kronos.signals.KronosSignal` for ``symbol`` as-of ``day``.

        ``df_asof`` is the backtest's as-of OHLCV slice (capitalised columns).
        Returns ``None`` when there is not enough history to forecast — callers
        treat that as "no opinion" (see :meth:`allows`).
        """
        from kronos.signals import derive_signal

        if df_asof is None or len(df_asof) < self.min_rows:
            return None

        key = (str(symbol), day.isoformat())
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        df = df_asof.rename(columns={c: c.lower() for c in df_asof.columns})
        cols = [c for c in _OHLCV if c in df.columns]
        if "close" not in cols:
            return None
        df = df[cols].tail(self.lookback)

        x_df = df.reset_index(drop=True)
        x_ts = pd.Series(pd.to_datetime(df.index))
        last_ts = pd.Timestamp(df.index[-1])
        y_ts = pd.Series(
            pd.bdate_range(start=last_ts + pd.Timedelta(days=1), periods=self.pred_len)
        )

        paths = self.forecaster.predict_paths(
            x_df, x_ts, y_ts, pred_len=self.pred_len, sample_paths=self.sample_paths
        )
        signal = derive_signal(
            str(symbol), float(df["close"].iloc[-1]), paths, horizon=self.pred_len
        )
        self._cache[key] = signal
        return signal

    # ── decision ─────────────────────────────────────────────────────────────
    def allows(self, signal) -> bool:
        """True if the candidate should be KEPT (not vetoed).

        Fail-open: a ``None`` signal (insufficient data to forecast) is *not*
        vetoed, so the A/B difference is attributable to real Kronos opinions
        rather than data gaps.
        """
        if signal is None:
            return True
        if self.block_avoid and signal.direction == "AVOID":
            return False
        if signal.prob_up < self.min_prob_up:
            return False
        if self.min_reward_risk > 0 and signal.reward_risk < self.min_reward_risk:
            return False
        return True

    def decision_record(self, symbol: str, day: date, signal, allowed: bool) -> dict:
        """A serialisable log row explaining one gate decision (for the report)."""
        base = {
            "date": day.isoformat(),
            "symbol": symbol,
            "allowed": bool(allowed),
        }
        if signal is None:
            base.update({"reason": "no_forecast", "prob_up": None, "direction": None})
        else:
            base.update(
                {
                    "reason": "kept" if allowed else "vetoed",
                    "direction": signal.direction,
                    "prob_up": signal.prob_up,
                    "expected_return": signal.expected_return,
                    "reward_risk": signal.reward_risk,
                }
            )
        return base


__all__ = ["KronosGate"]
