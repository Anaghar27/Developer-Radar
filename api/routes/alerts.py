import logging

from fastapi import APIRouter, Depends, Query, Request

from api.auth.dependencies import get_current_user
from api.schemas import AlertResponse, AlertsListResponse
from storage.db_client import fetch_recent_alerts

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/alerts", response_model=AlertsListResponse, tags=["data"])
async def get_alerts(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """
    Volume spike alerts ordered by triggered_at DESC.
    Reads directly from PostgreSQL alerts table — not cached
    (alerts are low volume and must always be fresh).
    """
    try:
        rows = fetch_recent_alerts(limit=limit)
        alerts = [AlertResponse(**row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to fetch alerts: {e}")
        alerts = []

    return AlertsListResponse(alerts=alerts, total=len(alerts))
