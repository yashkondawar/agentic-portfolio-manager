"""Live GFS (Grandfather / Father / Son) multi-timeframe RSI strategy.

The research harness lives in ``backtesting/gfs``. This package is the *live*
runner, and it deliberately owns as little decision logic as possible: every
entry, stop, exit, ranking and sizing call is made by importing the backtest's
own modules and replaying the backtest's own daily loop over the sessions that
have elapsed since the last run.

See ``gfs/USAGE.md`` for the operating guide.
"""
