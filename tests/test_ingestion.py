"""Smoke tests for ingestion and storage work."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from ingestion import hackernews_ingestor, reddit_ingestor
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
        "created_at": datetime.utcnow(),
    }

    insert_raw_post(post)
    insert_raw_post(post)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw_posts WHERE id = %s", (TEST_POST_ID,))
            row_count = cur.fetchone()[0]

    assert row_count == 1


def test_reddit_ingestor_returns_posts():
    """Mock Reddit ingestion and assert at least one post is inserted."""
    fake_submission = Mock()
    fake_submission.id = "abc123"
    fake_submission.title = "Test Reddit Post"
    fake_submission.selftext = "Body"
    fake_submission.url = "https://reddit.com/test"
    fake_submission.score = 42
    fake_submission.created_utc = 1710000000

    fake_subreddit = Mock()
    fake_subreddit.hot.return_value = [fake_submission]

    fake_reddit = Mock()
    fake_reddit.subreddit.return_value = fake_subreddit

    with patch("ingestion.reddit_ingestor.praw.Reddit", return_value=fake_reddit), patch(
        "ingestion.reddit_ingestor.insert_raw_post"
    ) as mock_insert, patch("ingestion.reddit_ingestor.post_exists", return_value=False):
        reddit_ingestor.run()

    assert mock_insert.call_count >= 1


def test_hn_ingestor_returns_posts():
    """Mock Hacker News ingestion and assert three posts are inserted."""
    topstories_response = Mock()
    topstories_response.raise_for_status.return_value = None
    topstories_response.json.return_value = [1, 2, 3]

    def make_item_response(item_id: int) -> Mock:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": item_id,
            "type": "story",
            "title": f"Story {item_id}",
            "text": f"Body {item_id}",
            "url": f"https://example.com/{item_id}",
            "score": item_id * 10,
            "time": 1710000000 + item_id,
        }
        return response

    def mock_get(url, timeout=10):
        if url.endswith("/topstories.json"):
            return topstories_response
        item_id = int(url.rsplit("/", 1)[-1].split(".")[0])
        return make_item_response(item_id)

    with patch("ingestion.hackernews_ingestor.requests.get", side_effect=mock_get), patch(
        "ingestion.hackernews_ingestor.insert_raw_post"
    ) as mock_insert, patch(
        "ingestion.hackernews_ingestor.post_exists", return_value=False
    ), patch("ingestion.hackernews_ingestor.time.sleep", return_value=None):
        hackernews_ingestor.run()

    assert mock_insert.call_count == 3
