"""Review schedules use exchange sessions, never weekday approximations."""

import numpy as np
import pandas as pd


def review_flags(
    dates, tranche: str, *, reference: bool = False, complete_through=None
):
    if tranche not in ("A", "B"):
        raise ValueError("Tranche must be A or B")
    days = pd.DatetimeIndex(dates)
    if days.empty or not days.is_monotonic_increasing or days.has_duplicates:
        raise ValueError("Session calendar must be nonempty, ordered and unique")
    months = days.to_period("M")
    month_ends = np.flatnonzero(months[:-1] != months[1:])
    if not reference:
        coverage = (
            pd.Timestamp(complete_through) if complete_through is not None else days[-1]
        )
        if (
            pd.isna(coverage)
            or coverage.tzinfo is not None
            or coverage.normalize() < days[-1].normalize()
        ):
            raise ValueError(
                "Calendar completeness must cover every supplied session date"
            )
        # A partial next-month preview is not a month end. Shifting that
        # artificial boundary would introduce another B review in this month.
        if coverage.normalize() >= months[-1].end_time.normalize():
            month_ends = np.append(month_ends, len(days) - 1)
    shift = 0 if tranche == "A" else 10
    flags = np.zeros(len(days), dtype=bool)
    eligible = month_ends - shift
    flags[eligible[eligible >= 0]] = True
    if reference:
        flags[0] = True
        flags[-1] = True
    return flags
