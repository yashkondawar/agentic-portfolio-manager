"""Whole exchange-share sizing over S18's adjusted price panel."""

import math

from .config import COST


class ExecutionDataError(ValueError):
    """Execution must stop until price units or corporate actions are resolved."""

    def __init__(self, message, *, identity=None):
        self.identity = identity
        super().__init__(message)


def quote_factor(market, identity: str, row: int) -> float:
    historical = getattr(market, "execution_factors", None)
    if historical is not None:
        factor = float(historical[row, market.identities.index(identity)])
        if not math.isfinite(factor) or factor <= 0:
            raise ExecutionDataError(
                f"Missing verified exchange quote for {identity} on {market.dates[row]}",
                identity=identity,
            )
        return factor
    scales = market.provenance.get("raw_to_book")
    if not isinstance(scales, dict) or identity not in scales:
        raise ValueError(f"Missing current quote conversion for {identity}")
    factor = float(scales[identity])
    day = str(market.dates[row])
    # The entire panel is rebased to its final session. Undo later share changes
    # to recover the actual exchange quote/quantity on an earlier fill date.
    for event in market.provenance.get("raw_to_book_events", []):
        if event["identity"] == identity and event["date"] > day:
            factor *= float(event["factor"])
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError(f"Invalid current quote conversion for {identity}")
    return factor


def whole_quantity(value: float, identity: str) -> int:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Invalid share quantity for {identity}: {value}")
    quantity = round(value)
    if quantity <= 0 or not math.isclose(value, quantity, rel_tol=0, abs_tol=1e-7):
        raise ExecutionDataError(
            f"Fractional share entitlement for {identity}: {value}. "
            "Corporate-action reconciliation is required; no shares were rounded away.",
            identity=identity,
        )
    return quantity


def size_buy(budget: float, price: float) -> tuple[int, float]:
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("S18 buy budget must be finite and nonnegative")
    if not math.isfinite(price) or price <= 0:
        raise ValueError("S18 exchange price must be finite and positive")
    # S18 charges COST on the cash outlay, unlike ATH's markup on share value.
    unit_cost = price / (1 - COST)
    quantity = math.floor(budget / unit_cost)
    if (quantity + 1) * unit_cost <= budget:
        quantity += 1
    if quantity * unit_cost > budget:
        quantity -= 1
    return quantity, quantity * unit_cost
