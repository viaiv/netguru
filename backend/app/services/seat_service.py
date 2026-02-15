"""
Seat management service — seat limits, Stripe quantity sync, and seat info.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

import stripe
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.workspace import Workspace, WorkspaceMember

logger = logging.getLogger(__name__)


class SeatLimitError(Exception):
    """Raised when a workspace cannot add more members."""

    def __init__(
        self,
        detail: str,
        current_members: int,
        max_allowed: int,
    ) -> None:
        self.detail = detail
        self.current_members = current_members
        self.max_allowed = max_allowed
        super().__init__(detail)


class SeatService:
    """Manages seat counting, limit enforcement, and Stripe quantity sync."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_member_count(self, workspace_id: UUID) -> int:
        """Return the number of members in a workspace."""
        stmt = (
            select(func.count())
            .select_from(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _get_workspace_plan(self, workspace: Workspace) -> Plan:
        """Resolve the Plan from workspace.plan_tier."""
        tier = getattr(workspace, "plan_tier", None) or "free"
        stmt = select(Plan).where(Plan.name == tier)
        result = await self._db.execute(stmt)
        plan = result.scalar_one_or_none()
        if plan is None:
            stmt = select(Plan).where(Plan.name == "free")
            result = await self._db.execute(stmt)
            plan = result.scalar_one_or_none()
        return plan

    async def _get_active_subscription(
        self, workspace_id: UUID,
    ) -> Optional[Subscription]:
        """Fetch the most recent active subscription for a workspace."""
        stmt = (
            select(Subscription)
            .where(
                Subscription.workspace_id == workspace_id,
                Subscription.status.in_(["active", "trialing", "past_due"]),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def check_seat_limit(self, workspace: Workspace) -> None:
        """
        Raise SeatLimitError if the workspace cannot invite more members.

        Solo/Free (max_members=1): always block invites.
        Team/Enterprise: compare member_count with seat_quantity (or plan.max_members).
        """
        plan = await self._get_workspace_plan(workspace)
        if plan is None:
            raise SeatLimitError(
                detail="Plano nao encontrado.",
                current_members=0,
                max_allowed=0,
            )

        member_count = await self.get_member_count(workspace.id)

        # Solo/Free: only the owner, no invites
        if plan.max_members <= 1:
            raise SeatLimitError(
                detail=(
                    "Seu plano nao permite membros adicionais. "
                    "Faca upgrade para Team ou Enterprise."
                ),
                current_members=member_count,
                max_allowed=1,
            )

        # Team/Enterprise: check against seat_quantity or plan base
        sub = await self._get_active_subscription(workspace.id)
        max_allowed = sub.seat_quantity if sub else plan.max_members

        if member_count >= max_allowed:
            raise SeatLimitError(
                detail=(
                    f"Limite de assentos atingido ({member_count}/{max_allowed}). "
                    f"Adicione mais assentos em Assinatura > Assentos ou faca upgrade."
                ),
                current_members=member_count,
                max_allowed=max_allowed,
            )

    async def sync_stripe_quantity(
        self,
        workspace: Workspace,
        stripe_api_key: str,
    ) -> Optional[int]:
        """
        Sync Stripe subscription quantity with actual member count.

        Formula: quantity = max(plan.max_members, member_count)
        Returns the new quantity, or None if no sync was needed.
        """
        plan = await self._get_workspace_plan(workspace)
        if plan is None or plan.max_members <= 1:
            return None

        sub = await self._get_active_subscription(workspace.id)
        if sub is None or not sub.stripe_subscription_id:
            return None

        member_count = await self.get_member_count(workspace.id)
        new_quantity = max(plan.max_members, member_count)

        if new_quantity == sub.seat_quantity:
            return None

        # Update Stripe
        try:
            stripe.api_key = stripe_api_key
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                items=[{
                    "id": self._get_stripe_item_id(sub.stripe_subscription_id),
                    "quantity": new_quantity,
                }],
                proration_behavior="create_prorations",
            )
        except stripe.StripeError as exc:
            logger.error(
                "Falha ao atualizar quantity no Stripe: sub=%s err=%s",
                sub.stripe_subscription_id,
                str(exc),
            )
            raise

        # Update local
        sub.seat_quantity = new_quantity
        await self._db.flush()

        logger.info(
            "seat_quantity_synced: workspace=%s old=%s new=%s",
            workspace.id, sub.seat_quantity, new_quantity,
        )
        return new_quantity

    @staticmethod
    def _get_stripe_item_id(stripe_subscription_id: str) -> str:
        """Retrieve the first subscription item ID from Stripe."""
        sub = stripe.Subscription.retrieve(stripe_subscription_id)
        items = sub.get("items", {}).get("data", [])
        if not items:
            raise ValueError(
                f"Nenhum item encontrado na subscription {stripe_subscription_id}"
            )
        return items[0]["id"]

    async def get_seat_info(self, workspace: Workspace) -> Optional[dict[str, Any]]:
        """
        Build seat info dict for API responses.

        Returns None for plans with max_members <= 1 (Solo/Free).
        """
        plan = await self._get_workspace_plan(workspace)
        if plan is None or plan.max_members <= 1:
            return None

        member_count = await self.get_member_count(workspace.id)
        sub = await self._get_active_subscription(workspace.id)
        seats_billed = sub.seat_quantity if sub else plan.max_members
        extra_seats = max(0, seats_billed - plan.max_members)

        return {
            "max_members_included": plan.max_members,
            "current_members": member_count,
            "seats_billed": seats_billed,
            "extra_seats": extra_seats,
            "extra_seat_price_cents": plan.price_per_extra_seat_cents,
            "can_invite": member_count < seats_billed,
        }
