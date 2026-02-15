"""
Plan limit enforcement service — centralizes plan resolution and limit checks.

Limits are workspace-level: aggregated usage across all workspace members.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.workspace import Workspace
from app.services.usage_tracking_service import UsageTrackingService

logger = logging.getLogger(__name__)


class PlanLimitError(Exception):
    """Raised when a workspace exceeds a plan limit."""

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
    """Static methods to resolve the workspace's plan and enforce daily limits."""

    @staticmethod
    async def get_workspace_plan(db: AsyncSession, workspace: Workspace) -> Plan:
        """Resolve the Plan from workspace.plan_tier (defaults to 'free')."""
        tier = getattr(workspace, "plan_tier", None) or "free"
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
    async def check_upload_limit(db: AsyncSession, workspace: Workspace) -> None:
        """Raise PlanLimitError if workspace daily upload limit is exceeded."""
        plan = await PlanLimitService.get_workspace_plan(db, workspace)
        ws_usage = await UsageTrackingService.get_workspace_today_usage(db, workspace.id)
        current = ws_usage["uploads_total"]
        limit_value = plan.upload_limit_daily

        if current >= limit_value:
            logger.warning(
                "plan_limit_exceeded: uploads workspace=%s plan=%s current=%d limit=%d",
                workspace.id, plan.name, current, limit_value,
            )
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
    async def check_file_size(db: AsyncSession, workspace: Workspace, size_mb: float) -> None:
        """Raise PlanLimitError if file size exceeds plan limit."""
        plan = await PlanLimitService.get_workspace_plan(db, workspace)
        limit_value = plan.max_file_size_mb

        if size_mb > limit_value:
            logger.warning(
                "plan_limit_exceeded: file_size workspace=%s plan=%s size=%.1fMB limit=%dMB",
                workspace.id, plan.name, size_mb, limit_value,
            )
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
    async def check_message_limit(db: AsyncSession, workspace: Workspace) -> None:
        """Raise PlanLimitError if workspace daily message limit is exceeded."""
        plan = await PlanLimitService.get_workspace_plan(db, workspace)
        ws_usage = await UsageTrackingService.get_workspace_today_usage(db, workspace.id)
        current = ws_usage["messages_total"]
        limit_value = plan.max_conversations_daily

        if current >= limit_value:
            logger.warning(
                "plan_limit_exceeded: messages workspace=%s plan=%s current=%d limit=%d",
                workspace.id, plan.name, current, limit_value,
            )
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

    @staticmethod
    async def check_token_limit(db: AsyncSession, workspace: Workspace) -> None:
        """Raise PlanLimitError if workspace daily token limit is exceeded."""
        plan = await PlanLimitService.get_workspace_plan(db, workspace)
        limit_value = plan.max_tokens_daily
        if not limit_value or limit_value <= 0:
            return
        ws_usage = await UsageTrackingService.get_workspace_today_usage(db, workspace.id)
        current = ws_usage["tokens_total"]

        if current >= limit_value:
            logger.warning(
                "plan_limit_exceeded: tokens workspace=%s plan=%s current=%d limit=%d",
                workspace.id, plan.name, current, limit_value,
            )
            raise PlanLimitError(
                detail=(
                    f"Limite diario de tokens atingido ({current:,}/{limit_value:,}). "
                    f"Faca upgrade do seu plano para continuar."
                ),
                code="token_limit_exceeded",
                limit_name="max_tokens_daily",
                current_value=current,
                max_value=limit_value,
            )
