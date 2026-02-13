"""
Public plans endpoint — no authentication required.
Returns active plans for the landing page pricing section.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.plan import Plan
from app.schemas.plan import PublicPlanResponse

router = APIRouter()


@router.get("", response_model=list[PublicPlanResponse])
async def list_public_plans(
    db: AsyncSession = Depends(get_db),
) -> list[PublicPlanResponse]:
    """List active plans (public, no auth required)."""
    stmt = select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)
    plans = (await db.execute(stmt)).scalars().all()
    return [PublicPlanResponse.model_validate(p) for p in plans]
