CREATE TABLE IF NOT EXISTS raw_posts (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    body TEXT,
    url TEXT,
    score INTEGER,
    created_at TIMESTAMP
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
    embedding vector(384)
);

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
    query TEXT,
    report_text TEXT,
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
    USING ivfflat (embedding vector_cosine_ops);
