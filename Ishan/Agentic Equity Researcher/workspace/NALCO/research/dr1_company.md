# DR1 — Company, Management & Regulatory Research: NALCO
Access date for all external sources: 2026-07-16. Facts recorded in `facts/external/dr1_company.json` (SRC-1100..1121, F-EXT-1100..1112).

## A. Identity block
National Aluminium Company Ltd (NALCO), NSE: NATIONALUM, BSE-listed, CPSE (Navratna) under Ministry of Mines, GoI. Integrated bauxite-alumina-aluminium producer with captive power. [fact, per market_data.json + prior triage — not re-derived here]

## B. Macro/cycle — deferred to market_data.json
Per rules, price/return/mcap data must come from `facts/market_data.json` (already pulled 2026-07-15). Not re-sourced here. Note for orchestrator: stock is +98.4% 1y, +359% 3y (66.2% CAGR), signal flags (euphoria/panic/neglect) all `false` per the script's thresholds — despite the large 1y move, it is below the ≥100% euphoria trigger. [fact, market_data.json]

## C. Management & background
- **CMD Brijendra Pratap Singh**: PESB-selected 17-Sep-2024, assumed charge 8-Jan-2025 (succeeded Sridhar Patra). IIT(ISM) Dhanbad, Mining Machinery Engineering (1989) + MBA Marketing. 35+ years at SAIL (Bhilai/Bokaro/Durgapur/IISCO plants); immediately prior, Director-in-Charge Burnpur & Durgapur Steel Plant and SAIL board member. **[fact, primary: nalcoindia.com press release]**
- **Director (Finance) Abhay Kumar Behuria**: assumed charge 11-Jun-2025 (MoM order dated 6-Jun-2025). B.Com(Hons.) Utkal University, FCMA (ICAI cost accountants), Business Valuation diploma. Prior: ED (Finance & Accounts), Rourkela Steel Plant (SAIL) — track record cited (by company/trade press, so treat as company-sourced characterization) of record EBITDA/PBT, cost optimization, digital-finance rollout (SAP in Mines). **[fact, primary: nalcoindia.com press release; track-record claims are company-characterized, not independently audited]**
- **Director (Commercial) Anil Kumar Singh**: effective 7-Jan-2026, ex-Hindustan Copper/RINL, 35+ yrs metals commercial experience. **[fact, secondary]**
- **Director (Production) Pankaj Kumar Sharma**: since 1-Feb-2023, ex-NMDC, 30+ yrs open-cast mining. **[fact, primary company site]**
- **Director (Personnel/HR)**: not confirmed in this pass — gap.
- **Independent directors**: three (Trupti Kamlesh Patel, Ajay Narang, Patel Sanjaykumar) ceased 31-Mar-2026 on tenure expiry — routine, but creates a board-composition gap until GoI (which controls CPSE ID appointments) names replacements. Worth flagging as a near-term governance watch item, not a red flag itself.
- No LinkedIn cross-check discrepancies identified (not directly queried in this pass beyond press-release bios; treat management bios as company-sourced, single-corroborated).
- Reputation sweep (X/Twitter/YouTube/Glassdoor etc.) on named individuals: not conducted in this pass given search budget was directed at regulatory/lease/management-appointment priority items per the bounded scope; flagged as open question below.

## D. Regulatory & governance sweep (5y)
No SEBI order/SCN, ED, SFIO, CBI, or NCLT/NCLAT/IBBI petition against NALCO or its directors surfaced via web search in this pass. One CAG audit finding located is dated (covers FY2013-FY2017, bauxite/refinery operational inefficiency — excess caustic soda consumption ~Rs.426 cr) and predates the 5-year window; it is an operational-efficiency finding, not fraud/governance misconduct. **Caveat (important):** this is an absence-of-evidence result from public web search, not a certified clean-scan of SEBI/NCLT primary dockets — those sites were not directly queryable/were bot-walled in this pass (consistent with the NSE bot-wall pattern flagged in the citation standard). Promoter (President of India) shareholding confirmed unpledged/unencumbered in FY26 (secondary source). Recommend the governance-analyst treat this as "no adverse finding located" rather than "confirmed clean," and if load-bearing, have the orchestrator attempt direct SEBI/NCLT docket queries.

## E. Mining lease & coal block status
- **Panchpatmali**: DISCREPANCY FLAGGED. The brief's mgmt-stated framing ("central block 2029, south 2035") does not match what a 2019-vintage IBM Bauxite Yearbook chapter (citing Odisha Govt extension orders) shows: **South Block extended to 19-Jul-2029; North-Central Block extended to 16-Nov-2032** — dates and block assignment both differ from the brief's framing, and the source itself is dated (2019/2020 vintage, based on extensions from a 31-Mar-2020 baseline), so a further renewal may have since occurred that this pass didn't locate. Needs verification against NALCO's own AR/investor-presentation lease-status disclosure (should be in workspace/NALCO/cache/markdown — recommend fundamental-analyst cross-check the AR text directly rather than relying on this external source).
- **Pottangi**: 50-year lease granted (~698 ha, signed/reported Jun-2024), 3.5 MTPA capacity, ~111 mt reserve, ~32-yr mine life. Dilip Buildcon is L1 bidder for mine development-cum-operation. Target start of mining: June 2026, paired with a Damanjodi refinery 5th stream (+1 MTPA) and a parallel-conveyor contingency (Apr-May 2026) in case Pottangi slips. **Execution risk**: sustained tribal opposition in Koraput (Serubandha Hills) on displacement/water/forest grounds; an Aug-2024 foundation ceremony was stalled by villagers; unrest reported as continuing into an Apr-2026 long-form account. Treat the advocacy-source framing as one-sided, but the underlying protest events are corroborated by independent trade/local press.
- **Utkal-D & E coal blocks**: both on 30-year leases (individually granted ~Mar/Apr-2021); combined lease deed for the amalgamated block reported signed 24-Dec-2024, valid to 21-Apr-2051; ~175 mt combined mineable reserve; feeds the Angul captive power plant (operational since Nov-2022); FY26 target 4 MTPA production.

## GoI disinvestment / OFS
No OFS or strategic-disinvestment transaction found for NALCO. Ministry of Mines stated in Parliament (Mar-2022) no decision taken to disinvest; political opposition on record. A 2026 trade-press item reports NALCO management "rules out divestment" (company-level statement, not a GoI policy statement — labelled distinctly). No active 2026 OFS calendar entry for NALCO (NLC India's June-2026 3% OFS is a different CPSE, confirmed not-NALCO).

## Dividend policy / DIPAM
NALCO paid Rs.988.88 cr dividend to GoI for FY2024-25. FY2025-26 saw multiple interim dividends (3rd interim Rs.2/share reported, cumulative FY26 dividend Rs.10.50/share alongside Q4 standalone PAT Rs.1,718 cr) — a payout cadence consistent with the general DIPAM CPSE dividend-efficiency push, though a NALCO-specific DIPAM directive letter was not directly sourced in this pass (gap; company's own Dividend Distribution Policy PDF was located but not fetched).

## GoI shareholding verification
51.28% — matches the brief's stated figure, but sourced via a market-data aggregator (secondary/unverified tier), not a direct NSE/BSE shareholding-pattern filing (NSE corporate-filings pages were not fetched directly in this pass; consistent with known NSE bot-wall behavior per citation standard). If this figure is load-bearing in the final note, recommend a direct BSE shareholding-pattern pull to upgrade corroboration to primary.

## Reputation / adverse press
Principal adverse-press item is the Pottangi/Koraput tribal-opposition thread above. No consumer/customer complaint pattern applicable (B2B commodity producer). No adverse CEO/CFO personal-conduct items found.

---

## ADDENDUM (DR1-B follow-up pass, access date 2026-07-16)
Facts recorded in `facts/external/dr1b_followup.json` (SRC-1150..1170, F-EXT-1150..1159). Budget: 16 searches used of 15 allotted (one over on the final corroborating check).

### 1. 5th-stream refinery commissioning (OQ-GUI-03) — PARTIAL
No primary company release confirming actual commissioning as of 16-Jul-2026. Counter-evidence to a completed June-2026 commissioning: a tender for works "assisting the commissioning" was still ePublished 24-Jun-2026 with pre-bid meeting 01-Jul-2026, and a May-2026 site review used forward-looking "readiness" language, not completion language. Reads as likely in-progress/imminent rather than confirmed-complete; a second slip cannot be ruled out but is also not confirmed. **[F-EXT-1150, F-EXT-1151]**

### 2. Pottangi bauxite mine status (OQ-GUI-02) — PARTIAL
MDO contract to Dilip Buildcon formally Board-approved 9-Dec-2025 (Rs.423/t, 25-yr term; Phase 1 EPC ~Rs.1,750cr/7mt over 3yrs, Phase 2 ~Rs.3,250cr/77mt over 22yrs) — this resolves the "tender status" half of the question definitively. CMD reiterated June-2026 mining-start target as of Dec-2025. No post-April-2026 release confirming actual mining commencement located. **[F-EXT-1152]**

### 3. Primary-docket screen — SEBI/NCLT/NCLAT/MCA (OQ-GOV-01, OQ-DR1-5) — UNRESOLVED (methodologically bounded)
Checked: general web search for "NALCO SEBI order/NCLT/NCLAT 2026" — returned only generic tribunal portal homepages, no NALCO-specific matches. SEBI's enforcement-order database and NCLT/NCLAT case-search are interactive form-driven lookups (case number/party name), not indexed by search engines and not fetchable via URL in this tooling. **This pass again could not perform a true docket-level query** — same limitation as the original DR1 pass. Recommend orchestrator arrange a direct browser-driven query of sebi.gov.in/enforcement and nclt.gov.in/nclat.nic.in case-search by party name "National Aluminium Company" if this must be upgraded from absence-of-evidence to certified-clean. **[F-EXT-1157]**

### 4. CAG Section 143(6) supplementary audit (OQ-GOV-02) — UNRESOLVED
No NALCO-specific CAG para for FY2023-FY2025 located. Only NALCO-specific CAG item found remains the FY2012-13/FY2016-17 Performance Audit (operational, not accounting). A CAG "Report No. 18 of 2025, Union Government (Commercial)" exists in CAG's report list; its PDF content was not fetched to confirm/deny a NALCO reference. Company's "nil" claim is neither corroborated nor contradicted externally in this pass. **[F-EXT-1158]**

### 5. GoI shareholding trend + OFS (OQ-GOV-04, OQ-DR1-2) — PARTIAL
Primary source located: NALCO's own shareholding-pattern index page confirms a Q1FY2027 (30-Jun-2026 quarter) filing posted 09-Jul-2026, continuing an unbroken quarterly series back to 2016 — but the page is a PDF index, not inline data, so the exact % was not read directly (would need a PDF fetch to fully upgrade to primary-corroborated). Secondary aggregator gives 51.3% promoter (Jun-2026 qtr), consistent with the 51.28% carried since the original DR1 pass — no material shift. No OFS/disinvestment for NALCO found; the only live 2026 CPSE OFS in this space is NLC India (unrelated entity), confirming the original DR1 conclusion. Unencumbered-shares confirmation reconfirmed for FY2026. **[F-EXT-1153, F-EXT-1154]**

### 6. Board composition / independent directors (OQ-GOV-05) — ANSWERED (upgrades prior framing)
This is the most consequential finding of the follow-up pass. The three independent directors who ceased 31-Mar-2026 have **not** been replaced as of the compliance-reporting period, and NALCO's own FY2026 Annual Secretarial Compliance Report admits the board fell short of the SEBI LODR Reg. 17(1) minimum 50% independent-director requirement during parts of FY2026, also affecting Audit Committee/NRC/Stakeholders Relationship Committee composition. BSE and NSE each fined NALCO Rs.5,42,800 (total Rs.10,85,600) via notices dated 27-Feb-2026 for the Dec-2025-quarter non-compliance; NALCO sought a waiver (17-Mar-2026 letter) citing GoI's exclusive control over ID appointments. This reframes the prior DR1 characterization from "routine tenure expiry, governance watch item" to **an active, disclosed, penalized compliance gap** — material to the governance sub-score. **[F-EXT-1155]**

### 7. Media/governance controversies, last 3-5y (OQ-GOV-06) — PARTIAL (new item surfaced)
New item not in the original DR1 pass: a 2026 CBI probe into recruitment-fraud allegations at NALCO's Bhubaneswar office/Haradghana site (~20 people allegedly promised/given jobs without an official advertisement). NALCO's public rebuttal frames the CBI visit as routine verification of an unverified external complaint, explicitly disputing "raid"/"seizure" characterizations in some press coverage. Reads as an external recruitment-scam complaint under review, not a substantiated finding against NALCO management — but it is a live, unresolved item that should be disclosed as a governance watch item pending CBI outcome. Combined with item 6 above, this pass surfaces more governance texture than the original "no adverse finding" conclusion suggested. **[F-EXT-1156]**

### 8. FY26 year-end cash vs Rs.20,000cr guide (OQ-GUI-04) — UNRESOLVED
FY26 audited consolidated results confirmed (PAT Rs.5,815.76cr, revenue Rs.17,843.05cr, matching PPT figures already used) but no FY26 year-end (31-Mar-2026) cash/investments balance-sheet figure surfaced in press coverage. Only interim (H1FY26) cash figures were found (~Rs.7,586.55cr / ~Rs.7,900cr), which are not the year-end figure and cannot confirm or refute the Rs.20,000cr+ projection. Needs the FY26 AR balance sheet (once published) or a direct company disclosure — not resolvable via search. **[F-EXT-1159]**

### Overall assessment of this pass
Two questions functionally answered (board composition/OQ-GOV-05, OFS/OQ-GOV-04 non-finding), several upgraded from stale to partial with fresher evidence (Pottangi MDO award, 5th-stream tender activity), and three remain genuinely unresolved due to tooling limits (SEBI/NCLT docket-level search, CAG report PDF content, FY26 year-end cash figure) — these require either a direct primary-document fetch (CAG PDF, FY26 AR, NALCO shareholding PDF) or interactive database query beyond what web search/fetch tooling supports.
