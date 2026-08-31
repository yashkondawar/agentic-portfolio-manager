# Deep Research 2nd iteration

## 1. Comprehensive Web & Deep Search Prompt

Objective: You are a data-gathering expert. Your mission is to perform a comprehensive web and deep search for the target company [mentioned as per documents attached] and its industry. You will gather all necessary external data required to complete a multi-stage equity research report. Prioritize primary regulatory sources, reputable financial data providers, and credible news outlets. Supplement this with deep searches on social and professional networks.

Mandatory Macro & Cycle Positioning Check (Top-Down Filter):

•	Credit Cycle Status: Assess the current state of the Interest Rate & Credit Cycle (Layer 1). Is the "Credit Window" wide open (easy money, high risk) or slammed shut (tight credit, bargains available)?

•	Sentiment Stage: Determine the position of the Sentiment & Psychology Cycle. Is the market in Stage 3 (Idiot Stage), characterized by everyone believing things will get better forever, signaling an exit/defensive posture?,.

•	Contrarian Price Signal: Analyze the relevant Market Cap Index and Sectoral Index (e.g., Nifty Pharma) for the following signals over the last 5 years:

o	Euphoria Signal (AVOID): Absolute Return $\geq 100%$ in the last 1 year (Asset may not give good returns next year),.

o	Panic Signal (BUY): Absolute Return $\leq -40%$ in the last 1 year, or CAGR $\leq -10%$ over 5 years (Protracted Decline),.

Output Instructions: Present all findings under task-specific headings (e.g., "Task 2: Company & Management Background"). Use bullet points for qualitative data and Markdown tables for quantitative data. For every fact, number, or significant claim, provide the source URL and the date accessed. Label missing data as N/A. Always differentiate between facts and opinions and mention it. Present all the information in crisp bullet points or tables with minimum paragraph content. Keep all the tables you find in Appendix in report itself, don’t give downloadable CSVs give all of it in the report itself (all tables without filtering).

Use https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol=’TICKER’&tabIndex=equity for company disclosures for last 3 years. (Find better how to capture and replace ‘TICKER’ in the link by actual ticker without single quote marks of the company in focus in capital letters) Use https://www.nseindia.com/companies-listing/corporate-filings-actions for company’s corporate actions for last 3-5 years. Use https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern for latest shareholding pattern.

2. Initial Deep Search: Company & Management Background

Search across the public web, including social platforms (LinkedIn, X/Twitter, YouTube), forums, and news archives.

First and foremost: Start with Company name, Ticker, Industry, Sector, Business (short description), and Market Cap. And while giving output start report with these points.

Management & Promoter Background: Compile a table of key management personnel with their career history, previous roles, and any notable public track record (successes or controversies). Verify against their LinkedIn profiles and flag discrepancies.

•	Risk Attitude & Behavior Check: Analyze the management's track record concerning leverage and prudence. Did management demonstrate prudence/defensiveness when the Credit Window was wide open (easy money) by maintaining lower leverage than peers, or did they engage in "dumb deals" or excessive leverage near a cycle peak?,.

Search for any past or present legal cases, regulatory scrutiny, or criminal records, or third-party transactions, related party transactions, insider trading or SEBI related issues associated with the company's promoters and key management using the queries below.

Company Reputation & Employee Feedback: Find public views, reviews, and complaints about the company, its products, and services from customers and stakeholders on platforms like X/Twitter, job boards like Glassdoor, Indeed, Naukri, LinkedIn or any other and YouTube.

Search for posts and articles by former employees on LinkedIn and other platforms regarding company culture, ethics, and operations. And present consensus in a table citing positive or negative for all 3.

Execute the following boolean searches: "[COMPANY_NAME]" OR "[PROMOTER_NAME]" reviews complaints issues site:linkedin.com/in/ "[KEY_MANAGER_NAME]" site:twitter.com ("[COMPANY_NAME]" OR "[PRODUCT_NAME]") (love OR hate OR issue OR problem) site:youtube.com "[COMPANY_NAME]" review OR expose.

3. Task 2 & 3: Regulatory & Governance Deep Dive (India-Specific)

Regulatory Filings & Actions: Search the following regulator websites for any records, orders, or disclosures related to [company] and its promoters over the last 5 years.

Mandatory Sources to Check: SEBI: Search for orders, show-cause notices, and investor complaints, SCOs. BSE/NSE: Retrieve all company disclosures, focusing on shareholding patterns (for promoter pledge data), material events, and auditor changes, get latest shareholding data and create table, get latest or recent any bulk deals or block deals data and present context/summary in 1-2 lines. MCA/ROC: (Ministry of Corporate Affairs / MCA21) Check for company filings, creation of charges on assets, and changes in directors, company master data, filings (e.g., annual returns, charge creation, changes in directors, MOA/AOA filings) NCLT/NCLAT: Search for any insolvency petitions or other company petitions, NCLAT orders (insolvency / company petitions). ED/SFIO/CBI: Search for any investigations, orders, or attachments, FIRs. IBBI (insolvency listings) / insolvency proceedings. RBI (if company is NBFC / bank-linked),. Major Indian financial press (Economic Times, Business Standard, Mint, LiveMint, The Hindu BusinessLine, BloombergQuint, Reuters India) use as secondary sources and corroborate with filings. Court judgments (High Courts / Supreme Court) when relevant. LinkedIn / company website for management bios verification (flag discrepancies). LinkedIn/X Company related views, claims, reviews, complaints (good or bad, facts and opinions both).

Quantifying Political & Counterparty Risk (Advanced India Filter):

•	Electoral/Policy Risk: Quantify the company's explicit exposure to Electoral/Policy Risk (e.g., risks from potential Farm Loan Waivers in Agri/MFI portfolios),,.

•	Counterparty Risk: Closely track and quantify the risk of money stuck in slow-paying government bodies, specifically: Receivable Days from the Ministry of Defence, State Electricity Boards (SEBs), or specific state government bodies,,,.

Execute the following boolean searches: "[COMPANY_NAME]" SEBI order OR "show cause" site:sebi.gov.in "[COMPANY_NAME]" (BSE OR NSE) disclosure "pledge" OR "shareholding pattern" site:nclt.gov.in "[COMPANY_NAME]" "[COMPANY_NAME]" "Enforcement Directorate" OR "SFIO" OR "CBI" site:mca.gov.in "COMPANY" OR "CIN" OR "charges". Output Format: Create a chronological table of all significant findings with columns: Date | Event/Finding | Source (URL) | Summary.

4. Task 5, 6 & 7: Data for Strategy & Valuation

Company specific historical inputs (This information is essential and needed): Find and present information in following format:

Metric	Financial year Current (T)	Financial year (T-1)	Financial year (T-2)	Financial year (T-3)	Financial year (T-4)	Financial year (T-5)

Price (Per share) (Average)

Price Returns yearly

Market Cap (Average)in Cr.

•	Note on Time Horizon: Data should extend to T-5 to check for the Protracted Decline Buy Signal (5-year CAGR $\leq -10%$). If historical price data is readily available, record price returns for T-10/T-12 to check for the Long-Term Neglect Buy Signal (Zero return over 10 to 12 years).

After peer identification need to do only one deep research with headings qualitative (sub headings company specific, sector specific), quantitative aspects (sub headings company specific, sector specific). Strictly no company financial data, search and give only asked data and numbers.

## 5. Deep Research 2: Sector/Industry specific prompts (Peers Identification)

You are an expert buy-side equity & research analyst. Your mission is to perform a comprehensive web and deep search to produce a rigorous competitor / peer analysis for a listed company....

do these steps exactly Peer identification (priority order)

Start with any peer list already present in the supplied documents.

If not present then search online (use Screener.in, StockScans.in, Capitaline, or other reputable market intelligence platforms, perplexity finance) to find relevant listed peers in the same industry/sector (up to maximum 8). Only listed companies with comparable business. Once you are done finding relevant domestic competitors only then check for similar sized (market cap and/or revenues /business model/ type of business) international competitors (up to maximum 8) for comparison, do change all currency adjustments into INR for international.

For each candidate peer, record the source(s) used (e.g., “Screener.in — RELIANCE, retrieved 2025-09-08” or “StockScans, TCS, retrieved 2025-09-08”). Show the exact query used (brief).

Important additional instruction (use exactly as stated): Change to similar businesses for domestic and international competition for valuations with specifically mentioning changes in ops or model or any other.

Output: Provide a list or table with names of domestic and international competitors. (feel free to add any relevant information after the table in bullet points.

Value Chain Mapping & Bottleneck Identification (Top-Down Context):

Value Chain Mapping: Map the Horizontal (Raw Material $\rightarrow$ Processing $\rightarrow$ End User) and Vertical (local competitors) chain for the target sector.

Integration Strategy: Determine if Backward or Forward integration by the company is designed to mitigate Input Price Volatility or secure Distribution Monopoly in a key region.

Bottleneck Location: Locate the single Bottleneck in the value chain that grants extraordinary pricing power (e.g., Spectrum in Telecom, NPPA in Pharma, Freight Cost in Cement).

## BFSI Analyst: Deep-Dive Peer Comparison & Sector-Specific Analysis

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst specializing in BFSI. Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven peer comparison report for a target BFSI entity (Bank, NBFC, or Insurer).

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, and significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize primary regulatory and reputable financial sources (e.g., Screener.in, StockScans.in, Exchange Filings, RBI/SEBI white papers).

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Competitor Strategy & Franchise Quality)

Competitive Differentiation: Research and summarize the key strategic advantages for each key peer, focusing on Liability Franchise strength (CASA quality), Asset Mix (secured vs. unsecured), and Digital Acquisition Cost Benchmarking.

Core Truth & Book Quality: Assess the peer group's ability to achieve sustainable ROA/ROCE by efficiently pricing risk. Analyze and comment on Book Value Quality (true loan loss provisioning and through-cycle stability).

Moat Analysis (Regulatory Focus): Evaluate the strength of the Regulatory Moat (driven by RBI/IRDA policies) for the target entity and its peers. Find and summarize key insights from RBI/SEBI white papers on recent or impending regulatory changes (e.g., Basel III, digital lending rules).

1.1.1 Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current P/B premium/discount is justified by ROCE Stability or if it is driven purely by the Valuation Cycle (investor enthusiasm).,.

Credit Cycle + Risk Cycle: Given the status of the Interest Rate & Credit Cycle (Layer 1), assess the specific risk to the Book Value Quality (true provisioning) and how peers handle ALM pressure due to wholesale funding reliance,.

#### 1.2 Sector Specific Aspects (BFSI Market Dynamics)

Porter's 5 Forces (BFSI-Specific):

Analyze Rivalry based on pricing of the next rupee of lending/deposit.

Assess the Bargaining Power of Suppliers (i.e., depositors/wholesale money markets) and its sensitivity to RBI rate hikes (ALM Pressure).

Upstream & Downstream Drivers:

Liabilities: Analyze the Marginal Cost of Funds for key peers, especially for NBFCs relying on the Commercial Paper market, versus the core CASA ratio.

Assets: Assess Collection Efficiency and the efficient deployment of capital against Risk-Weighted Assets (RWA).

Niche Pointers (Business Model Nuances):

For Life Insurers: Focus on VNB Margin (Protection vs. Savings mix) and the growth in Non-Par protection products.

For HFCs: Analyze sensitivity to interest rates and regional property registration volume trends.

For MFIs/Rural Lenders: Assess explicit exposure and resilience to Political Risk from state-level loan waivers.

Stress Testing: Find and summarize the results of recent stress tests on the loan book of key peers (if publicly available), especially concerning resilience to RBI rate hikes.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Core Valuation | Price date (analysis date), Market Cap, Price-to-Book (P/B), P/E (LTM), Forward P/E |

| Core Profitability | Net Interest Income (NII), Net Profit (Excl. One-offs), Earnings Per Share (Diluted) |

| Core Returns | Return on Assets (ROA) (%), Return on Equity (ROE) (%), Return on Capital Employed (ROCE) (%) |

| Asset Quality | Gross Non-Performing Assets (GNPA) (%), Net Non-Performing Assets (NNPA) (%), Provisioning Coverage Ratio (PCR) (%), Credit Cost (%) |

| Capital | Common Equity Tier 1 (CET1) Ratio (%), Capital Adequacy Ratio (CAR) (%) |

| Cash Flow Quality | FCF-to-EBITDA Conversion (%) (Mandatory check for asset/infra-heavy financials like HFCs/AUM-heavy NBFCs) |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Liability Franchise: CASA Ratio (%), Cost of Funds (%), NIM (Net Interest Margin) (%).

Growth: Loan Book/AUM Growth (YoY %), Deposit Growth (YoY %).

Insurance-Specific (If applicable): Value of New Business (VNB) Margin (%), Annualized Premium Equivalent (APE) Growth (YoY %).

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

P/B vs. ROA/ROCE Regression Analysis Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation. Specifically, analyze whether the P/B premium/discount is justified by sustained superior ROA/ROCE, and comment on the market's perceived Book Value Quality and Through-Cycle Stability. Cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $NNPA = GNPA - Provisions$; $ROA = Net\ Income / Avg.\ Total\ Assets$).

## Consumer & Retail Analyst: Deep-Dive Peer Comparison & Sector-Specific Analysis

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst specializing in Consumer & Retail (FMCG, Discretionary, Durables). Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven peer comparison report for a target Consumer entity.

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, or significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize primary regulatory and reputable financial sources (e.g., Screener.in, StockScans.in, Company Presentations/Transcripts).

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Competitor Strategy & Moat)

Competitive Differentiation: Research and summarize the key strategic advantages for each key peer, focusing on their ability to achieve Pricing Power (Gross Margin expansion), the strength of their Distribution Moat (especially rural reach/last-mile logistics efficiency), and their Brand Strength/DTC success.

DTC/Digital Focus: Analyze the DTC (Direct-to-Consumer) success and assess the Cannibalization Risk between online and traditional retail channels for key brands/peers.

Moat Analysis (Distribution Focus): Evaluate the sustainability of the Distribution Moat and the efficiency of last-mile logistics (especially for e-commerce/Q-commerce players) as the true source of competitive advantage.

Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current valuation premium/discount is justified by sustainable ROCE Stability (Layer 2) or if it is driven purely by the Valuation Cycle (investor enthusiasm/Stage 3 Euphoria). If the P/E is high, is it due to genuine ROCE improvement or merely Valuation Cycle expansion?.

Credit Cycle + Capex/Growth Cycle: Assess the company/sector's Capex demands or growth funding requirements against the current state of the Credit Window (Layer 1). Quantify the resulting FCF constraints and potential debt risk,.

Policy Cycle + Profit Cycle: If the sector is enjoying a Regulatory Moat (e.g., PLI, Indigenization List), assess the political risk and long-term sustainability of that moat, especially concerning Receivable Days (Government Counterparty Risk),.

#### 1.2 Sector Specific Aspects (Market Dynamics & Risk)

Porter's 5 Forces (Consumption Focus):

Analyze Bargaining Power of Suppliers (especially for agri-commodities and crude derivatives) and its impact on cost of goods sold.

Assess the level of Rivalry based on marketing spend and pricing/discounting strategies.

Monsoon & Rural Demand:

Quantify the Monsoon Effect by researching and correlating peer sales (especially FMCG) with recent Southwest Monsoon data, farm income, and consumption sentiment.

Find data on the sector's specific Rural Income Sensitivity Index (if available) to map sales against MSP data or monsoon performance.

Growth & Pricing Elasticity:

Determine and compare the balance between Volume growth and Premiumization as drivers of overall revenue growth for key peers.

Research and comment on the Consumer Pricing Elasticity for core product categories within the peer group.

Niche Pointers (Sub-Sector Nuances):

For QSR: Focus on Same-Store Sales Growth (SSSG) trends.

For Consumer Durables/Discretionary: Correlate performance with recent trends in US/EU housing/retail and analyze demand volatility.

For Liquor/Beverages: Comment on the impact of state-wise pricing and taxation on margins and business strategy.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Core Valuation | Price date (analysis date), Market Cap, Enterprise Value (EV), P/E (LTM), Forward P/E, EV/EBITDA (LTM) |

| Core Profitability | Revenue (LTM), EBITDA (LTM), Net Profit (Excl. One-offs), Gross Margins (%), EBITDA Margins (%), Net Margins (%), ROCE (%), ROE (%) |

| Working Capital | Working Capital Days, Inventory Days, Payables/Receivables Days, Inventory as % of Sales |

| Cash Flow | Operating Cashflows, Capital Expenditure (CapEx), FCF Post-Dividend/Acquisitions, FCF Yield (%) |

| Growth | Revenue Growth Rate (%), Expected Future Growth Rate (%) |

| Cash Flow Quality | FCF-to-EBITDA Conversion (%) (Mandatory check for asset/infra-heavy financials like HFCs/AUM-heavy NBFCs) |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Core Consumption Metrics: Volume Growth (%), Value Growth (%) (if reported), Advertising & Promotion (A&P) Spend as % of Sales.

Retail/QSR Specific (If applicable): Same-Store Sales Growth (SSSG) (%) or LFL (Like-for-Like) Growth (%), Store Count/Expansion Rate (YoY %).

Durable/Discretionary Specific (If applicable): Inventory Turnover Ratio (x), Channel Mix (% of Sales from key channels: E-commerce, GT, MT).

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

Relative Valuation Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation across key multiples. Specifically, analyze whether the premium/discount is justified by superior Gross Margin stability/expansion (Pricing Power) or the strength of the Distribution Moat (ROCE stability). Cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $Gross\ Margin = (Revenue - COGS) / Revenue$; $Inventory\ Turnover = COGS / Avg.\ Inventory$).

## Commodities & Energy Analyst: Deep-Dive Peer Comparison & Sector-Specific Analysis

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst specializing in Commodities & Energy (Metals, Cement, Oil & Gas, Power). Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven peer comparison report for a target Commodity/Energy entity.

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, or significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize primary regulatory and reputable financial sources (e.g., Screener.in, Exchange Filings, Global Industry/Price Indices).

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Cost Moat & Integration)

Competitive Differentiation: Research and summarize the key strategic advantages for each peer, focusing on their Global Cost Curve Positioning (e.g., 1st quartile vs. 3rd quartile) and the extent of Integration (Mine/Well to Finished Product) to defend against volatile intermediate Indian spot markets.

Cost Structure Moat: Analyze the role of Backward Integration (captive mines/power) in mitigating the dominant cost inputs (Energy, Coal/Power). Quantify the cost differential this provides versus peers.

Capital Allocation Strategy: Assess and compare the peer group's Capital Allocation strategy: prioritizing debt reduction, high Capex for growth, or returns through buybacks/dividends during peak cycles.

Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current valuation premium/discount is justified by sustainable ROCE Stability (Layer 2) or if it is driven purely by the Valuation Cycle (investor enthusiasm/Stage 3 Euphoria). If the P/E is high, is it due to genuine ROCE improvement or merely Valuation Cycle expansion?.

Credit Cycle + Capex/Growth Cycle: Assess the company/sector's Capex demands or growth funding requirements against the current state of the Credit Window (Layer 1). Quantify the resulting FCF constraints and potential debt risk,.

Policy Cycle + Profit Cycle: If the sector is enjoying a Regulatory Moat (e.g., PLI, Indigenization List), assess the political risk and long-term sustainability of that moat, especially concerning Receivable Days (Government Counterparty Risk),.

#### 1.2 Sector Specific Aspects (Macro & Regulatory Dynamics)

Core Truth & Price Takers: Assess how efficiently each peer manages its Cost Curve given the core truth that players are Price Takers. Analyze the Spread (Realization minus Cost) trends.

Upstream & Trade Policies:

Find evidence and assess the sustainability of any local moats created by Trade Policies (e.g., Anti-Dumping Duty, regulatory hurdles) that protect domestic producers.

For Power/Renewables, detail the average PPA terms (Power Purchase Agreement) and the associated tariff certainty for key peers.

Downstream & Demand Drivers:

Correlate demand visibility with recent and planned Government Capex and Infra Spending (e.g., National Infrastructure Pipeline - NIP).

For Cement, analyze how high freight costs make it a hyper-local business and compare regional pricing power among peers.

Niche Pointers (Sub-Sector Nuances):

For City Gas Distribution (CGD): Analyze the impact of APM Gas allocation (low-cost sourcing) on profit margins versus peers reliant on market gas.

For Oil & Gas (Upstream): Detail the direct sensitivity of profitability to Brent Crude prices and regulatory changes in cess/taxes.

Mandatory ESG/Risk: Research and identify key ESG Compliance risks (e.g., carbon taxes, pollution norms) and their potential impact on future cost structures.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Core Valuation | Price date (analysis date), Market Cap, Enterprise Value (EV), P/E (LTM), Forward P/E, EV/EBITDA (LTM) |

| Core Profitability | Revenue (LTM), EBITDA (LTM), Net Profit (Excl. One-offs), Gross Margins (%), EBITDA Margins (%), ROCE (%), ROE (%) |

| Balance Sheet | Net Debt (or Net Cash), Net Debt/EBITDA, Capital Expenditure (CapEx), Interest Coverage Ratio |

| Growth | Revenue Growth Rate (%), Production/Capacity Utilization (%) |

| Cash Flow | Operating Cashflows, FCF Post-Dividend/Acquisitions, FCF Yield (%), Dividend Payout Ratio (%) |

| Cash Flow Quality | FCF-to-EBITDA Conversion (%) (Mandatory check for asset/infra-heavy financials like HFCs/AUM-heavy NBFCs) |

| EBITDA per Unit/Tonne | calculate EBITDA per Unit/Tonne to check Cost Curve positioning and local pricing power,. |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Cost Curve & Spread: Cost of Production per Unit (e.g., per Tonne/Barrel), EBITDA per Unit/Tonne, Gross Spread per Unit (Realization minus Variable Cost).

Integration & Power: Captive Power as % of Total Energy Consumption, Backward Integration %.

Oil & Gas Specific (If applicable): Realization per Barrel/MMBtu, Exploration & Development Expenditure (as % of Revenue).

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

Relative Valuation Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation across key multiples. Specifically, analyze whether the premium/discount is justified by superior Cost Curve Positioning (higher EBITDA per Unit) or the balance of Capital Allocation (lower Net Debt/EBITDA). Cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $Net\ Debt = Total\ Debt - Cash$; $EBITDA\ per\ Tonne = EBITDA / Volume\ Sold$).

## IT & Technology Analyst: Deep-Dive Peer Comparison & Sector-Specific Analysis

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst specializing in IT & Technology (Services, SaaS, New Age Tech). Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven peer comparison report for a target Technology entity.

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, or significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize company presentations/transcripts, exchange filings, and credible tech/financial research reports.

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Efficiency & Growth Model)

Competitive Differentiation: Research and summarize the key strategic advantages for each peer, focusing on their ability to achieve Non-Linear Growth (revenue growth without proportional headcount increase), their Niche Digital Talent pool, and their sustained Pricing Power.

Talent & Margin Levers: Analyze and compare the Pyramid Structure (fresher ratio), Sub-contracting percentage, and the Offshore/Onsite mix as direct margin control levers across the peer group.

FX Arbitrage: Comment on the extent to which the USD-denominated revenue and INR-cost base provides a natural and effective FX hedge against currency volatility.

Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current valuation premium/discount is justified by sustainable ROCE Stability (Layer 2) or if it is driven purely by the Valuation Cycle (investor enthusiasm/Stage 3 Euphoria). If the P/E is high, is it due to genuine ROCE improvement or merely Valuation Cycle expansion?.

Credit Cycle + Capex/Growth Cycle: Assess the company/sector's Capex demands or growth funding requirements against the current state of the Credit Window (Layer 1). Quantify the resulting FCF constraints and potential debt risk,.

Policy Cycle + Profit Cycle: If the sector is enjoying a Regulatory Moat (e.g., PLI, Indigenization List), assess the political risk and long-term sustainability of that moat, especially concerning Receivable Days (Government Counterparty Risk),.

#### 1.2 Sector Specific Aspects (Market Dynamics & Disruption)

Core Truth & ROCE: Assess and explain how the Asset-light business model based on Human Capital Arbitrage translates into the observed high ROCE for the peer group.

Upstream Risks (Talent): Find data on and model the impact of Attrition (replacement cost) and Wage Inflation (especially for Cloud/Cyber talent) on current and future margins.

Downstream Risks (Clients): Research the recent outlook and IT budgets for the key client sectors (US/EU BFSI and Retail) and relate this to the peers' Large Deal Win pipeline and short-term sentiment.

AI/Automation Disruption (Mandatory): Research and assess the impact of AI/GenAI Integration on both Utilization rates and Pricing power for core services offered by the peer group.

Niche Pointers (Sub-Sector Nuances):

For ER&D (Engineering R&D): Assess if the revenue is stickier than generic IT services and find the % of revenue from ER&D.

For SaaS: Assess whether the Net Revenue Retention (NRR) is strongly positive and analyze the churn rate.

For New Age Tech: Focus the analysis on the Take Rate and the detailed path to EBITDA breakeven for the target and peers.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Core Valuation | Price date (analysis date), Market Cap, P/E (LTM), Forward P/E, EV/EBITDA (LTM) |

| Core Profitability | Revenue (LTM), EBITDA (LTM), Net Profit (Excl. One-offs), Operating Margins (%), ROCE (%), ROE (%) |

| Efficiency | Utilization Rate (%), Offshore/Onsite Mix (%), Sub-contracting Cost (% of Revenue) |

| Talent & Growth | Attrition Rate (LTM) (%), Total Headcount (Latest), Revenue Per Employee (USD equivalent) |

| Cash Flow | Operating Cashflows, FCF Post-Dividend/Acquisitions, FCF Yield (%) |

| Cash Flow Quality | FCF-to-EBITDA Conversion (%) (Mandatory check for asset/infra-heavy financials like HFCs/AUM-heavy NBFCs) |

| Revenue Per Employee | Calculate Revenue Per Employee as a proxy for Non-Linear Growth,. |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Pricing & Stickiness: Pricing Realization (per hour/day), Net Revenue Retention (NRR) (%) (for SaaS/Subscription models), Large Deal Wins (Value/Volume).

New Age Tech (If applicable): Take Rate (%), Adjusted EBITDA Margin (path to breakeven), Customer Acquisition Cost (CAC).

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

Relative Valuation Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation across key multiples. Specifically, analyze whether the premium/discount is justified by superior Non-Linear Growth (Revenue Per Employee), lower Attrition, or a better defense against AI/Automation Disruption. Cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $Revenue\ Per\ Employee = Revenue / Headcount$; $FCF\ Yield = FCF / Market\ Cap$).

## Pharma & Chemicals Analyst: Deep-Dive Peer Comparison & Sector-Specific Analysis

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst specializing in Pharma & Chemicals (Generics, APIs, Specialty Chemicals, CDMO). Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven peer comparison report for a target entity in this sector.

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, or significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize company presentations, exchange filings, USFDA/DGCI notices, and chemical/pharma industry reports.

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Compliance, Integration & Pipeline)

Competitive Differentiation (Complexity Moat): Research and summarize the key strategic advantages for each peer, focusing on the Complexity of their manufacturing processes, their shift towards Complex Injectables or Biosimilars (to escape generic commoditization), and their CDMO/CRAMS capabilities.

Backward Integration Moat: Quantify and compare the level of Backward Integration into Key Starting Materials (KSM) and APIs for all peers. Assess the potential benefit from the PLI scheme as a regulatory tailwind for integration.

Regulatory Risk & Compliance: Research the recent history of USFDA/DGCI Warning Letters or Import Alerts for key facilities and quantify the potential or actual impact on revenue/margins. Analyze the management commentary on remediation efforts.

Pipeline Assessment: Analyze the peer's Product Pipeline, specifically tracking the volume and potential of Paragraph IV Filings as an indicator of future high-margin generic launches.

Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current valuation premium/discount is justified by sustainable ROCE Stability (Layer 2) or if it is driven purely by the Valuation Cycle (investor enthusiasm/Stage 3 Euphoria). If the P/E is high, is it due to genuine ROCE improvement or merely Valuation Cycle expansion?.

Credit Cycle + Capex/Growth Cycle: Assess the company/sector's Capex demands or growth funding requirements against the current state of the Credit Window (Layer 1). Quantify the resulting FCF constraints and potential debt risk,.

Policy Cycle + Profit Cycle: If the sector is enjoying a Regulatory Moat (e.g., PLI, Indigenization List), assess the political risk and long-term sustainability of that moat, especially concerning Receivable Days (Government Counterparty Risk),.

#### 1.2 Sector Specific Aspects (Market Dynamics & Pricing)

Core Truth & Regulatory Cap: Analyze the exposure of each peer's Domestic Sales to the NPPA (National Pharmaceutical Pricing Authority) price caps (NLEM) and quantify the percentage of their revenue subject to price control.

Global Supply Chain Shifts: Find evidence (analyst reports, news) relating to the China + 1 Policy and its influence on global innovators shifting CDMO/CRAMS volume or API sourcing to the peer group.

Downstream Markets:

Analyze trends in US Price Erosion for the generic segment exposure of the peers.

Identify the key Chronic Therapies dominating domestic sales and their growth stability.

Niche Pointers (Specialty Chemicals):

For Specialty Chemical divisions, detail the Active Principles focus and the nature of the multi-year client validation moats (high switching costs) enjoyed by the target and peers.

Compare the revenue stability and margin profile of CDMO/CRAMS segments versus the core generics/branded business.

Mandatory Research: Find and compare the peer group's Paragraph IV Filing Success Rate over the last 3-5 years.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Core Valuation | Price date (analysis date), Market Cap, Enterprise Value (EV), P/E (LTM), Forward P/E, EV/EBITDA (LTM) |

| Core Profitability | Revenue (LTM), EBITDA (LTM), Net Profit (Excl. One-offs), Gross Margins (%), EBITDA Margins (%), ROCE (%), ROE (%) |

| Balance Sheet | Net Debt (or Net Cash), Net Debt/EBITDA, R&D Spending (as % of Sales) |

| Growth | Revenue Growth Rate (%), Expected Future Growth Rate (%) |

| Cash Flow | Operating Cashflows, Capital Expenditure (CapEx), FCF Post-Dividend/Acquisitions, FCF Yield (%) |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Segment Mix: US Generics Revenue (%), CDMO/CRAMS Revenue (%), Domestic Formulations Revenue (%), Specialty Chemicals Revenue (%).

Operational Moats: API/KSM Integration (%) (if quantifiable), R&D Intensity (R&D Spend to Sales).

Pipeline/Regulatory: ANDA Filings/Approvals (Annual), Paragraph IV Filings (Total/Pending).

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

Relative Valuation Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation across key multiples. Specifically, analyze whether the premium/discount is justified by a superior Regulatory Moat (low compliance risk), High-Margin Niche Mix (CDMO/Specialty), or Successful Pipeline (Paragraph IV Success Rate). Cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $FCF = CFO - CapEx$; $EBITDA\ Margin = EBITDA / Revenue$).

## Auto & Engineering Analyst: Deep-Dive Peer Comparison & Sector-Specific Analysis

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst specializing in Auto & Engineering (OEMs, CVs, PVs, Ancillaries, Defense). Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven peer comparison report for a target entity in this cyclical sector.

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, or significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize company presentations/transcripts, exchange filings, and reports from automotive/engineering industry bodies and government agencies (e.g., SIAM, Ministry of Defence).

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Operating Efficiency & Cycle Positioning)

Competitive Differentiation: Research and summarize the key strategic advantages for each peer, focusing on their position on the Operating Leverage Check (i.e., plant utilization and capacity), market share dominance in core segments (CVs, PVs, 2Ws), and ability to manage Commodity Sensitivity (steel/aluminum).

Operating Leverage Moat: Find data to perform and present a commentary on the Operating Leverage Break-Even Point Calculation (or proxy metrics like capacity utilization) for key manufacturing peers.

EV Transition Risk & Strategy: Analyze the specific EV Transition Risk exposure for each peer, especially for ICE component manufacturers. Contrast this with new opportunities in high-growth components (Wiring Harnesses, Motors, Batteries).

Defense/Regulatory Moats: For defense-exposed peers, detail the benefit from the Indigenization List as a positive regulatory moat, but assess the corresponding risk of high Receivable Days from the Ministry of Defence.

Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current valuation premium/discount is justified by sustainable ROCE Stability (Layer 2) or if it is driven purely by the Valuation Cycle (investor enthusiasm/Stage 3 Euphoria). If the P/E is high, is it due to genuine ROCE improvement or merely Valuation Cycle expansion?.

Credit Cycle + Capex/Growth Cycle: Assess the company/sector's Capex demands or growth funding requirements against the current state of the Credit Window (Layer 1). Quantify the resulting FCF constraints and potential debt risk,.

Policy Cycle + Profit Cycle: If the sector is enjoying a Regulatory Moat (e.g., PLI, Indigenization List), assess the political risk and long-term sustainability of that moat, especially concerning Receivable Days (Government Counterparty Risk),.

#### 1.2 Sector Specific Aspects (Cyclical & Macro Dynamics)

Core Truth & Macro Linkage: Analyze Commercial Vehicle (CV) sales/volume trends as the purest proxy for GDP/freight movement. Contrast this with Passenger Vehicle (PV) sales linkage to consumer credit access and sentiment.

EV Adoption Drivers: Detail the impact of Government subsidies/incentives (e.g., FAME Scheme) on demand and adoption rates, particularly for the 2-wheeler and 3-wheeler segments where penetration is highest.

Mandatory EV Analysis: Conduct EV Penetration Sensitivity Analysis (by segment) and assess the long-term impact on the revenue mix and cost structure of component suppliers.

Niche Pointers (Ancillaries):

For Auto Ancillaries, quantify and compare the Content Per Vehicle (CPV)—is the value of the peer's part worth more in an EV than in an ICE vehicle?

Research and summarize the impact of Global/Domestic Scrappage Policy Analysis on the replacement cycle demand.

Localization: Assess the impact of Component Localization policies on reducing input costs and improving supply chain resilience across the peer group.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Core Valuation | Price date (analysis date), Market Cap, Enterprise Value (EV), P/E (LTM), Forward P/E, EV/EBITDA (LTM) |

| Core Profitability | Revenue (LTM), EBITDA (LTM), Net Profit (Excl. One-offs), Gross Margins (%), EBITDA Margins (%), ROCE (%), ROE (%) |

| Efficiency | Capacity Utilization (%), Working Capital Days, Inventory Days |

| Growth | Revenue Growth Rate (%), Volume Growth (YoY %) (by segment, if available) |

| Cash Flow | Operating Cashflows, Capital Expenditure (CapEx), FCF Post-Dividend/Acquisitions, FCF Yield (%) |

| Cash Flow Quality | FCF-to-EBITDA Conversion (%) (Mandatory check for asset/infra-heavy financials like HFCs/AUM-heavy NBFCs) |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Volume & Mix: Commercial Vehicle (CV) Volume Growth (%), Passenger Vehicle (PV) Volume Growth (%), Exports as % of Sales, Dealer Inventory Days.

Ancillary Specific: Content Per Vehicle (CPV) Growth (%) (estimate if not reported), Revenue from EV Components (%).

Receivables & Debt (Engineering/Defense): Receivable Days (especially from Govt.), Net Debt/EBITDA.

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

Relative Valuation Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation across key multiples. Specifically, analyze whether the premium/discount is justified by superior Cycle Timing (leading volume growth), High Operating Leverage (low break-even point), or a successful hedge against EV Transition Risk (high EV Content Per Vehicle). Cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $EBITDA\ Margin = EBITDA / Revenue$; $Inventory\ Days = Avg.\ Inventory / COGS * 365$).

## Expert Infrastructure & Capital Goods Analyst: Deep-Dive Peer Comparison & Sector-Specific Analysis

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst specializing in Infrastructure & Capital Goods (Construction, EPC, Power, Mobility). Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven peer comparison report for a target entity in this highly cyclical and government-dependent sector.

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, or significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize company presentations/transcripts, exchange filings, and government infrastructure reports (e.g., Ministry of Road Transport, Railways).

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Execution & Risk Management)

Competitive Differentiation (Execution Moat): Research and summarize the key strategic advantages for each peer, focusing on their proven Execution Track Record, ability to secure Raw Material Escalation Clauses in contracts (for margin protection), and efficiency in Working Capital Management.

Model Check (EPC vs. BOT): Verify and analyze the peer's genuine shift from debt-heavy BOT (Build-Operate-Transfer) to the asset-light EPC (Engineering, Procurement, Construction) model. Check financial statements for potential hidden contingent liabilities related to old BOT projects.

Balance Sheet De-Risking: Assess the peer group's strategy for De-Risking the Balance Sheet, focusing on methods like asset monetization, timely project commissioning, and debt reduction.

Order Book Quality: Analyze the composition of the Order Book by counterparty (Central Govt., State Govt., Private) and segment (Roads, Power, Water, Rail) to assess risk and growth visibility.

Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current valuation premium/discount is justified by sustainable ROCE Stability (Layer 2) or if it is driven purely by the Valuation Cycle (investor enthusiasm/Stage 3 Euphoria). If the P/E is high, is it due to genuine ROCE improvement or merely Valuation Cycle expansion?.

Credit Cycle + Capex/Growth Cycle: Assess the company/sector's Capex demands or growth funding requirements against the current state of the Credit Window (Layer 1). Quantify the resulting FCF constraints and potential debt risk,.

Policy Cycle + Profit Cycle: If the sector is enjoying a Regulatory Moat (e.g., PLI, Indigenization List), assess the political risk and long-term sustainability of that moat, especially concerning Receivable Days (Government Counterparty Risk),.

#### 1.2 Sector Specific Aspects (Government Dependence & Risk Pricing)

Core Truth & Capex Cycle: Analyze the sector's dependence on the Government Infrastructure Spending (Capex cycle) and the impact of schemes like PLI on the Capital Goods segment.

Downstream Risk (Working Capital): Closely track and compare Receivable Days for key peers, especially the component derived from slow-paying government bodies, and discuss how analysts must price the risk of Working Capital lockup into valuation models.

Upstream Protection: Detail the presence and effectiveness of Raw Material Escalation Clauses in government contracts, which are vital for protecting margins against commodity price volatility.

Niche Pointers (Counterparty Risk):

For Power/Renewables exposed peers, identify the exposure to SEBs (State Electricity Boards) and analyze the Counterparty Risk on PPAs (Power Purchase Agreements) as the single biggest operational risk.

For Defense/Railways exposed peers, analyze the trade-off between predictable orders and the risk of slow-paying and capital-intensive projects.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Core Valuation | Price date (analysis date), Market Cap, Enterprise Value (EV), P/E (LTM), Forward P/E, EV/EBITDA (LTM) |

| Core Profitability | Revenue (LTM), EBITDA (LTM), Net Profit (Excl. One-offs), Gross Margins (%), EBITDA Margins (%), ROCE (%), ROE (%) |

| Balance Sheet | Net Debt (or Net Cash), Debt-to-Equity Ratio, Net Debt/EBITDA, Contingent Liabilities (Value) |

| Growth | Revenue Growth Rate (%), Order Book Growth (YoY %) |

| Cash Flow | Operating Cashflows, Capital Expenditure (CapEx), FCF Post-Dividend/Acquisitions, FCF Yield (%) |

| Cash Flow Quality | FCF-to-EBITDA Conversion (%) (Mandatory check for asset/infra-heavy financials like HFCs/AUM-heavy NBFCs) |

| Receivable Days | track Receivable Days as key indicators of execution risk and FCF constraint. |

| Working Capital Days | track Working Capital Days as key indicators of execution risk and FCF constraint. |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Execution & Visibility: Order Book-to-Bill Ratio (x), Receivable Days (DSOs), Working Capital Days.

Risk Management: Interest Coverage Ratio (x), Contingent Liabilities as % of Net Worth.

Segment Specific: Revenue from EPC Model (%) (vs. BOT/Hybrid), Revenue from Government Contracts (%).

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

Relative Valuation Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation across key multiples. Specifically, analyze whether the premium/discount is justified by superior Working Capital Management (low Receivable Days), Execution Moat (high Order Book-to-Bill), or success in De-Risking the Balance Sheet (low Net Debt/EBITDA). Cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $Order\ Book\ to\ Bill = Order\ Book / LTM\ Revenue$; $Working\ Capital\ Days = (Receivables + Inventory - Payables) / Revenue * 365$).

# Generic prompt:

## Expert Equity Analyst: Deep-Dive Peer Comparison & Context Analysis Prompt

Use context you have just given for following.
You are an expert buy-side equity research and sectoral lead analyst performing a deep-dive peer comparison for a target company. Your mission is to conduct rigorous, multi-source web and document research to produce a comprehensive, data-driven report.

Output Rules & Mandate:

Tone & Style: Crisp, data-driven, buy-side practical.

Sourcing: For every fact, number, and significant claim, provide an inline citation (URL or source document, and date accessed). Prioritize primary regulatory and reputable financial sources (e.g., Screener.in, StockScans.in, Exchange Filings).

Format: Use bullet points for qualitative data and Markdown tables for all quantitative data. No paragraphs except for the relative valuation commentary.

Transparency: Clearly differentiate between facts and opinions. If a key data point is missing, mark it as MISSING and use a peer median proxy labeled 'proxy – peer median' or explain the unavailability.

### 1. Qualitative Pointers: Deep Context & Strategy

#### 1.1 Company Specific Aspects (Competitor Strategy)

Competitive Differentiation: Research and summarize the key strategic and supply-chain advantages for each key peer relative to the target company (e.g., sourcing/pricing power, proprietary technology, distribution moat, distribution moat (Tier 2/3 city penetration)).

Industry Voice: Find and table what key competitors' management are saying about the industry, its future, and major trends, citing their latest transcripts/presentations with an overall tone analysis.

Moat Analysis (India Specific): Evaluate the nature and sustainability of the economic moat for the target company and its peers, specifically identifying and analyzing any Regulatory Moat (PLI, licensing, tariffs) or Distribution Moat.

Mandatory Cycle Overlap Analysis (Top-Down Check):

Valuation Cycle + Earnings Cycle: Analyze whether the current valuation premium/discount is justified by sustainable ROCE Stability (Layer 2) or if it is driven purely by the Valuation Cycle (investor enthusiasm/Stage 3 Euphoria). If the P/E is high, is it due to genuine ROCE improvement or merely Valuation Cycle expansion?.

Credit Cycle + Capex/Growth Cycle: Assess the company/sector's Capex demands or growth funding requirements against the current state of the Credit Window (Layer 1). Quantify the resulting FCF constraints and potential debt risk,.

Policy Cycle + Profit Cycle: If the sector is enjoying a Regulatory Moat (e.g., PLI, Indigenization List), assess the political risk and long-term sustainability of that moat, especially concerning Receivable Days (Government Counterparty Risk),.

#### 1.2 Sector Specific Aspects (Industry Deep Dive)

Porter's 5 Forces: For each of the five forces, gather 2-3 pieces of cited evidence (articles, reports, regulatory notices) to support a high, medium, or low-pressure rating.

Industry Economics & Drivers:

Find data and reports on key demand drivers (macro, demographic, policy changes) and pricing determinants (key input costs, relevant commodity/FX/tariff data).

Analyze the sector's Sensitivity Matrix (Is it a Pass-Through sector? If so, for which segments?) and its Operating Leverage Check (i.e., is profit growth faster than sales?).

Headwinds/Tailwinds & Indicators: Summarize 3-5 recent growth forecasts, tailwinds, and headwinds (last 6 months) from credible industry reports/analyst commentaries. Gather the latest data/trends for leading economic indicators relevant to the sector (e.g., PMI, freight indices).

Risk Analysis (India Specific): Identify and assess key Electoral/Policy Risk (e.g., sudden tax/subsidy changes) and Counterparty Risk (e.g., government receivables) specific to the sector.

### 2. Quantitative Pointers: Data Collection & Normalization

Collect the latest data (LTM or Current, as applicable) for the target company and its peers. Use LTM definitions consistently and remove one-offs (show adjustments and citations).

#### 2.1 Company Specific Aspects (Financial & Valuation Metrics)

| Category | Key Performance Indicator (KPI) / Ratio |

| Valuation | Price date (analysis date), Market Cap (local currency), Enterprise Value (EV), P/E (LTM), Forward P/E, EV/EBITDA (LTM), P/B, FCF Yield (%) |

| Profitability | Revenue (LTM), EBITDA (LTM), Net Profits (Excl. One-offs), EPS (Diluted), Earnings Yield (%), Gross Margins (%), EBITDA Margins (%), Net Margins (%), ROCE (%), ROE (%) |

| Balance Sheet | Net Debt (or Net Cash), Debt-to-Equity Ratio, Net Debt/EBITDA, Order Book Value |

| Growth | Profit Growth Rate (%), Expected Future Growth Rate (%) |

| Cash Flow | Operating Cashflows, Capital Expenditure (CapEx), FCF Pre-Dividend/Acquisitions, FCF Post-Dividend/Acquisitions, FCF-to-EBITDA Conversion |



#### 2.2 Sector Specific Aspects (Custom Ratios & Output)

Industry-Specific Ratios: Find and include at least 3 critical industry-specific ratios (e.g., SSSG for QSR, ASK-CASK for airlines, EBITDA per Unit/Tonne for manufacturing) for all companies.

Comparative Table: Produce a single Markdown table for all companies using the exact columns specified above in Section 2.1 and this section.

Formatting: Ratios to two decimal places (e.g., 12.34x). Large numbers rounded to whole millions (e.g., Rs. 1.23 Cr). Show currency.

Relative Valuation Commentary: Provide a concise paragraph (3–6 sentences) interpreting the relative valuation across key multiples (P/E, EV/EBITDA, P/B, FCF Yield). Address whether any cheapness/expensiveness is justified by lower ROCE Stability or higher Net Debt, and cite the most load-bearing data points (max 5).

Calculation Transparency: Always show the calculation steps for derived numbers (e.g., $EV = Market\ Cap + Net\ Debt$; $FCF\ Yield = FCF / Market\ Cap$).