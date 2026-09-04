# 📈 NSE Stock Research & Analysis System

A sophisticated multi-agent AI system for analyzing Indian NSE-listed stocks using real-time data, technical indicators, news sentiment, and advanced AI reasoning.

## 🧭 Unified Strategy Architecture

Every "system" in this project pursues the same goal — turning market data into
actionable stock research/trading decisions — via a different method. They are all
exposed as interchangeable **strategies** behind one entry point, so any UI can list
and run them uniformly.

| Strategy id | System | Category |
|-------------|--------|----------|
| `sequential_agents` | Four research stages run in sequence, on any provider | research |
| `parallel_agents`   | Concurrent multi-analyst fan-out + risk/portfolio managers | research |
| `swing_trading`     | Daily swing-trading copilot | swing |
| `portfolio_analysis`| Holistic portfolio review + rebalancing | portfolio |
| `watchlist_curation`| Universe screening + LLM curation | watchlist |
| `qtr_results`       | Quarterly-results momentum + tracked exits | swing |
| `swing_backtest`    | Point-in-time validation of the swing playbook | backtest |

**Layout**

```
core/            # shared backbone
  strategy.py    # BaseStrategy contract, ParamSpec, StrategyResult
  registry.py    # register / list / get / run strategies
  llm.py         # GitHub Copilot SDK client, tools, and model adapter
  config.py      # env-backed defaults
strategies/      # one self-registering module per system (wraps existing code)
run.py           # single CLI + programmatic entry point
```

**Use it**

```bash
python run.py --list                 # discover all strategies + their params
python run.py --list --json          # machine-readable specs (for a UI)
python run.py parallel_agents --param symbols="RELIANCE,TCS" --param use_llm=true
```

**Integrate a UI** — everything a front end needs comes from the registry:

```python
from core import registry

options = registry.list_specs()                       # render each as a UI option/form
result  = registry.run_strategy(selected_id, params)  # uniform StrategyResult
print(result.report)                                  # markdown/text to display
```

The concrete implementation modules (`agents/`, `scraper/`, `zerodha/`,
`backtesting/`, `main.py`, `swing_trading_copilot.py`, …) remain separate and are
wrapped — not replaced — by the strategy layer.

## Trader Workbench

Run the complete local interface with:

```bash
uv run streamlit run app.py
```

The workbench is organized around a trader's workflow rather than individual
scripts:

| Page | Purpose |
|------|---------|
| Dashboard | Shared idea basket, readiness, and recent persisted runs |
| Discover Ideas | Watchlist screening and quarterly-results catalysts |
| Stock Research | Parallel specialist agents or sequential supervisor |
| Market Temperature | Long-horizon read on whether an index is unusually cheap or expensive, used to pace new-money deployment |
| Swing Desk | Manage open swing positions and evaluate new entries |
| Portfolio Review | Concentration, risk, conviction, and rebalancing review |
| Backtest Lab | Historical return/risk metrics, equity curve, and trade log |
| Broker & Holdings | Read-only Zerodha holdings, positions, margins, and orders |
| Automation & Schedules | Daily unattended runs, their parameters, and scheduler health |
| Settings & Catalog | Integration setup and every strategy parameter |

Forms are generated from each strategy's `ParamSpec`, so new registered
strategies and parameters become discoverable without adding another CLI-only
workflow. Reports and structured data can be downloaded, and sanitized run
history is stored in the local SQLite database described below.

### Automation & Schedules

Both daily strategies are *post-close* jobs whose output is meant to be read
before the **next** open, so they run unattended overnight rather than by hand
at 09:15. Install once and the scheduler starts with every logon, restarts
itself if it dies, and keeps running whether or not the app is open:

```bash
uv run python -m core.scheduler install-task   # set it up (once)
uv run python -m core.scheduler list           # inspect the configured jobs
uv run python -m core.scheduler once           # fire whatever is due, then exit
```

Defaults, seeded on first use and editable on the **Automation & Schedules**
page: `gfs_live` at 17:30 IST Mon-Fri, `qtr_results` at 19:30 IST daily, plus an
optional 08:15 pre-open pass that ships disabled.

Every scheduled run is written to the run history, so opening the app in the
morning shows last night's report without re-running anything. A run button on
every page still forces a fresh run at any time.

Full details — timing rationale, catch-up behaviour, crash recovery, log
locations and troubleshooting — are in [`core/SCHEDULER.md`](core/SCHEDULER.md).

### Backtest dossier

The `qtr_results` strategy exports a nine-sheet Excel workbook matching the
layout of the reference `dossier_*.xlsx` files — summary metrics on three cost
bases against NIFTY 50, equity curve, per-position and per-fill ledgers, yearly
returns, and a financial-year capital-gains ledger with carry-forward:

```bash
uv run python -m backtesting.qtr_results.build_dossier
```

Output lands in `backtesting/qtr_results/results/qtr_results_dossier.xlsx`. See
[`backtesting/qtr_results/DOSSIER.md`](backtesting/qtr_results/DOSSIER.md) for
the flags, the cost/tax model, and the limits worth knowing before quoting a
number.

### Local storage

All durable application data uses one SQLite database outside the repository:
runs, reports and backtest artifacts, scraper/backtest caches, watchlists, and
quarterly-strategy state. On Windows the default is
`%LOCALAPPDATA%\AgenticPortfolioManager\portfolio.sqlite3`. Set
`PORTFOLIO_DB_PATH` in `.env` to use another local path. SQLite runs in WAL mode
and requires no service, container, account, or network connection.

```bash
python -m core.storage path
python -m core.storage summary
python -m core.storage list-artifacts --limit 20
python -m core.storage logs --level ERROR --limit 50
python -m core.storage export <group-id> C:\exports\backtest
python -m core.storage migrate --repo-root .
python -m core.storage migrate --repo-root . --replace-state
```

The migration command imports legacy `.trader_workbench/`, `qtr_results/state/`,
backtest caches/results, and known generated reports without deleting them. It is
safe to rerun. Use `--replace-state` when the legacy folder contains the current
authoritative mutable state; run and artifact history is still only appended.
Inspect or edit the database directly with `sqlite3` or a desktop
tool such as DB Browser for SQLite. Explicit CLI output paths remain available
as exports; they are no longer the primary store.

**Trading safety:** the UI is decision-support only. Zerodha integration can
authenticate and read account data, and research can show proposed orders, but
the workbench has no order-placement control and only uses the read-only broker
facade. Daily Zerodha authentication is launched from **Broker & Holdings**:
click **Connect Zerodha in browser**, sign in on Kite, and the local callback
completes the session without copying a request token into the UI.

## 🌟 Features

### 🤖 Multi-Agent Architecture
- **Stock Finder Agent**: Identifies promising NSE stocks based on liquidity, market cap, and momentum
- **Market Data Agent**: Gathers real-time pricing, volume, and technical indicators  
- **News Analyst Agent**: Analyzes recent news sentiment and market impact
- **Recommendation Agent**: Provides actionable BUY/SELL/HOLD recommendations with target prices

### 📊 Advanced Analytics
- Real-time NSE stock data integration
- Technical indicators (RSI, Moving Averages, MACD)
- Volume and volatility analysis
- News sentiment classification
- Risk-reward assessment

### 🎯 Smart Recommendations
- Specific entry/exit price points
- Stop-loss levels and risk management
- Confidence scoring for each recommendation
- Time horizon-based analysis (short-term to medium-term)

### 🎨 Unified UI
- Task-oriented navigation across every strategy
- Forms generated from registered strategy contracts
- Structured decisions, picks, portfolio tables, and backtest charts
- Shared symbol basket, local run history, and report/data downloads
- Read-only Zerodha portfolio integration

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- **One** model provider — either a GitHub Copilot subscription, or any LLM API
  key (Gemini / OpenAI / Anthropic), or a local Ollama install. See
  [Choosing a model provider](#choosing-a-model-provider).
- Bright Data account only when the optional paid data source is enabled

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/rooneyrulz/agentic-stock-research-system
   cd nse-stock-research-system
   ```

2. **Install dependencies** — pick the extra matching your provider
   ```bash
   uv sync --extra copilot     # GitHub Copilot CLI (default)
   uv sync --extra gemini      # Gemini API key
   uv sync --extra openai      # OpenAI API key
   uv sync --extra anthropic   # Anthropic API key
   ```

3. **Set up environment variables**
   ```bash
   cp example.env .env
   # Edit the AGENT BACKEND block at the top, plus data-source/broker settings
   ```

4. **Verify your provider**
   ```bash
   copilot --version           # only for AI_AGENT_BACKEND=copilot_cli
   ```
   For `copilot_cli`, run `copilot` once and complete sign-in if prompted.
   For `native`, nothing to verify — just make sure the API key is in `.env`.

5. **Install Bright Data MCP (optional)**
   ```bash
   npm install -g @brightdata/mcp
   ```

### Running the Application

1. **Start the Streamlit app**
   ```bash
   uv run streamlit run app.py
   ```

2. **Access the application**
   - Open your browser to `http://localhost:8501`
   - Review integration readiness on **Settings & Catalog**
   - Pick a workflow from the navigation
   - Configure the generated form and run the strategy

## 🔧 Configuration

### Choosing a model provider

The research agents run on a pluggable harness selected by `AI_AGENT_BACKEND`.
Strategy logic, prompts and the ten scraper MCP tools are identical across all
of them — only the harness changes, so **every workflow runs on every backend**.

**You usually don't need to set anything.** On first run the app detects what
your machine can actually do and says so in the logs:

```
No Copilot CLI found, but GOOGLE_API_KEY is set — using the native backend
with Google Gemini (google_genai:gemini-2.5-pro).
```

To change or confirm the choice, open **Settings & Catalog** in the sidebar. It
shows which backends are ready on this machine, lets you pick one and paste an
API key, and **saves to `.env`** so the choice survives a restart. Detection is
never silent — an API key costs money, so the app always tells you which
provider it picked and why.

| You have | `AI_AGENT_BACKEND` | Extra install | Needs a CLI? |
|---|---|---|---|
| GitHub Copilot subscription | `copilot_cli` | `--extra copilot` + `npm i -g @github/copilot` | yes |
| Any LLM API key | `native` | `--extra gemini` / `openai` / `anthropic` | **no** |
| Nothing, but a local GPU/CPU | `native` + Ollama | — | no |
| Claude Pro/Max subscription | *not yet supported* — see [the plan](docs/multi-provider-plan.md) | — | — |

**GitHub Copilot (default).** Uses your existing Copilot login; no model API
key required.

```bash
AI_AGENT_BACKEND=copilot_cli
COPILOT_MODEL=claude-opus-4.7
COPILOT_TIMEOUT=300
```

**Any API key — no CLI, no subscription, no GitHub account.** This is also the
only backend that runs in a container or in CI. `AI_MODEL` is **optional**: with
a single API key set, the matching model is inferred.

```bash
AI_AGENT_BACKEND=native
GOOGLE_API_KEY=...                     # that's enough — model is inferred
# AI_MODEL=google_genai:gemini-2.5-pro # set only to override the inference
# AI_MODEL=openai:gpt-4o               # + OPENAI_API_KEY
# AI_MODEL=anthropic:claude-sonnet-4-5 # + ANTHROPIC_API_KEY
# AI_MODEL=ollama:llama3.1             # fully local, no API key at all
WEB_GROUNDING=false
```

> **Why `WEB_GROUNDING=false` for `native`:** unlike the vendor CLIs there is no
> built-in web-browsing tool, so a run that requires live browsing is rejected
> up front rather than quietly returning a report that looks complete but was
> written without current information. The scraper MCP tools — live prices,
> fundamentals, technicals, news and `scrape_url` — work on **every** backend,
> because they are plain MCP.

#### Bright Data API Token (optional)
1. Sign up at [Bright Data](https://brightdata.com)
2. Navigate to your dashboard
3. Go to "Zones" → "Web Unlocker" 
4. Copy your API token

### Analysis Types

- **Short-term Trading (1-7 days)**: Focus on momentum, technical breakouts, and news catalysts
- **Medium-term Investment (1-4 weeks)**: Emphasis on earnings, sector trends, and technical setups  
- **General Market Analysis**: Broad market overview with top stock picks across sectors

## 📈 Sample Output

```
🎯 TRADING RECOMMENDATIONS
═══════════════════════════════════

RELIANCE - Reliance Industries Limited
─────────────────────────────────
📋 RECOMMENDATION: BUY
🎯 TARGET PRICE: ₹2,650
⏰ TIME HORIZON: 1-3 days
📊 CONFIDENCE: HIGH

📈 ENTRY STRATEGY:
Current Price: ₹2,450
Suggested Entry: ₹2,430 - ₹2,460
Stop Loss: ₹2,380 (3.2% below entry)
Target: ₹2,650 (8.2% upside potential)

💡 RATIONALE:
Technical: Breakout above 50-day MA with strong volume
Fundamental: Positive earnings guidance + new project announcements
Risk-Reward: 1:2.6 ratio
```

## 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Streamlit UI  │────│   Supervisor     │────│  Bright Data    │
│                 │    │     Agent        │    │   MCP Server    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
            ┌───────▼───┐ ┌───▼───┐ ┌───▼────┐
            │Stock Finder│ │Market │ │News    │
            │   Agent    │ │Data   │ │Analyst │
            └────────────┘ │Agent  │ │Agent   │
                          └───────┘ └────────┘
                                │
                        ┌───────▼────────┐
                        │ Recommendation │
                        │     Agent      │
                        └────────────────┘
```

## 🔍 Agent Details

### Stock Finder Agent
- Scans NSE universe for liquid, high-potential stocks
- Filters by market cap, volume, and momentum criteria
- Avoids penny stocks and illiquid securities
- Focuses on large-cap and mid-cap opportunities

### Market Data Agent  
- Real-time price, volume, and market data
- Technical indicators (RSI, MACD, Moving Averages)
- Support/resistance level identification
- Trend analysis and momentum assessment

### News Analyst Agent
- Scrapes recent financial news and announcements
- Sentiment classification (Positive/Negative/Neutral)
- Impact assessment on stock prices
- Catalyst identification for price movements

### Recommendation Agent
- Synthesizes all data into actionable recommendations
- Provides specific entry/exit strategies
- Risk management and position sizing guidance
- Confidence scoring and time horizon analysis

## 🛡️ Risk Management Features

- **Stop-loss recommendations** for every trade suggestion
- **Position sizing guidance** based on volatility
- **Risk-reward ratio analysis** (minimum 1:2 ratio)
- **Confidence scoring** to help with decision making
- **Time horizon specification** for each recommendation

## 📊 Export & Reporting

- **CSV Export**: Download analysis results for further analysis
- **Interactive Charts**: Visualize current vs target prices
- **Performance Tracking**: Monitor recommendation accuracy
- **Historical Analysis**: Compare predictions with actual outcomes

## ⚠️ Important Disclaimers

- This tool is for **educational and research purposes only**
- Always consult with a qualified financial advisor before investing
- Past performance does not guarantee future results
- The Indian stock market involves substantial risk of loss
- Do your own due diligence before making any investment decisions

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Open an issue on GitHub
- Check the documentation
- Review the troubleshooting guide below

### Troubleshooting

**Common Issues:**

1. **Copilot Authentication or Model Errors** (`AI_AGENT_BACKEND=copilot_cli`)
   - Run `copilot` and complete sign-in with a Copilot-enabled account
   - Verify `COPILOT_MODEL` is available to your Copilot subscription
   - On restricted Windows machines, set `COPILOT_CLI_PATH` to the signed
     `copilot.exe` installation
   - No Copilot subscription? Switch to `AI_AGENT_BACKEND=native` — see
     [Choosing a model provider](#choosing-a-model-provider)

2. **`UnsupportedCapability: backend 'native' cannot satisfy web_search`**
   - The `native` backend has no built-in web browsing. Set
     `WEB_GROUNDING=false` in `.env`, or pass `--no-web-grounding` on the CLI.
   - The scraper MCP tools still supply live prices, fundamentals, technicals
     and news, so reports stay grounded in current data.

3. **`ModuleNotFoundError: copilot` / `langchain`**
   - The provider SDKs are optional extras. Install the one matching your
     backend: `uv sync --extra copilot` or `uv sync --extra gemini`.

4. **MCP Installation Issues**
   ```bash
   # Reinstall MCP globally
   npm uninstall -g @brightdata/mcp
   npm install -g @brightdata/mcp
   ```

5. **Streamlit Issues**
   ```bash
   # Clear Streamlit cache
   streamlit cache clear
   ```

6. **Import Errors**
   ```bash
   # Reinstall dependencies
   pip install -r requirements.txt --force-reinstall
   ```
## 🔄 Version History

- **v1.0.0** - Initial release with multi-agent architecture
- **v1.1.0** - Added Streamlit UI and export functionality  
- **v1.2.0** - Enhanced recommendation parsing and visualization

---

**Made with ❤️ for the Indian Stock Market Community**
