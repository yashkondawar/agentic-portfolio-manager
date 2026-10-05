"""The five preselected S18 books; these are not a parameter search."""

from dataclasses import dataclass
import math

COST = 0.0002
RF_DAILY = 1.065 ** (1 / 252) - 1
METAL_MODES = ("none", "both", "both_priority")
COMBOS = ("P5", "P10", "P15", "P20", "A20")
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class S18Config:
    combo: str = "P15"
    metal_mode: str = "both_priority"

    def __post_init__(self):
        if self.combo not in COMBOS:
            raise ValueError(f"Unknown S18 combo {self.combo!r}; choose {COMBOS}")
        if self.metal_mode not in METAL_MODES:
            raise ValueError(f"Unknown S18 metal mode {self.metal_mode!r}")

    @property
    def n(self) -> int:
        return int(self.combo[1:])

    @property
    def stop_fraction(self) -> float:
        return 0.20 if self.combo == "P5" else 0.25

    @property
    def tiered(self) -> bool:
        return self.combo in ("P15", "P20")

    @property
    def clear_threshold(self) -> int:
        return math.ceil(0.8 * self.n)

    def weight(self, gid: int, n_stocks: int) -> int:
        return 2 if gid >= n_stocks and self.n > 15 else 1


def validate_capital(capital: float) -> float:
    value = float(capital)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Capital must be a finite positive number")
    return value
