"""
Tarefas periodicas de billing (Celery Beat).

- reconcile_seat_quantities: sincroniza seat_quantity com member_count no Stripe
- check_byollm_discount_eligibility: revoga desconto BYO-LLM apos grace period
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import stripe
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.workspace import Workspace, WorkspaceMember
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.billing_tasks.reconcile_seat_quantities")
def reconcile_seat_quantities() -> dict:
    """
    Reconcilia seat_quantity de subscriptions ativas com o member_count real.

    Para cada subscription ativa de um plano com max_members > 1:
    1. Conta membros do workspace
    2. Calcula quantity = max(plan.max_members, member_count)
    3. Se diferente de sub.seat_quantity, atualiza Stripe + local
    """
    from app.core.database_sync import get_sync_db
    from app.services.subscription_service import SubscriptionService

    updated = 0
    errors = 0
    checked = 0

    with get_sync_db() as db:
        try:
            sub_svc = SubscriptionService.from_settings_sync(db)
        except Exception:
            logger.warning("reconcile_seat_quantities: Stripe nao configurado, pulando.")
            return {"checked": 0, "updated": 0, "errors": 0}

        # Find active subscriptions for plans with max_members > 1
        stmt = (
            select(Subscription, Plan)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(
                Subscription.status.in_(["active", "trialing"]),
                Plan.max_members > 1,
                Subscription.stripe_subscription_id.isnot(None),
            )
        )
        rows = db.execute(stmt).all()

        for sub, plan in rows:
            checked += 1
            try:
                # Count members
                count_stmt = (
                    select(func.count())
                    .select_from(WorkspaceMember)
                    .where(WorkspaceMember.workspace_id == sub.workspace_id)
                )
                member_count = db.execute(count_stmt).scalar_one()
                expected_quantity = max(plan.max_members, member_count)

                if expected_quantity != sub.seat_quantity:
                    logger.info(
                        "reconcile_seat: workspace=%s sub=%s current=%d expected=%d",
                        sub.workspace_id,
                        sub.stripe_subscription_id,
                        sub.seat_quantity,
                        expected_quantity,
                    )

                    # Update Stripe
                    stripe.api_key = sub_svc._secret_key
                    stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
                    items = stripe_sub.get("items", {}).get("data", [])
                    if items:
                        stripe.Subscription.modify(
                            sub.stripe_subscription_id,
                            items=[{
                                "id": items[0]["id"],
                                "quantity": expected_quantity,
                            }],
                            proration_behavior="create_prorations",
                        )

                    sub.seat_quantity = expected_quantity
                    updated += 1

            except Exception:
                logger.exception(
                    "reconcile_seat_error: workspace=%s sub=%s",
                    sub.workspace_id,
                    sub.stripe_subscription_id,
                )
                errors += 1

        if updated > 0:
            db.commit()

    result = {"checked": checked, "updated": updated, "errors": errors}
    logger.info("reconcile_seat_quantities: %s", result)
    return result


@celery_app.task(name="app.workers.tasks.billing_tasks.check_byollm_discount_eligibility")
def check_byollm_discount_eligibility() -> dict:
    """
    Verifica subscriptions com desconto BYO-LLM e revoga apos grace period.

    Fluxo por subscription:
    1. Owner ainda tem API key → limpa grace (usuario reconfigurou)
    2. Owner removeu API key:
       a. Grace nao iniciado → envia email warning, seta byollm_grace_notified_at
       b. Grace expirado (7+ dias) → revoga coupon no Stripe, limpa flags
       c. Ainda dentro do grace → nenhuma acao
    """
    from app.core.database_sync import get_sync_db
    from app.workers.tasks.email_tasks import send_byollm_discount_warning_email

    if not settings.STRIPE_SECRET_KEY:
        logger.warning("check_byollm_discount: Stripe nao configurado, pulando.")
        return {"checked": 0, "grace_started": 0, "revoked": 0, "restored": 0, "errors": 0}

    stripe.api_key = settings.STRIPE_SECRET_KEY
    grace_period = timedelta(days=settings.BYOLLM_GRACE_PERIOD_DAYS)

    checked = 0
    grace_started = 0
    revoked = 0
    restored = 0
    errors = 0

    with get_sync_db() as db:
        stmt = (
            select(Subscription)
            .join(Plan, Subscription.plan_id == Plan.id)
            .options(
                joinedload(Subscription.workspace).joinedload(Workspace.owner)
            )
            .where(
                Subscription.status.in_(["active", "trialing"]),
                Subscription.byollm_discount_applied.is_(True),
                Subscription.stripe_subscription_id.isnot(None),
                Plan.stripe_byollm_coupon_id.isnot(None),
            )
        )
        subscriptions = db.execute(stmt).scalars().unique().all()

        for sub in subscriptions:
            checked += 1
            try:
                workspace = sub.workspace
                if not workspace:
                    continue
                owner = workspace.owner
                if not owner:
                    continue

                has_api_key = bool(owner.encrypted_api_key)

                if has_api_key:
                    # Owner reconfigurou a API key — limpar grace se existia
                    if sub.byollm_grace_notified_at is not None:
                        logger.info(
                            "byollm_grace_restored: sub=%s owner=%s",
                            sub.stripe_subscription_id, owner.id,
                        )
                        sub.byollm_grace_notified_at = None
                        restored += 1
                    continue

                # Owner removeu a API key
                if sub.byollm_grace_notified_at is None:
                    # Iniciar grace period
                    sub.byollm_grace_notified_at = datetime.utcnow()
                    grace_started += 1
                    logger.info(
                        "byollm_grace_started: sub=%s owner=%s",
                        sub.stripe_subscription_id, owner.id,
                    )
                    # Enviar email warning (fire-and-forget)
                    send_byollm_discount_warning_email.delay(
                        owner.email,
                        owner.full_name,
                        settings.BYOLLM_GRACE_PERIOD_DAYS,
                        str(owner.id),
                    )

                elif sub.byollm_grace_notified_at + grace_period <= datetime.utcnow():
                    # Grace expirado — revogar desconto
                    logger.info(
                        "byollm_discount_revoking: sub=%s owner=%s",
                        sub.stripe_subscription_id, owner.id,
                    )
                    stripe.Subscription.delete_discount(sub.stripe_subscription_id)
                    sub.byollm_discount_applied = False
                    sub.byollm_grace_notified_at = None
                    revoked += 1
                # else: ainda dentro do grace, nenhuma acao

            except Exception:
                logger.exception(
                    "byollm_check_error: sub=%s",
                    getattr(sub, "stripe_subscription_id", "?"),
                )
                errors += 1

        if grace_started > 0 or revoked > 0 or restored > 0:
            db.commit()

    result = {
        "checked": checked,
        "grace_started": grace_started,
        "revoked": revoked,
        "restored": restored,
        "errors": errors,
    }
    logger.info("check_byollm_discount_eligibility: %s", result)
    return result
