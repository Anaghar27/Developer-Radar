from fastapi import APIRouter, Depends, Request, Query
from typing import Optional
from api.schemas import PostsListResponse, PostResponse
from api.auth.dependencies import get_current_user
from api.cache.redis_client import cache_get, cache_set, make_cache_key
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/posts", response_model=PostsListResponse, tags=["data"])
async def get_posts(
    request: Request,
    source: Optional[str] = Query(None, description="Filter by source: reddit or hackernews"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    tool: Optional[str] = Query(None, description="Filter by tool_mentioned"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment"),
    limit: int = Query(50, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """
    Return recent posts with classification labels.
    Filters: source, topic, tool, sentiment.
    Redis cached for 5 minutes.
    Mirrors int_posts_enriched: raw_posts LEFT JOIN processed_posts.
    """
    cache_key = make_cache_key("posts", source=source, topic=topic, tool=tool, sentiment=sentiment, limit=limit)
    redis = request.app.state.redis

    cached = await cache_get(redis, cache_key)
    if cached:
        return PostsListResponse(**cached)

    try:
        pool = request.app.state.db_pool

        # Mirror int_posts_enriched: raw_posts LEFT JOIN processed_posts
        # raw_posts uses: id, source, title, url, score, created_at, ingest_batch_id
        # processed_posts joins on: post_id (= raw_posts.id)
        query = """
            SELECT
                r.id::text              AS post_id,
                r.source,
                NULL::text              AS subreddit,
                r.title,
                r.url,
                COALESCE(r.score, 0)    AS score,
                p.sentiment,
                p.emotion,
                p.topic,
                p.tool_mentioned,
                p.controversy_score,
                r.created_at::date      AS post_date,
                r.created_at            AS created_at_utc
            FROM raw_posts r
            LEFT JOIN processed_posts p ON r.id = p.post_id
            WHERE r.title IS NOT NULL AND trim(r.title) != ''
        """
        params = []
        idx = 1

        if source:
            query += f" AND r.source = ${idx}"
            params.append(source)
            idx += 1
        if topic:
            query += f" AND p.topic = ${idx}"
            params.append(topic)
            idx += 1
        if tool:
            query += f" AND p.tool_mentioned = ${idx}"
            params.append(tool)
            idx += 1
        if sentiment:
            query += f" AND p.sentiment = ${idx}"
            params.append(sentiment)
            idx += 1

        count_query = query.replace(
            "SELECT\n                r.id::text              AS post_id,\n                r.source,\n                NULL::text              AS subreddit,\n                r.title,\n                r.url,\n                COALESCE(r.score, 0)    AS score,\n                p.sentiment,\n                p.emotion,\n                p.topic,\n                p.tool_mentioned,\n                p.controversy_score,\n                r.created_at::date      AS post_date,\n                r.created_at            AS created_at_utc",
            "SELECT COUNT(*)"
        )
        total_row = await pool.fetchrow(count_query, *params)
        total = total_row[0] if total_row else 0

        query += f" ORDER BY r.created_at DESC LIMIT ${idx}"
        params.append(limit)

        rows = await pool.fetch(query, *params)
        posts = [PostResponse(**dict(row)) for row in rows]

    except Exception as e:
        logger.error(f"Posts query failed: {e}")
        posts = []
        total = 0

    result = PostsListResponse(posts=posts, total=total, limit=limit)
    await cache_set(redis, cache_key, result.model_dump())
    return result
