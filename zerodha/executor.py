"""
Trade executor — bridges analysis pipeline decisions with Zerodha orders.

Takes portfolio decisions from the parallel agent system and executes
them on Zerodha after applying safety checks and position sizing.

Usage:
    from zerodha.executor import TradeExecutor
    executor = TradeExecutor(client)
    results = executor.execute_decisions(analysis_results)
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from agents.models import StockAnalysis, PortfolioDecision

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Result of a trade execution attempt."""
    symbol: str
    action: str
    status: str  # "executed", "skipped", "failed", "dry_run"
    order_id: Optional[str] = None
    quantity: int = 0
    price: float = 0.0
    reason: str = ""


class TradeExecutor:
    """
    Executes trades based on analysis pipeline decisions.

    Safety features:
    - Minimum confidence threshold (default 70%)
    - Maximum position size cap
    - Dry-run mode (default) — logs orders without executing
    - Order confirmation summary before execution
    """

    def __init__(
        self,
        client,  # ZerodhaClient instance
        min_confidence: float = 70.0,
        max_position_pct: float = 15.0,
        dry_run: bool = True,
        product: str = "CNC",  # CNC for delivery, MIS for intraday
    ):
        self.client = client
        self.min_confidence = min_confidence
        self.max_position_pct = max_position_pct
        self.dry_run = dry_run
        self.product = product

    def execute_decisions(
        self,
        results: Dict[str, StockAnalysis],
        portfolio_value: Optional[float] = None,
    ) -> List[TradeResult]:
        """
        Execute trading decisions from analysis results.

        Args:
            results: Dict of symbol -> StockAnalysis from the pipeline
            portfolio_value: Total portfolio value. If None, fetches from Zerodha.

        Returns:
            List of TradeResult for each decision
        """
        if not portfolio_value:
            portfolio_value = self.client.get_available_cash()

        logger.info(f"[EXECUTOR] Processing {len(results)} decisions | Portfolio=₹{portfolio_value:,.0f} | DryRun={self.dry_run}")

        trade_results = []

        for symbol, analysis in results.items():
            decision = analysis.final_decision
            if not decision:
                trade_results.append(TradeResult(
                    symbol=symbol, action="NONE", status="skipped",
                    reason="No decision from pipeline"
                ))
                continue

            result = self._execute_single(symbol, decision, analysis.current_price, portfolio_value)
            trade_results.append(result)

        # Summary log
        executed = [r for r in trade_results if r.status in ("executed", "dry_run")]
        skipped = [r for r in trade_results if r.status == "skipped"]
        failed = [r for r in trade_results if r.status == "failed"]

        logger.info(
            f"[EXECUTOR] Done: {len(executed)} executed/dry-run, "
            f"{len(skipped)} skipped, {len(failed)} failed"
        )

        return trade_results

    def _execute_single(
        self,
        symbol: str,
        decision: PortfolioDecision,
        current_price: float,
        portfolio_value: float,
    ) -> TradeResult:
        """Execute a single trade decision."""

        action = decision.action.upper()

        # Skip HOLD decisions
        if action == "HOLD":
            return TradeResult(
                symbol=symbol, action="HOLD", status="skipped",
                reason="HOLD — no action needed"
            )

        # Check confidence threshold
        if decision.confidence < self.min_confidence:
            return TradeResult(
                symbol=symbol, action=action, status="skipped",
                reason=f"Confidence {decision.confidence:.0f}% below threshold {self.min_confidence:.0f}%"
            )

        # Calculate position size
        max_amount = portfolio_value * (self.max_position_pct / 100)
        if decision.position_size_pct:
            amount = min(
                portfolio_value * (decision.position_size_pct / 100),
                max_amount,
            )
        else:
            amount = max_amount * 0.5  # Default to half of max if not specified

        # Calculate quantity
        price = decision.entry_price or current_price
        if price <= 0:
            return TradeResult(
                symbol=symbol, action=action, status="failed",
                reason="Invalid price (zero or negative)"
            )

        quantity = int(amount // price)
        if quantity <= 0:
            return TradeResult(
                symbol=symbol, action=action, status="skipped",
                reason=f"Position too small: ₹{amount:,.0f} / ₹{price:,.2f} = 0 shares"
            )

        # Log the planned trade
        logger.info(
            f"[EXECUTOR] {action} {quantity}x {symbol} @ ₹{price:,.2f} "
            f"(amount=₹{quantity * price:,.0f}, conf={decision.confidence:.0f}%)"
        )

        if decision.stop_loss:
            logger.info(f"[EXECUTOR]   SL: ₹{decision.stop_loss:,.2f}")
        if decision.target_price:
            logger.info(f"[EXECUTOR]   Target: ₹{decision.target_price:,.2f}")

        # Dry run mode
        if self.dry_run:
            logger.info(f"[EXECUTOR]   ⚠️  DRY RUN — order NOT placed")
            return TradeResult(
                symbol=symbol, action=action, status="dry_run",
                quantity=quantity, price=price,
                reason=f"Dry run: would {action} {quantity}x @ ₹{price:,.2f}"
            )

        # Execute the actual order
        try:
            if action == "BUY":
                result = self.client.place_order(
                    symbol=symbol,
                    transaction_type="BUY",
                    quantity=quantity,
                    price=price if decision.entry_price else None,
                    order_type="LIMIT" if decision.entry_price else "MARKET",
                    product=self.product,
                    tag="agentic_buy",
                )
            elif action == "SELL":
                result = self.client.place_order(
                    symbol=symbol,
                    transaction_type="SELL",
                    quantity=quantity,
                    price=price if decision.entry_price else None,
                    order_type="LIMIT" if decision.entry_price else "MARKET",
                    product=self.product,
                    tag="agentic_sell",
                )
            else:
                return TradeResult(
                    symbol=symbol, action=action, status="skipped",
                    reason=f"Unknown action: {action}"
                )

            if result.get("status") == "success":
                return TradeResult(
                    symbol=symbol, action=action, status="executed",
                    order_id=result.get("order_id"),
                    quantity=quantity, price=price,
                    reason=f"Order placed: {result.get('order_id')}"
                )
            else:
                return TradeResult(
                    symbol=symbol, action=action, status="failed",
                    reason=f"Order error: {result.get('error', 'unknown')}"
                )

        except Exception as e:
            logger.error(f"[EXECUTOR] Exception executing {action} for {symbol}: {e}")
            return TradeResult(
                symbol=symbol, action=action, status="failed",
                reason=str(e)
            )

    def generate_order_summary(self, results: Dict[str, StockAnalysis]) -> str:
        """
        Generate a human-readable summary of planned trades (before execution).
        Useful for confirmation in the UI.
        """
        lines = ["## 📋 Planned Trades\n"]
        lines.append("| Symbol | Action | Qty | Price | Amount | Confidence |")
        lines.append("|--------|--------|-----|-------|--------|-----------|")

        portfolio_value = 1_000_000  # Default for display

        for symbol, analysis in results.items():
            decision = analysis.final_decision
            if not decision or decision.action.upper() == "HOLD":
                continue
            if decision.confidence < self.min_confidence:
                continue

            price = decision.entry_price or analysis.current_price
            max_amount = portfolio_value * (self.max_position_pct / 100)
            if decision.position_size_pct:
                amount = min(portfolio_value * (decision.position_size_pct / 100), max_amount)
            else:
                amount = max_amount * 0.5
            quantity = int(amount // price) if price > 0 else 0

            emoji = "🟢" if decision.action.upper() == "BUY" else "🔴"
            lines.append(
                f"| {symbol} | {emoji} {decision.action} | {quantity} | "
                f"₹{price:,.2f} | ₹{quantity * price:,.0f} | {decision.confidence:.0f}% |"
            )

        if len(lines) == 3:  # Only header
            lines.append("| — | No actionable trades | — | — | — | — |")

        lines.append(f"\n*Mode: {'🔴 DRY RUN' if self.dry_run else '🟢 LIVE'}*")
        return "\n".join(lines)
