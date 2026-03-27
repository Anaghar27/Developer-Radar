"""Reddit producer for publishing raw posts to Kafka."""

import json
import logging
import os

from dotenv import load_dotenv
from kafka import KafkaProducer
import praw
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


def run(ingest_batch_id: str, limit: int = 200) -> int:
    """
    Publish Reddit posts to Kafka raw_posts topic.
    Returns the number of messages published.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    reddit = get_reddit_client()
    producer = get_kafka_producer()
    published_count = 0

    try:
        for subreddit_name in SUBREDDITS:
            if published_count >= limit:
                break

            fetched_count = 0
            subreddit_published_count = 0

            try:
                subreddit = reddit.subreddit(subreddit_name)
                for submission in subreddit.hot(limit=500):
                    if published_count >= limit:
                        break

                    fetched_count += 1
                    message = map_submission(submission, ingest_batch_id)

                    try:
                        producer.send(
                            TOPIC_NAME,
                            key=submission.id.encode("utf-8"),
                            value=message,
                        )
                        published_count += 1
                        subreddit_published_count += 1
                    except Exception:
                        logger.exception(
                            "Failed to publish Reddit submission %s from r/%s to Kafka",
                            getattr(submission, "id", "unknown"),
                            subreddit_name,
                        )
            except prawcore_exceptions.PrawcoreException:
                logger.exception("Failed to fetch posts from r/%s", subreddit_name)
                continue
            except Exception:
                logger.exception("Unexpected error while iterating r/%s", subreddit_name)
                continue

            logger.info(
                "Reddit producer complete for r/%s: fetched=%s published=%s",
                subreddit_name,
                fetched_count,
                subreddit_published_count,
            )
    finally:
        producer.flush()
        producer.close()

    logger.info("Reddit Kafka publish complete: published_total=%s", published_count)
    return published_count


if __name__ == "__main__":
    run("manual_batch")
