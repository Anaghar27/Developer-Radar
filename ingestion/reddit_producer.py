"""Reddit producer for publishing raw posts to Kafka."""

import json
import logging
import os
from datetime import UTC

import praw
from dotenv import load_dotenv
from kafka import KafkaProducer
from prawcore import exceptions as prawcore_exceptions

load_dotenv()


logger = logging.getLogger(__name__)

SUBREDDITS = [
    "MachineLearning",
    "datascience",
    "mlops",
    "LocalLLaMA",
    "Python",
]

TOPIC_NAME = "raw_posts"


def get_reddit_client() -> praw.Reddit:
    """Create and return a read-only Reddit client from environment variables."""
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )
    reddit.read_only = True
    return reddit


def get_kafka_producer() -> KafkaProducer:
    """Create a Kafka producer and fail fast if the broker is unreachable."""
    producer = KafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k if isinstance(k, bytes) else k.encode("utf-8"),
        acks="all",
        retries=3,
    )
    if not producer.bootstrap_connected():
        producer.close()
        raise ConnectionError("Kafka producer could not connect to bootstrap servers")
    return producer


def map_submission(submission, ingest_batch_id: str) -> dict:
    """Map a PRAW submission into the raw Kafka payload schema."""
    return {
        "id": submission.id,
        "source": "reddit",
        "subreddit": submission.subreddit.display_name,
        "title": submission.title,
        "body": submission.selftext or "",
        "url": submission.url,
        "score": submission.score,
        "created_utc": submission.created_utc,
        "ingest_batch_id": ingest_batch_id,
    }


def _publish_submissions(submissions, feed: str, subreddit_name: str, producer, ingest_batch_id: str,
                         since: float | None, limit: int, published_count: int, seen_ids: set) -> tuple[int, int]:
    """Iterate submissions from a feed, deduplicate, apply cutoff, and publish to Kafka."""
    fetched = 0
    published = 0
    for submission in submissions:
        if published_count + published >= limit:
            break

        fetched += 1

        if submission.id in seen_ids:
            continue

        if since and feed == "new" and submission.created_utc <= since:
            break

        if since and feed == "hot" and submission.created_utc <= since:
            continue

        seen_ids.add(submission.id)
        message = map_submission(submission, ingest_batch_id)

        try:
            producer.send(
                TOPIC_NAME,
                key=submission.id.encode("utf-8"),
                value=message,
            )
            published += 1
        except Exception:
            logger.exception(
                "Failed to publish Reddit submission %s from r/%s to Kafka",
                submission.id,
                subreddit_name,
            )

    return fetched, published


def run(ingest_batch_id: str, limit: int = 200, since: float | None = None) -> int:
    """
    Publish Reddit posts from both .new() and .hot() feeds to Kafka.
    Deduplicates across feeds. Only fetches posts newer than `since` (Unix timestamp) if provided.
    Returns the number of messages published.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if since:
        from datetime import datetime, timezone
        logger.info("Reddit: fetching posts newer than %s", datetime.fromtimestamp(since, tz=UTC).isoformat())
    else:
        logger.info("Reddit: no cutoff set, fetching latest posts")

    reddit = get_reddit_client()
    producer = get_kafka_producer()
    published_count = 0
    seen_ids: set = set()

    try:
        for subreddit_name in SUBREDDITS:
            if published_count >= limit:
                break

            subreddit_published = 0

            try:
                subreddit = reddit.subreddit(subreddit_name)

                _, new_published = _publish_submissions(
                    subreddit.new(limit=500), "new", subreddit_name,
                    producer, ingest_batch_id, since, limit, published_count, seen_ids,
                )
                published_count += new_published
                subreddit_published += new_published

                if published_count < limit:
                    _, hot_published = _publish_submissions(
                        subreddit.hot(limit=500), "hot", subreddit_name,
                        producer, ingest_batch_id, since, limit, published_count, seen_ids,
                    )
                    published_count += hot_published
                    subreddit_published += hot_published

            except prawcore_exceptions.PrawcoreException:
                logger.exception("Failed to fetch posts from r/%s", subreddit_name)
                continue
            except Exception:
                logger.exception("Unexpected error while iterating r/%s", subreddit_name)
                continue

            logger.info(
                "Reddit producer complete for r/%s: published=%s (new+hot)",
                subreddit_name,
                subreddit_published,
            )
    finally:
        producer.flush()
        producer.close()

    logger.info("Reddit Kafka publish complete: published_total=%s", published_count)
    return published_count


if __name__ == "__main__":
    run("manual_batch")
