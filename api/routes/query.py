import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth.dependencies import get_current_user
from api.cache.redis_client import RAG_TTL, cache_get, cache_set
from api.schemas import QueryRequest, QueryResponse
from rag.corrective_rag import make_query_hash, run_corrective_rag
from storage.db_client import insert_insight_report

_FAILED_REPORT_PREFIXES = (
    "Insight generation failed",
    "No relevant posts",
    "Rate limit",
    "Provider returned error",
)


def _is_failed_report(report: str) -> bool:
    return any(report.startswith(p) for p in _FAILED_REPORT_PREFIXES)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse, tags=["rag"])
async def query_insights(
    body: QueryRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Natural language query → Corrective RAG → grounded insight report.

    Pipeline:
    1. Check Redis cache (1 hour TTL per query hash)
    2. If cache miss: hybrid retrieval → relevance grading → reranking → generation
    3. Store report in PostgreSQL insight_reports table
    4. Cache result in Redis

    Note: First call for a query takes 15-60s. Subsequent calls return instantly from cache.
    """
    redis = request.app.state.redis
    cache_key = f"devpulse:rag:v2:{make_query_hash(body.query)}"

    # ── Step 1: Cache hit ──────────────────────────────────────────────────────
    cached = await cache_get(redis, cache_key)
    if cached:
        if _is_failed_report(cached.get("report", "")):
            logger.warning("Stale failed report found in cache — evicting and re-running pipeline")
            await redis.delete(cache_key)
        else:
            logger.info(f"RAG cache hit for query: '{body.query[:60]}'")
            cached["cached"] = True
            return QueryResponse(**cached)

    # ── Step 2: Cache miss — run pipeline in thread pool ──────────────────────
    logger.info(f"RAG cache miss — running pipeline for: '{body.query[:60]}'")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_corrective_rag(body.query, limit=body.limit),
        )
    except Exception as e:
        logger.error(f"Corrective RAG pipeline failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"RAG pipeline error: {str(e)}",
        )

    report = result["report"]
    report_failed = _is_failed_report(report)

    # ── Step 3: Persist to PostgreSQL — only on success ───────────────────────
    if not report_failed:
        try:
            insert_insight_report(
                query=body.query,
                report_text=report,
                sources=result["sources_used"],
            )
        except Exception as e:
            logger.warning(f"Failed to persist insight report: {e}")
    else:
        logger.warning("Skipping DB persist — report indicates failure: %s", report[:120])

    # ── Step 4: Cache and return — only cache successful reports ──────────────
    payload = {
        "query": result["query"],
        "report": report,
        "sources_used": result["sources_used"],
        "generated_at": result["generated_at"].isoformat()
        if isinstance(result["generated_at"], datetime)
        else result["generated_at"],
        "cached": False,
    }
    if not report_failed:
        await cache_set(redis, cache_key, payload, ttl=RAG_TTL)
    else:
        logger.warning("Skipping Redis cache — report indicates failure, will retry on next request")

    return QueryResponse(**payload)
