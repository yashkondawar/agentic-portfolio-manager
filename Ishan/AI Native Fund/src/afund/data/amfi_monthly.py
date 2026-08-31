"""AMFI monthly mutual-fund report pipeline — Phase 8 macro KPI sourcing.

Source: https://www.amfiindia.com/research-information/amfi-monthly (see
config/sources.yaml macro.amfi_monthly) — a listing page linking to a
monthly "Monthly Report" PDF at
https://portal.amfiindia.com/spages/{mon}{yyyy}repo.pdf (e.g.
ammay2026repo.pdf for May 2026), newest first in page order.

CORRECTION vs the original plan wording ("AMFI monthly note"): this is a
2-page structured DATA TABLE PDF (scheme-category counts/folios/inflows/
AUM), not a narrative note, and it has NO SIP contribution figure
anywhere in it (also confirmed amfiindia.com/research-information/
sip-statistics returns HTTP 404 directly). This pipeline therefore
extracts only what the PDF genuinely contains:

  - "Sub Total - II (...)" row (Growth/Equity Oriented Schemes sub-total)
    -> its Net Inflow(+)/Outflow(-) column -> macro_series
       MF_EQUITY_NET_INFLOW (INR crore)
  - "Grand Total" row -> its Net AUM column -> macro_series
    MF_TOTAL_AUM (INR crore)

SIP_CONTRIBUTION is left honestly source_status: missing in
knowledge/data/kpis/mf_retail_inflows.yaml — no AMFI source was found for
it within budget; fabricating a number here would violate the
never-fabricate-missing-data rule in CLAUDE.md.

PDF text extraction uses pypdf (the same library as
afund.data.newsletter_text, though the parsing logic itself is custom
line-based regex against this PDF's fixed table structure rather than
reusing that module's prose-oriented extractor).
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

from afund.data.base import Pipeline
from afund.data.http import get, make_session
from afund.sources import get_source

AMFI_HOST_KEY = "amfiindia.com"
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "amfi"

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_PDF_LINK_RE = re.compile(
    r'href="(https://portal\.amfiindia\.com/spages/(am)([a-z]{3})(\d{4})repo\.pdf)"',
    re.IGNORECASE,
)

# Matches an AMFI monthly-report number, Indian-style comma grouping,
# with or without a decimal part, e.g. "22,907.77", "-1,953.89", "569",
# "18,49,15,510". Requires at least one digit before any comma/decimal so
# a bare "-" (AMFI's "nil" placeholder) is never matched as -0 or similar.
_NUMBER_RE = r"-?\d[\d,]*(?:\.\d+)?"


def find_latest_pdf_url(listing_html: str) -> tuple[str, str] | None:
    """Scan the amfi-monthly listing page HTML for repo.pdf links and
    return (url, period_label) for the most recent one, e.g.
    ("https://portal.amfiindia.com/spages/ammay2026repo.pdf", "2026-05").
    Matches are naturally newest-first in page order, so the first match
    wins (also cross-checked by comparing (year, month) across all matches
    to be defensive against a future reordering)."""
    candidates: list[tuple[int, int, str]] = []
    for match in _PDF_LINK_RE.finditer(listing_html):
        url, _prefix, mon_abbr, year_str = match.groups()
        month = _MONTH_ABBR.get(mon_abbr.lower())
        if month is None:
            continue
        candidates.append((int(year_str), month, url))

    if not candidates:
        return None

    year, month, url = max(candidates, key=lambda c: (c[0], c[1]))
    return url, f"{year:04d}-{month:02d}"


def extract_pdf_text(pdf_path: Path, max_pages: int = 2) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _numbers_in(line: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(_NUMBER_RE, line)]


def parse_amfi_monthly_text(text: str) -> dict[str, float]:
    """Parse the two rows of interest out of the AMFI monthly report's
    extracted page-0 text. Returns whatever it can honestly find (a dict
    with 0, 1, or 2 keys among {"MF_EQUITY_NET_INFLOW", "MF_TOTAL_AUM"}) —
    never guesses or interpolates a value it can't locate.

    Row shapes (pypdf's extract_text() collapses each table row onto one
    text line; the row label itself ("Sub Total - II (i+ii+...)",
    "Grand Total") contains no digits, so _NUMBER_RE's matches on that
    line are exactly the data columns, counted from the start):

      "Sub Total - II (i+ii+...+xi) 569  18,49,15,510  57,603.83  34,696.05
       22,907.77  36,13,718.41  36,12,941.46  -  -"
       columns: [0]=no_of_schemes [1]=no_of_folios [2]=funds_mobilized
       [3]=repurchase [4]=NET_INFLOW(+)/OUTFLOW(-) [5]=net_aum [6]=avg_aum
       -> MF_EQUITY_NET_INFLOW = numbers[4] = 22907.77

      "Grand Total 1,946  27,65,67,797  12,02,732.09  12,66,753.26
       -64,021.17  81,58,341.65  83,46,578.72  10.00  -"
       columns: [0]=no_of_schemes [1]=no_of_folios [2]=funds_mobilized
       [3]=repurchase [4]=net_inflow [5]=NET_AUM [6]=avg_aum
       -> MF_TOTAL_AUM = numbers[5] = 8158341.65
    """
    result: dict[str, float] = {}

    sub_total_ii_re = re.compile(r"^Sub Total\s*-\s*II\b(?!I)")

    for line in text.splitlines():
        stripped = line.strip()

        if sub_total_ii_re.match(stripped):
            nums = _numbers_in(stripped)
            # [no_schemes, no_folios, funds_mobilized, repurchase, net_inflow, net_aum, avg_aum, ...]
            if len(nums) >= 5:
                result["MF_EQUITY_NET_INFLOW"] = nums[4]

        if stripped.startswith("Grand Total"):
            nums = _numbers_in(stripped)
            # [no_schemes, no_folios, funds_mobilized, repurchase, net_inflow, net_aum, avg_aum, ...]
            if len(nums) >= 6:
                result["MF_TOTAL_AUM"] = nums[5]

    return result


class AmfiMonthlyPipeline(Pipeline):
    """Discover the latest AMFI monthly report PDF, download, extract text,
    parse the two reliably-present rows, and upsert."""

    job_name = "amfi_monthly"

    def fetch(self) -> tuple[str, str, bytes]:
        source = get_source("macro", "amfi_monthly")
        session = make_session()
        listing_resp = get(session, source["url"], host_key=AMFI_HOST_KEY, min_interval=1.0, timeout=20.0)
        listing_resp.raise_for_status()

        found = find_latest_pdf_url(listing_resp.text)
        if found is None:
            raise RuntimeError("no repo.pdf link found on amfi-monthly listing page")
        pdf_url, period_label = found

        pdf_resp = get(session, pdf_url, host_key=AMFI_HOST_KEY, min_interval=1.0, timeout=30.0)
        pdf_resp.raise_for_status()
        return pdf_url, period_label, pdf_resp.content

    def parse(self, raw: tuple[str, str, bytes]) -> tuple[str, dict[str, float]]:
        pdf_url, period_label, content = raw

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        local_name = pdf_url.rsplit("/", 1)[-1]
        local_path = RAW_DIR / local_name
        local_path.write_bytes(content)

        text = extract_pdf_text(local_path)
        parsed = parse_amfi_monthly_text(text)
        return period_label, parsed

    def upsert(self, parsed: tuple[str, dict[str, float]]) -> int:
        period_label, values = parsed
        date = f"{period_label}-01"  # month-start convention, matches other monthly macro_series rows

        written = 0
        for series_code, value in values.items():
            cur = self.conn.execute(
                """
                INSERT INTO macro_series (series_code, source, date, value, unit, freq)
                VALUES (?, 'AMFI', ?, ?, 'INR_cr', 'M')
                ON CONFLICT(series_code, date) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source
                """,
                (series_code, date, value),
            )
            written += cur.rowcount
        self.conn.commit()
        return written


if __name__ == "__main__":
    result = AmfiMonthlyPipeline().run()
    print(result)
