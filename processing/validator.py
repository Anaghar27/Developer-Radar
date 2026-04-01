"""Schema validation for raw post messages consumed from Kafka."""

import logging

logger = logging.getLogger(__name__)

VALID_SOURCES = {"reddit", "hackernews"}
MIN_BODY_LENGTH = 0
MIN_TITLE_LENGTH = 5
MAX_TITLE_LENGTH = 500
MAX_BODY_LENGTH = 50_000


def coerce_message(message: dict) -> dict:
    """
    Coerce and clean a raw message before validation.
    - Set body to "" if None
    - Strip whitespace from title
    - Ensure score defaults to 0 if missing
    - Ensure subreddit defaults to None if missing
    Returns the coerced message dict.
    """
    coerced = dict(message)
    if coerced.get("body") is None:
        coerced["body"] = ""
    if "title" in coerced and isinstance(coerced["title"], str):
        coerced["title"] = coerced["title"].strip()
    if "score" not in coerced:
        coerced["score"] = 0
    if "subreddit" not in coerced:
        coerced["subreddit"] = None
    return coerced


def validate_post(message: dict) -> tuple[bool, str]:
    """
    Validate a raw post message from Kafka.

    Returns:
        (True, "") if valid
        (False, error_reason) if invalid
    """
    for field_name in ("id", "source", "title"):
        if field_name not in message:
            error_reason = f"Missing required field: {field_name}"
            logger.warning(error_reason)
            return False, error_reason

    source = message.get("source")
    if source not in VALID_SOURCES:
        error_reason = f"Invalid source: {source!r}. Expected one of {sorted(VALID_SOURCES)}"
        logger.warning(error_reason)
        return False, error_reason

    title = message.get("title")
    if title is None or title == "":
        error_reason = "Title must not be None or empty"
        logger.warning(error_reason)
        return False, error_reason

    if not isinstance(title, str):
        error_reason = f"Title must be a string, got {type(title).__name__}"
        logger.warning(error_reason)
        return False, error_reason

    title_length = len(title)
    if title_length < MIN_TITLE_LENGTH or title_length > MAX_TITLE_LENGTH:
        error_reason = (
            f"Title length {title_length} is out of bounds "
            f"({MIN_TITLE_LENGTH} to {MAX_TITLE_LENGTH})"
        )
        logger.warning(error_reason)
        return False, error_reason

    body = message.get("body", "")
    if body is None:
        body = ""
    if not isinstance(body, str):
        error_reason = f"Body must be a string, got {type(body).__name__}"
        logger.warning(error_reason)
        return False, error_reason

    body_length = len(body)
    if body_length < MIN_BODY_LENGTH or body_length > MAX_BODY_LENGTH:
        error_reason = (
            f"Body length {body_length} exceeds allowed maximum of {MAX_BODY_LENGTH}"
        )
        logger.warning(error_reason)
        return False, error_reason

    post_id = message.get("id")
    if not isinstance(post_id, str) or post_id == "":
        error_reason = "id must be a non-empty string"
        logger.warning(error_reason)
        return False, error_reason

    if "score" in message:
        score = message.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            error_reason = f"score must be an integer or float, got {type(score).__name__}"
            logger.warning(error_reason)
            return False, error_reason

    return True, ""
