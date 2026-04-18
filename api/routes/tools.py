import logging
import os
from datetime import UTC, datetime
from typing import Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth.dependencies import get_current_user
from api.cache.redis_client import cache_get, cache_set, make_cache_key
from api.rate_limit import limiter
from api.schemas import (
    DataWindowResponse,
    ToolComparisonResponse,
    ToolReportRequest,
    ToolReportResponse,
    ToolStatSummary,
    ToolsListResponse,
)
from api.utils import duckdb_available
from processing.llm_client import OPENAI_DEFAULT_MODEL, call_llm

logger = logging.getLogger(__name__)
router = APIRouter()
DUCKDB_PATH = os.getenv("DBT_DUCKDB_PATH", "transform/developer_radar.duckdb")


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


@router.get("/tools/window", response_model=DataWindowResponse, tags=["data"])
async def get_tools_window(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Return the available tool-comparison date window for dashboard lookback controls."""
    cache_key = make_cache_key("tools_window")
    redis = request.app.state.redis

    cached = await cache_get(redis, cache_key)
    if cached:
        return DataWindowResponse(**cached)

    if not duckdb_available():
        return DataWindowResponse(
            earliest_post_date=None,
            latest_post_date=None,
            max_lookback_days=1,
        )

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        earliest_post_date, latest_post_date = conn.execute(
            """
            SELECT
                MIN(post_date)::date AS earliest_post_date,
                MAX(post_date)::date AS latest_post_date
            FROM mart_tool_comparison
            """
        ).fetchone()
        conn.close()

        if earliest_post_date is None or latest_post_date is None:
            result = DataWindowResponse(
                earliest_post_date=None,
                latest_post_date=None,
                max_lookback_days=1,
            )
        else:
            result = DataWindowResponse(
                earliest_post_date=earliest_post_date,
                latest_post_date=latest_post_date,
                max_lookback_days=max(1, (latest_post_date - earliest_post_date).days + 1),
            )
    except Exception as e:
        logger.error(f"DuckDB tools window query failed: {e}")
        result = DataWindowResponse(
            earliest_post_date=None,
            latest_post_date=None,
            max_lookback_days=1,
        )

    await cache_set(redis, cache_key, result.model_dump())
    return result


@router.post("/tools/report", response_model=ToolReportResponse, tags=["data"])
@limiter.limit("5/minute")
async def generate_tool_report(
    request: Request,
    body: ToolReportRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Generate a plain-English tool decision report from community sentiment data.
    Queries mart_tool_comparison in DuckDB, then calls the OpenAI LLM.
    Rate-limited to 5 requests/minute per IP.
    """
    del request, current_user
    tools = list({t.strip().lower() for t in body.tools if t.strip()})

    if not duckdb_available():
        raise HTTPException(status_code=503, detail="DuckDB unavailable")

    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        placeholders = ",".join(["?" for _ in tools])
        query = f"""
            SELECT
                tool,
                SUM(post_count)                                          AS total_posts,
                AVG(avg_sentiment)                                       AS avg_sentiment,
                SUM(positive_count) * 100.0 / NULLIF(SUM(post_count), 0) AS positive_pct,
                AVG(avg_controversy)                                     AS avg_controversy
            FROM mart_tool_comparison
            WHERE post_date >= current_date - INTERVAL (?) DAY
              AND tool IN ({placeholders})
            GROUP BY tool
            ORDER BY total_posts DESC
        """
        rows = conn.execute(query, [body.days] + tools).fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"DuckDB tool report query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to query tool data")

    if not rows:
        raise HTTPException(
            status_code=422,
            detail=f"No data found for {tools} in the last {body.days} days.",
        )

    stats = [
        ToolStatSummary(
            tool=row[0],
            total_posts=int(row[1] or 0),
            avg_sentiment=round(float(row[2] or 0), 4),
            positive_pct=round(float(row[3] or 0), 1),
            avg_controversy=round(float(row[4] or 0), 4),
        )
        for row in rows
    ]

    tool_lines = "\n".join(
        f"  - {s.tool}: {s.total_posts} posts, avg_sentiment={s.avg_sentiment:.3f} "
        f"(−1 negative → +1 positive), positive_rate={s.positive_pct:.1f}%, "
        f"avg_controversy={s.avg_controversy:.3f}"
        for s in stats
    )
    context_line = f"\nUser context: {body.context}" if body.context else ""

    prompt = f"""You are a developer tooling analyst. Write a concise tool decision report (max 250 words).

Tools: {', '.join(s.tool for s in stats)}
Time window: last {body.days} days{context_line}

Community sentiment data:
{tool_lines}

Structure:
1. Recommendation (1 sentence)
2. Per-tool summary (2 sentences each)
3. Caveats (1–2 sentences)

    Write for a senior developer audience. Be direct."""

    try:
        narrative = call_llm(
            prompt,
            provider="openai",
            model=OPENAI_DEFAULT_MODEL,
            max_tokens=600,
        )
    except Exception as e:
        logger.error(f"LLM call failed for tool report: {e}")
        raise HTTPException(status_code=502, detail="LLM call failed — try again shortly")

    return ToolReportResponse(
        tools=[s.tool for s in stats],
        days=body.days,
        stats_summary=stats,
        narrative=narrative,
        generated_at=datetime.now(UTC).isoformat(),
        model_used=OPENAI_DEFAULT_MODEL,
    )
