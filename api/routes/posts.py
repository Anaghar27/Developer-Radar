import logging
import os

import duckdb
from fastapi import APIRouter, Depends, Query, Request

from api.auth.dependencies import get_current_user
from api.cache.redis_client import cache_get, cache_set, make_cache_key
from api.schemas import PostResponse, PostsListResponse
from api.utils import duckdb_available

logger = logging.getLogger(__name__)
router = APIRouter()
DUCKDB_PATH = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")


def _build_posts_filters(
    source: str | None = None,
    topic: str | None = None,
    tool: str | None = None,
    sentiment: str | None = None,
) -> tuple[str, list]:
    """
    Build WHERE clause and params for posts queries.
    Returns (where_clause, params) tuple.
    Both the data query and count query use the same output.
    """
    conditions = ["1=1"]
    params = []

    if source:
        conditions.append("source = ?")
        params.append(source)
    if topic:
        conditions.append("topic = ?")
        params.append(topic)
    if tool:
        conditions.append("tool_mentioned = ?")
        params.append(tool)
    if sentiment:
        conditions.append("sentiment = ?")
        params.append(sentiment)

    where_clause = " AND ".join(conditions)
    return where_clause, params


@router.get("/posts", response_model=PostsListResponse, tags=["data"])
async def get_posts(
    request: Request,
    source: str | None = Query(None, description="Filter by source: reddit or hackernews"),
    topic: str | None = Query(None, description="Filter by topic"),
    tool: str | None = Query(None, description="Filter by tool_mentioned"),
    sentiment: str | None = Query(None, description="Filter by sentiment"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, description="Number of posts to skip for pagination"),
    current_user: dict = Depends(get_current_user),
):
    """
    Return recent posts with classification labels.
    Filters: source, topic, tool, sentiment.
    Redis cached for 5 minutes via int_posts_enriched in DuckDB.
    """
    cache_key = make_cache_key(
        "posts",
        source=source,
        topic=topic,
        tool=tool,
        sentiment=sentiment,
        limit=limit,
        offset=offset,
    )
    redis = request.app.state.redis

    cached = await cache_get(redis, cache_key)
    if cached:
        return PostsListResponse(**cached)

    if not duckdb_available():
        logger.warning("DuckDB not available — returning empty response")
        return PostsListResponse(
            posts=[],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
            next_offset=None,
        )

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        where_clause, filter_params = _build_posts_filters(
            source=source,
            topic=topic,
            tool=tool,
            sentiment=sentiment,
        )

        count_sql = f"""
            SELECT COUNT(*)
            FROM int_posts_enriched
            WHERE {where_clause}
        """
        total_count = conn.execute(count_sql, filter_params).fetchone()[0]

        data_sql = f"""
            SELECT
                post_id, source, subreddit, title, url, score,
                sentiment, emotion, topic, tool_mentioned,
                controversy_score, post_date, created_at_utc
            FROM int_posts_enriched
            WHERE {where_clause}
            ORDER BY created_at_utc DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(data_sql, filter_params + [limit, offset]).fetchall()

        columns = [
            "post_id", "source", "subreddit", "title", "url", "score",
            "sentiment", "emotion", "topic", "tool_mentioned",
            "controversy_score", "post_date", "created_at_utc",
        ]
        posts = [PostResponse(**dict(zip(columns, row))) for row in rows]
        conn.close()
    except Exception as e:
        logger.error(f"DuckDB posts query failed: {e}")
        posts = []
        total_count = 0

    has_more = (offset + limit) < total_count
    next_offset = (offset + limit) if has_more else None
    result = PostsListResponse(
        posts=posts,
        total=total_count,
        limit=limit,
        offset=offset,
        has_more=has_more,
        next_offset=next_offset,
    )
    await cache_set(redis, cache_key, result.model_dump())
    return result
