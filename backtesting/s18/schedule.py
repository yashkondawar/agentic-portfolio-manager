"""Prepare the workbench schedule without retargeting its existing daemon."""

from dataclasses import replace

from core import schedules, storage
from .config import S18Config, validate_capital
from .dataset import get_dataset


def prepare_schedule(
    *,
    capital=500000.0,
    combo="P15",
    metal_mode="both_priority",
    book_id="s18-p15-forward",
    run_at="19:00",
):
    get_dataset()
    config = S18Config(combo, metal_mode)
    params = {
        "combo": config.combo,
        "metal_mode": config.metal_mode,
        "capital": validate_capital(capital),
        "book_id": book_id,
        "persist": True,
    }
    matching = [
        s
        for s in schedules.list_schedules()
        if s.strategy_id == "s18_daily" and s.params.get("book_id") == book_id
    ]
    if len(matching) > 1:
        raise ValueError(
            "Multiple S18 schedules already target this book; resolve duplicates"
        )
    name = f"S18 {combo} priority metals (enable after deployment)"
    if matching:
        current = matching[0]
        if current.enabled:
            raise ValueError(
                "The matching S18 schedule is active; not replacing it implicitly"
            )
        schedule = schedules.save_schedule(
            replace(
                current,
                name=name,
                params=params,
                run_at=run_at,
                days_of_week=schedules.ALL_DAYS,
                timezone="Asia/Kolkata",
                enabled=False,
            )
        )
    else:
        schedule = schedules.create_schedule(
            strategy_id="s18_daily",
            name=name,
            run_at=run_at,
            days_of_week=schedules.ALL_DAYS,
            timezone="Asia/Kolkata",
            enabled=False,
            params=params,
        )
    storage.set_document("strategy_defaults", "s18_daily", params)
    return schedule
