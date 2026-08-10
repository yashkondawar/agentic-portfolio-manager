"""Lazy wrapper around the Kronos foundation model.

Kronos (https://github.com/shiyu-coder/Kronos) is **not** published to PyPI and
pulls in a heavy ``torch`` dependency. To keep the rest of the app importable on
a machine without torch/GPU, all of that is imported *lazily* here: nothing in
this module touches torch or the network until :meth:`KronosForecaster.load` is
actually called.

Consumption model (matches the upstream README):

    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model     = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
    pred_df   = predictor.predict(df=..., x_timestamp=..., y_timestamp=..., ...)

Because the model classes live in the cloned repo's ``model`` package, we make
that package importable via ``KRONOS_REPO_PATH`` (or expect it already on
``sys.path``). If it cannot be resolved we raise :class:`KronosUnavailable` with
actionable install guidance rather than a bare ``ImportError``.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, List, Optional

import pandas as pd

from .config import KronosConfig

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

logger = logging.getLogger("kronos.predictor")


class KronosUnavailable(RuntimeError):
    """Raised when the Kronos model code or ``torch`` cannot be imported."""


_INSTALL_HINT = (
    "Kronos is not available in this environment.\n"
    "  1. Install torch (CPU build is fine, no GPU needed):\n"
    "       pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
    "     plus: pip install huggingface_hub einops\n"
    "  2. Get the model code (not on PyPI):\n"
    "       git clone https://github.com/shiyu-coder/Kronos\n"
    "     then set KRONOS_REPO_PATH=/path/to/Kronos so 'from model import Kronos' resolves.\n"
    "  3. First run downloads weights from Hugging Face (small model ~100MB)."
)


def _ensure_model_importable(repo_path: Optional[str]) -> None:
    """Put the Kronos ``model`` package on ``sys.path`` if a repo path is set."""
    if repo_path:
        resolved = os.path.abspath(os.path.expanduser(repo_path))
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def _import_kronos(repo_path: Optional[str]):
    """Import the Kronos classes lazily, converting failures into a clear error."""
    _ensure_model_importable(repo_path)
    try:
        import torch  # noqa: F401  (validate torch is present first)
        from model import Kronos, KronosPredictor, KronosTokenizer
    except Exception as exc:  # noqa: BLE001
        raise KronosUnavailable(f"{_INSTALL_HINT}\n\nUnderlying error: {exc}") from exc
    return Kronos, KronosTokenizer, KronosPredictor


class KronosForecaster:
    """Load Kronos once and produce sampled OHLCV forecast paths.

    The predictor is created lazily and cached, so constructing this object is
    cheap and safe even when torch is missing — the cost is only paid on the
    first :meth:`predict_paths` / :meth:`load` call.
    """

    def __init__(self, config: Optional[KronosConfig] = None):
        self.config = config or KronosConfig()
        self._predictor = None  # type: ignore[var-annotated]

    # ── availability ────────────────────────────────────────────────────────
    @staticmethod
    def is_available(repo_path: Optional[str] = None) -> bool:
        """True when torch + the Kronos model package can be imported."""
        try:
            _import_kronos(repo_path)
            return True
        except KronosUnavailable:
            return False

    # ── lifecycle ───────────────────────────────────────────────────────────
    def load(self):
        """Instantiate the underlying ``KronosPredictor`` (idempotent)."""
        if self._predictor is not None:
            return self._predictor

        cfg = self.config
        Kronos, KronosTokenizer, KronosPredictor = _import_kronos(cfg.repo_path)
        logger.info(
            "Loading Kronos model=%s tokenizer=%s device=%s",
            cfg.model,
            cfg.tokenizer,
            cfg.device,
        )
        tokenizer = KronosTokenizer.from_pretrained(cfg.tokenizer)
        model = Kronos.from_pretrained(cfg.model)
        try:
            self._predictor = KronosPredictor(
                model, tokenizer, device=cfg.device, max_context=cfg.max_context
            )
        except TypeError:
            # Older signature without an explicit device kwarg.
            self._predictor = KronosPredictor(model, tokenizer, max_context=cfg.max_context)
        return self._predictor

    # ── inference ───────────────────────────────────────────────────────────
    def predict_paths(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        *,
        pred_len: Optional[int] = None,
        sample_paths: Optional[int] = None,
    ) -> List[pd.DataFrame]:
        """Return a list of stochastic forecast DataFrames (one per path).

        Sampling is stochastic (temperature / top_p), so ``sample_paths`` gives an
        empirical distribution of outcomes for :func:`kronos.signals.derive_signal`.

        For speed we run all paths as a **single batched forward pass** via the
        upstream ``predict_batch`` — we hand it ``sample_paths`` copies of the same
        series (each ``sample_count=1``), so every batch element is an independent
        stochastic draw. On CPU this is dramatically faster than looping
        ``predict`` once per path. If ``predict_batch`` is unavailable (older
        Kronos) or fails, we transparently fall back to the sequential loop.
        """
        cfg = self.config
        pred_len = pred_len or cfg.pred_len
        sample_paths = sample_paths or cfg.sample_paths
        predictor = self.load()

        if sample_paths > 1 and hasattr(predictor, "predict_batch"):
            try:
                df_list = [df] * sample_paths
                xts_list = [x_timestamp] * sample_paths
                yts_list = [y_timestamp] * sample_paths
                preds = predictor.predict_batch(
                    df_list=df_list,
                    x_timestamp_list=xts_list,
                    y_timestamp_list=yts_list,
                    pred_len=pred_len,
                    T=cfg.temperature,
                    top_p=cfg.top_p,
                    sample_count=1,
                    verbose=False,
                )
                return [p.rename(columns=str.lower) for p in preds]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "predict_batch failed (%s); falling back to sequential sampling",
                    exc,
                )

        paths: List[pd.DataFrame] = []
        for i in range(sample_paths):
            pred_df = predictor.predict(
                df=df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=pred_len,
                T=cfg.temperature,
                top_p=cfg.top_p,
                sample_count=1,
                verbose=False,
            )
            pred_df = pred_df.rename(columns=str.lower)
            paths.append(pred_df)
            logger.debug("Sampled forecast path %d/%d", i + 1, sample_paths)
        return paths


__all__ = ["KronosForecaster", "KronosUnavailable"]
