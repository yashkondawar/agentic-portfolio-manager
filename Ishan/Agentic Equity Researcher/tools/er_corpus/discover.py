"""Enumerate candidate initiation-note PDF URLs. Deterministic, zero LLM tokens.

    python tools/er_corpus/discover.py --crawl                 # crawl known hosts
    python tools/er_corpus/discover.py --merge a.txt b.txt     # dedupe seed files
    python tools/er_corpus/discover.py --crawl --out reference/er_corpus/seeds/crawled.txt

Two discovery channels, because no single one is sufficient:

1. CRAWLABLE HOSTS (this script). A few brokers publish research from a flat or
   listable directory. Probed 2026-08-02:
       reports.emkayglobal.com/downloads/     flat PDF dir
       mailcontent.icicidirect.com/...        flat PDF dir, 100+ links per index page
   Broker sites are fragile — several 404'd on probe. Every failure is logged
   rather than silently dropped.

2. SEARCH HARVESTING (done by the agent, not here). The richest source is
   bsmedia.business-standard.com/_media/bs/data/market-reports/equity-brokertips/
   YYYY-MM/<timestamp>.pdf — a date-partitioned multi-broker mirror carrying
   Nuvama, JM Financial, Anand Rathi, ICICI, Kotak and others. Its filenames are
   opaque timestamps so it cannot be enumerated, and the Business Standard
   listing pages return 403 to non-browser clients. Harvested URLs are written
   to a seed file and merged here.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from er_corpus import corpus_lib as L  # noqa: E402

# (label, index page(s), regex a PDF href must match to be kept)
CRAWL_TARGETS: list[tuple[str, list[str], str]] = [
    ("emkay", [
        "https://www.emkayglobal.com/research-reports",
        "https://reports.emkayglobal.com/downloads/",
    ], r"\.pdf$"),
    ("icicidirect", [
        "https://www.icicidirect.com/research/equity/investing-ideas",
        "https://www.icicidirect.com/research/equity/company-reports",
    ], r"mailcontent\.icicidirect\.com/.*\.pdf$"),
    ("barodaetrade", [
        "https://www.barodaetrade.com/Research.aspx",
        "https://www.barodaetrade.com/",
    ], r"/Reports/.*\.pdf$"),
    ("geojit", [
        "https://www.geojit.com/company-reports",
        "https://www.geojit.com/research",
    ], r"\.pdf$"),
    ("smifs", ["https://www.smifs.com/research-reports"], r"\.pdf$"),
    ("ventura", ["https://www.ventura1.com/research-reports"], r"\.pdf$"),
    ("choice", ["https://choiceindia.com/research-report"], r"\.pdf$"),
]

# Filenames that are obviously not initiations — cheap pre-filter so we don't
# spend a download + 25s conversion to discover it was a daily market wrap.
SKIP_FILENAME = re.compile(
    r"(daily|weekly|monthly|morning|market[_\s-]?(wrap|pulse|round)|"
    r"derivative|technical|mutual[_\s-]?fund|ipo[_\s-]?note|disclaimer|"
    r"advisory|kyc|account[_\s-]?opening|tariff|policy|newsletter)", re.I)

PDF_HREF = re.compile(r"""href\s*=\s*["']([^"']+?\.pdf(?:\?[^"']*)?)["']""", re.I)


def crawl_page(url: str, keep: str, session: requests.Session) -> tuple[list[str], str]:
    try:
        r = session.get(url, headers=L.HTTP_HEADERS, timeout=45, allow_redirects=True)
    except Exception as e:
        return [], f"{type(e).__name__}: {str(e)[:70]}"
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}"
    found = []
    for href in PDF_HREF.findall(r.text):
        absu = urljoin(r.url, href.strip())
        if not re.search(keep, absu, re.I):
            continue
        if SKIP_FILENAME.search(Path(urlparse(absu).path).name):
            continue
        found.append(absu)
    # also catch bare PDF URLs printed in text/JSON payloads
    for m in re.findall(r"https?://[^\s\"'<>\\]+?\.pdf", r.text, re.I):
        if re.search(keep, m, re.I) and not SKIP_FILENAME.search(Path(urlparse(m).path).name):
            found.append(m)
    return sorted(set(found)), "ok"


def do_crawl(out_path: Path) -> None:
    session = requests.Session()
    all_urls: set[str] = set()
    print(f"{'target':14} {'status':12} {'new':>5}  page")
    for label, pages, keep in CRAWL_TARGETS:
        for page in pages:
            urls, status = crawl_page(page, keep, session)
            fresh = set(urls) - all_urls
            all_urls |= fresh
            print(f"{label:14} {status:12} {len(fresh):>5}  {page[:70]}")
            time.sleep(L.POLITENESS_SECONDS)
    write_seeds(out_path, sorted(all_urls))


def write_seeds(out_path: Path, urls: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if out_path.exists():
        existing = {ln.strip().split("\t")[0]
                    for ln in out_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")}
    merged = sorted(existing | set(urls))
    out_path.write_text("\n".join(merged) + "\n", encoding="utf-8")
    print(f"\n{len(merged)} unique URL(s) in {out_path} (+{len(set(urls) - existing)} new)")


def do_merge(paths: list[Path], out_path: Path) -> None:
    urls: set[str] = set()
    for p in paths:
        if not p.exists():
            print(f"WARN missing: {p}", file=sys.stderr)
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and ln.lower().startswith("http"):
                urls.add(ln.split("\t")[0] if "\t" in ln else ln)
    already = L.seen_urls()
    fresh = sorted(u for u in urls if u not in already)
    print(f"{len(urls)} unique in inputs; {len(urls) - len(fresh)} already fetched; "
          f"{len(fresh)} new")
    write_seeds(out_path, fresh)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", action="store_true", help="crawl the known listable hosts")
    ap.add_argument("--merge", nargs="*", default=[], help="seed files to merge+dedupe")
    ap.add_argument("--out", default=str(L.SEED_DIR / "discovered.txt"))
    a = ap.parse_args()

    L.ensure_dirs()
    out = Path(a.out)
    if a.crawl:
        do_crawl(out)
    if a.merge:
        do_merge([Path(p) for p in a.merge], out)
    if not a.crawl and not a.merge:
        ap.error("nothing to do — pass --crawl and/or --merge")


if __name__ == "__main__":
    main()
