import logging
import os
from typing import Optional

import duckdb
from fastapi import APIRouter, Depends, Query, Request

from api.auth.dependencies import get_current_user
from api.cache.redis_client import cache_get, cache_set, make_cache_key
from api.schemas import DailySentimentResponse, TrendsListResponse

logger = logging.getLogger(__name__)
router = APIRouter()
DUCKDB_PATH = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")


@router.get("/trends", response_model=TrendsListResponse, tags=["data"])
async def get_trends(
    request: Request,
    topic: str | None = Query(None),
    tool: str | None = Query(None),
    source: str | None = Query(None),
    days: int = Query(30, ge=1, le=90, description="Number of days to look back"),
    current_user: dict = Depends(get_current_user),
):
    """
    Daily sentiment aggregates from mart_daily_sentiment.
    Redis cached for 5 minutes.
    """
    cache_key = make_cache_key("trends", topic=topic, tool=tool, source=source, days=days)
    redis = request.app.state.redis

    cached = await cache_get(redis, cache_key)
    if cached:
        return TrendsListResponse(**cached)

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        # post_date is TIMESTAMP in DuckDB — cast to date for the schema.
        # Exclude updated_at (internal mart column).
        query = """
            SELECT
                post_date::date     AS post_date,
                topic,
                tool_mentioned,
                source,
                post_count,
                avg_sentiment,
                positive_count,
                negative_count,
                neutral_count,
                dominant_emotion,
                avg_controversy
            FROM mart_daily_sentiment
            WHERE post_date >= current_date - INTERVAL (?) DAY
        """
        params = [days]

        if topic:
            query += " AND topic = ?"
            params.append(topic)
        if tool:
            query += " AND tool_mentioned = ?"
            params.append(tool)
        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY post_date DESC"
        rows = conn.execute(query, params).fetchall()
        columns = [
            "post_date", "topic", "tool_mentioned", "source",
            "post_count", "avg_sentiment", "positive_count",
            "negative_count", "neutral_count", "dominant_emotion",
            "avg_controversy",
        ]
        data = [DailySentimentResponse(**dict(zip(columns, row))) for row in rows]
        conn.close()
    except Exception as e:
        logger.error(f"DuckDB trends query failed: {e}")
        data = []

    result = TrendsListResponse(data=data, total=len(data))
    await cache_set(redis, cache_key, result.model_dump())
    return result
