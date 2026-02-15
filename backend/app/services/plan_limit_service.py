"""
Plan limit enforcement service — centralizes plan resolution and limit checks.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.user import User
from app.services.usage_tracking_service import UsageTrackingService


class PlanLimitError(Exception):
    """Raised when a user exceeds a plan limit."""

    def __init__(
        self,
        detail: str,
        code: str,
        limit_name: str,
        current_value: int,
        max_value: int,
    ) -> None:
        self.detail = detail
        self.code = code
        self.limit_name = limit_name
        self.current_value = current_value
        self.max_value = max_value
        super().__init__(detail)


class PlanLimitService:
    """Static methods to resolve the user's plan and enforce daily limits."""

    @staticmethod
    async def get_user_plan(db: AsyncSession, user: User) -> Plan:
        """Resolve the Plan from user.plan_tier (defaults to 'free')."""
        tier = getattr(user, "plan_tier", None) or "free"
        stmt = select(Plan).where(Plan.name == tier)
        result = await db.execute(stmt)
        plan = result.scalar_one_or_none()
        if plan is None:
            # Fallback to free plan
            stmt = select(Plan).where(Plan.name == "free")
            result = await db.execute(stmt)
            plan = result.scalar_one_or_none()
        if plan is None:
            raise PlanLimitError(
                detail="Plano nao encontrado. Contate o suporte.",
                code="plan_not_found",
                limit_name="plan",
                current_value=0,
                max_value=0,
            )
        return plan

    @staticmethod
    async def check_upload_limit(db: AsyncSession, user: User) -> None:
        """Raise PlanLimitError if daily upload limit is exceeded."""
        plan = await PlanLimitService.get_user_plan(db, user)
        usage = await UsageTrackingService.get_today_usage(db, user.id)
        current = usage.uploads_count if usage else 0
        limit_value = plan.upload_limit_daily

        if current >= limit_value:
            raise PlanLimitError(
                detail=(
                    f"Limite diario de uploads atingido ({current}/{limit_value}). "
                    f"Faca upgrade do seu plano para continuar."
                ),
                code="upload_limit_exceeded",
                limit_name="upload_limit_daily",
                current_value=current,
                max_value=limit_value,
            )

    @staticmethod
    async def check_file_size(db: AsyncSession, user: User, size_mb: float) -> None:
        """Raise PlanLimitError if file size exceeds plan limit."""
        plan = await PlanLimitService.get_user_plan(db, user)
        limit_value = plan.max_file_size_mb

        if size_mb > limit_value:
            raise PlanLimitError(
                detail=(
                    f"Arquivo excede o limite do plano ({size_mb:.1f} MB / {limit_value} MB). "
                    f"Faca upgrade do seu plano para enviar arquivos maiores."
                ),
                code="file_size_limit_exceeded",
                limit_name="max_file_size_mb",
                current_value=int(size_mb),
                max_value=limit_value,
            )

    @staticmethod
    async def check_message_limit(db: AsyncSession, user: User) -> None:
        """Raise PlanLimitError if daily message limit is exceeded."""
        plan = await PlanLimitService.get_user_plan(db, user)
        usage = await UsageTrackingService.get_today_usage(db, user.id)
        current = usage.messages_count if usage else 0
        limit_value = plan.max_conversations_daily

        if current >= limit_value:
            raise PlanLimitError(
                detail=(
                    f"Limite diario de mensagens atingido ({current}/{limit_value}). "
                    f"Faca upgrade do seu plano para continuar."
                ),
                code="message_limit_exceeded",
                limit_name="max_conversations_daily",
                current_value=current,
                max_value=limit_value,
            )
