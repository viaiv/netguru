"""
Tarefas periodicas de billing (Celery Beat).

- reconcile_seat_quantities: sincroniza seat_quantity com member_count no Stripe
"""
from __future__ import annotations

import logging

import stripe
from sqlalchemy import func, select

from app.core.config import settings
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.workspace import WorkspaceMember
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
