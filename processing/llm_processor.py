"""LLM classification pipeline using the Groq API."""

import json
import logging
import os
import re
import time

from groq import APITimeoutError, Groq, RateLimitError

from processing.prompts import format_prompt
from storage import db_client


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


def _call_groq(prompt: str) -> str:
    """Send a prompt to Groq and return the raw response text with retry/backoff."""
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    delays = [2, 4, 8]

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            content = response.choices[0].message.content
            return content or ""
        except (RateLimitError, APITimeoutError):
            logger.warning("Groq request failed on attempt %s/3", attempt + 1, exc_info=True)
            if attempt == 2:
                raise
            time.sleep(delays[attempt])

    raise RuntimeError("Groq request failed after retries")


def _parse_response(raw: str) -> dict | None:
    """Parse Groq JSON output, strip fences, validate keys, and normalize nulls."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Groq response as JSON: %s", raw)
        return None

    if not isinstance(parsed, dict):
        logger.warning("Groq response is not a JSON object: %s", raw)
        return None

    missing_keys = [key for key in REQUIRED_KEYS if key not in parsed]
    if missing_keys:
        for key in missing_keys:
            logger.warning("Groq response missing required key: %s", key)
        return None

    if parsed.get("tool_mentioned") in {"null", ""}:
        parsed["tool_mentioned"] = None

    if isinstance(parsed.get("controversy_score"), str):
        try:
            parsed["controversy_score"] = int(parsed["controversy_score"])
        except ValueError:
            logger.warning("Groq controversy_score is not an int: %s", raw)
            return None

    return parsed


def classify_post(post: dict) -> dict | None:
    """Classify one raw post with the LLM and return parsed structured output."""
    try:
        prompt = format_prompt(post.get("title", ""), post.get("body", ""))
        raw_response = _call_groq(prompt)
        return _parse_response(raw_response)
    except Exception:
        logger.exception("Failed to classify post: %s", post.get("id"))
        return None


def process_batch(limit: int = 100):
    """Process a batch of unprocessed posts and persist valid classifications."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    posts = db_client.fetch_unprocessed_posts(limit)
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    for post in posts:
        post_id = post["id"]
        if db_client.post_is_processed(post_id):
            skipped_count += 1
            continue

        classification = classify_post(post)
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
