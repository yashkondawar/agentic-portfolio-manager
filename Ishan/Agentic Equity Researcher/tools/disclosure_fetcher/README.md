# India Disclosure Fetcher

Given an Indian listed company's name, downloads its public regulatory disclosures:

- 5 Annual Reports (configurable)
- 8 latest Quarterly Results
- 4 latest Half-Yearly Results (see note below - usually 0 for main-board companies, and that's correct)
- 4 latest Earnings Call Transcripts
- 4 latest Investor Presentations (PPTs)
- Up to 8 "special disclosures" (credit rating actions, M&A, related-party transactions, key resignations, etc.)

into `downloads/<company>/<doc_type>/`, plus a `manifest.csv` recording exactly what was found, where from, and how confident the system is that it's the right document.

## Why this design, not a single big scraper

The brief asked for: search-query generation → find candidate documents → LLM-evaluate metadata → download on a "go" decision, using Gemini + Tavily + DuckDuckGo. That's exactly what happens here, but **BSE itself is used as the primary source, not generic web search** - web search is the fallback for whatever BSE and Screener don't have. Reasoning:

1. **BSE India is the regulator-mandated disclosure feed.** Every result, presentation, transcript, and annual report a listed company files legally has to land there. There's an actively-maintained, well-behaved open-source wrapper (`bse` on PyPI) around the same JSON API bseindia.com's own announcements page calls - it throttles itself automatically and needs no API key. Querying it directly is far more precise and reliable than search-engine-guessing for something that has an authoritative, structured source.
2. **Screener.in** aggregates a "Documents" tab per company (annual reports, concalls with transcript/PPT links, credit ratings) that's a great single-page cross-check - used here as a light, single-GET bonus source, not a crawl.
3. **Tavily (primary) + DuckDuckGo (backup) + Gemini** fill in whatever's still missing after steps 1-2 - e.g. a transcript a company only ever posted to its own investor-relations page and never formally filed as a BSE attachment.

This hybrid design needs far fewer LLM calls than "search + LLM-evaluate everything," which matters on a free-tier Gemini quota, and it's much less fragile than relying on generic web search for documents that already live at a known, queryable source.

## Architecture

```
company name
     │
     ▼
company_resolver.py ──► bse.lookup()          (BSE scrip code, ISIN, NSE symbol)
     │                  screener /api/company/search/   (Screener slug)
     │                  [web search + LLM, only if both of the above fail - see below]
     ▼
sources/bse_source.py ──► BSE announcements API (Result / Company Update / AGM
     │                     categories), keyword-classified into doc types,
     │                     FY/quarter labelled from "...ended DD Month YYYY" text
     ▼
sources/screener_source.py ──► single fetch of the company's Documents tab
     │                          (annual reports, concalls, credit ratings)
     ▼
   dedupe (one candidate per doc_type × period; BSE > Screener > web search,
           unless a confidence gap says otherwise - see pipeline.py:_better)
     ▼
llm_agent.py ──► Gemini batch-classifies every candidate found so far:
     │           confirms doc type + period, scores confidence, gives a reason
     ▼
   gap detection: for each doc_type, compute the N most recent expected
     │            periods (quarters/halves/FYs) and see which are missing
     │            above the confidence threshold
     ▼
sources/web_fallback.py + llm_agent.py ──► for each gap: Gemini writes 2-4
     │      targeted queries → Tavily search (DuckDuckGo backup) → Gemini
     │      validates each hit before it's accepted
     ▼
   final selection (top N per doc_type, most recent first)
     ▼
downloader.py ──► download, save to downloads/<company>/<doc_type>/,
                   write manifest.csv + manifest.json
```

Every stage degrades gracefully instead of crashing the run:

- No `GEMINI_API_KEY` (or `--no-llm`) → BSE/Screener candidates keep their keyword-heuristic confidence; web-search hits are kept but marked low-confidence and unverified in the manifest rather than auto-downloaded, since there's no reliable non-LLM way to confirm a random search hit is the right document.
- No `TAVILY_API_KEY` → falls straight to DuckDuckGo (no key needed) for the fallback stage.
- Screener's page structure changes / a selector stops matching → that function logs a warning and returns whatever it could parse (possibly nothing); BSE + web search still run normally.
- A single BSE/Screener/web request fails → logged and skipped; it doesn't take down the rest of the run.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in GEMINI_API_KEY and TAVILY_API_KEY
```

Get free API keys at:
- Gemini: https://aistudio.google.com/apikey
- Tavily: https://app.tavily.com (free tier is roughly 1,000 searches/month)

Neither key is strictly required - see the graceful-degradation notes above - but you'll get far better recall on the web-search-fallback stage with both set.

## Usage

```bash
python main.py "Tata Consultancy Services"
python main.py --company TCS --outdir ./my_downloads
python main.py "Persistent Systems" --annual 3 --quarterly 4 --no-llm
python main.py "Cyient DLM" -v            # verbose logging
```

Or from Python directly:

```python
from disclosure_fetcher.pipeline import run_pipeline
from disclosure_fetcher.config import FetchTargets

result = run_pipeline("Infosys", targets=FetchTargets(annual_reports=3))
print(result.counts_by_type())
print(result.manifest_path)
```

## Reading the output

```
downloads/
  Tata_Consultancy_Services/
    annual_reports/
    quarterly_results/
    half_yearly_results/
    transcripts/
    presentations/
    special_disclosures/
    manifest.csv
    manifest.json
```

`manifest.csv` lists **every candidate the pipeline considered**, not just what got downloaded - including ones found but rejected for low confidence, so you can review edge cases by hand. Columns: `doc_type, company, period_label, source, title, url, announced_on, heuristic_confidence, llm_confidence, llm_reasoning, local_path`. An empty `local_path` means it was found but not auto-downloaded (below `--min-confidence`, default 0.4).

## Things worth knowing before you run this at scale

- **Respect BSE's and Screener's terms of service and rate limits.** This is built to be polite by default (the `bse` package self-throttles; Screener gets exactly one GET per company, not a crawl) but you are responsible for how you use it. If you plan to query many companies on a schedule or commercially, check both sites' current ToS, and consider Screener's own limited official API (`screener.in/api/docs/`) instead of the HTML scrape in `screener_source.py`.
- **Half-yearly results being 0 for a large/mid-cap company is expected, not a bug.** SEBI has required quarterly reporting for main-board equity since 2017; half-yearly reporting mostly survives for SME-platform-listed companies and debt-only-listed issuers. The pipeline surfaces this as an explicit note in `result.warnings` rather than silently returning nothing.
- **Screener's HTML structure isn't officially documented** and the parsing in `screener_source.py` is written defensively (falls back to whole-page scanning, wrapped in try/except per section) precisely because it may need small selector updates if Screener redesigns their page. It's a bonus source; BSE carries the system if Screener parsing yields nothing.
- **The web-search fallback currently only accepts direct file links** (URLs ending `.pdf/.ppt/.pptx/.doc/.docx`), not IR-page landing pages that list several PDFs. This keeps the "go/no-go" gate simple and safe, but means a transcript that only exists behind a non-obvious IR-page link may be missed. `sources/web_fallback.fetch_page_text()` is already there as the building block for a v2 that follows landing pages and asks the LLM to pick out the right link from the page text - that was left as an extension point rather than built out, to keep the LLM's job (and the review surface in manifest.csv) simple for v1.
- **BSE scrip codes and page structures can change.** The `bse` package (BennyThadikaran/BseIndiaApi) is actively maintained; if BSE changes their API, update it via `pip install -U bse` before assuming this code is broken.
- I could not test live network calls to bseindia.com, screener.in, Tavily, or the Gemini API from the sandboxed environment this was built in (only package registries are reachable there) - every API shape used here was verified against the `bse` package's actual installed source code, Screener's public search endpoint, and the official current docs for Tavily/Gemini/`ddgs`, and the pure date/fiscal-quarter logic was unit-tested directly. But you should still do a first run with `-v` on a company you know well and skim `manifest.csv` before trusting this unattended.

## Extending it

- **More companies in one run**: loop `run_pipeline()` over a list, with a delay between companies - `main.py` is intentionally single-company so you can see this clearly; a `batch.py` wrapper is a natural next step.
- **Concurrency**: everything here is sequential by design, to stay well under free-tier rate limits (Gemini's free tier is roughly 10-15 requests/minute depending on model). If you upgrade to a paid Gemini/Tavily tier, `llm_agent.classify_items` and `sources/web_fallback.WebSearchClient.search` are the two places to parallelize.
- **NSE as an additional source**: NSE India publishes a similar (if differently shaped) corporate-announcements feed; `sources/bse_source.py` is the template to copy for an `nse_source.py`.
- **Following IR-page landing links**: see the fallback-limitation note above.

## Fund integration (vendored copy)

This copy lives at `research/disclosure_fetcher/` inside the AI-Native Fund
repo (sibling of `research/equity_researcher/` — shared research tooling,
not part of that subsystem itself) and is also mirrored standalone at
`tools/disclosure_fetcher/` in the separate Agentic Equity Researcher
project. Two changes from upstream, both about the key-free/fallback
boundary:

- **`config.ENABLE_WEB_FALLBACK` (env `ENABLE_WEB_FALLBACK`, default `0`/OFF)** gates the Gemini-classification stage (`llm_agent.py`) and the
  Tavily/DuckDuckGo web-search-fallback stage (`sources/web_fallback.py`)
  together. When OFF (the fund's default), **BSE + Screener are the only
  sources that run** — no API key needed, `google-genai` / `tavily-python`
  / `ddgs` are never imported, and `pipeline.run_pipeline()` accepts a
  `_NullLLMAgent`/`_NullWebSearchClient` stand-in instead. Candidates keep
  their keyword-heuristic confidence (same as upstream's `--no-llm`), and
  gaps BSE/Screener didn't cover are reported in `result.warnings` rather
  than searched for on the open web.
- Turning it on (`ENABLE_WEB_FALLBACK=1` or `run_pipeline(...,
  enable_web_fallback=True)`) with **neither** `GEMINI_API_KEY` nor
  `TAVILY_API_KEY` set now raises a clear `RuntimeError` at the start of
  the run, instead of silently running a degraded fallback stage — opting
  in implies you want the better coverage, so a no-key opt-in is surfaced
  as a misconfiguration rather than swallowed. DuckDuckGo itself still
  needs no key, so setting just one of the two keys is enough to pass this
  check.
- `requirements.txt` is split into a **key-free primary** block (installed
  into the fund's shared venv via `pyproject.toml`) and an **optional
  fallback** block (`google-genai`, `pydantic`, `tavily-python`, `ddgs`,
  `tenacity` — install separately only if you're enabling the fallback
  path; the fund does not install these).

Everything else (BSE/Screener parsing, fiscal-period math, manifest
format, download behaviour, politeness delays) is unchanged from upstream.
