"""
Billing endpoints — Stripe checkout, customer portal, webhook, subscription info.
"""
from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace
from app.core.rbac import (
    WorkspacePermission,
    has_workspace_permission,
    normalize_workspace_role,
)
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.admin import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalResponse,
)
from app.schemas.billing import (
    SeatInfoResponse,
    SubscriptionDetail,
    UpdateSeatsRequest,
    UsageTodayResponse,
    UserSubscriptionPlan,
    UserSubscriptionResponse,
)
from app.services.seat_service import SeatService
from app.services.subscription_service import (
    StripeNotConfiguredError,
    SubscriptionService,
    SubscriptionServiceError,
)
from app.services.usage_tracking_service import UsageTrackingService

router = APIRouter()


def _validate_return_url(url: str) -> None:
    """
    Validate that a return URL belongs to an allowed origin.

    Uses CORS_ORIGINS as the allowlist. Rejects URLs pointing to
    external hosts to prevent open-redirect after Stripe flows.

    Raises:
        HTTPException 400 if the URL host is not in the allowlist.
    """
    allowed_origins = settings.cors_origins_list
    # Wildcard CORS = skip validation (dev only, logged as warning elsewhere)
    if "*" in allowed_origins:
        return

    parsed = urlparse(url)
    url_origin = f"{parsed.scheme}://{parsed.netloc}"

    for origin in allowed_origins:
        origin = origin.strip().rstrip("/")
        if url_origin == origin:
            return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"URL de retorno nao permitida: host '{parsed.netloc}' fora da allowlist.",
    )


async def _require_billing_permission(
    workspace: Workspace, user: User, db: AsyncSession,
) -> None:
    """Raise 403 if user lacks WORKSPACE_BILLING_MANAGE."""
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voce nao e membro deste workspace.",
        )
    role = normalize_workspace_role(member.workspace_role)
    if not has_workspace_permission(role, WorkspacePermission.WORKSPACE_BILLING_MANAGE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissao insuficiente: workspace:billing_manage",
        )


async def _get_subscription_service(db: AsyncSession) -> SubscriptionService:
    """Cria SubscriptionService por request via SystemSettings."""
    try:
        return await SubscriptionService.from_settings(db)
    except StripeNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def create_checkout(
    body: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout session for workspace plan subscription."""
    _validate_return_url(body.success_url)
    _validate_return_url(body.cancel_url)
    await _require_billing_permission(workspace, current_user, db)
    svc = await _get_subscription_service(db)
    try:
        result = await svc.create_checkout_session(
            db,
            workspace=workspace,
            user=current_user,
            plan_id=body.plan_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
        return CheckoutSessionResponse(**result)
    except SubscriptionServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc


@router.post("/portal", response_model=CustomerPortalResponse)
async def create_portal(
    request: Request,
    current_user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> CustomerPortalResponse:
    """Create a Stripe Customer Portal session."""
    await _require_billing_permission(workspace, current_user, db)
    svc = await _get_subscription_service(db)
    referer = request.headers.get("referer", "/")
    _validate_return_url(referer)
    try:
        result = await svc.create_customer_portal_session(
            db,
            workspace=workspace,
            return_url=referer,
        )
        return CustomerPortalResponse(**result)
    except SubscriptionServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc


@router.get("/subscription", response_model=UserSubscriptionResponse)
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> UserSubscriptionResponse:
    """Return the workspace's plan, active subscription, and today's usage."""
    # Resolve plan from workspace.plan_tier
    tier = getattr(workspace, "plan_tier", None) or "free"
    stmt = select(Plan).where(Plan.name == tier)
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if plan is None:
        stmt = select(Plan).where(Plan.name == "free")
        plan = (await db.execute(stmt)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Plano nao encontrado.",
        )

    plan_data = UserSubscriptionPlan.model_validate(plan)

    # Fetch active subscription for workspace
    sub_stmt = (
        select(Subscription)
        .where(
            Subscription.workspace_id == workspace.id,
            Subscription.status.in_(["active", "trialing", "past_due"]),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = (await db.execute(sub_stmt)).scalar_one_or_none()
    sub_data = SubscriptionDetail.model_validate(subscription) if subscription else None

    # Fetch today's usage (workspace-aggregated)
    ws_usage = await UsageTrackingService.get_workspace_today_usage(db, workspace.id)
    usage_data = UsageTodayResponse(
        uploads_today=ws_usage["uploads_total"],
        messages_today=ws_usage["messages_total"],
        tokens_today=ws_usage["tokens_total"],
    )

    # Build seat info for plans with max_members > 1
    seat_info_data = None
    if plan.max_members > 1:
        seat_svc = SeatService(db)
        raw = await seat_svc.get_seat_info(workspace)
        if raw:
            seat_info_data = SeatInfoResponse(**raw)

    return UserSubscriptionResponse(
        has_subscription=subscription is not None,
        plan=plan_data,
        subscription=sub_data,
        usage_today=usage_data,
        seat_info=seat_info_data,
    )


@router.post("/seats", response_model=SeatInfoResponse)
async def update_seats(
    body: UpdateSeatsRequest,
    current_user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> SeatInfoResponse:
    """Pre-purchase seats — owner/admin only. Updates Stripe quantity with proration."""
    await _require_billing_permission(workspace, current_user, db)
    svc = await _get_subscription_service(db)
    try:
        await svc.update_seat_quantity(db, workspace, body.quantity)
        await db.commit()
    except SubscriptionServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc

    seat_svc = SeatService(db)
    raw = await seat_svc.get_seat_info(workspace)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seu plano nao suporta gerenciamento de assentos.",
        )
    return SeatInfoResponse(**raw)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Stripe webhook endpoint — no JWT auth, uses Stripe signature verification.
    """
    svc = await _get_subscription_service(db)
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event_type = await svc.handle_webhook_event(db, payload, sig_header)
        return {"status": "ok", "event": event_type}
    except SubscriptionServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc
