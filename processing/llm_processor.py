"""LLM classification pipeline."""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock

from llm_client import call_llm, active_provider
from processing.prompts import format_prompt
from storage import db_client
from storage.db_client import insert_failed_event


logger = logging.getLogger(__name__)
REQUIRED_KEYS = {
    "sentiment",
    "emotion",
    "topic",
    "tool_mentioned",
    "controversy_score",
    "reasoning",
}


def _parse_response(raw: str) -> dict | None:
    """Parse JSON output, strip fences, validate keys, and normalize nulls."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse response as JSON: %s", raw)
        return None

    if not isinstance(parsed, dict):
        logger.warning("Response is not a JSON object: %s", raw)
        return None

    missing_keys = [key for key in REQUIRED_KEYS if key not in parsed]
    if missing_keys:
        for key in missing_keys:
            logger.warning("Response missing required key: %s", key)
        return None

    if parsed.get("tool_mentioned") in {"null", ""}:
        parsed["tool_mentioned"] = None

    if isinstance(parsed.get("controversy_score"), str):
        try:
            parsed["controversy_score"] = int(parsed["controversy_score"])
        except ValueError:
            logger.warning("controversy_score is not an int: %s", raw)
            return None

    return parsed


def classify_post(post: dict, post_id: str) -> dict | None:
    """Classify one raw post with the LLM and return parsed structured output."""
    try:
        prompt = format_prompt(post.get("title", ""), post.get("body", ""))
        classification_provider = os.getenv("CLASSIFICATION_PROVIDER", "openrouter")
        try:
            raw_response = call_llm(prompt, max_tokens=512, temperature=0.0, provider=classification_provider)
            result = _parse_response(raw_response)
            if result is not None:
                return result
            logger.warning("Invalid classification structure from %s for post %s", active_provider(classification_provider), post_id)
        except Exception as exc:
            logger.warning("LLM call failed via %s for post %s: %s", active_provider(classification_provider), post_id, exc)

        insert_failed_event(
            event_type="classification",
            payload={"post_id": post_id, "title": post.get("title", "")[:200]},
            error_reason=f"LLM classification failed via {active_provider(classification_provider)}",
        )
        return None
    except Exception:
        logger.exception("Failed to classify post: %s", post_id)
        return None


def _process_single(post: dict, index: int, total: int, lock: Lock, counters: dict) -> None:
    """Classify a single post and persist it. Designed to run in a thread."""
    post_id = post["id"]
    post_start = time.time()

    if db_client.post_is_processed(post_id):
        with lock:
            counters["skipped"] += 1
        return

    classification = classify_post(post, post_id=post_id)
    elapsed = round(time.time() - post_start, 1)

    if classification is None:
        with lock:
            counters["failed"] += 1
        logger.warning("Post %s/%s FAILED [%.1fs]: %s", index, total, elapsed, post_id)
        return

    db_client.insert_processed_post({**classification, "post_id": post_id})
    with lock:
        counters["processed"] += 1
        done = counters["processed"] + counters["failed"] + counters["skipped"]
        if done % 10 == 0:
            logger.info(
                "Progress [%s/%s] — processed=%s failed=%s skipped=%s",
                done, total, counters["processed"], counters["failed"], counters["skipped"],
            )
    logger.info("Post %s/%s OK [%.1fs]: %s", index, total, elapsed, post_id)


def process_batch(limit: int = 100, ingest_batch_id: str | None = None, workers: int = 5):
    """Process a batch of unprocessed posts in parallel and persist valid classifications."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    posts = db_client.fetch_unprocessed_posts(limit, ingest_batch_id=ingest_batch_id)
    total = len(posts)
    counters = {"processed": 0, "failed": 0, "skipped": 0}
    lock = Lock()

    batch_start = time.time()
    logger.info(
        "===== LLM batch START: provider=%s total_posts=%s workers=%s batch_id=%s start_time=%s =====",
        active_provider(os.getenv("CLASSIFICATION_PROVIDER", "openrouter")), total, workers, ingest_batch_id, datetime.now(timezone.utc).isoformat(),
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_process_single, post, i, total, lock, counters): post
            for i, post in enumerate(posts, start=1)
        }
        for future in as_completed(futures):
            if future.exception():
                logger.exception("Unexpected error in worker: %s", future.exception())

    total_elapsed = round(time.time() - batch_start, 1)
    logger.info(
        "===== LLM batch END: processed=%s failed=%s skipped=%s total=%s duration=%.1fs end_time=%s =====",
        counters["processed"],
        counters["failed"],
        counters["skipped"],
        total,
        total_elapsed,
        datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    process_batch()
