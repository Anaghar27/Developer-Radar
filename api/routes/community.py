from fastapi import APIRouter, Depends, Request, Query
from typing import Optional
from api.schemas import CommunityListResponse, CommunityDivergenceResponse
from api.auth.dependencies import get_current_user
from api.cache.redis_client import cache_get, cache_set, make_cache_key
import duckdb, os, logging

logger = logging.getLogger(__name__)
router = APIRouter()
DUCKDB_PATH = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")


@router.get("/community/divergence", response_model=CommunityListResponse, tags=["data"])
async def get_community_divergence(
    request: Request,
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days: int = Query(30, ge=1, le=90),
    current_user: dict = Depends(get_current_user),
):
    """
    Reddit vs HN sentiment delta per topic per day.
    From mart_community_divergence. Redis cached 5 minutes.
    """
    cache_key = make_cache_key("community", topic=topic, days=days)
    redis = request.app.state.redis

    cached = await cache_get(redis, cache_key)
    if cached:
        return CommunityListResponse(**cached)

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        # post_date is TIMESTAMP — cast to date. Exclude updated_at.
        query = """
            SELECT
                post_date::date     AS post_date,
                topic,
                reddit_sentiment,
                hn_sentiment,
                reddit_count,
                hn_count,
                sentiment_delta
            FROM mart_community_divergence
            WHERE post_date >= current_date - INTERVAL (?) DAY
        """
        params = [days]

        if topic:
            query += " AND topic = ?"
            params.append(topic)

        query += " ORDER BY post_date DESC, ABS(sentiment_delta) DESC"
        rows = conn.execute(query, params).fetchall()
        columns = [
            "post_date", "topic",
            "reddit_sentiment", "hn_sentiment",
            "reddit_count", "hn_count", "sentiment_delta",
        ]
        data = [CommunityDivergenceResponse(**dict(zip(columns, row))) for row in rows]
        conn.close()
    except Exception as e:
        logger.error(f"DuckDB community query failed: {e}")
        data = []

    result = CommunityListResponse(data=data)
    await cache_set(redis, cache_key, result.model_dump())
    return result
