"""
Admin BYO-LLM usage endpoints.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission
from app.models.user import User
from app.schemas.admin import ByoLlmUsageReportResponse
from app.services.byollm_usage_service import ByoLlmUsageService

router = APIRouter()


@router.get("/usage/byollm", response_model=ByoLlmUsageReportResponse)
async def get_byollm_usage(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    provider: Optional[str] = Query(default=None, max_length=50),
    user_id: UUID | None = Query(default=None),
    export: str = Query(default="json", pattern="^(json|csv)$"),
    _current_user: User = Depends(require_permissions(Permission.ADMIN_DASHBOARD)),
    db: AsyncSession = Depends(get_db),
):
    """
    BYO-LLM usage dashboard data with optional CSV export.
    """
    effective_end = end_date or date.today()
    effective_start = start_date or (effective_end - timedelta(days=6))
    if effective_start > effective_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date deve ser menor ou igual a end_date",
        )

    report = await ByoLlmUsageService.build_report(
        db=db,
        start_date=effective_start,
        end_date=effective_end,
        provider_filter=provider.lower().strip() if provider else None,
        user_id=user_id,
    )

    if export == "csv":
        csv_payload = ByoLlmUsageService.report_to_csv(report)
        filename = f"byollm-usage-{effective_start.isoformat()}-{effective_end.isoformat()}.csv"
        return Response(
            content=csv_payload,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return ByoLlmUsageReportResponse(**report)
