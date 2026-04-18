"""
Admin routes — restricted to internal services OR users with is_admin=True.
Regular authenticated users are always rejected with 403.

Two access paths per endpoint:
  GET /admin/llm-stats      → X-API-Key header (Airflow, CI, scripts)
  GET /admin/me/llm-stats   → JWT bearer with is_admin=True (dashboard tab)
"""
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth.dependencies import require_admin_user, require_api_key
from api.schemas import LLMStatsResponse
from rag.llm_tracker import get_stats, reset_stats
from storage.db_client import fetch_llm_stats, reset_llm_stats

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_stats_response(do_reset: bool) -> LLMStatsResponse:
    try:
        stats = fetch_llm_stats()
        if do_reset:
            reset_llm_stats()
            logger.info("[ADMIN] Durable LLM stats reset")
    except Exception:
        logger.exception("Failed to read durable llm stats; falling back to in-memory tracker")
        stats = get_stats()
        if do_reset:
            reset_stats()
            logger.info("[ADMIN] In-memory LLM stats reset")

    snapshot_at = datetime.now(UTC).isoformat()
    return LLMStatsResponse(
        total_calls=stats["total_calls"],
        total_cost_usd=stats["total_cost_usd"],
        success_rate=stats["success_rate"],
        avg_latency_ms=stats["avg_latency_ms"],
        by_operation=stats["by_operation"],
        by_provider=stats["by_provider"],
        snapshot_taken_at=snapshot_at,
    )


def _read_latest_digest() -> dict:
    digests_dir = Path(__file__).resolve().parent.parent.parent / "artifacts" / "weekly_digests"
    if not digests_dir.exists():
        raise HTTPException(status_code=404, detail="No weekly digests found")
    files = sorted(digests_dir.glob("digest_*.json"), reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="No weekly digests found")
    return json.loads(files[0].read_text())


# ── Machine-to-machine (X-API-Key) ────────────────────────────────────────────

@router.get("/llm-stats", response_model=LLMStatsResponse, tags=["admin"])
async def get_llm_stats_internal(
    reset: bool = Query(False),
    _key: str = Depends(require_api_key),
):
    """LLM stats for internal services. Auth: X-API-Key header."""
    return _build_stats_response(reset)


@router.get("/weekly-digest", tags=["admin"])
async def get_weekly_digest_internal(_key: str = Depends(require_api_key)):
    """Latest weekly digest JSON. Auth: X-API-Key header."""
    return _read_latest_digest()


# ── Human admin (JWT + is_admin=True) ─────────────────────────────────────────

@router.get("/me/llm-stats", response_model=LLMStatsResponse, tags=["admin"])
async def get_llm_stats_admin(
    reset: bool = Query(False),
    current_user: dict = Depends(require_admin_user),
):
    """LLM stats for admin dashboard. Auth: JWT with is_admin=True."""
    return _build_stats_response(reset)


@router.get("/me/weekly-digest", tags=["admin"])
async def get_weekly_digest_admin(current_user: dict = Depends(require_admin_user)):
    """Latest weekly digest JSON. Auth: JWT with is_admin=True."""
    return _read_latest_digest()
