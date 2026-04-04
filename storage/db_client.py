"""Database helpers for the developer sentiment intelligence pipeline."""

import logging
import os
from typing import Any

import psycopg2
from psycopg2 import extras

logger = logging.getLogger(__name__)


def ensure_raw_posts_batch_column() -> None:
    """Ensure raw_posts has the ingest_batch_id column used for DAG batch scoping."""
    query = """
        ALTER TABLE raw_posts
        ADD COLUMN IF NOT EXISTS ingest_batch_id TEXT
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
    except psycopg2.Error:
        logger.exception("Failed to ensure raw_posts.ingest_batch_id column exists")
        raise


def get_connection():
    """Create and return a new PostgreSQL connection using environment variables."""
    try:
        return psycopg2.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        )
    except psycopg2.Error:
        logger.exception("Failed to create PostgreSQL connection")
        raise


def insert_raw_post(post: dict) -> None:
    """Insert a raw post into raw_posts and ignore duplicates by post id."""
    ensure_raw_posts_batch_column()
    query = """
        INSERT INTO raw_posts (id, source, title, body, url, score, created_at, ingest_batch_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        post["id"],
                        post["source"],
                        post.get("title"),
                        post.get("body"),
                        post.get("url"),
                        post.get("score"),
                        post.get("created_at"),
                        post.get("ingest_batch_id"),
                    ),
                )
    except psycopg2.Error:
        logger.exception("Failed to insert raw post: %s", post.get("id"))
        raise


def get_latest_ingested_timestamp(source: str) -> float | None:
    """Return the MAX created_at for a source as a Unix timestamp, or None if no posts exist."""
    query = "SELECT EXTRACT(EPOCH FROM MAX(created_at)) FROM raw_posts WHERE source = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (source,))
                result = cur.fetchone()
                return float(result[0]) if result and result[0] else None
    except psycopg2.Error:
        logger.exception("Failed to fetch latest ingested timestamp for source: %s", source)
        return None


def post_exists(post_id: str) -> bool:
    """Return True when the given post id already exists in raw_posts."""
    query = "SELECT EXISTS (SELECT 1 FROM raw_posts WHERE id = %s)"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (post_id,))
                result = cur.fetchone()
                return bool(result[0]) if result else False
    except psycopg2.Error:
        logger.exception("Failed to check raw post existence for post: %s", post_id)
        raise


def post_is_processed(post_id: str) -> bool:
    """Return True when the given post id already exists in processed_posts."""
    query = "SELECT EXISTS (SELECT 1 FROM processed_posts WHERE post_id = %s)"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (post_id,))
                result = cur.fetchone()
                return bool(result[0]) if result else False
    except psycopg2.Error:
        logger.exception("Failed to check processed status for post: %s", post_id)
        raise


def insert_processed_post(data: dict) -> None:
    """Insert structured LLM output into processed_posts."""
    query = """
        INSERT INTO processed_posts (
            post_id,
            sentiment,
            emotion,
            topic,
            tool_mentioned,
            controversy_score,
            reasoning,
            processed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        data["post_id"],
                        data["sentiment"],
                        data["emotion"],
                        data["topic"],
                        data.get("tool_mentioned"),
                        data["controversy_score"],
                        data["reasoning"],
                        data.get("processed_at"),
                    ),
                )
    except psycopg2.Error:
        logger.exception("Failed to insert processed post: %s", data.get("post_id"))
        raise


def insert_embedding(post_id: str, embedding: list[float]) -> None:
    """Insert a vector embedding for a post into post_embeddings."""
    query = """
        INSERT INTO post_embeddings (post_id, embedding)
        VALUES (%s, %s::vector)
        ON CONFLICT (post_id) DO UPDATE
        SET embedding = EXCLUDED.embedding
    """
    vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (post_id, vector_literal))
    except psycopg2.Error:
        logger.exception("Failed to insert embedding for post: %s", post_id)
        raise


def embedding_exists(post_id: str) -> bool:
    """Return True when the given post id already exists in post_embeddings."""
    query = "SELECT EXISTS (SELECT 1 FROM post_embeddings WHERE post_id = %s)"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (post_id,))
                result = cur.fetchone()
                return bool(result[0]) if result else False
    except psycopg2.Error:
        logger.exception("Failed to check embedding existence for post: %s", post_id)
        raise


def upsert_daily_aggregate(record: dict) -> None:
    """
    DEPRECATED: Use mart_daily_sentiment DuckDB mart instead.
    This function writes to the legacy daily_aggregates PostgreSQL table.
    Kept for backward compatibility only.
    """
    import warnings
    warnings.warn(
        "upsert_daily_aggregate() is deprecated. "
        "Use mart_daily_sentiment from DuckDB instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    query = """
        INSERT INTO daily_aggregates (
            date,
            topic,
            tool,
            avg_sentiment,
            dominant_emotion,
            post_count
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, topic, tool) DO UPDATE
        SET avg_sentiment = EXCLUDED.avg_sentiment,
            dominant_emotion = EXCLUDED.dominant_emotion,
            post_count = EXCLUDED.post_count
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        record["date"],
                        record["topic"],
                        record["tool"],
                        record["avg_sentiment"],
                        record["dominant_emotion"],
                        record["post_count"],
                    ),
                )
    except psycopg2.Error:
        logger.exception(
            "Failed to upsert daily aggregate for %s / %s / %s",
            record.get("date"),
            record.get("topic"),
            record.get("tool"),
        )
        raise


def insert_insight_report(query: str, report_text: str, sources: list[str]) -> None:
    """
    Upsert a generated insight report.
    ON CONFLICT on query hash updates the report and timestamp so repeated
    pipeline runs (e.g. after a crash before cache_set) never produce duplicate rows.
    """
    sql = """
        INSERT INTO insight_reports (query, report_text, sources_used)
        VALUES (%s, %s, %s)
        ON CONFLICT (query) DO UPDATE
            SET report_text  = EXCLUDED.report_text,
                sources_used = EXCLUDED.sources_used,
                generated_at = now()
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (query, report_text, sources))
    except psycopg2.Error:
        logger.exception("Failed to upsert insight report for query: %s", query)
        raise


def fetch_unprocessed_posts(
    limit: int = 100,
    ingest_batch_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch raw posts without processed rows, optionally filtered to one ingest batch."""
    ensure_raw_posts_batch_column()
    if ingest_batch_id is None:
        query = """
            SELECT
                r.id,
                r.source,
                r.title,
                r.body,
                r.url,
                r.score,
                r.created_at,
                r.ingest_batch_id
            FROM raw_posts AS r
            LEFT JOIN processed_posts AS p
                ON r.id = p.post_id
            WHERE p.post_id IS NULL
            ORDER BY r.created_at DESC
            LIMIT %s
        """
        params = (limit,)
    else:
        query = """
            SELECT
                r.id,
                r.source,
                r.title,
                r.body,
                r.url,
                r.score,
                r.created_at,
                r.ingest_batch_id
            FROM raw_posts AS r
            LEFT JOIN processed_posts AS p
                ON r.id = p.post_id
            WHERE p.post_id IS NULL
              AND r.ingest_batch_id = %s
            ORDER BY r.created_at DESC
            LIMIT %s
        """
        params = (ingest_batch_id, limit)
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except psycopg2.Error:
        logger.exception("Failed to fetch unprocessed posts")
        raise


def fetch_batch_posts_without_embeddings(
    ingest_batch_id: str | None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch raw posts that do not yet have embeddings.
    When ingest_batch_id is None, returns all posts without embeddings.
    When ingest_batch_id is provided, scopes to that batch only.
    """
    ensure_raw_posts_batch_column()
    if ingest_batch_id is None:
        query = """
            SELECT
                r.id,
                r.source,
                r.title,
                r.body,
                r.url,
                r.score,
                r.created_at,
                r.ingest_batch_id
            FROM raw_posts AS r
            LEFT JOIN post_embeddings AS e
                ON r.id = e.post_id
            WHERE e.post_id IS NULL
            ORDER BY r.created_at DESC
            LIMIT %s
        """
        params = (limit,)
    else:
        query = """
            SELECT
                r.id,
                r.source,
                r.title,
                r.body,
                r.url,
                r.score,
                r.created_at,
                r.ingest_batch_id
            FROM raw_posts AS r
            LEFT JOIN post_embeddings AS e
                ON r.id = e.post_id
            WHERE r.ingest_batch_id = %s
              AND e.post_id IS NULL
            ORDER BY r.created_at DESC
            LIMIT %s
        """
        params = (ingest_batch_id, limit)
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except psycopg2.Error:
        logger.exception(
            "Failed to fetch posts without embeddings for batch: %s",
            ingest_batch_id,
        )
        raise


def smoke_test_db() -> dict[str, Any]:
    """Run a minimal DB smoke test by inserting and reading back one dummy raw post."""
    test_post = {
        "id": "smoke_test_post",
        "source": "smoke_test",
        "title": "Smoke Test Title",
        "body": "Smoke test body",
        "url": "https://example.com/smoke-test",
        "score": 1,
        "created_at": "2026-03-15 00:00:00",
    }
    select_query = """
        SELECT id, source, title, body, url, score, created_at
        FROM raw_posts
        WHERE id = %s
    """
    cleanup_query = "DELETE FROM raw_posts WHERE id = %s"

    try:
        insert_raw_post(test_post)
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(select_query, (test_post["id"],))
                row = cur.fetchone()
                cur.execute(cleanup_query, (test_post["id"],))
        if not row:
            raise RuntimeError("Smoke test insert succeeded but row could not be read back")
        return dict(row)
    except psycopg2.Error:
        logger.exception("Database smoke test failed")
        raise


# ── New table CRUDs (Day 1 addition) ────────────────────────────────────────


def insert_failed_event(event_type: str, payload: dict, error_reason: str) -> None:
    """Insert a new failed event record."""
    query = """
        INSERT INTO failed_events (event_type, payload, error_reason)
        VALUES (%s, %s, %s)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (event_type, extras.Json(payload), error_reason))
    except psycopg2.Error:
        logger.exception("Failed to insert failed event for type: %s", event_type)
        raise


def increment_failed_event_attempt(event_id: int) -> None:
    """Increment attempt_count and update last_attempted_at for a failed event."""
    query = """
        UPDATE failed_events
        SET attempt_count = attempt_count + 1,
            last_attempted_at = NOW()
        WHERE id = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (event_id,))
    except psycopg2.Error:
        logger.exception("Failed to increment failed event attempt for id: %s", event_id)
        raise


def fetch_failed_events(event_type: str = None, limit: int = 100) -> list[dict]:
    """Fetch failed events, optionally filtered by event_type. Returns list of dicts."""
    if event_type:
        query = """
            SELECT
                id,
                event_type,
                payload,
                error_reason,
                attempt_count,
                last_attempted_at,
                created_at
            FROM failed_events
            WHERE event_type = %s
            ORDER BY created_at DESC
            LIMIT %s
        """
        params = (event_type, limit)
    else:
        query = """
            SELECT
                id,
                event_type,
                payload,
                error_reason,
                attempt_count,
                last_attempted_at,
                created_at
            FROM failed_events
            ORDER BY created_at DESC
            LIMIT %s
        """
        params = (limit,)

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except psycopg2.Error:
        logger.exception("Failed to fetch failed events for type: %s", event_type)
        raise


def insert_alert(topic: str, today_count: int, rolling_avg: float, pct_increase: float) -> None:
    """Insert a volume spike alert, skipping if one already exists for this topic today."""
    query = """
        INSERT INTO alerts (topic, today_count, rolling_avg, pct_increase, alert_date)
        VALUES (%s, %s, %s, %s, CURRENT_DATE)
        ON CONFLICT (topic, alert_date) DO NOTHING
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (topic, today_count, rolling_avg, pct_increase))
    except psycopg2.Error:
        logger.exception("Failed to insert alert for topic: %s", topic)
        raise


def fetch_recent_alerts(limit: int = 50) -> list[dict]:
    """Fetch most recent alerts ordered by triggered_at DESC."""
    query = """
        SELECT
            id,
            topic,
            today_count,
            rolling_avg,
            pct_increase,
            triggered_at
        FROM alerts
        ORDER BY triggered_at DESC
        LIMIT %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except psycopg2.Error:
        logger.exception("Failed to fetch recent alerts")
        raise


def insert_pipeline_run(run_id: str, dag_id: str, start_time) -> None:
    """Insert a new pipeline run record at the start of a DAG run."""
    query = """
        INSERT INTO pipeline_runs (run_id, dag_id, start_time)
        VALUES (%s, %s, %s)
        ON CONFLICT (run_id) DO NOTHING
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id, dag_id, start_time))
    except psycopg2.Error:
        logger.exception("Failed to insert pipeline run: %s", run_id)
        raise


def update_pipeline_run(
    run_id: str,
    end_time,
    duration_seconds: float,
    posts_ingested: int,
    posts_classified: int,
    posts_failed: int,
    error_rate: float,
) -> None:
    """Update a pipeline run with completion metrics."""
    query = """
        UPDATE pipeline_runs
        SET end_time = %s,
            duration_seconds = %s,
            posts_ingested = %s,
            posts_classified = %s,
            posts_failed = %s,
            error_rate = %s
        WHERE run_id = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        end_time,
                        duration_seconds,
                        posts_ingested,
                        posts_classified,
                        posts_failed,
                        error_rate,
                        run_id,
                    ),
                )
    except psycopg2.Error:
        logger.exception("Failed to update pipeline run: %s", run_id)
        raise


def fetch_latest_pipeline_run(dag_id: str = None) -> dict | None:
    """Fetch the most recent pipeline run, optionally filtered by dag_id."""
    if dag_id:
        query = """
            SELECT
                run_id,
                dag_id,
                start_time,
                end_time,
                duration_seconds,
                posts_ingested,
                posts_classified,
                posts_failed,
                error_rate,
                created_at
            FROM pipeline_runs
            WHERE dag_id = %s
            ORDER BY start_time DESC
            LIMIT 1
        """
        params = (dag_id,)
    else:
        query = """
            SELECT
                run_id,
                dag_id,
                start_time,
                end_time,
                duration_seconds,
                posts_ingested,
                posts_classified,
                posts_failed,
                error_rate,
                created_at
            FROM pipeline_runs
            ORDER BY start_time DESC
            LIMIT 1
        """
        params = ()

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                return dict(row) if row else None
    except psycopg2.Error:
        logger.exception("Failed to fetch latest pipeline run for dag_id: %s", dag_id)
        raise


def insert_user(email: str, hashed_password: str, api_key: str) -> int:
    """Insert a new user. Returns the new user id."""
    query = """
        INSERT INTO users (email, hashed_password, api_key, is_active)
        VALUES (%s, %s, %s, FALSE)
        RETURNING id
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (email, hashed_password, api_key))
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("User insert did not return an id")
                return int(row[0])
    except psycopg2.Error:
        logger.exception("Failed to insert user with email: %s", email)
        raise


def fetch_user_by_email(email: str) -> dict | None:
    """Fetch a user by email. Returns dict or None."""
    query = """
        SELECT
            id,
            email,
            hashed_password,
            api_key,
            is_active,
            created_at
        FROM users
        WHERE email = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, (email,))
                row = cur.fetchone()
                return dict(row) if row else None
    except psycopg2.Error:
        logger.exception("Failed to fetch user by email: %s", email)
        raise


def fetch_user_by_api_key(api_key: str) -> dict | None:
    """Fetch a user by api_key. Returns dict or None."""
    query = """
        SELECT
            id,
            email,
            hashed_password,
            api_key,
            is_active,
            created_at
        FROM users
        WHERE api_key = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, (api_key,))
                row = cur.fetchone()
                return dict(row) if row else None
    except psycopg2.Error:
        logger.exception("Failed to fetch user by api_key")
        raise


def deactivate_user(user_id: int) -> None:
    """Set is_active=False for the given user_id."""
    query = """
        UPDATE users
        SET is_active = FALSE
        WHERE id = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
    except psycopg2.Error:
        logger.exception("Failed to deactivate user: %s", user_id)
        raise


def activate_user(user_id: int) -> None:
    """Set is_active=True for the given user_id."""
    query = "UPDATE users SET is_active = TRUE WHERE id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
    except psycopg2.Error:
        logger.exception("Failed to activate user: %s", user_id)
        raise


# ── CRUD completion helpers for Day 1 tables ────────────────────────────────


def update_alert(
    alert_id: int,
    topic: str,
    today_count: int,
    rolling_avg: float,
    pct_increase: float,
) -> None:
    """Update an existing alert row."""
    query = """
        UPDATE alerts
        SET topic = %s,
            today_count = %s,
            rolling_avg = %s,
            pct_increase = %s
        WHERE id = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (topic, today_count, rolling_avg, pct_increase, alert_id),
                )
    except psycopg2.Error:
        logger.exception("Failed to update alert: %s", alert_id)
        raise


def delete_failed_event(event_id: int) -> None:
    """Delete a failed event by id."""
    query = "DELETE FROM failed_events WHERE id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (event_id,))
    except psycopg2.Error:
        logger.exception("Failed to delete failed event: %s", event_id)
        raise


def delete_alert(alert_id: int) -> None:
    """Delete an alert by id."""
    query = "DELETE FROM alerts WHERE id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (alert_id,))
    except psycopg2.Error:
        logger.exception("Failed to delete alert: %s", alert_id)
        raise


def delete_pipeline_run(run_id: str) -> None:
    """Delete a pipeline run by run_id."""
    query = "DELETE FROM pipeline_runs WHERE run_id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id,))
    except psycopg2.Error:
        logger.exception("Failed to delete pipeline run: %s", run_id)
        raise


def delete_user(user_id: int) -> None:
    """Delete a user by id."""
    query = "DELETE FROM users WHERE id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
    except psycopg2.Error:
        logger.exception("Failed to delete user: %s", user_id)
        raise


# ── Password reset tokens ────────────────────────────────────────────────────


def create_reset_token(user_id: int, token_hash: str, expires_at) -> None:
    """Store a hashed password reset token. Replaces any existing unused token for the user."""
    delete_query = "DELETE FROM password_reset_tokens WHERE user_id = %s AND used_at IS NULL"
    insert_query = """
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_query, (user_id,))
                cur.execute(insert_query, (user_id, token_hash, expires_at))
    except psycopg2.Error:
        logger.exception("Failed to create reset token for user: %s", user_id)
        raise


def fetch_reset_token(token_hash: str) -> dict | None:
    """Fetch a valid (unused, non-expired) reset token record. Returns dict or None."""
    query = """
        SELECT id, user_id, token_hash, expires_at, used_at
        FROM password_reset_tokens
        WHERE token_hash = %s
          AND used_at IS NULL
          AND expires_at > NOW()
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, (token_hash,))
                row = cur.fetchone()
                return dict(row) if row else None
    except psycopg2.Error:
        logger.exception("Failed to fetch reset token")
        raise


def consume_reset_token(token_id: int) -> None:
    """Mark a reset token as used so it cannot be reused."""
    query = "UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (token_id,))
    except psycopg2.Error:
        logger.exception("Failed to consume reset token: %s", token_id)
        raise


def update_user_password(user_id: int, hashed_password: str) -> None:
    """Update a user's hashed password."""
    query = "UPDATE users SET hashed_password = %s WHERE id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (hashed_password, user_id))
    except psycopg2.Error:
        logger.exception("Failed to update password for user: %s", user_id)
        raise


# ── Email verification tokens ────────────────────────────────────────────────


def create_verification_token(user_id: int, token_hash: str, expires_at) -> None:
    """Store a hashed email verification token. Replaces any existing unused token for the user."""
    delete_query = "DELETE FROM email_verification_tokens WHERE user_id = %s AND used_at IS NULL"
    insert_query = """
        INSERT INTO email_verification_tokens (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_query, (user_id,))
                cur.execute(insert_query, (user_id, token_hash, expires_at))
    except psycopg2.Error:
        logger.exception("Failed to create verification token for user: %s", user_id)
        raise


def fetch_verification_token(token_hash: str) -> dict | None:
    """Fetch a valid (unused, non-expired) verification token record. Returns dict or None."""
    query = """
        SELECT id, user_id, token_hash, expires_at, used_at
        FROM email_verification_tokens
        WHERE token_hash = %s
          AND used_at IS NULL
          AND expires_at > NOW()
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, (token_hash,))
                row = cur.fetchone()
                return dict(row) if row else None
    except psycopg2.Error:
        logger.exception("Failed to fetch verification token")
        raise


def consume_verification_token(token_id: int) -> None:
    """Mark a verification token as used so it cannot be reused."""
    query = "UPDATE email_verification_tokens SET used_at = NOW() WHERE id = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (token_id,))
    except psycopg2.Error:
        logger.exception("Failed to consume verification token: %s", token_id)
        raise
