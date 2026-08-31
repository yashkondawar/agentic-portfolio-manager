#!/usr/bin/env python3
"""
CLI entry point.

Usage:
    python main.py "Tata Consultancy Services"
    python main.py --company TCS --outdir ./my_downloads
    python main.py "Persistent Systems" --no-llm          # heuristics only
    python main.py "Persistent Systems" --annual 3 --quarterly 4
    python main.py "Cyient DLM" --enable-web-fallback     # opt into Gemini+Tavily/DDG gap-fill

Key-free by default: BSE + Screener work fully with no API key and no
--enable-web-fallback flag. Web-search gap-filling (Tavily/DuckDuckGo) and
Gemini classification are OFF by default (see config.ENABLE_WEB_FALLBACK) —
pass --enable-web-fallback (or set ENABLE_WEB_FALLBACK=1) to turn them on,
which requires GEMINI_API_KEY and/or TAVILY_API_KEY in a .env file (see
.env.example); the pipeline raises a clear error if neither is set while
the flag is on.
"""
from __future__ import annotations

import argparse
import logging
import sys

from disclosure_fetcher.config import ENABLE_WEB_FALLBACK, FetchTargets
from disclosure_fetcher.models import DocType
from disclosure_fetcher.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch BSE/Screener disclosures for an Indian listed company.")
    p.add_argument("company", nargs="?", help="Company name, or BSE/NSE symbol, e.g. 'Tata Consultancy Services' or 'TCS'")
    p.add_argument("--company", dest="company_flag", help="Alternative way to pass the company name")
    p.add_argument("--outdir", default=None, help="Output directory (default: ./downloads)")
    p.add_argument("--annual", type=int, default=5, help="Number of annual reports (default 5)")
    p.add_argument("--quarterly", type=int, default=8, help="Number of quarterly results (default 8)")
    p.add_argument("--half-yearly", type=int, default=4, help="Number of half-yearly results (default 4)")
    p.add_argument("--transcripts", type=int, default=4, help="Number of earnings-call transcripts (default 4)")
    p.add_argument("--presentations", type=int, default=4, help="Number of investor presentations (default 4)")
    p.add_argument("--special", type=int, default=8, help="Max number of special disclosures (default 8)")
    p.add_argument("--lookback-years", type=int, default=6, help="How many years back to query BSE (default 6)")
    p.add_argument("--min-confidence", type=float, default=0.4, help="Minimum confidence to auto-download (default 0.4)")
    p.add_argument("--no-llm", action="store_true", help="Disable Gemini calls; use keyword heuristics only")
    p.add_argument(
        "--enable-web-fallback",
        action="store_true",
        default=ENABLE_WEB_FALLBACK,
        help="Opt into the Gemini + Tavily/DuckDuckGo gap-filling stage "
        "(default OFF / key-free BSE+Screener-only; also settable via "
        "ENABLE_WEB_FALLBACK=1)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose (DEBUG) logging")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # the underlying HTTP libraries are noisy at INFO - keep them quiet
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    company_name = args.company_flag or args.company
    if not company_name:
        try:
            company_name = input("Company name (or BSE/NSE symbol): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNo company name given, exiting.", file=sys.stderr)
            return 1
    if not company_name:
        print("No company name given, exiting.", file=sys.stderr)
        return 1

    targets = FetchTargets(
        annual_reports=args.annual,
        quarterly_results=args.quarterly,
        half_yearly_results=args.half_yearly,
        earnings_transcripts=args.transcripts,
        investor_presentations=args.presentations,
        special_disclosures=args.special,
        lookback_years=args.lookback_years,
    )

    print(f"\nFetching disclosures for: {company_name}")
    if args.no_llm:
        print("(LLM validation disabled - using keyword heuristics only)")
    if args.enable_web_fallback:
        print("(Web-search fallback enabled - Gemini + Tavily/DuckDuckGo gap-filling active)")
        print("This can take a few minutes depending on how much needs the web-search fallback.\n")
    else:
        print("(Key-free mode: BSE + Screener only. Pass --enable-web-fallback to also search the open web for gaps.)\n")

    result = run_pipeline(
        company_query=company_name,
        targets=targets,
        output_dir=args.outdir,
        disable_llm=args.no_llm,
        min_confidence=args.min_confidence,
        enable_web_fallback=args.enable_web_fallback,
    )

    print("=" * 60)
    if not result.company.is_resolved():
        print(f"Could not resolve '{company_name}'.")
        for w in result.warnings:
            print(f"  ! {w}")
        return 1

    print(f"Company:        {result.company.name}")
    print(f"BSE scrip code: {result.company.bse_scrip_code or 'n/a'}")
    print(f"NSE symbol:     {result.company.nse_symbol or 'n/a'}")
    print(f"Screener:       {result.company.screener_url or 'n/a'}")
    print("-" * 60)

    counts = result.counts_by_type()
    targets_by_type = {
        DocType.ANNUAL_REPORT: targets.annual_reports,
        DocType.QUARTERLY_RESULT: targets.quarterly_results,
        DocType.HALF_YEARLY_RESULT: targets.half_yearly_results,
        DocType.EARNINGS_TRANSCRIPT: targets.earnings_transcripts,
        DocType.INVESTOR_PRESENTATION: targets.investor_presentations,
        DocType.SPECIAL_DISCLOSURE: targets.special_disclosures,
    }
    for doc_type, target_n in targets_by_type.items():
        if target_n <= 0:
            continue
        got = counts.get(doc_type.value, 0)
        print(f"  {doc_type.value:<24} {got}/{target_n} downloaded")

    print("-" * 60)
    print(f"Manifest: {result.manifest_path}")
    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings:
            print(f"  ! {w}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
