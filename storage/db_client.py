"""Database helpers for the developer sentiment intelligence pipeline."""

import logging
import os
from typing import Any

import psycopg2
from psycopg2 import extras


logger = logging.getLogger(__name__)


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
    except psycopg2.Error as exc:
        logger.exception("Failed to create PostgreSQL connection")
        raise


def insert_raw_post(post: dict) -> None:
    """Insert a raw post into raw_posts and ignore duplicates by post id."""
    query = """
        INSERT INTO raw_posts (id, source, title, body, url, score, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                    ),
                )
    except psycopg2.Error:
        logger.exception("Failed to insert raw post: %s", post.get("id"))
        raise


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
    """Insert or update an aggregate row keyed by date, topic, and tool."""
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
    """Insert a generated insight report and its source post ids."""
    sql = """
        INSERT INTO insight_reports (query, report_text, sources_used)
        VALUES (%s, %s, %s)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (query, report_text, sources))
    except psycopg2.Error:
        logger.exception("Failed to insert insight report for query: %s", query)
        raise


def fetch_unprocessed_posts(limit: int = 100) -> list[dict[str, Any]]:
    """Fetch raw posts that do not yet have matching rows in processed_posts."""
    query = """
        SELECT
            r.id,
            r.source,
            r.title,
            r.body,
            r.url,
            r.score,
            r.created_at
        FROM raw_posts AS r
        LEFT JOIN processed_posts AS p
            ON r.id = p.post_id
        WHERE p.post_id IS NULL
        ORDER BY r.created_at DESC
        LIMIT %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except psycopg2.Error:
        logger.exception("Failed to fetch unprocessed posts")
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
