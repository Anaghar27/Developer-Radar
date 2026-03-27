"""Smoke tests for ingestion and storage work."""

from datetime import UTC, datetime

import pytest

from storage.db_client import get_connection, insert_raw_post


TEST_POST_ID = "test_raw_post_ingestion"


@pytest.fixture
def cleanup_test_post():
    """Ensure the fixed test raw post is removed before and after a test."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM raw_posts WHERE id = %s", (TEST_POST_ID,))
    yield
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM raw_posts WHERE id = %s", (TEST_POST_ID,))


def test_db_connection():
    """Verify that a database connection can be established."""
    conn = get_connection()
    try:
        assert conn is not None
    finally:
        conn.close()


def test_insert_and_dedup(cleanup_test_post):
    """Insert the same raw post twice and assert only one row is stored."""
    post = {
        "id": TEST_POST_ID,
        "source": "test",
        "title": "Dedup Test",
        "body": "Testing duplicate insert handling",
        "url": "https://example.com/test",
        "score": 1,
        "created_at": datetime.now(UTC),
    }

    insert_raw_post(post)
    insert_raw_post(post)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw_posts WHERE id = %s", (TEST_POST_ID,))
            row_count = cur.fetchone()[0]

    assert row_count == 1
