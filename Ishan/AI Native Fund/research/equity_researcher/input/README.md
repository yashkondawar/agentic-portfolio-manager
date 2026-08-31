# input/ — drop company documents here

One folder per company: `input/<TICKER>/`. The agent classifies by content, but these name patterns speed up intake:

| Pattern | Document | Ideal count |
|---|---|---|
| `AR_FY2025.pdf` | Annual report | last 5 |
| `Q_FY2026Q1.pdf` | Quarterly/half-yearly results | last 6 |
| `TR_2026-05-12.pdf` | Earnings-call transcript | last 5 |
| `PPT_FY2026Q1.pdf` | Investor presentation | last 5 |
| `DR1_*.md/pdf/docx` | Prior deep research — company/management | if you have it |
| `DR2_*.md/pdf/docx` | Prior deep research — sector/peers | if you have it |
| `PEER_<name>_*.pdf` | Peer ARs/transcripts/decks | optional |
| `KPI_*.xlsx/csv/pdf` | Industry KPI data you already track | optional |
| anything else | Other disclosures (credit rating reports, exchange filings…) | optional |

Notes:
- **Run with whatever exists.** Shortfalls become disclosed gaps in the report, not blockers.
- Supplied deep research is **consumed, not redone** — the agent validates freshness and fills gaps only.
- Give the yfinance symbol when you start the run (e.g., `TICKER.NS`) so market data resolves deterministically.
