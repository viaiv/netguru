"""
Subscription service — Stripe checkout, portal, and webhook handling.

Carrega credenciais via SystemSettings (DB, Fernet-encrypted) com fallback
para variaveis de ambiente (retrocompatibilidade).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.plan import Plan
from app.models.stripe_event import StripeEvent
from app.models.subscription import Subscription
from app.models.user import User
from app.models.workspace import Workspace
from app.services.system_settings_service import SystemSettingsService

logger = logging.getLogger(__name__)


class SubscriptionServiceError(Exception):
    """Domain error for subscription operations."""

    def __init__(self, detail: str, code: str = "subscription_error") -> None:
        self.detail = detail
        self.code = code
        super().__init__(detail)


class StripeNotConfiguredError(SubscriptionServiceError):
    """Credenciais Stripe nao configuradas."""

    def __init__(self, detail: str = "Stripe nao configurado. Configure as credenciais no painel admin ou variaveis de ambiente.") -> None:
        super().__init__(detail, code="stripe_not_configured")


class SubscriptionService:
    """
    Manages Stripe checkout, customer portal, and webhook events.

    Usa factory ``from_settings`` (async) ou ``from_settings_sync`` (Celery)
    para carregar credenciais do SystemSettings com fallback para env vars.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        webhook_secret: str,
        publishable_key: str = "",
    ) -> None:
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self._publishable_key = publishable_key

    def _configure_stripe(self) -> None:
        """Seta stripe.api_key antes de cada operacao."""
        stripe.api_key = self._secret_key

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    async def from_settings(cls, db: AsyncSession) -> SubscriptionService:
        """
        Factory async — carrega credenciais do SystemSettings (FastAPI).

        Fallback para env vars se DB estiver vazio (retrocompatibilidade).

        Raises:
            StripeNotConfiguredError: Se nenhuma credencial disponivel.
        """
        enabled = await SystemSettingsService.get(db, "stripe_enabled")
        if enabled == "false":
            raise StripeNotConfiguredError(
                "Stripe esta desabilitado nas configuracoes do sistema."
            )

        secret_key = await SystemSettingsService.get(db, "stripe_secret_key")
        webhook_secret = await SystemSettingsService.get(db, "stripe_webhook_secret")
        publishable_key = await SystemSettingsService.get(db, "stripe_publishable_key")

        # Fallback para env vars
        if not secret_key:
            secret_key = settings.STRIPE_SECRET_KEY
        if not webhook_secret:
            webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        if not publishable_key:
            publishable_key = settings.STRIPE_PUBLISHABLE_KEY

        if not secret_key:
            raise StripeNotConfiguredError()

        return cls(
            secret_key=secret_key,
            webhook_secret=webhook_secret or "",
            publishable_key=publishable_key or "",
        )

    @classmethod
    def from_settings_sync(cls, db: Session) -> SubscriptionService:
        """
        Factory sync — carrega credenciais do SystemSettings (Celery).

        Fallback para env vars se DB estiver vazio (retrocompatibilidade).

        Raises:
            StripeNotConfiguredError: Se nenhuma credencial disponivel.
        """
        enabled = SystemSettingsService.get_sync(db, "stripe_enabled")
        if enabled == "false":
            raise StripeNotConfiguredError(
                "Stripe esta desabilitado nas configuracoes do sistema."
            )

        secret_key = SystemSettingsService.get_sync(db, "stripe_secret_key")
        webhook_secret = SystemSettingsService.get_sync(db, "stripe_webhook_secret")
        publishable_key = SystemSettingsService.get_sync(db, "stripe_publishable_key")

        # Fallback para env vars
        if not secret_key:
            secret_key = settings.STRIPE_SECRET_KEY
        if not webhook_secret:
            webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        if not publishable_key:
            publishable_key = settings.STRIPE_PUBLISHABLE_KEY

        if not secret_key:
            raise StripeNotConfiguredError()

        return cls(
            secret_key=secret_key,
            webhook_secret=webhook_secret or "",
            publishable_key=publishable_key or "",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_checkout_session(
        self,
        db: AsyncSession,
        *,
        workspace: Workspace,
        user: User,
        plan_id: UUID,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        """
        Create a Stripe Checkout Session for a workspace plan.

        Returns:
            dict with checkout_url and session_id.
        """
        self._configure_stripe()
        plan = await self._get_plan(db, plan_id)

        if not plan.stripe_price_id:
            raise SubscriptionServiceError(
                "Plano nao possui preco configurado no Stripe.",
                code="plan_no_stripe_price",
            )

        # Find or skip existing stripe customer
        existing_sub = await self._get_active_subscription(db, workspace.id)
        customer_kwarg: dict[str, Any] = {}
        if existing_sub and existing_sub.stripe_customer_id:
            customer_kwarg["customer"] = existing_sub.stripe_customer_id
        else:
            customer_kwarg["customer_email"] = user.email

        # Apply promo coupon if workspace never used it
        checkout_kwargs: dict[str, Any] = {}
        promo_applied = False
        if plan.stripe_promo_coupon_id and plan.promo_months:
            has_used = await self._has_used_promo(db, workspace.id, plan.id)
            if not has_used:
                checkout_kwargs["discounts"] = [{"coupon": plan.stripe_promo_coupon_id}]
                promo_applied = True

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "workspace_id": str(workspace.id),
                "user_id": str(user.id),
                "plan_id": str(plan.id),
                "promo_applied": "1" if promo_applied else "0",
            },
            **customer_kwarg,
            **checkout_kwargs,
        )

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    async def create_customer_portal_session(
        self,
        db: AsyncSession,
        *,
        workspace: Workspace,
        return_url: str,
    ) -> dict[str, str]:
        """
        Create a Stripe Customer Portal session for a workspace.

        Returns:
            dict with portal_url.
        """
        self._configure_stripe()
        sub = await self._get_active_subscription(db, workspace.id)
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
        self._configure_stripe()
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self._webhook_secret,
            )
        except stripe.SignatureVerificationError as exc:
            await self._log_event(
                db,
                event_id="unknown",
                event_type="signature_verification_error",
                status="failed",
                error_message=str(exc)[:500],
                payload_summary=str(payload[:500]),
            )
            raise SubscriptionServiceError(
                "Assinatura do webhook invalida.",
                code="invalid_webhook_signature",
            )

        event_type = event["type"]
        event_id = event["id"]
        data = event["data"]["object"]

        handler = {
            "checkout.session.completed": self._handle_checkout_completed,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "invoice.payment_failed": self._handle_payment_failed,
        }.get(event_type)

        if handler:
            try:
                await handler(db, data)
            except Exception as exc:
                await self._log_event(
                    db,
                    event_id=event_id,
                    event_type=event_type,
                    status="failed",
                    data=data,
                    error_message=str(exc)[:500],
                )
                raise
            await self._log_event(
                db,
                event_id=event_id,
                event_type=event_type,
                status="processed",
                data=data,
            )
            logger.info("Stripe webhook processed: %s", event_type)
        else:
            await self._log_event(
                db,
                event_id=event_id,
                event_type=event_type,
                status="ignored",
                data=data,
            )
            logger.debug("Stripe webhook ignored: %s", event_type)

        return event_type

    # ------------------------------------------------------------------
    # Internal webhook handlers
    # ------------------------------------------------------------------

    async def _handle_checkout_completed(
        self, db: AsyncSession, data: dict[str, Any],
    ) -> None:
        """checkout.session.completed — create subscription record."""
        workspace_id = data.get("metadata", {}).get("workspace_id")
        plan_id = data.get("metadata", {}).get("plan_id")
        if not workspace_id or not plan_id:
            logger.warning("Checkout completed sem metadata workspace_id/plan_id")
            return

        stripe_sub_id = data.get("subscription")
        stripe_customer_id = data.get("customer")

        # Fetch Stripe subscription details
        stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)

        promo_flag = data.get("metadata", {}).get("promo_applied") == "1"

        subscription = Subscription(
            workspace_id=workspace_id,
            plan_id=plan_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_sub_id,
            status="active",
            promo_applied=promo_flag,
            current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start),
            current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end),
        )
        db.add(subscription)

        # Update workspace plan_tier
        plan = await self._get_plan(db, UUID(plan_id))
        stmt = select(Workspace).where(Workspace.id == UUID(workspace_id))
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()
        if workspace:
            workspace.plan_tier = plan.name

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
        """customer.subscription.deleted — cancel and revert workspace to free."""
        sub = await self._find_subscription_by_stripe_id(db, data["id"])
        if not sub:
            return

        sub.status = "canceled"
        sub.canceled_at = datetime.utcnow()

        # Revert workspace to free tier
        stmt = select(Workspace).where(Workspace.id == sub.workspace_id)
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()
        if workspace:
            workspace.plan_tier = "free"

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
    # Event logging
    # ------------------------------------------------------------------

    async def _log_event(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        event_type: str,
        status: str,
        data: Optional[dict[str, Any]] = None,
        error_message: Optional[str] = None,
        payload_summary: Optional[str] = None,
    ) -> None:
        """Persist a StripeEvent record for admin visibility."""
        try:
            record = StripeEvent(
                event_id=event_id,
                event_type=event_type,
                status=status,
                customer_id=data.get("customer") if data else None,
                subscription_id=data.get("subscription") or (data.get("id") if data else None),
                user_id=self._extract_user_id(data),
                error_message=error_message,
                payload_summary=payload_summary or (str(data)[:500] if data else None),
            )
            db.add(record)
            await db.flush()
        except Exception:
            logger.exception("Falha ao persistir StripeEvent (event_id=%s)", event_id)

    @staticmethod
    def _extract_user_id(data: Optional[dict[str, Any]]) -> Optional[UUID]:
        """Extract user_id from event metadata, if present."""
        if not data:
            return None
        raw = data.get("metadata", {}).get("user_id")
        if raw:
            try:
                return UUID(raw)
            except (ValueError, AttributeError):
                pass
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _has_used_promo(
        self, db: AsyncSession, workspace_id: UUID, plan_id: UUID,
    ) -> bool:
        """Check if workspace has already used a promotional coupon for this plan."""
        stmt = (
            select(Subscription)
            .where(
                Subscription.workspace_id == workspace_id,
                Subscription.plan_id == plan_id,
                Subscription.promo_applied.is_(True),
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

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
        self, db: AsyncSession, workspace_id: UUID,
    ) -> Optional[Subscription]:
        stmt = (
            select(Subscription)
            .where(
                Subscription.workspace_id == workspace_id,
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
