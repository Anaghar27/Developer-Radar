"""Hacker News ingestion for the developer sentiment intelligence pipeline."""

import logging
import time
from datetime import UTC, datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from storage.db_client import insert_raw_post, post_exists

logger = logging.getLogger(__name__)

BASE_URL = "https://hacker-news.firebaseio.com/v0"
STORY_FEEDS = {
    "topstories": f"{BASE_URL}/topstories.json",
    "newstories": f"{BASE_URL}/newstories.json",
    "askstories": f"{BASE_URL}/askstories.json",
}
ITEM_ENDPOINT = f"{BASE_URL}/item/{{item_id}}.json"
ITEM_FETCH_RETRIES = 3
ITEM_FETCH_BACKOFF_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 10


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


def fetch_story_ids(feed_name: str, limit: int = 2500) -> list[int]:
    """Fetch story ids for one Hacker News feed and return the first `limit` ids."""
    response = SESSION.get(STORY_FEEDS[feed_name], timeout=REQUEST_TIMEOUT_SECONDS)
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
                raise
            logger.warning(
                "Retrying Hacker News item fetch %s after request failure (attempt %s/%s)",
                item_id,
                attempt + 1,
                ITEM_FETCH_RETRIES,
                exc_info=True,
            )
            time.sleep(ITEM_FETCH_BACKOFF_SECONDS * (attempt + 1))

    return None


def should_process_item(item: dict | None) -> bool:
    """Return True when the HN item matches the story criteria for ingestion."""
    if not item:
        return False
    if item.get("type") != "story":
        return False
    if item.get("title") is None:
        return False
    return bool(item.get("url") or item.get("text"))


def map_item(item: dict) -> dict:
    """Map a Hacker News item into the raw_posts schema."""
    return {
        "id": f"hn_{item['id']}",
        "source": "hackernews",
        "title": item.get("title", ""),
        "body": item.get("text", "") or "",
        "url": item.get("url", ""),
        "score": item.get("score", 0),
        "created_at": datetime.fromtimestamp(item["time"], UTC),
    }


def run() -> None:
    """Fetch Hacker News stories from multiple feeds and insert eligible items."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    fetched_count = 0
    new_count = 0
    story_ids: list[int] = []
    seen_ids: set[int] = set()

    for feed_name in STORY_FEEDS:
        try:
            feed_ids = fetch_story_ids(feed_name, limit=2500)
        except requests.exceptions.RequestException:
            logger.exception("Failed to fetch Hacker News feed: %s", feed_name)
            continue

        for item_id in feed_ids:
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                story_ids.append(item_id)

    for item_id in story_ids:
        try:
            item = fetch_item(item_id)
        except requests.exceptions.RequestException:
            logger.warning("Failed to fetch Hacker News item %s", item_id, exc_info=True)
            time.sleep(0.1)
            continue

        if not should_process_item(item):
            time.sleep(0.1)
            continue

        post = map_item(item)
        fetched_count += 1
        if not post_exists(post["id"]):
            new_count += 1
        insert_raw_post(post)
        time.sleep(0.1)

    logger.info(
        "Hacker News ingestion complete: feeds=%s fetched=%s new=%s duplicates=%s",
        ",".join(STORY_FEEDS.keys()),
        fetched_count,
        new_count,
        fetched_count - new_count,
    )


if __name__ == "__main__":
    run()
