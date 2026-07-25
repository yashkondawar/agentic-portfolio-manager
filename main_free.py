"""Free-data sequential stock research powered by GitHub Copilot SDK."""

from __future__ import annotations

import asyncio

from core.console import safe_print
from main import StockResearchSystem


class StockResearchSystemFree(StockResearchSystem):
    """Compatibility wrapper that always uses the free scraper tools."""

    def __init__(self) -> None:
        super().__init__()
        self.use_free_scraper = True


if __name__ == "__main__":
    system = StockResearchSystemFree()
    results = asyncio.run(system.analyze_stocks())
    safe_print(system.format_results_for_display(results))
