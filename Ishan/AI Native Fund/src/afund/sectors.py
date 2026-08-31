"""Canonical sector mapping shared across layers.

Raw NSE "Industry" strings (as stored in instruments.sector) -> registry
KPI sector keys (registry/kpis/<key>.yaml; also the cycle_assessments
sector scope names). Anything not listed here (or with no sector at all)
falls back to "generic" rather than silently omitting the registry slice.

This is the ONE definition. It lives in this dependency-free module so
that orchestrator/, cycles/, and portfolio/ can all import it without any
cross-layer import (orchestrator imports from cycles/derive, never the
reverse; portfolio imports neither). Add new NSE industry strings here —
never re-declare this mapping locally.
"""

SECTOR_TO_KPI_KEY: dict[str, str] = {
    "Financial Services": "bfsi",
    "Information Technology": "it_technology",
    "Healthcare": "pharma_chemicals",
    "Chemicals": "pharma_chemicals",
    "Fast Moving Consumer Goods": "consumer_retail",
    "Consumer Services": "consumer_retail",
    "Consumer Durables": "consumer_retail",
    "Automobile and Auto Components": "auto_engineering",
    "Capital Goods": "infra_capital_goods",
    "Construction": "infra_capital_goods",
    "Construction Materials": "infra_capital_goods",
    "Oil Gas & Consumable Fuels": "commodities_energy",
    "Metals & Mining": "commodities_energy",
    "Power": "commodities_energy",
}


def kpi_key_for_sector(raw_sector: str | None) -> str:
    """Registry KPI sector key for a raw NSE industry string ("generic" fallback)."""
    if not raw_sector:
        return "generic"
    return SECTOR_TO_KPI_KEY.get(raw_sector, "generic")
