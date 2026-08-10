# Kronos Price Forecast Integration

Consumes [Kronos](https://github.com/shiyu-coder/Kronos) — an open-source
foundation model for OHLCV candlesticks (AAAI 2026) — as a **standalone price
visualization module** for the NSE research system. Enter any ticker(s) in the
**Kronos Forecast Lab** UI page and it fetches full price history, forecasts
future candles with Kronos-base, and renders a chart with a forecast
percentile cone plus a per-symbol **BUY / HOLD / AVOID** summary.

> Indicative only. Kronos is a general-purpose forecaster run **zero-shot** on
> daily NSE bars (out-of-distribution). Read the **shape and spread** of the
> forecast cone — **not** the exact predicted price; absolute levels can be
> biased. This module is fully separate from the trading strategies and their
> backtests.

## Why this design

- **CPU-only, zero-shot.** Kronos-base (102M params) runs on CPU for EOD use.
  No GPU, no finetuning required to start.
- **Torch is isolated + lazy.** Nothing here imports `torch` until you actually
  run a forecast, so the rest of the app (and the registry) works without it.
- **The signal layer is pure.** `signals.py` has no torch/network dependency and
  is fully unit-tested (`tests/test_kronos_signals.py`).

## Layout

```
kronos/
  config.py     # env-backed KronosConfig (model, device, lookback, pred_len…)
  predictor.py  # KronosForecaster: lazy torch + Kronos loader, sampled paths
  signals.py    # PURE: forecast paths -> directional/volatility signal (tested)
  service.py    # fetch OHLCV (yfinance) -> forecast -> signal
  viz.py        # chart-ready payload (history + forecast cone) for the UI page
ui/pages.py     # kronos_page(): the "Kronos Forecast Lab" Streamlit page
```

## Setup (one-time)

Kronos is an **optional dependency** and is **not on PyPI**.

1. Install the Python deps (CPU torch build — no GPU needed):

   ```bash
   uv pip install -e ".[kronos]"
   # or:
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install huggingface_hub einops
   ```

2. Get the model code (the `Kronos` classes live in the repo's `model/` package):

   ```bash
   git clone https://github.com/shiyu-coder/Kronos C:\tools\Kronos
   ```

3. Point the integration at that checkout so `from model import Kronos` resolves:

   ```bash
   setx KRONOS_REPO_PATH C:\tools\Kronos      # Windows (new shell after)
   # export KRONOS_REPO_PATH=/path/to/Kronos   # macOS/Linux
   ```

The first forecast downloads the model weights from Hugging Face (~100 MB for
the base model), cached thereafter.

## Configuration (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `KRONOS_REPO_PATH` | — | Path to the cloned Kronos repo |
| `KRONOS_MODEL` | `NeoQuasar/Kronos-small` | HF model id (the viz page overrides to `Kronos-base`) |
| `KRONOS_TOKENIZER` | `NeoQuasar/Kronos-Tokenizer-base` | HF tokenizer id |
| `KRONOS_DEVICE` | `cpu` | `cpu` or `cuda` |
| `KRONOS_LOOKBACK` | `400` | History bars (clamped to 512 context) |
| `KRONOS_PRED_LEN` | `10` | Forecast horizon (sessions) |
| `KRONOS_SAMPLE_PATHS` | `20` | Stochastic paths for the distribution |
| `KRONOS_TEMPERATURE` | `1.0` | Sampling temperature `T` |
| `KRONOS_TOP_P` | `0.9` | Nucleus sampling |

## Usage

UI — the primary entry point:

```bash
streamlit run app.py
# → Ideas & research → "Kronos Forecast Lab"
# Enter one or more tickers, pick horizon / sample paths, Run forecast.
```

Programmatic (chart-ready payload with the bigger Kronos-base model):

```python
from kronos.viz import base_config, forecast_for_chart

fc = forecast_for_chart("RELIANCE", config=base_config(pred_len=10, sample_paths=20))
print(fc.signal.direction, fc.signal.prob_up)
print(fc.bands)  # per-step p10/p25/p50/p75/p90 close (the forecast cone)
```

Without the setup above, the page shows a clean error carrying these install
instructions — it never crashes the app.

## The signal

For each symbol we sample `sample_paths` forecast paths and compute:

- `prob_up` — fraction of paths finishing above the last close,
- `expected_return` / `expected_close` — mean terminal outcome,
- a **volatility cone** (mean predicted high/low) → `suggested_stop` / `suggested_target`,
- `direction` (BUY/HOLD/AVOID) gated by conviction + reward:risk (thresholds in `signals.py`).

## Note on strategy integration

This module is intentionally **standalone** — it is not wired into any trading
strategy or backtest. A prior experiment using zero-shot Kronos as a confirmation
gate on the swing screen did **not** show a robust edge on daily NSE bars
(absolute forecasts are downward-biased and the cross-sectional rank did not
replicate across windows). If pursued later, NSE finetuning (needs a rented GPU +
Qlib) or a different bar frequency would be the next thing to try.

