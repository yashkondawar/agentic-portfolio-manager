"""Portfolio analysis strategy.

Wraps ``portfolio_copilot_analysis`` — a holistic portfolio review that
produces per-stock theses, concentration/sector/risk diagnostics and concrete
restructuring instructions (BUY MORE / TRIM / EXIT / HOLD) via the GitHub
Copilot CLI + scraper MCP.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)

_DEFAULT_PROMPT = (
    "Perform a holistic review of this portfolio and give concrete "
    "restructuring instructions (BUY MORE / TRIM / EXIT / HOLD) with target "
    "weights and rationale."
)


@register
class PortfolioAnalysisStrategy(BaseStrategy):
    id = "portfolio_analysis"
    name = "Portfolio Analysis Copilot"
    description = (
        "Holistic portfolio review with per-stock theses, risk diagnostics "
        "and rebalancing instructions."
    )
    long_description = (
        "Analyzes a whole book: per-stock fundamentals/momentum/risk thesis, "
        "concentration and sector diagnostics, and a concrete restructuring "
        "plan with target weights. Runs through the GitHub Copilot CLI + "
        "scraper MCP (no API keys required)."
    )
    category = StrategyCategory.PORTFOLIO

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                name="holdings",
                label="Holdings (JSON)",
                type=ParamType.JSON,
                required=True,
                help='List of {"symbol","quantity","buy_price","last_price"?}.',
            ),
            ParamSpec(
                name="prompt",
                label="Analysis request",
                type=ParamType.TEXT,
                required=False,
                default=_DEFAULT_PROMPT,
                help="What you want the analysis to focus on.",
            ),
            ParamSpec(
                name="template",
                label="Report style",
                type=ParamType.ENUM,
                required=False,
                default="forensic",
                choices=["forensic", "concise"],
                help="forensic=10-part institutional review, concise=5-section brief.",
            ),
            ParamSpec(
                name="cash_available",
                label="Cash available (₹)",
                type=ParamType.FLOAT,
                required=False,
                default=None,
                min=0,
            ),
            ParamSpec(
                name="horizon_years",
                label="Investment horizon (years)",
                type=ParamType.FLOAT,
                required=False,
                default=None,
                min=0,
            ),
            ParamSpec(
                name="risk_appetite",
                label="Risk appetite",
                type=ParamType.ENUM,
                required=False,
                default=None,
                choices=["Low", "Moderate", "High"],
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        import portfolio_copilot_analysis as pca

        holdings = pca.load_portfolio_from_json(params.get("holdings") or [])
        if not holdings:
            raise ValueError("At least one holding is required.")

        user_prompt = (params.get("prompt") or "").strip() or _DEFAULT_PROMPT
        template = pca.resolve_template(params.get("template") or "forensic")

        context = pca.PortfolioContext(
            cash_available=_opt_float(params.get("cash_available")),
            horizon_years=_opt_float(params.get("horizon_years")),
            risk_appetite=params.get("risk_appetite") or None,
        )

        report = pca.run_analysis(
            holdings=holdings,
            user_prompt=user_prompt,
            context=context,
            template=template,
        )

        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=report,
            data={"num_holdings": len(holdings), "template": template.name},
        )


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)
