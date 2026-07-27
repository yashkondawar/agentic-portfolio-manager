# Kronos Price Forecast Integration

Consumes [Kronos](https://github.com/shiyu-coder/Kronos) — an open-source
foundation model for OHLCV candlesticks (AAAI 2026) — as a **diversifying price
signal** for the NSE research system. It forecasts future candles and turns the
forecast *distribution* into per-symbol **BUY / HOLD / AVOID** calls with a
stop and target.

> Decision-support only. Kronos forecasts candles, not trades. Treat the
> forecast **direction/distribution** as the signal — **not** the exact
> predicted price — and validate any edge in the backtest before risking money.

## Why this design

- **CPU-only, zero-shot.** Kronos-small (24.7M params) runs fine on CPU for
  EOD/swing use. No GPU, no finetuning required to start.
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
strategies/kronos_forecast.py   # BaseStrategy wrapper (shows up in CLI/UI)
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
the small model), cached thereafter.

## Configuration (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `KRONOS_REPO_PATH` | — | Path to the cloned Kronos repo |
| `KRONOS_MODEL` | `NeoQuasar/Kronos-small` | HF model id |
| `KRONOS_TOKENIZER` | `NeoQuasar/Kronos-Tokenizer-base` | HF tokenizer id |
| `KRONOS_DEVICE` | `cpu` | `cpu` or `cuda` |
| `KRONOS_LOOKBACK` | `400` | History bars (clamped to 512 context) |
| `KRONOS_PRED_LEN` | `10` | Forecast horizon (sessions) |
| `KRONOS_SAMPLE_PATHS` | `20` | Stochastic paths for the distribution |
| `KRONOS_TEMPERATURE` | `1.0` | Sampling temperature `T` |
| `KRONOS_TOP_P` | `0.9` | Nucleus sampling |

## Usage

CLI (registered strategy):

```bash
python run.py kronos_forecast --param symbols="RELIANCE,TCS,INFY" \
  --param pred_len=10 --param sample_paths=20
```

Programmatic:

```python
from kronos.config import KronosConfig
from kronos.service import forecast_symbol

res = forecast_symbol("RELIANCE", config=KronosConfig(pred_len=10, sample_paths=20))
print(res.signal.direction, res.signal.prob_up, res.signal.suggested_stop)
```

Without the setup above, the strategy returns a clean `failed` result carrying
these install instructions — it never crashes the app.

## The signal

For each symbol we sample `sample_paths` forecast paths and compute:

- `prob_up` — fraction of paths finishing above the last close,
- `expected_return` / `expected_close` — mean terminal outcome,
- a **volatility cone** (mean predicted high/low) → `suggested_stop` / `suggested_target`,
- `direction` (BUY/HOLD/AVOID) gated by conviction + reward:risk (thresholds in `signals.py`).

## Recommended next step

Wire `kronos.service.forecast_symbol` into the point-in-time backtest
(`backtesting/swing_trading/`) as (a) a standalone signal and (b) a *filter* on
the existing swing playbook, then compare Sharpe / CAGR / max-DD / hit-rate vs.
the current strategies and buy-and-hold NIFTY **with transaction costs**. Only
promote it to live decision-support if it adds risk-adjusted return. Consider
NSE finetuning (needs a rented GPU + Qlib) only if the zero-shot edge is real
but marginal.
