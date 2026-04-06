import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from api.auth.dependencies import get_current_user
from api.cache.redis_client import cache_get, cache_set, make_cache_key
from api.schemas import PostResponse, PostsListResponse
from api.utils import duckdb_available

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/posts", response_model=PostsListResponse, tags=["data"])
async def get_posts(
    request: Request,
    source: str | None = Query(None, description="Filter by source: reddit or hackernews"),
    topic: str | None = Query(None, description="Filter by topic"),
    tool: str | None = Query(None, description="Filter by tool_mentioned"),
    sentiment: str | None = Query(None, description="Filter by sentiment"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0, description="Number of posts to skip for pagination"),
    current_user: dict = Depends(get_current_user),
):
    """
    Return recent posts with classification labels.
    Filters: source, topic, tool, sentiment.
    Redis cached for 5 minutes.
    Mirrors int_posts_enriched: raw_posts LEFT JOIN processed_posts.
    """
    cache_key = make_cache_key("posts_v2", source=source, topic=topic, tool=tool, sentiment=sentiment, limit=limit, offset=offset)
    redis = request.app.state.redis

    cached = await cache_get(redis, cache_key)
    if cached:
        return PostsListResponse(**cached)

    if not duckdb_available():
        logger.warning("DuckDB not available — returning empty response")
        return PostsListResponse(posts=[], total=0, limit=limit)

    try:
        pool = request.app.state.db_pool
        if pool is None:
            raise RuntimeError("Database unavailable")

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
                CASE
                    WHEN p.sentiment IN ('positive', 'negative', 'neutral')
                        THEN p.sentiment
                    ELSE 'neutral'
                END                     AS sentiment,
                CASE
                    WHEN p.emotion IN ('excited', 'frustrated', 'skeptical', 'curious', 'hopeful', 'neutral')
                        THEN p.emotion
                    ELSE 'neutral'
                END                     AS emotion,
                CASE
                    WHEN p.topic IN ('LLM', 'Agents', 'RAG', 'MLOps', 'Python', 'WebDev', 'DevTools', 'Cloud', 'Hardware', 'Security', 'Career', 'OpenSource', 'Other')
                        THEN p.topic
                    ELSE 'Other'
                END                     AS topic,
                NULLIF(trim(p.tool_mentioned), '') AS tool_mentioned,
                CASE
                    WHEN p.controversy_score < 0 THEN 0.0
                    WHEN p.controversy_score > 1 THEN 1.0
                    ELSE COALESCE(p.controversy_score, 0.0)
                END                     AS controversy_score,
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
            "SELECT\n                r.id::text              AS post_id,\n                r.source,\n                NULL::text              AS subreddit,\n                r.title,\n                r.url,\n                COALESCE(r.score, 0)    AS score,\n                CASE\n                    WHEN p.sentiment IN ('positive', 'negative', 'neutral')\n                        THEN p.sentiment\n                    ELSE 'neutral'\n                END                     AS sentiment,\n                CASE\n                    WHEN p.emotion IN ('excited', 'frustrated', 'skeptical', 'curious', 'hopeful', 'neutral')\n                        THEN p.emotion\n                    ELSE 'neutral'\n                END                     AS emotion,\n                CASE\n                    WHEN p.topic IN ('LLM', 'Agents', 'RAG', 'MLOps', 'Python', 'WebDev', 'DevTools', 'Cloud', 'Hardware', 'Security', 'Career', 'OpenSource', 'Other')\n                        THEN p.topic\n                    ELSE 'Other'\n                END                     AS topic,\n                NULLIF(trim(p.tool_mentioned), '') AS tool_mentioned,\n                CASE\n                    WHEN p.controversy_score < 0 THEN 0.0\n                    WHEN p.controversy_score > 1 THEN 1.0\n                    ELSE COALESCE(p.controversy_score, 0.0)\n                END                     AS controversy_score,\n                r.created_at::date      AS post_date,\n                r.created_at            AS created_at_utc",
            "SELECT COUNT(*)"
        )
        total_row = await pool.fetchrow(count_query, *params)
        total = total_row[0] if total_row else 0

        query += f" ORDER BY r.created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
        params.append(limit)
        params.append(offset)

        rows = await pool.fetch(query, *params)
        posts = [PostResponse(**dict(row)) for row in rows]

    except Exception as e:
        logger.error(f"Posts query failed: {e}")
        posts = []
        total = 0

    has_more = (offset + limit) < total
    next_offset = (offset + limit) if has_more else None
    result = PostsListResponse(
        posts=posts,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
        next_offset=next_offset,
    )
    await cache_set(redis, cache_key, result.model_dump())
    return result
