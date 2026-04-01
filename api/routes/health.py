from fastapi import APIRouter, Request

from api.schemas import HealthResponse
from storage.db_client import fetch_latest_pipeline_run

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health(request: Request):
    """
    Returns API status and latest pipeline run stats.
    No auth required — used by Prometheus scraper.
    """
    latest_run = fetch_latest_pipeline_run()
    return HealthResponse(
        status="ok",
        latest_run=latest_run,
    )
