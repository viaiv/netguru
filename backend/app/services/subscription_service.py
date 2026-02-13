"""
Subscription service — Stripe checkout, portal, and webhook handling.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)


class SubscriptionServiceError(Exception):
    """Domain error for subscription operations."""

    def __init__(self, detail: str, code: str = "subscription_error") -> None:
        self.detail = detail
        self.code = code
        super().__init__(detail)


class SubscriptionService:
    """
    Manages Stripe checkout, customer portal, and webhook events.
    """

    def __init__(self) -> None:
        stripe.api_key = settings.STRIPE_SECRET_KEY

    async def create_checkout_session(
        self,
        db: AsyncSession,
        *,
        user: User,
        plan_id: UUID,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        """
        Create a Stripe Checkout Session for the given plan.

        Returns:
            dict with checkout_url and session_id.
        """
        plan = await self._get_plan(db, plan_id)

        if not plan.stripe_price_id:
            raise SubscriptionServiceError(
                "Plano nao possui preco configurado no Stripe.",
                code="plan_no_stripe_price",
            )

        # Find or skip existing stripe customer
        existing_sub = await self._get_active_subscription(db, user.id)
        customer_kwarg: dict[str, Any] = {}
        if existing_sub and existing_sub.stripe_customer_id:
            customer_kwarg["customer"] = existing_sub.stripe_customer_id
        else:
            customer_kwarg["customer_email"] = user.email

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user.id), "plan_id": str(plan.id)},
            **customer_kwarg,
        )

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    async def create_customer_portal_session(
        self,
        db: AsyncSession,
        *,
        user: User,
        return_url: str,
    ) -> dict[str, str]:
        """
        Create a Stripe Customer Portal session.

        Returns:
            dict with portal_url.
        """
        sub = await self._get_active_subscription(db, user.id)
        if not sub or not sub.stripe_customer_id:
            raise SubscriptionServiceError(
                "Nenhuma assinatura ativa encontrada.",
                code="no_active_subscription",
            )

        portal = stripe.billing_portal.Session.create(
            customer=sub.stripe_customer_id,
            return_url=return_url,
        )

        return {"portal_url": portal.url}

    async def handle_webhook_event(
        self,
        db: AsyncSession,
        payload: bytes,
        sig_header: str,
    ) -> str:
        """
        Verify and dispatch a Stripe webhook event.

        Returns:
            Event type string for logging.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET,
            )
        except stripe.SignatureVerificationError:
            raise SubscriptionServiceError(
                "Assinatura do webhook invalida.",
                code="invalid_webhook_signature",
            )

        event_type = event["type"]
        data = event["data"]["object"]

        handler = {
            "checkout.session.completed": self._handle_checkout_completed,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "invoice.payment_failed": self._handle_payment_failed,
        }.get(event_type)

        if handler:
            await handler(db, data)
            logger.info("Stripe webhook processed: %s", event_type)
        else:
            logger.debug("Stripe webhook ignored: %s", event_type)

        return event_type

    # ------------------------------------------------------------------
    # Internal webhook handlers
    # ------------------------------------------------------------------

    async def _handle_checkout_completed(
        self, db: AsyncSession, data: dict[str, Any],
    ) -> None:
        """checkout.session.completed — create subscription record."""
        user_id = data.get("metadata", {}).get("user_id")
        plan_id = data.get("metadata", {}).get("plan_id")
        if not user_id or not plan_id:
            logger.warning("Checkout completed sem metadata user_id/plan_id")
            return

        stripe_sub_id = data.get("subscription")
        stripe_customer_id = data.get("customer")

        # Fetch Stripe subscription details
        stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)

        subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_sub_id,
            status="active",
            current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start),
            current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end),
        )
        db.add(subscription)

        # Update user plan_tier
        plan = await self._get_plan(db, UUID(plan_id))
        stmt = select(User).where(User.id == UUID(user_id))
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.plan_tier = plan.name
            user.updated_at = datetime.utcnow()

        await db.flush()

    async def _handle_subscription_updated(
        self, db: AsyncSession, data: dict[str, Any],
    ) -> None:
        """customer.subscription.updated — update status/period."""
        sub = await self._find_subscription_by_stripe_id(db, data["id"])
        if not sub:
            return

        sub.status = data.get("status", sub.status)
        sub.cancel_at_period_end = data.get("cancel_at_period_end", False)
        if data.get("current_period_start"):
            sub.current_period_start = datetime.fromtimestamp(data["current_period_start"])
        if data.get("current_period_end"):
            sub.current_period_end = datetime.fromtimestamp(data["current_period_end"])
        if data.get("canceled_at"):
            sub.canceled_at = datetime.fromtimestamp(data["canceled_at"])

        await db.flush()

    async def _handle_subscription_deleted(
        self, db: AsyncSession, data: dict[str, Any],
    ) -> None:
        """customer.subscription.deleted — cancel and revert to solo."""
        sub = await self._find_subscription_by_stripe_id(db, data["id"])
        if not sub:
            return

        sub.status = "canceled"
        sub.canceled_at = datetime.utcnow()

        # Revert user to solo tier
        stmt = select(User).where(User.id == sub.user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.plan_tier = "solo"
            user.updated_at = datetime.utcnow()

        await db.flush()

    async def _handle_payment_failed(
        self, db: AsyncSession, data: dict[str, Any],
    ) -> None:
        """invoice.payment_failed — mark subscription as past_due."""
        stripe_sub_id = data.get("subscription")
        if not stripe_sub_id:
            return

        sub = await self._find_subscription_by_stripe_id(db, stripe_sub_id)
        if sub:
            sub.status = "past_due"
            await db.flush()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_plan(self, db: AsyncSession, plan_id: UUID) -> Plan:
        stmt = select(Plan).where(Plan.id == plan_id, Plan.is_active.is_(True))
        result = await db.execute(stmt)
        plan = result.scalar_one_or_none()
        if not plan:
            raise SubscriptionServiceError(
                "Plano nao encontrado ou inativo.",
                code="plan_not_found",
            )
        return plan

    async def _get_active_subscription(
        self, db: AsyncSession, user_id: UUID,
    ) -> Optional[Subscription]:
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_(["active", "trialing", "past_due"]),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_subscription_by_stripe_id(
        self, db: AsyncSession, stripe_sub_id: str,
    ) -> Optional[Subscription]:
        stmt = select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_sub_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
