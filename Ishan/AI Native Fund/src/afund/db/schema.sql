-- AI-Native Fund — Phase 0 schema
-- SQLite. Dates are stored as TEXT in ISO-8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
-- WAL mode and foreign_keys are enabled by the application (see connection.py),
-- not here, since PRAGMAs are connection-scoped in SQLite.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Instruments & universe
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS instruments (
    id                  INTEGER PRIMARY KEY,
    symbol              TEXT NOT NULL,
    isin                TEXT,
    name                TEXT,
    instrument_type     TEXT CHECK(instrument_type IN ('STOCK','ETF','INDEX_FUND','MUTUAL_FUND','INDEX')),
    sector              TEXT,
    industry            TEXT,
    amfi_scheme_code    TEXT,
    yf_ticker           TEXT,
    active              INTEGER DEFAULT 1,
    first_seen          TEXT,
    last_seen           TEXT,
    UNIQUE(symbol, instrument_type)
);

CREATE TABLE IF NOT EXISTS universe_membership (
    id              INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id),
    index_name      TEXT,
    effective_from  TEXT,
    effective_to    TEXT
);

-- ---------------------------------------------------------------------------
-- Prices & corporate actions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS daily_prices (
    id              INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id),
    date            TEXT NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    adj_close       REAL,
    volume          INTEGER,
    source          TEXT DEFAULT 'yfinance',
    UNIQUE(instrument_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_prices_instrument_date
    ON daily_prices(instrument_id, date);

CREATE TABLE IF NOT EXISTS corporate_actions (
    id              INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id),
    ex_date         TEXT,
    action_type     TEXT,
    details         TEXT,
    record_date     TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS index_data (
    id          INTEGER PRIMARY KEY,
    index_name  TEXT NOT NULL,
    date        TEXT NOT NULL,
    close       REAL,
    pe          REAL,
    pb          REAL,
    div_yield   REAL,
    -- Provenance of pe/pb/div_yield for this row. NULL/'nse_all_indices' for
    -- the daily live snapshot; 'backfill_niftyindices_daily_snapshot' for
    -- historical rows filled in by afund.data.index_valuation.
    -- backfill_index_valuation() (see that module's docstring re: the
    -- Apr-2021 standalone->consolidated PE methodology shift this tag lets
    -- later analysis scope around). Added in schema version
    -- 0002_index_data_source; existing DBs get this column via an
    -- ALTER TABLE in scripts/init_db.py since SQLite has no
    -- "ADD COLUMN IF NOT EXISTS".
    source      TEXT,
    UNIQUE(index_name, date)
);

-- ---------------------------------------------------------------------------
-- Fundamentals & derived ratios
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS financials_quarterly (
    id                  INTEGER PRIMARY KEY,
    instrument_id       INTEGER NOT NULL REFERENCES instruments(id),
    period_end          TEXT,
    statement_type      TEXT,
    revenue             REAL,
    ebitda              REAL,
    operating_profit    REAL,
    net_profit          REAL,
    eps                 REAL,
    raw_json            TEXT,
    source              TEXT,
    ingested_at         TEXT,
    UNIQUE(instrument_id, period_end, statement_type)
);

CREATE TABLE IF NOT EXISTS derived_ratios (
    id              INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id),
    as_of_date      TEXT,
    cadence         TEXT,
    metric_name     TEXT,
    metric_value    REAL,
    sector_kpi      INTEGER DEFAULT 0,
    UNIQUE(instrument_id, as_of_date, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_derived_ratios_instrument_metric
    ON derived_ratios(instrument_id, metric_name);

-- ---------------------------------------------------------------------------
-- Macro
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS macro_series (
    id              INTEGER PRIMARY KEY,
    series_code     TEXT NOT NULL,
    source          TEXT,
    date            TEXT NOT NULL,
    value           REAL,
    unit            TEXT,
    freq            TEXT,
    UNIQUE(series_code, date)
);

-- ---------------------------------------------------------------------------
-- News & newsletters
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS news_items (
    id              INTEGER PRIMARY KEY,
    event_scope     TEXT CHECK(event_scope IN ('MICRO','MACRO','NA')),
    tag             TEXT,
    instrument_id   INTEGER NULL REFERENCES instruments(id),
    impact          TEXT CHECK(impact IN ('POSITIVE','NEGATIVE','NA')),
    description     TEXT,
    event_date      TEXT,
    source          TEXT,
    url             TEXT UNIQUE,
    raw_title       TEXT,
    raw_hash        TEXT,
    fetched_at      TEXT,
    processed       INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_news_items_event_date ON news_items(event_date);
CREATE INDEX IF NOT EXISTS idx_news_items_tag ON news_items(tag);

CREATE TABLE IF NOT EXISTS newsletters (
    id          INTEGER PRIMARY KEY,
    publisher   TEXT CHECK(publisher IN ('DSP_NETRA','AEQUITAS')),
    title       TEXT,
    period      TEXT,
    url         TEXT,
    local_path  TEXT,
    fetched_at  TEXT,
    parsed      INTEGER DEFAULT 0,
    UNIQUE(publisher, period)
);

-- ---------------------------------------------------------------------------
-- Mutual funds
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mf_navs (
    id              INTEGER PRIMARY KEY,
    scheme_code     TEXT NOT NULL,
    date            TEXT NOT NULL,
    nav             REAL,
    source          TEXT DEFAULT 'AMFI',
    UNIQUE(scheme_code, date)
);

-- Future scope — created now for forward-compatibility (look-through holdings).
CREATE TABLE IF NOT EXISTS mf_holdings (
    id              INTEGER PRIMARY KEY,
    scheme_code     TEXT,
    as_of           TEXT,
    holding_isin    TEXT,
    holding_name    TEXT,
    weight          REAL,
    raw_json        TEXT
);

-- ---------------------------------------------------------------------------
-- Portfolio & transactions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY,
    trade_date      TEXT,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id),
    side            TEXT CHECK(side IN ('BUY','SELL')),
    qty             REAL,
    price           REAL,
    fees            REAL DEFAULT 0,
    decision_id     INTEGER NULL,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    instrument_id   INTEGER PRIMARY KEY REFERENCES instruments(id),
    qty             REAL,
    avg_cost        REAL,
    realized_pnl    REAL DEFAULT 0,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS nav_history (
    date            TEXT PRIMARY KEY,
    market_value    REAL,
    cash            REAL,
    total_nav       REAL,
    daily_return    REAL
);

-- ---------------------------------------------------------------------------
-- Decisions, thesis tracking, knowledge, lessons, calibration
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS decision_log (
    id                      INTEGER PRIMARY KEY,
    decision_date           TEXT,
    instrument_id           INTEGER NULL REFERENCES instruments(id),
    sector                  TEXT,
    action                  TEXT CHECK(action IN ('NEW','ADD','REDUCE','EXIT','HOLD','MONITOR_ONLY')),
    strategy_tag            TEXT,
    invalidation_condition  TEXT,
    fund_manager_rec_json   TEXT,
    human_decision          TEXT CHECK(human_decision IN ('APPROVE','REJECT','MODIFY','PENDING')),
    human_notes             TEXT,
    registry_version        TEXT,
    created_at              TEXT
);

CREATE TABLE IF NOT EXISTS thesis_tracker (
    id                      INTEGER PRIMARY KEY,
    instrument_id           INTEGER NOT NULL REFERENCES instruments(id),
    decision_id             INTEGER NOT NULL REFERENCES decision_log(id),
    thesis_text             TEXT,
    invalidation_condition  TEXT,
    status                  TEXT CHECK(status IN ('ACTIVE','WATCH','INVALIDATED','CLOSED')),
    opened_date             TEXT,
    last_checked            TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id          INTEGER PRIMARY KEY,
    tag_type    TEXT CHECK(tag_type IN ('INSTRUMENT','SECTOR','MACRO','SITUATION')),
    tag_value   TEXT,
    content     TEXT,
    source_ref  TEXT,
    created_at  TEXT,
    superseded  INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_knowledge_base_tag ON knowledge_base(tag_type, tag_value);

CREATE TABLE IF NOT EXISTS lessons (
    id                  INTEGER PRIMARY KEY,
    heuristic           TEXT,
    context_tag         TEXT,
    evidence_json       TEXT,
    confidence          REAL,
    approved_by_human   INTEGER DEFAULT 0,
    created_at          TEXT
);

CREATE TABLE IF NOT EXISTS calibration (
    id                  INTEGER PRIMARY KEY,
    decision_id         INTEGER NOT NULL REFERENCES decision_log(id),
    predicted_outcome   TEXT,
    predicted_prob      REAL,
    realized_outcome    TEXT,
    realized_at         TEXT
);

-- ---------------------------------------------------------------------------
-- Phase 7 — cycle engine (registry/strategies/cycle_framework.yaml)
-- ---------------------------------------------------------------------------
-- Field shapes match cycle_framework.yaml's governance.sizing/reconciliation
-- + docs/source-material/cycle-positioning-framework.txt section 6.5's
-- suggested output schema. narrative_* fields are NULL until the
-- narrative_intensity agent ingests (see orchestrator/run.py
-- _ingest_narrative_intensity, which UPDATEs these rows rather than
-- inserting new ones). All numeric thresholds driving phase/action here are
-- DRAFT per cycle_framework.yaml's own status field.

CREATE TABLE IF NOT EXISTS cycle_assessments (
    id                      INTEGER PRIMARY KEY,
    cycle_id                TEXT NOT NULL,      -- catalog cycle_id, e.g. 'valuation_cycle'
    scope                   TEXT NOT NULL,      -- 'NIFTY 50', 'NIFTY 500', or a registry sector slug e.g. 'bfsi'
    as_of_date              TEXT NOT NULL,
    framework_version       TEXT NOT NULL,      -- cycle_framework.yaml content_version (git-SHA-or-hash)
    percentile              REAL,               -- NULL when data_pending
    direction               TEXT,               -- 'rising' | 'falling' | 'flat', NULL when data_pending
    momentum_state          TEXT,               -- 'accelerating' | 'decelerating' | 'stable', NULL when data_pending
    phase_id                TEXT,               -- one of the 8 phase_ids, NULL when data_pending
    directional_lean        INTEGER,            -- -1/0/+1, NULL when data_pending
    quant_score             REAL,               -- directional_lean * 100 (or NULL), the cycle's own -100..+100 read
    -- Qualitative overlay — NULL until narrative_intensity agent ingests (weekly_cycle_assessment trigger).
    narrative_intensity_score  REAL,            -- -100..+100
    narrative_summary          TEXT,
    reconciliation_quadrant    TEXT,            -- cycle_framework.yaml reconciliation.quadrants[].quant_phase_bucket
    reconciliation_flags_json  TEXT,            -- JSON dict, e.g. {"contrarian_sweet_spot": true, "requires_premortem": true}
    data_pending            INTEGER NOT NULL DEFAULT 0,
    missing_kpis_json       TEXT,               -- JSON list[str], populated when data_pending = 1
    contributing_kpis       TEXT,               -- JSON list[str] of kpi_ids actually used for this reading
    note                    TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT,
    UNIQUE(cycle_id, scope, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_cycle_assessments_scope_date ON cycle_assessments(scope, as_of_date);
CREATE INDEX IF NOT EXISTS idx_cycle_assessments_cycle_date ON cycle_assessments(cycle_id, as_of_date);

CREATE TABLE IF NOT EXISTS composite_decisions (
    id                      INTEGER PRIMARY KEY,
    scope                   TEXT NOT NULL,      -- 'NIFTY 50', or a registry sector slug
    as_of_date              TEXT NOT NULL,
    framework_version       TEXT NOT NULL,
    regime_cluster          TEXT,               -- one of Recovery/Expansion/Overheating/Slowdown/Crisis, NULL if UNKNOWN
    regime_unknown          INTEGER NOT NULL DEFAULT 0,
    composite_score         REAL,               -- -100..+100, NULL when regime_unknown or no weighted group available
    alignment_score         REAL,               -- 0-100, NULL when no available cycles
    group_scores_json       TEXT,               -- JSON dict {functional_group: score|null}
    group_weights_json      TEXT,               -- JSON dict {functional_group: weight} actually applied (re-normalized)
    evi_value               REAL,
    evi_components_used_json     TEXT,          -- JSON list[str]
    evi_components_missing_json  TEXT,          -- JSON list[str]
    recommended_action      TEXT,               -- allocation_bands regime_label, or 'data_pending' when yield_gap unavailable
    allocation_band_json    TEXT,               -- JSON dict: the matched allocation_bands row, when available
    contributing_kpis       TEXT,               -- JSON list[str]
    requires_human_review   INTEGER NOT NULL DEFAULT 1,  -- always true per cycle_framework.yaml governance (HITL by default)
    note                    TEXT,
    created_at              TEXT NOT NULL,
    UNIQUE(scope, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_composite_decisions_scope_date ON composite_decisions(scope, as_of_date);

-- ---------------------------------------------------------------------------
-- Agent / job observability
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_runs (
    id              INTEGER PRIMARY KEY,
    run_batch_id    TEXT,
    role            TEXT,
    model           TEXT,
    backend         TEXT CHECK(backend IN ('claude_code','api')),
    trigger         TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        REAL,
    status          TEXT,
    error           TEXT,
    started_at      TEXT,
    finished_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_role_started ON agent_runs(role, started_at);

CREATE TABLE IF NOT EXISTS job_runs (
    id              INTEGER PRIMARY KEY,
    job_name        TEXT,
    status          TEXT,
    rows_written    INTEGER,
    started_at      TEXT,
    finished_at     TEXT,
    error           TEXT
);

-- ---------------------------------------------------------------------------
-- Phase 9 — research subsystem bridge (src/afund/research/)
-- ---------------------------------------------------------------------------
-- One row per research artifact ingested from either the external equity
-- researcher subsystem (research/equity_researcher/, report_type='EQUITY') or
-- an in-house sector_researcher/buy_side agent run (report_type='SECTOR' /
-- 'BUYSIDE'). final_note_path/handoff_path are file pointers (token
-- frugality — the note JSON itself lives under data/packets/research/, per
-- the fund's packet-pointer convention), not embedded content.

CREATE TABLE IF NOT EXISTS research_reports (
    id                  INTEGER PRIMARY KEY,
    instrument_id       INTEGER REFERENCES instruments(id),
    ticker              TEXT NOT NULL,
    report_type         TEXT NOT NULL CHECK(report_type IN ('EQUITY','SECTOR','BUYSIDE')),
    final_note_path     TEXT,
    handoff_path        TEXT,
    rating              TEXT,
    as_of_date          TEXT NOT NULL,
    status              TEXT,
    created_at          TEXT NOT NULL,
    -- Additive (Phase 11 — EPS-bridge doctrine): path to
    -- workspace/<TICKER>/exports/<TICKER>_financials.xlsx (export_financials_xlsx.py),
    -- nullable — most historical rows predate this artifact. New DBs get it
    -- here; existing DBs get it via scripts/init_db.py's _COLUMN_MIGRATIONS.
    xlsx_path           TEXT,
    UNIQUE(ticker, report_type, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_research_reports_ticker ON research_reports(ticker, report_type);

-- ---------------------------------------------------------------------------
-- Phase 10 — ETF/MF fund analytics cache (src/afund/derive/fund_analytics.py)
-- ---------------------------------------------------------------------------
-- One row per (instrument_or_scheme, metric_name, date). Either instrument_id
-- (ETF, matched via instruments.amfi_scheme_code) or scheme_code (a raw AMFI
-- MUTUAL_FUND scheme not necessarily registered as an instruments row) is set,
-- never both — the COALESCE(...,-1)/COALESCE(...,'') UNIQUE index below lets
-- SQLite treat NULL vs NULL as distinct rows the way a plain UNIQUE(a,b,c,d)
-- constraint cannot (NULL never equals NULL in a uniqueness check), so upserts
-- stay correct for whichever key is populated.
CREATE TABLE IF NOT EXISTS derived_series (
    id              INTEGER PRIMARY KEY,
    instrument_id   INTEGER NULL REFERENCES instruments(id),
    scheme_code     TEXT NULL,
    metric_name     TEXT NOT NULL,   -- e.g. 'rolling_return_3y', 'premium_discount_pct', 'capture_upside'
    date            TEXT NOT NULL,
    value           REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_derived_series_unique
    ON derived_series(COALESCE(instrument_id, -1), COALESCE(scheme_code, ''), metric_name, date);

CREATE INDEX IF NOT EXISTS idx_derived_series_lookup
    ON derived_series(metric_name, date);

-- ---------------------------------------------------------------------------
-- Phase 12 — universe screening: company-fit classification
-- (src/afund/derive/company_fit.py)
-- ---------------------------------------------------------------------------
-- One row per (instrument, as_of_date): a single-bucket classification of
-- every active STOCK against the 4-gate funnel + screener contrarian flags +
-- sector cycle phase, built AFTER a batch screener.in scrape has populated
-- derived_ratios for the wider universe (src/afund/data/financials.py
-- scrape_universe). fit_bucket/fit_score rules and thresholds are DRAFT
-- (undocumented in registry/knowledge, not yet back-tested) — see
-- company_fit.py's module docstring for the exact classification logic.
CREATE TABLE IF NOT EXISTS company_fit (
    id              INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id),
    symbol          TEXT NOT NULL,
    as_of_date      TEXT NOT NULL,
    sector          TEXT,               -- raw instruments.sector (NSE industry string)
    kpi_sector      TEXT,               -- registry KPI sector slug (afund.sectors.kpi_key_for_sector)
    sector_phase    TEXT,               -- latest cycle_assessments.phase_id for the sector scope, NULL if unknown
    mcap            REAL,
    pe              REAL,
    roce            REAL,
    roe             REAL,
    ret_1y          REAL,
    pct_52w         REAL,               -- 0-100 rebased 52w position proxy (0=at 52w low, 100=at 52w high)
    flags           TEXT,               -- JSON list[str] of screener contrarian/euphoria flags
    gates_passed    INTEGER,            -- count of funnel gates (gate1, gate4) that PASSed
    fit_bucket      TEXT,               -- contrarian_candidate|quality_watch|euphoria_avoid|weak_avoid|neutral|data_gap
    fit_score       REAL,               -- 0-100, see company_fit.py docstring for the formula
    created_at      TEXT NOT NULL,
    UNIQUE(instrument_id, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_company_fit_bucket_date ON company_fit(fit_bucket, as_of_date);
CREATE INDEX IF NOT EXISTS idx_company_fit_sector_date ON company_fit(kpi_sector, as_of_date);

-- ---------------------------------------------------------------------------
-- AMC monthly portfolio disclosure downloader (src/afund/data/amc_portfolios.py)
-- ---------------------------------------------------------------------------
-- One row per (amc, period, url) discovered/downloaded Excel disclosure file.
-- Download-only for now — NO parsing of Excel contents (that's future scope,
-- see the module docstring). status is 'downloaded' | 'skipped_exists' |
-- 'failed'; failed rows keep url/period so a re-run can retry them.
CREATE TABLE IF NOT EXISTS amc_portfolio_files (
    id              INTEGER PRIMARY KEY,
    amc             TEXT NOT NULL,
    period          TEXT NOT NULL,      -- "YYYY-MM"
    url             TEXT NOT NULL,
    local_path      TEXT,
    downloaded_at   TEXT,
    file_size       INTEGER,
    status          TEXT,
    UNIQUE(amc, period, url)
);

CREATE INDEX IF NOT EXISTS idx_amc_portfolio_files_amc_period ON amc_portfolio_files(amc, period);
