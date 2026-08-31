"""Shared helpers for the ER-initiation-note corpus tooling.

The corpus lives OUTSIDE the per-ticker run workspace, at:

    reference/er_corpus/
        pdf/<broker_slug>/<note_id>.pdf     downloaded source PDFs
        md/<broker_slug>/<note_id>.md       markitdown conversion (page-anchored)
        manifest.csv                        one row per attempted URL (incl. failures)
        seeds/*.txt|*.json                  discovered candidate URLs
        profile.json / profile_summary.md   zero-token structural profiling
        extracts/<note_id>.json             LLM deep-read output (phase 2)

Design rules (mirroring the repo's own doctrine in CLAUDE.md rule 1):
  * Everything here is DETERMINISTIC and costs zero LLM tokens. Downloading and
    converting 150 PDFs must not consume reasoning budget.
  * Every attempted URL lands in the manifest, success or failure. A corpus that
    silently shrinks is worse than one that reports what it could not reach.
  * Idempotent/resumable: re-running skips work already recorded.

LIGATURE HAZARD (learned the hard way, do not remove):
  pdfminer — under markitdown — drops the `ti`/`fi`/`fl`/`ff` ligature glyphs in
  many broker-report fonts. "Initiating Coverage" converts to "Ini a ng Coverage",
  "identified" to "iden fied", "classification" to "classi ca on". Any naive
  `"initiating coverage" in text.lower()` check therefore MISSES a large fraction
  of genuine initiation notes. Use `contains_fuzzy()` below for every keyword test.
"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "reference" / "er_corpus"
PDF_DIR = CORPUS_ROOT / "pdf"
MD_DIR = CORPUS_ROOT / "md"
SEED_DIR = CORPUS_ROOT / "seeds"
EXTRACT_DIR = CORPUS_ROOT / "extracts"
MANIFEST = CORPUS_ROOT / "manifest.csv"

MANIFEST_FIELDS = [
    "note_id", "broker", "broker_slug", "company", "sector_guess", "date",
    "is_initiation", "pages", "words", "bytes", "sha256", "url",
    "pdf_path", "md_path", "status", "note",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_PDF_BYTES = 60 * 1024 * 1024
POLITENESS_SECONDS = 0.7

# --------------------------------------------------------------------------
# Broker identification
# --------------------------------------------------------------------------

# User instruction: Motilal Oswal is excluded from this corpus entirely.
EXCLUDED_BROKERS = {"motilal_oswal"}

# Ordered: first match wins, so put distinctive multi-word names before generic ones.
BROKER_PATTERNS: list[tuple[str, str]] = [
    ("motilal_oswal", r"motilal|\bmosl\b|motilaloswal"),
    ("kotak_institutional", r"kotak\s*(institutional|securities|mahindra)|\bkie\b|kotaksecurities"),
    ("hdfc_securities", r"hdfc\s*sec|hdfcsec|\bhsl\b\s*research"),
    ("icici_securities", r"icici\s*(securities|direct)|icicidirect|\bisec\b"),
    ("axis_capital", r"axis\s*(capital|securities|direct)|axisdirect"),
    ("emkay_global", r"emkay"),
    ("anand_rathi", r"anand\s*rathi|anandrathi|\brathi\b"),
    ("nirmal_bang", r"nirmal\s*bang|nirmalbang"),
    ("sharekhan", r"sharekhan"),
    ("systematix", r"systematix"),
    ("elara_capital", r"elara"),
    ("centrum", r"centrum"),
    ("antique", r"antique\s*stock|antique\s*broking"),
    ("dolat_capital", r"dolat"),
    ("idbi_capital", r"idbi\s*capital"),
    ("ventura", r"ventura"),
    ("choice_broking", r"choice\s*(equity|broking|institutional)"),
    ("geojit", r"geojit"),
    ("smifs", r"\bsmifs\b|stewart.{0,3}mackertich"),
    ("ashika", r"ashika"),
    ("marwadi", r"marwadi"),
    ("jm_financial", r"jm\s*financial|\bjmfl\b"),
    ("nuvama", r"nuvama|edelweiss\s*(securities|research)"),
    ("prabhudas_lilladher", r"prabhudas|lilladher|\bplindia\b"),
    ("yes_securities", r"yes\s*securities"),
    ("bk_securities", r"b\s*&\s*k\s*securities|batlivala"),
    ("incred", r"incred"),
    ("dam_capital", r"dam\s*capital"),
    ("phillipcapital", r"phillip\s*capital|phillipcapital"),
    ("ambit", r"ambit\s*capital"),
    ("spark", r"spark\s*(capital|institutional)"),
    ("equirus", r"equirus"),
    ("narnolia", r"narnolia"),
    ("krchoksey", r"kr\s*choksey|krchoksey"),
    ("sushil_finance", r"sushil\s*finance"),
    ("arihant", r"arihant\s*capital"),
    ("monarch", r"monarch\s*network"),
    ("keynote", r"keynote\s*capital"),
    ("bob_capital", r"bob\s*capital|baroda\s*etrade|barodaetrade|bobcaps"),
    ("sbi_securities", r"sbi\s*securities|sbicap"),
    ("religare", r"religare"),
    ("mirae_asset", r"mirae\s*asset"),
    ("lkp", r"\blkp\b\s*securities"),
    ("progressive", r"progressive\s*share"),
    ("way2wealth", r"way2wealth"),
    ("swastika", r"swastika"),
    ("stoxbox", r"stoxbox|bp\s*equities"),
]


def infer_broker(*texts: str) -> tuple[str, str]:
    """Return (display_name, slug) inferred from any of the given strings
    (URL, filename, first page of text). Falls back to ('Unknown', 'unknown')."""
    blob = " ".join(t or "" for t in texts).lower()
    for slug, pattern in BROKER_PATTERNS:
        if re.search(pattern, blob, re.I):
            return slug.replace("_", " ").title(), slug
    return "Unknown", "unknown"


# --------------------------------------------------------------------------
# Ligature-tolerant text matching
# --------------------------------------------------------------------------

_LIGATURES = ("ffi", "ffl", "ti", "fi", "fl", "ff")


def squash(s: str) -> str:
    """Lowercase and strip everything that is not a letter or digit."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def delig(s: str) -> str:
    """Remove ligature character-pairs from an already-squashed string, the way
    pdfminer drops them when the font has no mapping for the ligature glyph."""
    out = s
    for lig in _LIGATURES:
        out = out.replace(lig, "")
    return out


def contains_fuzzy(haystack_squashed: str, term: str) -> bool:
    """True if `term` appears in the squashed text either intact or with its
    ligatures dropped. `haystack_squashed` must already be squash()-ed (do it
    once per document, not once per term — these documents are ~200 KB)."""
    t = squash(term)
    if t and t in haystack_squashed:
        return True
    d = delig(t)
    return bool(d) and d in haystack_squashed


# --------------------------------------------------------------------------
# Note identity
# --------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(s: str, maxlen: int = 60) -> str:
    out = _SAFE.sub("_", (s or "").strip()).strip("_")
    return (out[:maxlen] or "untitled").lower()


def note_id_for(url: str, broker_slug: str, company: str | None = None,
                date: str | None = None) -> str:
    """Stable, collision-resistant id. The URL hash keeps ids unique even when
    two brokers publish same-company same-month notes."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    parts = [broker_slug, slugify(company or "", 40) or "unknown", (date or "")[:7], h]
    return "__".join(p for p in parts if p)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------

def ensure_dirs() -> None:
    for d in (CORPUS_ROOT, PDF_DIR, MD_DIR, SEED_DIR, EXTRACT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_manifest(rows: list[dict]) -> None:
    ensure_dirs()
    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in MANIFEST_FIELDS})


def seen_urls() -> set[str]:
    return {r.get("url", "") for r in read_manifest() if r.get("url")}
