"""Unified entry point for every strategy in the platform.

This is the single door through which all "systems" are discovered and run —
the parallel agent system, the sequential agent system, swing trading,
portfolio analysis and watchlist curation. A UI can import
:func:`core.registry.list_specs` / :func:`core.registry.run_strategy` directly;
this module additionally provides a command-line interface over the same
registry.

Examples
--------
List every available strategy and its parameters::

    python run.py --list

Run a strategy with inline params::

    python run.py parallel_agents --param symbols="RELIANCE,TCS" --param use_llm=true

Run a strategy with a JSON params blob::

    python run.py portfolio_analysis --params '{"holdings": [{"symbol": "TCS", "quantity": 10, "buy_price": 3800}]}'
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from core import registry
from core.console import safe_print
from logging_config import setup_logging


def _print_strategy_list(as_json: bool) -> None:
    specs = registry.list_specs()
    if as_json:
        print(json.dumps(specs, indent=2, default=str))
        return

    print("\nAvailable strategies (options for the same goal):\n")
    for spec in specs:
        print(f"  * {spec['id']}  [{spec['category']}]")
        print(f"      {spec['name']} - {spec['description']}")
        params = spec.get("params", [])
        if params:
            print("      params:")
            for p in params:
                req = "required" if p["required"] else f"default={p['default']!r}"
                choices = f" choices={p['choices']}" if p.get("choices") else ""
                print(f"        - {p['name']} ({p['type']}, {req}){choices}")
        print()


def _parse_params(args: argparse.Namespace) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if args.params:
        loaded = json.loads(args.params)
        if not isinstance(loaded, dict):
            raise SystemExit("--params must be a JSON object")
        params.update(loaded)
    for item in args.param or []:
        if "=" not in item:
            raise SystemExit(f"--param must be key=value, got: {item!r}")
        key, value = item.split("=", 1)
        params[key.strip()] = value
    return params


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified entry point for all stock-research strategies.",
    )
    parser.add_argument(
        "strategy",
        nargs="?",
        help="Strategy id to run (omit with --list to see options).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available strategies and their parameters.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --list, emit machine-readable JSON specs.",
    )
    parser.add_argument(
        "--param",
        action="append",
        metavar="KEY=VALUE",
        help="Set a single parameter (repeatable).",
    )
    parser.add_argument(
        "--params",
        metavar="JSON",
        help="Set all parameters from a JSON object.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list or not args.strategy:
        _print_strategy_list(as_json=args.json)
        return 0

    params = _parse_params(args)
    result = registry.run_strategy(args.strategy, params)

    print("=" * 80)
    print(f"STRATEGY: {result.strategy_id}  |  STATUS: {result.status}")
    print("=" * 80)
    safe_print(result.report)
    if result.error:
        safe_print(f"\n[error] {result.error}", file=sys.stderr)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
