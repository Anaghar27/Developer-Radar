"""LLM classification pipeline."""

import json
import logging
import os
import re
import time

import requests

from processing.prompts import format_prompt
from storage import db_client
from storage.db_client import insert_failed_event


MODELS = [
    "nvidia/llama-3.1-nemotron-ultra-253b-v1:free",
    "stepfun-ai/step-3-5-flash",
    "nvidia/llama-3.1-nemotron-nano-8b-instruct:free",
]
logger = logging.getLogger(__name__)
MODEL_NAME = "llama-3.1-8b-instant"
REQUIRED_KEYS = {
    "sentiment",
    "emotion",
    "topic",
    "tool_mentioned",
    "controversy_score",
    "reasoning",
}


def call_openrouter(prompt: str, model: str | None = None) -> str:
    """Send a prompt and return the raw response text with retry/backoff."""
    delays = [2, 4, 8]
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or os.environ.get("OPENROUTER_MODEL", MODEL_NAME),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }

    for attempt in range(3):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return content or ""
        except requests.RequestException:
            logger.warning("LLM request failed on attempt %s/3", attempt + 1, exc_info=True)
            if attempt == 2:
                raise
            time.sleep(delays[attempt])

    raise RuntimeError("LLM request failed after retries")


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
        last_exception = None
        for attempt, model in enumerate(MODELS):
            try:
                raw_response = call_openrouter(prompt, model=model)
                return _parse_response(raw_response)
            except Exception as exc:
                last_exception = exc
                logging.warning(f"Attempt {attempt + 1} failed with model {model}: {exc}")
                continue
        insert_failed_event(
            event_type="classification",
            payload={"post_id": post_id, "title": post.get("title", "")[:200]},
            error_reason=f"All 3 models failed. Last error: {str(last_exception)}",
        )
        return None
    except Exception:
        logger.exception("Failed to classify post: %s", post_id)
        return None


def process_batch(limit: int = 100, ingest_batch_id: str | None = None):
    """Process a batch of unprocessed posts and persist valid classifications."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    posts = db_client.fetch_unprocessed_posts(limit, ingest_batch_id=ingest_batch_id)
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    for post in posts:
        post_id = post["id"]
        if db_client.post_is_processed(post_id):
            skipped_count += 1
            continue

        classification = classify_post(post, post_id=post["id"])
        if classification is None:
            failed_count += 1
            logger.warning("Skipping post after classification failure: %s", post_id)
            continue

        payload = {**classification, "post_id": post_id}
        db_client.insert_processed_post(payload)
        processed_count += 1

    logger.info(
        "LLM batch complete: processed=%s skipped=%s failed=%s total=%s",
        processed_count,
        skipped_count,
        failed_count,
        len(posts),
    )


if __name__ == "__main__":
    process_batch()
