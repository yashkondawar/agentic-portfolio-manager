# `tools/er_corpus/` — the broker-note corpus toolchain

Builds and profiles a local corpus of Indian sell-side **initiation-of-coverage**
notes, so the ER agent's methodology can be derived from *many* real notes instead
of one. Everything here is deterministic and costs **zero LLM tokens** — the same
doctrine as the rest of `tools/` (CLAUDE.md rule 1).

Why it exists: `docs/PROCESS_V2_REIMAGINED.md` was reverse-engineered by hand from
a single benchmark note (Emkay, NALCO, 2016). Useful, but a sample of one. This
toolchain turns "what does a good initiation note do?" into a counted question.

## Layout

```
reference/er_corpus/
    seeds/*.txt              candidate URLs (one per line, optional TAB-separated hints)
    pdf/<broker>/<id>.pdf    downloaded sources
    md/<broker>/<id>.md      markitdown conversion, page-anchored
    manifest.csv             one row per attempted URL — including every failure
    profile.json             per-note structural profile
    profile_summary.md       corpus-level statistics (the counted backbone)
    extracts/<id>.json       LLM deep-read output (phase 2, written by agents)
```

## Usage

```bash
# 1. discover candidates from crawlable hosts, and merge/dedupe seed files
python tools/er_corpus/discover.py --crawl
python tools/er_corpus/discover.py --merge reference/er_corpus/seeds/*.txt

# 2. download + convert (resumable; checkpoints the manifest after every note)
python tools/er_corpus/fetch_corpus.py --seeds reference/er_corpus/seeds/all_pending.txt
python tools/er_corpus/fetch_corpus.py --seeds ... --limit 40      # bite-sized run
python tools/er_corpus/fetch_corpus.py --refresh-meta              # re-derive metadata, no downloads

# 3. profile the corpus (rebuild any time) -> reference/er_corpus/profile_summary.md
python tools/er_corpus/profile_notes.py
python tools/er_corpus/profile_notes.py --summary-only

# 4. digest the notes -> reference/er_corpus/digest/<broker>__<company>__<date>__<hash>.md
python tools/er_corpus/digest_notes.py
```

**Seed files.** `discover.py --merge` writes **`all_pending.txt`** — the deduped set of
candidates not yet fetched. There is no `all.txt`; an earlier version of this README told you
to fetch one, and the command failed on a missing file. The other files in
`reference/er_corpus/seeds/` are inputs to that merge: `discovered.txt` (from `--crawl`) and
the hand-assembled `harvest_*.txt` batches.

**Step 4, `digest_notes.py`, is a full member of the toolchain** and was previously documented
only in `docs/ER_CORPUS_FINDINGS.md` §11. It produces a ~6x-compressed **reading copy** of each
note: the cover/tearsheet verbatim, the detected section order, the rating and target price as
regex-extracted, exhibit and `Source:` counts, and the exhibit titles it could recover. It is a
deterministic extract, **not a summary** — nothing in it is paraphrased, and financial-statement
appendices, disclaimers and repeated running headers are dropped. Use the digest to find the
note you want, then open the full markdown under `md/` for anything the digest truncates (each
digest links to its own full path in the header). This is the file to read when grounding a
sector playbook in what a broker actually wrote.

`fetch_corpus.py` reuses `tools/convert_docs.py:convert_markdown()`, so corpus notes
are converted by exactly the same code path as a real run's step 0.5 CONVERT.

## Access reality (probed 2026-08-02)

| Host | Status | Notes |
|---|---|---|
| `bsmedia.business-standard.com/_media/bs/data/market-reports/equity-brokertips/YYYY-MM/*.pdf` | **serves PDFs** | The richest source by far — a date-partitioned mirror carrying Nuvama, JM Financial, Anand Rathi, ICICI, Nirmal Bang, Elara and others, spanning ~2010–2026. Filenames are opaque timestamps, so it **cannot be enumerated**; and `business-standard.com` listing pages return **403** to non-browser clients. Only reachable via web search. |
| `mailcontent.icicidirect.com/**.pdf` | serves PDFs | ~100 links on one ICICIdirect research index page; many are result updates, filtered downstream. |
| `barodaetrade.com/Reports/*.pdf` | serves PDFs | Flat directory. |
| `reports.emkayglobal.com/downloads/*.pdf` | serves PDFs | Flat directory, sparse index. |
| `kotaksecurities.com/pdf/coverage/*.pdf` | serves PDFs | Not directory-listable; individual URLs work. |
| `investmentguruindia.com/editorial/uploads/news-pdf/*.pdf` | serves PDFs | Aggregator, mixed content. |
| `hdfcsec.com/hsl.research.pdf/*.pdf` | **404** | Search engines still index these paths but the host now redirects to `/404`. Dead. |
| `trendlyne.com/research-reports/broker/<X>/` | HTML loads, no PDFs | Report links are JS/API-driven. |
| `geojit.com`, `smifs.com`, `choiceindia.com`, `nirmalbang.com` research indexes | 404 on probed paths | Paths have moved. |

## WebFetch permissions

`bsmedia.business-standard.com` is only reachable via web search (see the table above), so the
fetch path needs explicit `WebFetch(domain:...)` grants. Those live in `.claude/settings.json`,
which is strict JSON and cannot carry comments — so the rationale lives here.

Fourteen domains were added on 2026-08-03, chosen by how many corpus URLs actually resolve to
them (counted across `tools/er_corpus/*.py` and `reference/er_corpus/seeds/*.txt`), led by
`bsmedia.business-standard.com` at 234 URLs — over twice the next source:

| Domain | Corpus URLs |
|---|---|
| `bsmedia.business-standard.com` | 234 |
| `mailcontent.icicidirect.com` | 96 |
| `images.assettype.com` | 22 |
| `simplehai.axisdirect.in` | 20 |
| `jmflresearch.com` | 18 |
| `dalal-broacha.com` | 18 |
| `investmentguruindia.com` | 17 |
| `barodaetrade.com` | 12 |
| `icicidirect.com` | 8 |
| `kotaksecurities.com` | 7 |
| `reliancesmartmoney.com` | 6 |
| `nirmalbang.com` | 6 |
| `smifs.com` | 5 |
| `rathi.com` | 4 |

**`hdfcsec.com` is deliberately NOT granted**, despite ranking third by URL count (26). The host
404s — search engines still index the paths but it redirects to `/404` (probed 2026-08-02, see
the access table above). Granting a dead domain buys nothing and makes the permission list read
as if that source were live.

Note also that `EXCLUDED_BROKERS = {"motilal_oswal"}` in `corpus_lib.py` governs the corpus
only. `prompts/31` step 3b now carries the same exclusion into **live** DR2 research, which it
previously did not — so the instruction is enforced on both paths rather than just this one.

## Two things that will bite you

**1. Ligatures.** pdfminer (under markitdown) drops `ti`/`fi`/`fl`/`ff` ligature
glyphs in many broker-report fonts. *"Initiating Coverage"* converts to
*"Ini a ng Coverage"*, *"identified"* to *"iden fied"*. A naive
`"initiating coverage" in text.lower()` therefore misses a large share of genuine
initiations. Always use `corpus_lib.contains_fuzzy()`, which also tries the
ligature-stripped form of the search term.

**2. Chart exhibits vanish.** Broker exhibits are usually rendered charts, and
markitdown recovers no text from an image — so the *"Exhibit 12: EBITDA/tonne"*
title disappears with the picture. `n_exhibits` is therefore an undercount, badly
so for chart-heavy houses (a Nuvama note profiled 0 labelled exhibits and 95
`Source:` lines). `profile_notes.py` reports `n_source_lines` alongside it,
because the *"Source: Company, XYZ Research"* attribution beneath each exhibit
survives as real text and is the better density proxy. **Never quote `n_exhibits`
on its own.**

## Manifest statuses

| status | meaning |
|---|---|
| `ok` | downloaded, converted, and confirmed an initiation note |
| `not_initiation` | fetched fine but reads as a result/company update — kept as a contrast set unless `--initiations-only` |
| `excluded_broker` | Motilal Oswal, excluded by instruction. Detected from the **document body**, not the URL, because the mirror's filenames reveal nothing |
| `http_error` / `fetch_error` / `not_pdf` / `too_large` / `convert_error` | self-explanatory; the row is kept so the corpus never silently shrinks |

## Scope and use

PDFs are downloaded for local analysis only. Derived documents
(`docs/ER_CORPUS_FINDINGS.md`, the sector playbooks, the thesis archetypes) are our
own synthesis — no substantial reproduction of source text, short attributed
quotes only. Do not redistribute the `pdf/` tree.
