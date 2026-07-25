"""Strategy contract shared by every "system" in the platform.

A *strategy* is one way of achieving the same overarching goal — turning
market data into actionable stock research / trading decisions. The
sequential-agent supervisor, the parallel multi-analyst workflow, the
swing-trading copilot, the portfolio analyzer and the watchlist curator
are all strategies.

Every strategy exposes:

* Metadata (``id``, ``name``, ``description``, ``category``) so a UI can
  list it as a selectable option.
* A declarative ``param_specs()`` so a UI can render an input form
  generically — no hard-coded knowledge of any single strategy.
* A single ``run(params) -> StrategyResult`` method so callers invoke every
  strategy the exact same way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ParamType(str, Enum):
    """Input types a UI can render generically from a ``ParamSpec``."""

    STRING = "string"  # single-line text
    TEXT = "text"  # multi-line text
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATE = "date"
    ENUM = "enum"  # one of ``choices``
    SYMBOLS = "symbols"  # comma/space separated tickers -> List[str]
    JSON = "json"  # structured payload (e.g. portfolio / positions)


class StrategyCategory(str, Enum):
    """High-level grouping used to organize options in the UI."""

    RESEARCH = "research"  # multi-agent stock research / recommendations
    SWING = "swing"  # short-term swing trading
    PORTFOLIO = "portfolio"  # portfolio-level analysis / rebalance
    WATCHLIST = "watchlist"  # universe screening / curation
    BACKTEST = "backtest"  # historical strategy validation


@dataclass
class ParamSpec:
    """Declarative description of one strategy input.

    A front end iterates over these to build a form; a CLI maps them to
    flags. Keep them serializable (``asdict``-friendly).
    """

    name: str
    label: str
    type: ParamType
    required: bool = False
    default: Any = None
    help: str = ""
    choices: Optional[List[str]] = None  # only for ParamType.ENUM
    min: Optional[float] = None
    max: Optional[float] = None
    group: str = "Basic"
    advanced: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class StrategyResult:
    """Uniform result envelope returned by every strategy."""

    strategy_id: str
    status: str  # "completed" | "failed"
    report: str = ""  # markdown/text for display
    data: Dict[str, Any] = field(default_factory=dict)  # structured extras
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseStrategy(ABC):
    """Base class every concrete strategy must implement.

    Subclasses set the class attributes below and implement
    :meth:`param_specs` and :meth:`run`.
    """

    id: str = ""
    name: str = ""
    description: str = ""
    long_description: str = ""
    category: StrategyCategory = StrategyCategory.RESEARCH

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #
    @classmethod
    @abstractmethod
    def param_specs(cls) -> List[ParamSpec]:
        """Return the declarative inputs this strategy accepts."""

    @abstractmethod
    def run(self, params: Dict[str, Any]) -> StrategyResult:
        """Execute the strategy with the given (already-parsed) params."""

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def spec(cls) -> Dict[str, Any]:
        """Serializable metadata + param schema — everything a UI needs."""
        return {
            "id": cls.id,
            "name": cls.name,
            "description": cls.description,
            "long_description": cls.long_description,
            "category": cls.category.value,
            "params": [p.to_dict() for p in cls.param_specs()],
        }

    def coerce_params(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply defaults + light coercion based on ``param_specs``.

        Missing optional params get their declared default; ``SYMBOLS`` are
        normalized to an upper-cased list; numeric/bool strings are cast.
        Required params that are still missing raise ``ValueError``.
        """
        params = dict(params or {})
        resolved: Dict[str, Any] = {}
        for spec in self.param_specs():
            value = params.get(spec.name, None)
            if value is None or value == "":
                if spec.required:
                    raise ValueError(
                        f"Missing required parameter '{spec.name}' for strategy '{self.id}'"
                    )
                resolved[spec.name] = spec.default
                continue
            resolved[spec.name] = _coerce_value(spec, value)
        # Preserve any extra params the caller supplied (forward-compatible).
        for key, val in params.items():
            resolved.setdefault(key, val)
        return resolved


def _coerce_value(spec: ParamSpec, value: Any) -> Any:
    t = spec.type
    if t == ParamType.SYMBOLS:
        if isinstance(value, (list, tuple)):
            items = value
        else:
            items = [s for s in str(value).replace(",", " ").split()]
        coerced = [str(s).strip().upper() for s in items if str(s).strip()]
    elif t == ParamType.INT:
        coerced = int(value)
    elif t == ParamType.FLOAT:
        coerced = float(value)
    elif t == ParamType.BOOL:
        if isinstance(value, bool):
            coerced = value
        else:
            coerced = str(value).strip().lower() in ("1", "true", "yes", "y", "on")
    elif t == ParamType.DATE:
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            coerced = value.isoformat()
        else:
            coerced = date.fromisoformat(str(value).strip()).isoformat()
    elif t == ParamType.JSON:
        if isinstance(value, str):
            import json

            coerced = json.loads(value)
        else:
            coerced = value
    else:
        coerced = value

    if spec.choices is not None and coerced not in spec.choices:
        choices = ", ".join(map(str, spec.choices))
        raise ValueError(f"Parameter '{spec.name}' must be one of: {choices}")
    if isinstance(coerced, (int, float)) and not isinstance(coerced, bool):
        if spec.min is not None and coerced < spec.min:
            raise ValueError(f"Parameter '{spec.name}' must be at least {spec.min}")
        if spec.max is not None and coerced > spec.max:
            raise ValueError(f"Parameter '{spec.name}' must be at most {spec.max}")
    return coerced
