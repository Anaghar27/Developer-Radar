"""Unit tests for Kafka producers, validator, and consumer."""

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "kafka" not in sys.modules:
    kafka_stub = types.ModuleType("kafka")
    kafka_stub.KafkaConsumer = MagicMock
    kafka_stub.KafkaProducer = MagicMock
    sys.modules["kafka"] = kafka_stub

from ingestion import consumer, hackernews_producer, reddit_producer
from processing.validator import coerce_message, validate_post


def test_reddit_producer_publishes_messages():
    """reddit_producer.run should publish one Kafka message per fetched submission."""
    fake_submissions = []
    for idx in range(5):
        fake_submissions.append(
            SimpleNamespace(
                id=f"reddit-{idx}",
                subreddit=SimpleNamespace(display_name="MachineLearning"),
                title=f"Reddit title {idx}",
                selftext=f"Reddit body {idx}",
                url=f"https://reddit.example/{idx}",
                score=idx,
                created_utc=1710000000.0 + idx,
            )
        )

    fake_subreddit = MagicMock()
    fake_subreddit.hot.return_value = fake_submissions
    empty_subreddit = MagicMock()
    empty_subreddit.hot.return_value = []
    fake_reddit = MagicMock()
    fake_reddit.subreddit.side_effect = [
        fake_subreddit,
        empty_subreddit,
        empty_subreddit,
        empty_subreddit,
        empty_subreddit,
    ]

    mock_producer = MagicMock()
    mock_producer.bootstrap_connected.return_value = True

    with patch("ingestion.reddit_producer.praw.Reddit", return_value=fake_reddit), patch(
        "ingestion.reddit_producer.KafkaProducer", return_value=mock_producer
    ):
        result = reddit_producer.run(ingest_batch_id="test_batch")

    assert result == 5
    assert mock_producer.send.call_count == 5
    assert mock_producer.send.call_args_list[0].args[0] == "raw_posts"


def test_hackernews_producer_publishes_messages():
    """hackernews_producer.run should publish valid HN stories to Kafka."""

    def make_response(payload):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def mock_get(url, timeout=10):
        if url.endswith("/topstories.json"):
            return make_response([101, 102, 103, 104])

        item_id = int(url.rsplit("/", 1)[-1].split(".")[0])
        return make_response(
            {
                "id": item_id,
                "type": "story",
                "title": f"Story {item_id}",
                "text": f"Body {item_id}",
                "url": f"https://example.com/{item_id}",
                "score": item_id,
                "time": 1710000000 + item_id,
            }
        )

    mock_producer = MagicMock()
    mock_producer.bootstrap_connected.return_value = True

    with patch.object(hackernews_producer.SESSION, "get", side_effect=mock_get), patch(
        "ingestion.hackernews_producer.KafkaProducer", return_value=mock_producer
    ):
        result = hackernews_producer.run(ingest_batch_id="test_batch", limit=3)

    assert result == 3
    assert mock_producer.send.call_count == 3


def test_validator_valid_post():
    """validate_post should accept a valid coerced Reddit message."""
    msg = coerce_message(
        {
            "id": "abc123",
            "source": "reddit",
            "title": "This is a valid post title",
            "body": None,
            "score": 42,
        }
    )
    is_valid, reason = validate_post(msg)
    assert is_valid is True
    assert reason == ""


def test_validator_missing_title():
    """validate_post should reject a message missing title."""
    msg = {"id": "abc123", "source": "reddit"}
    is_valid, reason = validate_post(msg)
    assert is_valid is False
    assert "title" in reason.lower()


def test_validator_invalid_source():
    """validate_post should reject an unsupported source."""
    msg = {"id": "abc123", "source": "twitter", "title": "Some title here"}
    is_valid, reason = validate_post(msg)
    assert is_valid is False
    assert "source" in reason.lower()


def test_validator_title_too_short():
    """validate_post should reject titles below the minimum length."""
    msg = {"id": "abc123", "source": "reddit", "title": "Hi"}
    is_valid, reason = validate_post(msg)
    assert is_valid is False
    assert "title" in reason.lower()


def test_consumer_routes_valid_to_db():
    """consumer.run should insert a valid non-duplicate post into PostgreSQL."""
    message = {
        "id": "abc123",
        "source": "reddit",
        "title": "This is a valid post title",
        "body": "",
        "score": 42,
        "created_utc": 1710000000.0,
    }
    record = SimpleNamespace(value=message)
    mock_consumer = MagicMock()
    mock_consumer.__iter__.return_value = iter([record])
    mock_producer = MagicMock()

    with patch("ingestion.consumer.KafkaConsumer", return_value=mock_consumer), patch(
        "ingestion.consumer.KafkaProducer", return_value=mock_producer
    ), patch("ingestion.consumer.post_exists", return_value=False), patch(
        "ingestion.consumer.insert_raw_post"
    ) as mock_insert_raw_post, patch(
        "ingestion.consumer.insert_failed_event"
    ) as mock_insert_failed_event:
        summary = consumer.run(ingest_batch_id="test_batch")

    mock_insert_raw_post.assert_called_once()
    mock_insert_failed_event.assert_not_called()
    assert summary["inserted"] == 1
    assert summary["failed"] == 0


def test_consumer_routes_invalid_to_dead_letter():
    """consumer.run should route invalid messages to failed_events."""
    message = {
        "id": "abc123",
        "source": "reddit",
    }
    record = SimpleNamespace(value=message)
    mock_consumer = MagicMock()
    mock_consumer.__iter__.return_value = iter([record])
    mock_producer = MagicMock()

    with patch("ingestion.consumer.KafkaConsumer", return_value=mock_consumer), patch(
        "ingestion.consumer.KafkaProducer", return_value=mock_producer
    ), patch("ingestion.consumer.insert_raw_post") as mock_insert_raw_post, patch(
        "ingestion.consumer.post_exists"
    ) as mock_post_exists, patch(
        "ingestion.consumer.insert_failed_event"
    ) as mock_insert_failed_event:
        summary = consumer.run(ingest_batch_id="test_batch")

    mock_insert_raw_post.assert_not_called()
    mock_post_exists.assert_not_called()
    mock_insert_failed_event.assert_called_once()
    assert mock_producer.send.call_args.args[0] == "failed_events"
    assert summary["failed"] == 1


def test_consumer_skips_duplicates():
    """consumer.run should skip valid posts already present in PostgreSQL."""
    message = {
        "id": "abc123",
        "source": "reddit",
        "title": "This is a valid post title",
        "body": "",
        "score": 10,
        "created_utc": 1710000000.0,
    }
    record = SimpleNamespace(value=message)
    mock_consumer = MagicMock()
    mock_consumer.__iter__.return_value = iter([record])
    mock_producer = MagicMock()

    with patch("ingestion.consumer.KafkaConsumer", return_value=mock_consumer), patch(
        "ingestion.consumer.KafkaProducer", return_value=mock_producer
    ), patch("ingestion.consumer.post_exists", return_value=True), patch(
        "ingestion.consumer.insert_raw_post"
    ) as mock_insert_raw_post:
        summary = consumer.run(ingest_batch_id="test_batch")

    mock_insert_raw_post.assert_not_called()
    assert summary["duplicates"] == 1
