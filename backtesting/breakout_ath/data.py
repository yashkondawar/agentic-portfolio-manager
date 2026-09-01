"""Loading prices for the ATH breakout sleeve.

The lifetime-high filter is expanding, so it is only correct if the store holds
a stock's whole listed history. Everything here therefore reads *unbounded*
history and lets the engine trim the trading calendar afterwards, rather than
downloading a window around the backtest dates.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional, Sequence

import pandas as pd

from backtesting.breakout_ath.config import AthBreakoutConfig
from backtesting.breakout_ath.engine import PriceBundle
from backtesting.breakout_ath.universe import UniverseMember, load_universe
from core import bars

logger = logging.getLogger(__name__)

#: Earliest date worth asking the price store for. NSE screens predate this,
#: but nothing usable for a systematic backtest does.
HISTORY_START = date(1996, 1, 1)


def sync_prices(
    tickers: Sequence[str], *, end: Optional[date] = None, force: bool = False
) -> None:
    """Fill any gaps in the store for ``tickers`` over their full history."""
    bars.sync(list(tickers), HISTORY_START, end or date.today(), force=force)


def _wide_closes(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    series = {
        f"{symbol}.NS": frame["Close"].astype(float)
        for symbol, frame in frames.items()
        if frame is not None and not frame.empty and "Close" in frame
    }
    if not series:
        raise ValueError("Price store returned no closes for the universe")
    wide = pd.DataFrame(series).sort_index()
    wide.index = pd.to_datetime(wide.index).normalize()
    return wide[~wide.index.duplicated(keep="last")]


def _index_frame(symbol: str, end: Optional[date]) -> Optional[pd.DataFrame]:
    frame = bars.read_symbol(symbol, None, end)
    if frame is None or frame.empty:
        logger.warning("No history for index %s", symbol)
        return None
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    return frame


def load_prices(
    cfg: AthBreakoutConfig,
    *,
    members: Optional[List[UniverseMember]] = None,
    download: bool = False,
) -> PriceBundle:
    """Assemble the price bundle the engine runs on."""
    members = members or load_universe()
    tickers = [m.ticker for m in members]

    if download:
        sync_prices(tickers + [cfg.benchmark, cfg.broad_index], end=cfg.end_date)

    frames = bars.read_bars(tickers, None, cfg.end_date)
    closes = _wide_closes(frames)
    logger.info(
        "Loaded %d of %d universe names, %s to %s",
        closes.shape[1],
        len(tickers),
        closes.index[0].date(),
        closes.index[-1].date(),
    )

    return PriceBundle(
        closes=closes,
        industries={m.ticker: m.industry for m in members},
        benchmark=_index_frame(cfg.benchmark, cfg.end_date),
        broad=_index_frame(cfg.broad_index, cfg.end_date),
    )
