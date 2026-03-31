import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth.dependencies import get_current_user
from api.cache.redis_client import RAG_TTL, cache_get, cache_set
from api.schemas import QueryRequest, QueryResponse
from rag.corrective_rag import make_query_hash, run_corrective_rag
from storage.db_client import insert_insight_report

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
    cache_key = f"devpulse:rag:{make_query_hash(body.query)}"

    # ── Step 1: Cache hit ──────────────────────────────────────────────────────
    cached = await cache_get(redis, cache_key)
    if cached:
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

    # ── Step 3: Persist to PostgreSQL (non-fatal) ──────────────────────────────
    try:
        insert_insight_report(
            query=body.query,
            report_text=result["report"],
            sources=result["sources_used"],
        )
    except Exception as e:
        logger.warning(f"Failed to persist insight report: {e}")

    # ── Step 4: Cache and return ───────────────────────────────────────────────
    payload = {
        "query": result["query"],
        "report": result["report"],
        "sources_used": result["sources_used"],
        "generated_at": result["generated_at"].isoformat()
        if isinstance(result["generated_at"], datetime)
        else result["generated_at"],
        "cached": False,
    }
    await cache_set(redis, cache_key, payload, ttl=RAG_TTL)

    return QueryResponse(**payload)
