CREATE TABLE IF NOT EXISTS raw_posts (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    body TEXT,
    url TEXT,
    score INTEGER,
    created_at TIMESTAMP,
    -- ingest_batch_id: groups posts from the same DAG run for batch-scoped processing
    ingest_batch_id VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS processed_posts (
    post_id TEXT PRIMARY KEY REFERENCES raw_posts(id),
    sentiment TEXT,
    emotion TEXT,
    topic TEXT,
    tool_mentioned TEXT,
    controversy_score INTEGER,
    reasoning TEXT,
    processed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS post_embeddings (
    post_id TEXT PRIMARY KEY REFERENCES raw_posts(id),
    embedding vector(1536)
);

-- DEPRECATED: daily_aggregates is superseded by mart_daily_sentiment in DuckDB.
-- Kept for backward compatibility. Do not write new data to this table.
-- Will be removed in a future migration once dbt marts are the single source of truth.
CREATE TABLE IF NOT EXISTS daily_aggregates (
    id SERIAL PRIMARY KEY,
    date DATE,
    topic TEXT,
    tool TEXT,
    avg_sentiment FLOAT,
    dominant_emotion TEXT,
    post_count INTEGER
);

CREATE TABLE IF NOT EXISTS insight_reports (
    id SERIAL PRIMARY KEY,
    query TEXT UNIQUE,
    report_text TEXT,
    -- NOTE: sources_used is a PostgreSQL array — denormalized from strict 1NF.
    -- The normalized form would be a child table (insight_report_sources).
    -- Array chosen deliberately: sources are always fetched together with
    -- the report (no standalone source queries exist), so a child table
    -- adds join complexity with zero query benefit.
    sources_used TEXT[],
    generated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_posts_source
    ON raw_posts(source);

CREATE INDEX IF NOT EXISTS idx_raw_posts_created_at
    ON raw_posts(created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_aggregates_date_topic_tool
    ON daily_aggregates(date, topic, tool);

CREATE INDEX IF NOT EXISTS idx_post_embeddings_embedding
    ON post_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS failed_events (
    id                SERIAL PRIMARY KEY,
    event_type        VARCHAR(50) NOT NULL, -- 'ingestion' | 'classification' | 'embedding'
    payload           JSONB NOT NULL,
    error_reason      TEXT NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 1,
    last_attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failed_events_event_type
    ON failed_events(event_type);

CREATE INDEX IF NOT EXISTS idx_failed_events_created_at
    ON failed_events(created_at);

CREATE TABLE IF NOT EXISTS alerts (
    id           SERIAL PRIMARY KEY,
    topic        VARCHAR(100) NOT NULL,
    today_count  INTEGER NOT NULL,
    rolling_avg  NUMERIC(10,2) NOT NULL,
    -- NOTE: pct_increase is a denormalized derived field:
    --   pct_increase = ((today_count - rolling_avg) / rolling_avg) * 100
    -- Stored explicitly (violates strict 3NF) for two reasons:
    --   1. Query performance — avoids recalculation on every read
    --   2. Historical accuracy — rolling_avg changes over time;
    --      snapshot at trigger time is the meaningful value
    pct_increase NUMERIC(10,2) NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at
    ON alerts(triggered_at);

CREATE INDEX IF NOT EXISTS idx_alerts_topic
    ON alerts(topic);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           VARCHAR(100) PRIMARY KEY,
    dag_id           VARCHAR(100) NOT NULL,
    start_time       TIMESTAMPTZ NOT NULL,
    end_time         TIMESTAMPTZ,
    -- NOTE: duration_seconds is a denormalized derived field:
    --   duration_seconds = EXTRACT(EPOCH FROM (end_time - start_time))
    -- Stored explicitly (violates strict 3NF) for Prometheus scraping —
    -- the metrics exporter reads this directly without timestamp arithmetic.
    duration_seconds NUMERIC(10,2),
    posts_ingested   INTEGER NOT NULL DEFAULT 0,
    posts_classified INTEGER NOT NULL DEFAULT 0,
    posts_failed     INTEGER NOT NULL DEFAULT 0,
    -- NOTE: error_rate is a denormalized derived field:
    --   error_rate = posts_failed / NULLIF(posts_ingested, 0)
    -- Stored explicitly (violates strict 3NF) for Prometheus scraping —
    -- devpulse_classification_error_rate gauge reads this directly.
    -- Alerts fire when error_rate > 0.10 (10%).
    error_rate       NUMERIC(5,4) NOT NULL DEFAULT 0.0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_dag_id
    ON pipeline_runs(dag_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_start_time
    ON pipeline_runs(start_time);

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    api_key         VARCHAR(64) UNIQUE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

CREATE INDEX IF NOT EXISTS idx_users_api_key
    ON users(api_key);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prt_token_hash
    ON password_reset_tokens(token_hash);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evt_token_hash
    ON email_verification_tokens(token_hash);
