import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.auth.dependencies import get_current_user
from api.schemas import SavedInsightReportResponse
from storage.db_client import build_source_items, fetch_latest_insight_report, resolve_source_references

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/reports/latest", response_model=SavedInsightReportResponse | None, tags=["reports"])
async def get_latest_saved_report(
    query: str | None = Query(None, description="Optional exact query filter for the saved report"),
    current_user: dict = Depends(get_current_user),
):
    """Return the latest saved insight report, optionally filtered by exact query text."""
    report = fetch_latest_insight_report(query=query)
    if report is None:
        return None

    return SavedInsightReportResponse(
        id=report["id"],
        query=report["query"],
        report_text=report["report_text"],
        formatted_report_text=report.get("formatted_report_text"),
        has_pdf=bool(report.get("report_pdf")),
        sources_used=resolve_source_references(list(report.get("sources_used") or [])),
        source_items=build_source_items(resolve_source_references(list(report.get("sources_used") or []))),
        generated_at=report["generated_at"],
    )


@router.get("/reports/latest/pdf", tags=["reports"])
async def get_latest_saved_report_pdf(
    query: str | None = Query(None, description="Optional exact query filter for the saved report"),
    current_user: dict = Depends(get_current_user),
):
    """Return the persisted PDF artifact for the latest saved insight report."""
    del current_user
    report = fetch_latest_insight_report(query=query)
    if report is None or not report.get("report_pdf"):
        return Response(status_code=404)

    generated_at = report["generated_at"]
    generated_date = generated_at.date().isoformat() if hasattr(generated_at, "date") else str(generated_at).split("T")[0]
    filename = f"developer-radar-weekly-report-{generated_date}.pdf"
    return Response(
        content=bytes(report["report_pdf"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
