"""Hacker News producer for publishing raw posts to Kafka."""

import json
import logging
import os
import time

from dotenv import load_dotenv
from kafka import KafkaProducer
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


load_dotenv()


logger = logging.getLogger(__name__)

BASE_URL = "https://hacker-news.firebaseio.com/v0"
TOP_STORIES_URL = f"{BASE_URL}/topstories.json"
ITEM_ENDPOINT = f"{BASE_URL}/item/{{item_id}}.json"
ITEM_FETCH_RETRIES = 3
ITEM_FETCH_BACKOFF_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 10
TOPIC_NAME = "raw_posts"


def _build_session() -> requests.Session:
    """Create a requests session with retry policy for transient HTTPS failures."""
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = _build_session()


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


def fetch_story_ids(limit: int = 75) -> list[int]:
    """Fetch top story ids and return the first `limit` ids."""
    response = SESSION.get(TOP_STORIES_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    story_ids = response.json() or []
    return story_ids[:limit]


def fetch_item(item_id: int) -> dict | None:
    """Fetch a single Hacker News item by id with retry for transient failures."""
    for attempt in range(ITEM_FETCH_RETRIES):
        try:
            response = SESSION.get(
                ITEM_ENDPOINT.format(item_id=item_id),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            if attempt == ITEM_FETCH_RETRIES - 1:
                logger.exception(
                    "Failed to fetch Hacker News item %s after %s attempts",
                    item_id,
                    ITEM_FETCH_RETRIES,
                )
                return None
            logger.warning(
                "Retrying Hacker News item fetch %s after request failure (attempt %s/%s)",
                item_id,
                attempt + 1,
                ITEM_FETCH_RETRIES,
                exc_info=True,
            )
            time.sleep(ITEM_FETCH_BACKOFF_SECONDS)

    return None


def should_process_item(item: dict | None) -> bool:
    """Return True when the HN item matches the story criteria for publishing."""
    if not item:
        return False
    if item.get("type") != "story":
        return False
    if item.get("title") is None:
        return False
    return True


def map_item(item: dict, ingest_batch_id: str) -> dict:
    """Map a Hacker News item into the raw Kafka payload schema."""
    return {
        "id": f"hn_{item['id']}",
        "source": "hackernews",
        "subreddit": None,
        "title": item.get("title", ""),
        "body": item.get("text", "") or "",
        "url": item.get("url", ""),
        "score": item.get("score", 0),
        "created_utc": float(item.get("time", 0)),
        "ingest_batch_id": ingest_batch_id,
    }


def run(ingest_batch_id: str, limit: int = 75, since: float | None = None) -> int:
    """
    Publish Hacker News top stories to Kafka raw_posts topic.
    Only fetches stories newer than `since` (Unix timestamp) if provided.
    Returns the number of messages published.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if since:
        from datetime import datetime, timezone
        logger.info("HN: fetching posts newer than %s", datetime.fromtimestamp(since, tz=timezone.utc).isoformat())
    else:
        logger.info("HN: no cutoff set, fetching latest posts")

    producer = get_kafka_producer()
    published_count = 0
    skipped_count = 0

    try:
        story_ids = fetch_story_ids(limit=500)
        for item_id in story_ids:
            if published_count >= limit:
                break

            item = fetch_item(item_id)
            if not should_process_item(item):
                continue

            assert item is not None

            if since and float(item.get("time", 0)) <= since:
                skipped_count += 1
                continue

            message = map_item(item, ingest_batch_id)

            try:
                producer.send(
                    TOPIC_NAME,
                    key=f"hn_{item['id']}".encode("utf-8"),
                    value=message,
                )
                published_count += 1
            except Exception:
                logger.exception(
                    "Failed to publish Hacker News item %s to Kafka",
                    item_id,
                )
    finally:
        producer.flush()
        producer.close()

    logger.info("Hacker News Kafka publish complete: published_total=%s skipped_old=%s", published_count, skipped_count)
    return published_count


if __name__ == "__main__":
    run("manual_batch")
