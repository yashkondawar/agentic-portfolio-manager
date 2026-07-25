"""
Parallel Multi-Analyst Stock Research System.

Agents module providing:
- 6 parallel analyst agents (technical, fundamentals, valuation, sentiment, 2 investor personas)
- Risk manager
- Portfolio manager
- Concurrent parallel workflow
"""

from agents.workflow import create_parallel_workflow, run_parallel_analysis

__all__ = ["create_parallel_workflow", "run_parallel_analysis"]
