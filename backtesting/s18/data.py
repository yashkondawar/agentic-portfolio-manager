"""Validated database-owned S18 panels and the prepared-market contract.

Product reads never unpack or consult an experiment folder. Folder adapters
remain available solely to the one-time importer and synthetic fixture tests.
"""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

import numpy as np

from . import signals
from .dataset import AssetReader, FolderSource, get_dataset

PRICE_FIELDS = ("open", "high", "low", "close")
METAL_NAMES = ("GOLD", "SILVER")
METAL_SYMBOLS = ("GOLDBEES", "SILVERBEES")
METAL_IDENTITIES = ("ISIN:INF204KB17I5", "ISIN:INF204KC1402")


def validate_dates(values: np.ndarray, name: str = "dates") -> None:
    if (
        values.ndim != 1
        or not len(values)
        or values.dtype != np.dtype("datetime64[D]")
        or np.isnat(values).any()
        or np.any(np.diff(values).astype(np.int64) <= 0)
    ):
        raise ValueError(f"{name} must be unique increasing datetime64[D] sessions")


def validate_prices(
    prices: dict[str, np.ndarray], shape: tuple[int, int], *, incomplete: bool = False
) -> None:
    for name in PRICE_FIELDS:
        value = prices[name]
        if value.shape != shape or value.dtype.kind != "f":
            raise ValueError(f"{name} must be a floating OHLC matrix of shape {shape}")
        if np.isinf(value).any() or np.any(value[np.isfinite(value)] <= 0):
            raise ValueError(f"{name} contains nonpositive or infinite prices")
    close = prices["close"]
    traded = np.isfinite(close)
    for name in PRICE_FIELDS[:-1]:
        if not incomplete and np.any(traded & ~np.isfinite(prices[name])):
            raise ValueError(f"{name} is missing on a traded close")
    if (
        np.any(traded & (prices["low"] > np.minimum(prices["open"], close)))
        or np.any(traded & (prices["high"] < np.maximum(prices["open"], close)))
        or np.any(traded & (prices["low"] > prices["high"]))
    ):
        raise ValueError("OHLC high/low range is inconsistent")


def content_provenance(root: Path, paths: list[Path]) -> dict:
    digest = hashlib.sha256()
    files = {}
    for path in sorted(set(paths)):
        file_hash = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                file_hash.update(chunk)
        name = path.relative_to(root).as_posix()
        checksum = file_hash.hexdigest()
        files[name] = checksum
        digest.update(name.encode("utf-8") + b"\0" + checksum.encode("ascii"))
    return {"content_hash": digest.hexdigest(), "files": files}


@dataclass
class RawMarket:
    dates: np.ndarray
    prices: dict[str, np.ndarray]
    universe: np.ndarray
    benchmark: np.ndarray
    rows: np.ndarray
    symbols: tuple[str, ...]
    identities: tuple[str, ...]
    isin_chains: tuple[tuple[str, ...], ...]
    n_stocks: int
    provenance: dict


@dataclass
class PreparedMarket:
    dates: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    tradable: np.ndarray
    last_rows: np.ndarray
    benchmark: np.ndarray
    risk_off: np.ndarray
    buy_order: np.ndarray
    sell_rank: np.ndarray
    s2_buy_order: np.ndarray
    s2_sell_rank: np.ndarray
    x63: np.ndarray
    sc15: np.ndarray
    at_high: np.ndarray
    symbols: tuple[str, ...]
    identities: tuple[str, ...]
    n_stocks: int
    provenance: dict
    _orders: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        validate_dates(self.dates)
        shape = (len(self.dates), len(self.symbols))
        if len(set(self.identities)) != shape[1] or len(self.identities) != shape[1]:
            raise ValueError("Company identities must be unique and match the columns")
        if not 0 < self.n_stocks <= shape[1]:
            raise ValueError("Invalid stock column count")
        for name in PRICE_FIELDS:
            values = getattr(self, name)
            if (
                values.shape != shape
                or values.dtype != np.float64
                or not np.isfinite(values).all()
                or np.any(values < 0)
            ):
                raise ValueError(f"{name} must contain finite float64 valuation prices")
        for name in ("tradable", "x63", "sc15", "at_high"):
            value = getattr(self, name)
            if value.shape != shape or value.dtype != np.bool_:
                raise ValueError(f"Invalid {name} shape or bool dtype")
        if np.any(self.tradable & ((self.open <= 0) | (self.close <= 0))):
            raise ValueError("Tradable bars require positive open and close")
        if (
            self.last_rows.shape != (shape[1],)
            or self.last_rows.dtype.kind not in "iu"
            or np.any((self.last_rows < -1) | (self.last_rows >= shape[0]))
        ):
            raise ValueError("Invalid last_rows range")
        if (
            self.benchmark.shape != (shape[0],)
            or not np.isfinite(self.benchmark).all()
            or np.any(self.benchmark <= 0)
            or self.risk_off.shape != (shape[0],)
            or self.risk_off.dtype != np.bool_
        ):
            raise ValueError("Invalid benchmark or risk_off series")
        for name in ("sell_rank", "s2_sell_rank"):
            rank = getattr(self, name)
            if (
                rank.shape != shape
                or rank.dtype.kind not in "iu"
                or np.any((rank < 1) | (rank > signals.NO_RANK))
            ):
                raise ValueError(f"Invalid {name} shape or rank range")
        for name, limit in (("buy_order", shape[1]), ("s2_buy_order", self.n_stocks)):
            order = getattr(self, name)
            _validate_order(order, shape[0], limit, name)
        if np.any(self.s2_sell_rank[:, self.n_stocks :] != signals.NO_RANK):
            raise ValueError("S2 must never rank metals")
        json.dumps(self.provenance, allow_nan=False)

    def s1_order(self, tiered: bool, priority: bool) -> np.ndarray:
        """Stable high/sc15/remainder tiers, then optional metals-first walk."""
        key = (bool(tiered), bool(priority))
        if key not in self._orders:
            result = self.buy_order.copy()
            for i, row in enumerate(result):
                gids = row[row >= 0]
                if tiered:
                    tier = np.where(
                        self.at_high[i, gids], 0, np.where(self.sc15[i, gids], 1, 2)
                    )
                    gids = gids[np.argsort(tier, kind="stable")]
                if priority:
                    gids = np.concatenate(
                        (gids[gids >= self.n_stocks], gids[gids < self.n_stocks])
                    )
                result[i, : len(gids)] = gids
            self._orders[key] = np.ascontiguousarray(result)
        return self._orders[key]


def _validate_order(order, nrows, limit, name):
    if (
        order.ndim != 2
        or order.shape[0] != nrows
        or order.dtype.kind not in "iu"
        or np.any((order < -1) | (order >= limit))
    ):
        raise ValueError(f"Invalid {name} shape or gid range")
    for row in order:
        good = row >= 0
        if np.any(np.diff(good.astype(np.int8)) > 0):
            raise ValueError(f"{name} padding must be at the end")
        if len(np.unique(row[good])) != good.sum():
            raise ValueError(f"{name} contains duplicate company ids")


def load_raw_kit(path: Path | str, *, metals: bool = False) -> RawMarket:
    """Read-only one-time import adapter; product code uses load_raw_market."""
    return load_raw_market(source=FolderSource(path), metals=metals)


def load_raw_market(
    *, source: AssetReader | None = None, metals: bool = False
) -> RawMarket:
    source = source or get_dataset()
    names = [f"{f}.npy" for f in PRICE_FIELDS]
    names += [
        "dates.npy",
        "universe.npy",
        "nifty500.npy",
        "signals/rows.npy",
        "companies.csv",
    ]
    if metals:
        names.append("ext/gold_silver.npz")
    names = [f"data/{name}" for name in names]
    source.require(names)
    dates = source.array("data/dates.npy")
    validate_dates(dates)
    prices = {name: source.array(f"data/{name}.npy") for name in PRICE_FIELDS}
    if prices["close"].ndim != 2 or prices["close"].shape[0] != len(dates):
        raise ValueError("Close panel does not match the session calendar")
    shape = prices["close"].shape
    validate_prices(prices, shape)
    n_stocks = shape[1]
    if not 0 < n_stocks < signals.NO_RANK - 2:
        raise ValueError("Kit company count is outside the supported gid range")
    universe = source.array("data/universe.npy")
    if universe.shape != shape or universe.dtype != np.bool_:
        raise ValueError("universe must be a point-in-time bool price-shaped matrix")
    if np.any(universe & ~np.isfinite(prices["close"])):
        raise ValueError("Kit universe contains a non-traded stock")
    benchmark = source.array("data/nifty500.npy")
    if (
        benchmark.shape != (len(dates),)
        or benchmark.dtype.kind != "f"
        or not np.isfinite(benchmark).all()
        or np.any(benchmark <= 0)
    ):
        raise ValueError("nifty500 must contain a positive close for every session")
    rows = source.array("data/signals/rows.npy")
    if (
        rows.ndim != 1
        or not len(rows)
        or rows.dtype.kind not in "iu"
        or rows[0] < 0
        or rows[-1] != len(dates) - 1
        or not np.array_equal(rows, np.arange(rows[0], len(dates)))
        or dates[rows[0]] != np.datetime64("2013-12-31")
    ):
        raise ValueError(
            "Engine rows must be contiguous from 2013-12-31 through the panel"
        )
    companies = source.csv(
        "data/companies.csv", dtype=str, keep_default_na=False
    ).to_dict("records")
    if len(companies) != n_stocks:
        raise ValueError("companies.csv does not match the price columns")
    symbols, identities, chains = [], [], []
    all_isins = set()
    for gid, company in enumerate(companies):
        if int(company.get("gid", -1)) != gid:
            raise ValueError("companies.csv gids must be contiguous and column-ordered")
        chain = tuple(company.get("isins", "").split("|"))
        symbol = company.get("symbols", "").split("|")[0]
        if (
            not symbol
            or any(not x or len(x) != 12 or not x.isalnum() for x in chain)
            or len(set(chain)) != len(chain)
            or all_isins.intersection(chain)
        ):
            raise ValueError(f"Invalid or ambiguous company ISIN chain at gid {gid}")
        all_isins.update(chain)
        symbols.append(symbol)
        chains.append(chain)
        identities.append("ISIN:" + chain[0])
    if metals:
        with source.archive("data/ext/gold_silver.npz") as archive:
            missing = {"dates", *METAL_NAMES} - set(archive.files)
            if missing:
                raise ValueError(f"Raw ETF archive is missing keys: {sorted(missing)}")
            if not np.array_equal(archive["dates"], dates):
                raise ValueError("Raw ETF dates do not match stock price dates")
            blocks = [archive[name] for name in METAL_NAMES]
        for block in blocks:
            if block.shape != (len(dates), 4):
                raise ValueError(
                    "Raw ETF OHLC must have one four-price row per session"
                )
            validate_prices(
                dict(zip(PRICE_FIELDS, (block[:, j : j + 1] for j in range(4)))),
                (len(dates), 1),
                incomplete=True,
            )
        for j, name in enumerate(PRICE_FIELDS):
            prices[name] = np.column_stack((prices[name], *(x[:, j] for x in blocks)))
        universe = np.column_stack((universe, np.ones((len(dates), 2), dtype=bool)))
        symbols.extend(METAL_SYMBOLS)
        identities.extend(METAL_IDENTITIES)
        chains.extend((identity[5:],) for identity in METAL_IDENTITIES)
    provenance = source.provenance(names)
    canonical = tuple(identities[:n_stocks]) + METAL_IDENTITIES
    provenance.update(
        **source.origin,
        warmup_start=str(dates[0]),
        warmup_end=str(dates[-1]),
        price_scale="kit_ending_share_units",
        price_scales={identity: 1.0 for identity in canonical},
        canonical_identities=list(canonical),
        canonical_indices={identity: i for i, identity in enumerate(canonical)},
        engine_indices={identity: i for i, identity in enumerate(identities)},
        session_calendar=[str(day) for day in dates],
        calendar_complete_through=str(dates[-1]),
        dividends=False,
        metal_history=(
            "Kit GOLD/SILVER inputs; SILVER before 2022-02-07 is a proxy"
            if metals
            else "disabled"
        ),
    )
    return RawMarket(
        dates,
        prices,
        universe,
        benchmark.astype(np.float64),
        rows.astype(np.int64),
        tuple(symbols),
        tuple(identities),
        tuple(chains),
        n_stocks,
        provenance,
    )


def prepare_market(
    raw: RawMarket, signal: signals.SignalPanel, *, last_rows: np.ndarray | None = None
) -> PreparedMarket:
    rows = raw.rows
    cff = np.nan_to_num(signals.forward_close(raw.prices["close"]), nan=0)
    tradable = np.isfinite(raw.prices["close"])[rows]
    tradable[:, raw.n_stocks :] &= np.isfinite(raw.prices["open"][rows, raw.n_stocks :])
    values = {"close": cff[rows]}
    if raw.n_stocks < len(raw.symbols):
        metal_close = np.where(
            tradable[:, raw.n_stocks :],
            raw.prices["close"][rows, raw.n_stocks :],
            np.nan,
        )
        values["close"][:, raw.n_stocks :] = np.nan_to_num(
            signals.forward_close(metal_close), nan=0
        )
    for name in PRICE_FIELDS[:-1]:
        valid = tradable & np.isfinite(raw.prices[name][rows])
        values[name] = np.where(valid, raw.prices[name][rows], values["close"])
    if last_rows is None:
        last_rows = np.full(len(raw.symbols), -1, dtype=np.int64)
        has = tradable.any(0)
        last_rows[has] = len(rows) - 1 - tradable[::-1, has].argmax(0)
        last_rows[raw.n_stocks :] = len(rows) - 1
    n_metals = len(raw.symbols) - raw.n_stocks
    buy_order = signal.buy_order
    sell_rank = signal.sell_rank
    s2_rank = np.column_stack(
        (sell_rank, np.full((len(rows), n_metals), signals.NO_RANK, dtype=np.int16))
    )
    if n_metals:
        buy_order = signals.insert_metal_order(
            signal.buy_order,
            signal.buy_rank,
            signal.metal_buy_rank,
            signal.buy_score[:, raw.n_stocks :],
        )
        sell_rank = signals.insert_metal_ranks(
            signal.sell_rank,
            signal.metal_sell_rank,
            signal.sell_score[:, raw.n_stocks :],
        )
    return PreparedMarket(
        dates=raw.dates[rows],
        **{k: np.ascontiguousarray(v) for k, v in values.items()},
        tradable=np.ascontiguousarray(tradable),
        last_rows=last_rows,
        benchmark=raw.benchmark[rows],
        risk_off=signal.risk_off,
        buy_order=buy_order,
        sell_rank=sell_rank,
        s2_buy_order=signal.buy_order,
        s2_sell_rank=s2_rank,
        x63=signal.x63,
        sc15=signal.sc15,
        at_high=signal.at_high,
        symbols=raw.symbols,
        identities=raw.identities,
        n_stocks=raw.n_stocks,
        provenance=raw.provenance,
    )


def _cached_signals(raw: RawMarket, source: AssetReader) -> signals.SignalPanel:
    names = [
        "signals/AL_L6_G1_rank.npy",
        "signals/AL_L3_G2_rank.npy",
        "signals/AL_L6_G1_orderfull.npy",
        "gates_fresh.npy",
        "gates_tier.npy",
    ]
    metals = len(raw.symbols) > raw.n_stocks
    if metals:
        names.append("ext/etf_signals.npz")
    names = [f"data/{name}" for name in names]
    source.require(names)
    arrays = [source.array(name) for name in names[:5]]
    buy, sell, order, fresh, tiers = arrays
    shape = (len(raw.rows), raw.n_stocks)
    for name, rank in (("buy", buy), ("sell", sell)):
        if (
            rank.shape != shape
            or rank.dtype.kind not in "iu"
            or np.any((rank < 1) | (rank > signals.NO_RANK))
        ):
            raise ValueError(f"Invalid cached {name} ranks")
        for row in rank:
            ranked = np.sort(row[row < signals.NO_RANK])
            if not np.array_equal(ranked, np.arange(1, len(ranked) + 1)):
                raise ValueError(f"Cached {name} ranks are not a permutation")
    _validate_order(order, shape[0], shape[1], "cached buy order")
    if not np.array_equal(order, signals.order_from_ranks(buy, order.shape[1])):
        raise ValueError("Cached buy order does not match its full ranks")
    if (
        fresh.shape != (8, *shape)
        or tiers.shape != (5, *shape)
        or fresh.dtype != np.bool_
        or tiers.dtype != np.bool_
    ):
        raise ValueError("Invalid cached gate/tier arrays")
    total = len(raw.symbols)
    blank = np.full((shape[0], total), np.nan)
    buy_score, sell_score = blank.copy(), blank.copy()
    metal_buy = np.empty((shape[0], 0), np.int16)
    metal_sell = metal_buy.copy()
    x63, sc15, at_high = fresh[6], tiers[3], tiers[0]
    if metals:
        with source.archive("data/ext/etf_signals.npz") as archive:
            required = {
                f"{prefix}|{metal}|{key}"
                for prefix in ("rank", "score")
                for metal in METAL_NAMES
                for key in ("AL_L6_G1", "AL_L3_G2")
            } | {f"{key}|{metal}" for key in ("fresh", "tier") for metal in METAL_NAMES}
            if required - set(archive.files):
                raise ValueError(
                    "Cached ETF archive is missing required S18 signal keys"
                )

            def vectors(prefix, key):
                result = np.column_stack(
                    [archive[f"{prefix}|{m}|{key}"] for m in METAL_NAMES]
                )
                if result.shape != (shape[0], 2):
                    raise ValueError(f"Invalid cached ETF {prefix} shape")
                if prefix == "rank" and (
                    result.dtype.kind not in "iu"
                    or np.any((result < 1) | (result > signals.NO_RANK))
                ):
                    raise ValueError("Invalid cached ETF rank values")
                if prefix == "score" and (
                    result.dtype.kind != "f" or np.isinf(result).any()
                ):
                    raise ValueError("Invalid cached ETF score values")
                return result

            metal_buy = vectors("rank", "AL_L6_G1")
            metal_sell = vectors("rank", "AL_L3_G2")
            buy_score[:, raw.n_stocks :] = vectors("score", "AL_L6_G1")
            sell_score[:, raw.n_stocks :] = vectors("score", "AL_L3_G2")
            for target, key, index, count in (
                ("x63", "fresh", 6, 8),
                ("sc15", "tier", 3, 5),
                ("at_high", "tier", 0, 5),
            ):
                blocks = [archive[f"{key}|{m}"] for m in METAL_NAMES]
                if any(
                    b.shape != (count, shape[0]) or b.dtype != np.bool_ for b in blocks
                ):
                    raise ValueError("Invalid cached ETF gate arrays")
                extra = np.column_stack([b[index] for b in blocks])
                if target == "x63":
                    x63 = np.column_stack((x63, extra))
                elif target == "sc15":
                    sc15 = np.column_stack((sc15, extra))
                else:
                    at_high = np.column_stack((at_high, extra))
    raw.provenance.update(source.provenance([*raw.provenance["files"], *names]))
    index = raw.benchmark
    risk_off = (index < signals._window_sum(index, 100) / 100)[raw.rows]
    return signals.SignalPanel(
        blank,
        blank,
        buy_score,
        sell_score,
        buy,
        sell,
        order,
        x63,
        sc15,
        at_high,
        risk_off,
        metal_buy,
        metal_sell,
    )


def load_kit(
    path: Path | str, *, metals: bool = False, recompute: bool = True
) -> PreparedMarket:
    """Maintenance/test adapter; never selected implicitly by product services."""
    return load_market(source=FolderSource(path), metals=metals, recompute=recompute)


def load_market(
    *, source: AssetReader | None = None, metals: bool = False, recompute: bool = True
) -> PreparedMarket:
    source = source or get_dataset()
    raw = load_raw_market(source=source, metals=metals)
    if recompute:
        panel = signals.compute_signals(
            raw.prices["close"],
            raw.benchmark,
            raw.universe,
            raw.rows,
            n_stocks=raw.n_stocks,
        )
    else:
        panel = _cached_signals(raw, source)
    raw.provenance.update(
        stock_signals="recomputed" if recompute else "cached",
        metal_signals=(
            ("recomputed" if recompute else "cached") if metals else "disabled"
        ),
        signals_version="s18-native-v1",
        n_stocks=raw.n_stocks,
    )
    return prepare_market(raw, panel)
