from fastapi import APIRouter, Depends, Request
from api.schemas import CacheInvalidateResponse
from api.auth.dependencies import require_api_key
from api.cache.redis_client import cache_invalidate_all

router = APIRouter()


@router.post(
    "/cache/invalidate",
    response_model=CacheInvalidateResponse,
    tags=["internal"],
    dependencies=[Depends(require_api_key)],
)
async def invalidate_cache(request: Request):
    """
    Flush all DevPulse Redis cache keys.
    Internal API key required.
    Called by Airflow after dbt run completes.
    """
    redis = request.app.state.redis
    deleted = await cache_invalidate_all(redis)
    return CacheInvalidateResponse(status="ok", keys_deleted=deleted)
