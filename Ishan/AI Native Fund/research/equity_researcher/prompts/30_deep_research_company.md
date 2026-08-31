# 30 — Deep Research 1: Company, Management, Regulatory & Cycle Context
*(refined from DR "1st" prompt set; sonnet tier; WebSearch/WebFetch. Consumes open questions routed `deep_research_company` + the standing checklist below.)*

## Ground rules
- **Never search for what a script already pulled.** Prices, returns, mcap, index levels, euphoria/panic signals come from `facts/market_data.json` (yfinance). If that file is missing items, say so in your summary — the orchestrator re-runs the script; you only web-source prices as last resort with an explicit `second_best_evidence` flag.
- Every finding: URL + access date + `fact|opinion` label + corroboration tier (primary regulator/exchange > reputable press > social/blog = unverified). Citation standard §1 applies.
- Prior deep-research documents in input/ are pre-filled answers: validate freshness, fill gaps, don't redo.
- Every external fact carries `impacts: [module names]` so the orchestrator can invalidate stale findings.

## Standing checklist (always, beyond routed questions)

**A. Identity block** (report starts with this): company, ticker, exchange(s), industry/sector, one-line business, mcap.

**B. Macro & cycle positioning (top-down filter)**
- Credit cycle: is the credit window open (easy money) or shut? Evidence: policy rate path, credit growth, spreads (RBI data preferred).
- Sentiment stage of the relevant market-cap segment and sector index; note euphoria/panic signals **read from market_data facts**: 1y return ≥ +100% (euphoria/avoid), 1y ≤ −40% or 5y CAGR ≤ −10% (panic/protracted decline), ~zero 10–12y return (neglect).
- Where in its own earnings cycle the sector sits (upcycle year N / peak signs / downcycle).

**C. Management & promoter background**
- Key people: career history, prior ventures and their outcomes, LinkedIn cross-check (flag discrepancies with filings' bios).
- Risk attitude through cycles: leverage/deal behaviour when money was easy vs tight (feeds governance module).
- Reputation sweep: X/Twitter, YouTube, Glassdoor/Indeed/Naukri (culture & ethics signals from ex-employees), customer complaint patterns. Consensus table: customers / employees / investors — positive/negative/mixed, with representative citations. Opinions labelled as opinions.
- Boolean seeds: `"[COMPANY]" OR "[PROMOTER]" reviews complaints issues` · `site:linkedin.com/in "[KEY_MANAGER]"` · `site:twitter.com "[COMPANY]" (issue OR problem OR fraud)` · `site:youtube.com "[COMPANY]" review OR expose`.

**D. Regulatory & governance sweep (India)**
Check, for company + promoters, last 5 years: SEBI (orders, SCNs, investor complaints) · BSE/NSE (disclosures, shareholding pattern incl. pledge, bulk/block deals — summarize context in 1–2 lines, auditor changes) · MCA/ROC (master data, charges, director changes, DIN status) · NCLT/NCLAT + IBBI (petitions) · ED/SFIO/CBI · RBI if BFSI-linked · High Court/SC judgments where relevant. Corroborate press with filings.
- NSE URL patterns (replace TICKER, no quotes, caps): announcements `https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol=TICKER&tabIndex=equity` · corporate actions `…/corporate-filings-actions` · shareholding `…/corporate-filings-shareholding-pattern`. NSE blocks bare fetches at times — fall back to BSE listing page or exchange-filing aggregation via search, and record which source actually served the data.
- Boolean seeds: `"[COMPANY]" SEBI order OR "show cause" site:sebi.gov.in` · `site:nclt.gov.in "[COMPANY]"` · `"[COMPANY]" "Enforcement Directorate" OR SFIO OR CBI` · `site:mca.gov.in "[CIN]"`.
- **Output**: chronological table Date | Event/Finding | Source (URL, tier) | 1-line summary.

**E. Political & counterparty risk (quantified where possible)**
Electoral/policy exposure (subsidy/waiver-sensitive segments); receivables from government bodies (MoD, SEBs, state entities) — days and trend if disclosed or findable.

## Output
`facts/external/dr1_*.json` (external fact records + registry entries) + `research/dr1_report.md` (bullets/tables, headed per section) + answered-question updates + new open questions + summary listing `impacts`.
