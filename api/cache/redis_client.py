import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_TTL = 300       # 5 minutes for data endpoints
RAG_TTL = 3600          # 1 hour for RAG query results


# ── Connection lifecycle ──────────────────────────────────────────────────────

async def init_redis(app) -> None:
    """Create Redis connection and attach to app state."""
    app.state.redis = aioredis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    # Test connection
    await app.state.redis.ping()
    logger.info(f"Redis connected at {REDIS_URL}")


async def close_redis(app) -> None:
    """Close Redis connection on shutdown."""
    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()
        logger.info("Redis connection closed")


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def cache_get(redis, key: str) -> Optional[Any]:
    """
    Get a value from Redis cache.
    Returns deserialized Python object or None if not found.
    """
    try:
        value = await redis.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        logger.warning(f"Cache get failed for key {key}: {e}")
        return None


async def cache_set(redis, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """
    Set a value in Redis cache with TTL.
    Serializes Python object to JSON.
    """
    try:
        await redis.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logger.warning(f"Cache set failed for key {key}: {e}")


async def cache_invalidate_pattern(redis, pattern: str) -> int:
    """
    Delete all keys matching a pattern.
    Returns number of keys deleted.
    Used by Airflow after dbt runs.
    """
    try:
        keys = await redis.keys(pattern)
        if not keys:
            return 0
        deleted = await redis.delete(*keys)
        logger.info(f"Cache invalidated {deleted} keys matching '{pattern}'")
        return deleted
    except Exception as e:
        logger.warning(f"Cache invalidation failed for pattern {pattern}: {e}")
        return 0


async def cache_invalidate_all(redis) -> int:
    """Delete all DevPulse cache keys. Called after dbt run."""
    return await cache_invalidate_pattern(redis, "devpulse:*")


# ── Cache key builders ────────────────────────────────────────────────────────

def make_cache_key(prefix: str, **kwargs) -> str:
    """
    Build a consistent cache key from prefix and query params.
    Example: make_cache_key("trends", topic="ml", source="reddit")
    → "devpulse:trends:source=reddit:topic=ml"
    """
    parts = [f"devpulse:{prefix}"]
    for k, v in sorted(kwargs.items()):
        if v is not None:
            parts.append(f"{k}={v}")
    return ":".join(parts)
