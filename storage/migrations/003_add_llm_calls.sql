-- Migration 003: Add durable LLM call tracking table
-- Run: psql $DATABASE_URL -f storage/migrations/003_add_llm_calls.sql

CREATE TABLE IF NOT EXISTS llm_calls (
    id BIGSERIAL PRIMARY KEY,
    operation VARCHAR(100) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    model VARCHAR(255) NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms NUMERIC(12,2) NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_reason TEXT,
    cost_usd NUMERIC(12,8) NOT NULL DEFAULT 0,
    post_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_created_at
    ON llm_calls(created_at);

CREATE INDEX IF NOT EXISTS idx_llm_calls_operation
    ON llm_calls(operation);

CREATE INDEX IF NOT EXISTS idx_llm_calls_provider
    ON llm_calls(provider);
