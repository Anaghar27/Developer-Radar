import logging
import os
from typing import Optional

import duckdb
from fastapi import APIRouter, Depends, Query, Request

from api.auth.dependencies import get_current_user
from api.cache.redis_client import cache_get, cache_set, make_cache_key
from api.schemas import ToolComparisonResponse, ToolsListResponse
from api.utils import duckdb_available

logger = logging.getLogger(__name__)
router = APIRouter()
DUCKDB_PATH = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")


@router.get("/tools/compare", response_model=ToolsListResponse, tags=["data"])
async def compare_tools(
    request: Request,
    tools: str | None = Query(None, description="Comma-separated tool names e.g. pytorch,tensorflow"),
    days: int = Query(30, ge=1, le=90),
    current_user: dict = Depends(get_current_user),
):
    """
    Side-by-side sentiment comparison from mart_tool_comparison.
    Redis cached for 5 minutes.
    """
    cache_key = make_cache_key("tools", tools=tools, days=days)
    redis = request.app.state.redis

    cached = await cache_get(redis, cache_key)
    if cached:
        return ToolsListResponse(**cached)

    if not duckdb_available():
        logger.warning("DuckDB not available — returning empty response")
        return ToolsListResponse(data=[], tools=[])

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        # post_date is TIMESTAMP in DuckDB — cast to date for the schema.
        # Column order in mart: post_date, tool, source, post_count,
        # avg_sentiment, avg_controversy, positive_count, negative_count,
        # neutral_count, updated_at — select explicitly to match schema order.
        query = """
            SELECT
                post_date::date     AS post_date,
                tool,
                source,
                post_count,
                avg_sentiment,
                positive_count,
                negative_count,
                neutral_count,
                avg_controversy
            FROM mart_tool_comparison
            WHERE post_date >= current_date - INTERVAL (?) DAY
        """
        params = [days]

        tool_list = []
        if tools:
            tool_list = [t.strip() for t in tools.split(",") if t.strip()]
            placeholders = ",".join(["?" for _ in tool_list])
            query += f" AND tool IN ({placeholders})"
            params.extend(tool_list)

        query += " ORDER BY post_date DESC, tool"
        rows = conn.execute(query, params).fetchall()
        columns = [
            "post_date", "tool", "source", "post_count",
            "avg_sentiment", "positive_count", "negative_count",
            "neutral_count", "avg_controversy",
        ]
        data = [ToolComparisonResponse(**dict(zip(columns, row))) for row in rows]
        conn.close()

        unique_tools = list({row.tool for row in data})

    except Exception as e:
        logger.error(f"DuckDB tools query failed: {e}")
        data = []
        unique_tools = []

    result = ToolsListResponse(data=data, tools=unique_tools)
    await cache_set(redis, cache_key, result.model_dump())
    return result
