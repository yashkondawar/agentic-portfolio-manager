# 📈 NSE Stock Research & Analysis System

A sophisticated multi-agent AI system for analyzing Indian NSE-listed stocks using real-time data, technical indicators, news sentiment, and advanced AI reasoning.

## 🧭 Unified Strategy Architecture

Every "system" in this project pursues the same goal — turning market data into
actionable stock research/trading decisions — via a different method. They are all
exposed as interchangeable **strategies** behind one entry point, so any UI can list
and run them uniformly.

| Strategy id | System | Category |
|-------------|--------|----------|
| `sequential_agents` | Copilot SDK agents run in four research stages | research |
| `parallel_agents`   | Concurrent multi-analyst fan-out + risk/portfolio managers | research |
| `swing_trading`     | Daily swing-trading copilot | swing |
| `breakout_52w_daily`| Daily Nifty 500 breakout scanner + paper portfolio | swing |
| `portfolio_analysis`| Holistic portfolio review + rebalancing | portfolio |
| `watchlist_curation`| Universe screening + LLM curation | watchlist |
| `qtr_results`       | Quarterly-results momentum + tracked exits | swing |
| `swing_backtest`    | Point-in-time validation of the swing playbook | backtest |
| `breakout_52w_backtest` | Deterministic 52-week-high breakout system | backtest |

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
python run.py breakout_52w_backtest --param symbols="RELIANCE,TCS,INFY"
python run.py breakout_52w_daily
```

`breakout_52w_daily` scans the selected NSE index (Nifty 500 by default), so
`symbols` is only a focused-universe override. It keeps its paper portfolio at
`.trader_workbench/breakout_52w_portfolio.json`: close-of-day signals are queued,
validated at the next session's open, and then managed on later daily runs.
Every result also includes the complete `portfolio_state` JSON for backup,
inspection, or use as an explicit state override.

The cross-regime defaults require a close at least 0.5% above the prior high,
2.0x relative volume, three-month return at least 15 percentage points above
the Nifty, and a 50-day SMA that has risen at least 2% over 20 sessions. Each
trade risks 1% of equity to a 1.5 ATR initial stop. Backtests model the stop
before the target when both prices occur in one daily candle. For live use,
place both exit orders after entry; the daily workflow reports and persists
their exact levels but does not submit broker orders.

An institutional hardening pass (see
`docs/52-week-breakout-strategy-finance-review.md`, section 18) adds a realistic
Indian delivery-cost model (~0.33% round-trip), a diversification framework (up
to 12 positions with per-sector and pairwise-correlation caps and a 15%
per-name notional cap), and partial-profit booking. Continuous regime
scaling is implemented but **disabled by default** because the simple binary
market gate produced better drawdowns and Sharpe across every test window.

A subsequent trade-management pass (section 19) widened the initial stop to
1.5 ATR, widened the Chandelier trail from 2 ATR to 4 ATR, and cut the
partial-profit booking from half the position at 2.5 ATR to **20% at 3.5 ATR**,
so winners keep most of their size instead of being halved early. Entry filters
were left untouched: an exit-time study of 727 trades found day-one losers and
multi-week winners statistically indistinguishable at entry, so the edge is in
trade management, not in more selective entries.

Under these realistic-cost defaults, the five-year simulation
(2021-07-24 through 2026-07-24, ₹500,000 initial cash) produces roughly
24.3% CAGR, -14.5% maximum drawdown, 1.36 Sharpe, a 1.96 profit factor, and a
~47% win rate, ending near ₹14.8 lakh. The same change improves 2012-2014,
2019, 2022-2024 and 2025-2026, and is roughly 3 percentage points worse across
the choppy 2015-2018 stretch, where the wider trail gives back more in
sideways markets.
The strategy is signal-scarce (≈28% average exposure), so its edge comes from
selectivity — relaxing filters to deploy more capital was tested and degraded
every window. All figures use today's Nifty 500 membership and therefore retain
survivorship bias; they are validation results, not a return guarantee.

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
| Swing Desk | Manage open swing positions and evaluate new entries |
| Portfolio Review | Concentration, risk, conviction, and rebalancing review |
| Backtest Lab | Historical return/risk metrics, equity curve, and trade log |
| Broker & Holdings | Read-only Zerodha holdings, positions, margins, and orders |
| Settings & Catalog | Integration setup and every strategy parameter |

Forms are generated from each strategy's `ParamSpec`, so new registered
strategies and parameters become discoverable without adding another CLI-only
workflow. Reports and structured data can be downloaded, and sanitized run
history is stored locally under `.trader_workbench/`.

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
- GitHub Copilot subscription with Copilot CLI installed and signed in
- Bright Data account only when the optional paid data source is enabled

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/rooneyrulz/agentic-stock-research-system
   cd nse-stock-research-system
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Set up environment variables**
   ```bash
   cp example.env .env
   # Edit optional data-source and broker settings
   ```

4. **Verify GitHub Copilot CLI**
   ```bash
   copilot --version
   ```
   Run `copilot` once and complete sign-in if prompted. The application uses
   this existing login through the GitHub Copilot SDK.

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

### Model Setup

GitHub Copilot is the only model provider. No separate model API key is
required. The default model is `claude-opus-4.7`; override it in `.env`:

```bash
COPILOT_MODEL=claude-opus-4.7
COPILOT_TIMEOUT=300
```

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

1. **Copilot Authentication or Model Errors**
   - Run `copilot` and complete sign-in with a Copilot-enabled account
   - Verify `COPILOT_MODEL` is available to your Copilot subscription
   - On restricted Windows machines, set `COPILOT_CLI_PATH` to the signed
     `copilot.exe` installation

2. **MCP Installation Issues**
   ```bash
   # Reinstall MCP globally
   npm uninstall -g @brightdata/mcp
   npm install -g @brightdata/mcp
   ```

3. **Streamlit Issues**
   ```bash
   # Clear Streamlit cache
   streamlit cache clear
   ```

4. **Import Errors**
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
