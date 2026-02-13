"""
Billing endpoints — Stripe checkout, customer portal, webhook.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.admin import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalResponse,
)
from app.services.subscription_service import (
    StripeNotConfiguredError,
    SubscriptionService,
    SubscriptionServiceError,
)

router = APIRouter()


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
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout session for plan subscription."""
    svc = await _get_subscription_service(db)
    try:
        result = await svc.create_checkout_session(
            db,
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
    db: AsyncSession = Depends(get_db),
) -> CustomerPortalResponse:
    """Create a Stripe Customer Portal session."""
    svc = await _get_subscription_service(db)
    referer = request.headers.get("referer", "/")
    try:
        result = await svc.create_customer_portal_session(
            db,
            user=current_user,
            return_url=referer,
        )
        return CustomerPortalResponse(**result)
    except SubscriptionServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc


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
