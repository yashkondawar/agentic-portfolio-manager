"""Native, close-of-session S18 signals; no research-engine imports.

The reference has one material precision convention: stock tiers compare the
float32 stored d52, whereas ETF tiers compare float64 d52. Beta and AL scores
always use float64 (rounding beta before ranking changes the result).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

NO_RANK = 32767
RF21 = 1.065 ** (21 / 252) - 1


def forward_close(close: np.ndarray) -> np.ndarray:
    """Carry suspensions and terminal gaps forward, never backfill an IPO."""
    close = np.asarray(close, dtype=np.float64)
    if close.ndim != 2 or not len(close):
        raise ValueError("close must be a nonempty sessions-by-companies matrix")
    indices = np.where(np.isfinite(close), np.arange(len(close))[:, None], 0)
    np.maximum.accumulate(indices, axis=0, out=indices)
    return np.take_along_axis(close, indices, axis=0)


def _window_sum(values: np.ndarray, window: int) -> np.ndarray:
    prefix = np.zeros((len(values) + 1,) + values.shape[1:], dtype=np.float64)
    np.cumsum(values, axis=0, out=prefix[1:])
    result = np.full(values.shape, np.nan, dtype=np.float64)
    if len(values) >= window:
        result[window - 1 :] = prefix[window:] - prefix[:-window]
    return result


def rolling_beta(close: np.ndarray, benchmark: np.ndarray) -> np.ndarray:
    """252 daily returns, at least 200 pairs, including carried zero returns."""
    prices = forward_close(close)
    benchmark = np.asarray(benchmark, dtype=np.float64)
    if benchmark.shape != (len(prices),):
        raise ValueError("benchmark length must equal close sessions")
    market_return = np.full(len(prices), np.nan)
    market_return[1:] = benchmark[1:] / benchmark[:-1] - 1
    result = np.full(prices.shape, np.nan)
    # Column chunks limit peak memory without changing per-column summation.
    for start in range(0, prices.shape[1], 128):
        part = prices[:, start : start + 128]
        returns = np.full(part.shape, np.nan)
        returns[1:] = part[1:] / part[:-1] - 1
        valid = np.isfinite(returns) & np.isfinite(market_return[:, None])
        x = np.where(valid, market_return[:, None], 0)
        y = np.where(valid, returns, 0)
        count, sx, sy, sxy, sxx = (
            _window_sum(a, 252) for a in (valid, x, y, x * y, x * x)
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            variance = sxx - sx * sx / count
            beta = (sxy - sx * sy / count) / variance
        result[:, start : start + 128] = np.where(
            (count >= 200) & (variance > 0) & np.isfinite(beta), beta, np.nan
        )
    return result


def alpha_score(
    close: np.ndarray,
    benchmark: np.ndarray,
    membership: np.ndarray,
    rows: np.ndarray,
    beta: np.ndarray,
    *,
    lookback: int,
    gap: int,
) -> np.ndarray:
    """Compounded Jensen excess of 21-session blocks using beta at decision t."""
    prices = forward_close(close)
    rows = np.asarray(rows, dtype=np.int64)
    if lookback < 1 or gap < 0:
        raise ValueError("lookback must be positive and gap nonnegative")
    if (
        membership.shape != prices.shape
        or beta.shape != prices.shape
        or np.asarray(benchmark).shape != (len(prices),)
        or rows.ndim != 1
        or np.any((rows < 0) | (rows >= len(prices)))
    ):
        raise ValueError("Invalid AL input shapes or row range")
    blocks = np.full(prices.shape, np.nan)
    blocks[21:] = prices[21:] / prices[:-21] - 1
    index_blocks = np.full(len(prices), np.nan)
    index_blocks[21:] = benchmark[21:] / benchmark[:-21] - 1
    product = np.ones((len(rows), prices.shape[1]))
    for block in range(lookback):
        ends = rows - 21 * (gap + block)
        good = ends >= 21
        factor = np.full(product.shape, np.nan)
        factor[good] = 1 + (
            blocks[ends[good]]
            - (RF21 + beta[rows[good]] * (index_blocks[ends[good], None] - RF21))
        )
        product *= factor
    score = product - 1
    has_price = np.isfinite(close)
    first = np.where(has_price.any(0), has_price.argmax(0), len(close))
    history = first[None, :] <= (rows - 21 * (gap + lookback))[:, None]
    score[~(membership[rows] & history)] = np.nan
    return score


def rank_scores(score: np.ndarray) -> np.ndarray:
    """Rank finite scores, descending, with lower company id breaking ties."""
    if score.ndim != 2 or score.shape[1] >= NO_RANK:
        raise ValueError("Score matrix exceeds the int16 rank range")
    ranked = np.full(score.shape, NO_RANK, dtype=np.int16)
    for i, values in enumerate(score):
        eligible = np.flatnonzero(np.isfinite(values))
        order = eligible[np.lexsort((eligible, -values[eligible]))]
        ranked[i, order] = np.arange(1, len(order) + 1)
    return ranked


def order_from_ranks(rank: np.ndarray, width: int | None = None) -> np.ndarray:
    needed = int(np.max((rank < NO_RANK).sum(1), initial=0))
    width = needed if width is None else width
    if width < needed or width > rank.shape[1]:
        raise ValueError("Order capacity cannot truncate rankable stocks")
    order = np.full((len(rank), width), -1, dtype=np.int16)
    for i, row in enumerate(rank):
        gids = np.flatnonzero(row < NO_RANK)
        order[i, : len(gids)] = gids[np.argsort(row[gids], kind="stable")]
    return order


def metal_ranks(stock_score: np.ndarray, metal_score: np.ndarray) -> np.ndarray:
    """ETF rank among stocks only; an ETF wins a tie against a stock."""
    result = np.full(metal_score.shape, NO_RANK, dtype=np.int16)
    for j in range(metal_score.shape[1]):
        good = np.isfinite(metal_score[:, j])
        result[good, j] = 1 + (stock_score[good] > metal_score[good, j, None]).sum(1)
    return result


def insert_metal_ranks(
    stocks: np.ndarray, metals: np.ndarray, scores: np.ndarray
) -> np.ndarray:
    shifted = stocks.astype(np.int32)
    for j in range(metals.shape[1]):
        shifted += metals[:, j, None] <= stocks
    shifted[stocks == NO_RANK] = NO_RANK
    extra = metals.astype(np.int32).copy()
    scores = np.where(np.isfinite(scores), scores, -np.inf)
    for j in range(metals.shape[1]):
        extra[:, j] += (scores > scores[:, j, None]).sum(1)
    extra[metals == NO_RANK] = NO_RANK
    return np.minimum(np.column_stack((shifted, extra)), NO_RANK).astype(np.int16)


def insert_metal_order(
    stock_order: np.ndarray,
    stock_rank: np.ndarray,
    relative_rank: np.ndarray,
    scores: np.ndarray,
) -> np.ndarray:
    """Reproduce score insertion without re-ranking cached stock scores."""
    n_stocks = stock_rank.shape[1]
    count = relative_rank.shape[1]
    result = np.full((len(stock_order), stock_order.shape[1] + count), -1, np.int16)
    scores = np.where(np.isfinite(scores), scores, -np.inf)
    for i in range(len(result)):
        stocks = stock_order[i][stock_order[i] >= 0]
        metals = np.flatnonzero(relative_rank[i] < NO_RANK)
        precedence = (scores[i, None, :] > scores[i, :, None]).sum(1)
        keys = np.concatenate(
            (
                stock_rank[i, stocks],
                relative_rank[i, metals] - 0.5 + 0.1 * precedence[metals],
            )
        )
        gids = np.concatenate((stocks, metals + n_stocks))
        result[i, : len(gids)] = gids[np.argsort(keys, kind="stable")]
    return result


@dataclass
class SignalPanel:
    beta: np.ndarray
    d52: np.ndarray
    buy_score: np.ndarray
    sell_score: np.ndarray
    buy_rank: np.ndarray
    sell_rank: np.ndarray
    buy_order: np.ndarray
    x63: np.ndarray
    sc15: np.ndarray
    at_high: np.ndarray
    risk_off: np.ndarray
    metal_buy_rank: np.ndarray
    metal_sell_rank: np.ndarray


def compute_signals(
    close: np.ndarray,
    benchmark: np.ndarray,
    membership: np.ndarray,
    rows: np.ndarray,
    *,
    n_stocks: int | None = None,
) -> SignalPanel:
    """Compute only S18's two AL signals and gates from complete warm-up prices."""
    close = np.asarray(close, dtype=np.float64)
    benchmark = np.asarray(benchmark, dtype=np.float64)
    membership = np.asarray(membership)
    rows = np.asarray(rows)
    if (
        close.ndim != 2
        or not len(close)
        or close.shape[1] >= NO_RANK
        or membership.dtype != np.bool_
        or membership.shape != close.shape
        or benchmark.shape != (len(close),)
        or rows.ndim != 1
        or rows.dtype.kind not in "iu"
        or not len(rows)
        or np.any((rows < 0) | (rows >= len(close)))
        or np.any(np.diff(rows) <= 0)
    ):
        raise ValueError("Invalid signal panel shape, membership dtype, or row range")
    if (
        np.isinf(close).any()
        or np.any(close[np.isfinite(close)] <= 0)
        or not np.isfinite(benchmark).all()
        or np.any(benchmark <= 0)
    ):
        raise ValueError("Prices must be positive finite values or missing stock bars")
    n_stocks = close.shape[1] if n_stocks is None else n_stocks
    if not 0 < n_stocks <= close.shape[1]:
        raise ValueError("n_stocks must identify the leading stock columns")
    beta = rolling_beta(close, benchmark)
    buy = alpha_score(close, benchmark, membership, rows, beta, lookback=6, gap=1)
    sell = alpha_score(close, benchmark, membership, rows, beta, lookback=3, gap=2)
    prices = forward_close(close)
    high = pd.DataFrame(prices).rolling(252, min_periods=252).max().to_numpy()
    distance = prices / high - 1
    known = np.isfinite(distance)
    crossed = known & (distance >= -1e-12)
    last = np.where(crossed, np.arange(len(prices))[:, None], -NO_RANK)
    np.maximum.accumulate(last, axis=0, out=last)
    x63 = known & ((np.arange(len(prices))[:, None] - last) < 63)
    # 02e_prox rounds stocks before thresholding; 132 does not round ETFs.
    tier_distance = distance[rows].copy()
    tier_distance[:, :n_stocks] = tier_distance[:, :n_stocks].astype(np.float32)
    stock_distance = tier_distance[:, :n_stocks].astype(np.float32)
    at_high = tier_distance >= -1e-12
    sc15 = tier_distance >= -0.15 - 1e-12
    at_high[:, :n_stocks] = stock_distance >= -1e-12
    sc15[:, :n_stocks] = stock_distance >= -0.15 - 1e-12
    buy_rank = rank_scores(buy[:, :n_stocks])
    sell_rank = rank_scores(sell[:, :n_stocks])
    return SignalPanel(
        beta=beta[rows],
        d52=tier_distance,
        buy_score=buy,
        sell_score=sell,
        buy_rank=buy_rank,
        sell_rank=sell_rank,
        buy_order=order_from_ranks(
            buy_rank, int(membership[rows, :n_stocks].sum(1).max())
        ),
        x63=x63[rows],
        sc15=sc15,
        at_high=at_high,
        risk_off=(benchmark < _window_sum(benchmark, 100) / 100)[rows],
        metal_buy_rank=metal_ranks(buy[:, :n_stocks], buy[:, n_stocks:]),
        metal_sell_rank=metal_ranks(sell[:, :n_stocks], sell[:, n_stocks:]),
    )
