"""
Pydantic schemas for Billing API — subscription details and daily usage.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionDetail(BaseModel):
    """Stripe subscription data exposed to the user."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    stripe_subscription_id: Optional[str] = None
    seat_quantity: int = 1
    byollm_discount_applied: bool = False
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    canceled_at: Optional[datetime] = None


class UsageTodayResponse(BaseModel):
    """Daily usage counters for the current user."""

    uploads_today: int = 0
    messages_today: int = 0
    tokens_today: int = 0


class SeatInfoResponse(BaseModel):
    """Seat usage breakdown for the workspace."""

    max_members_included: int
    current_members: int
    seats_billed: int
    extra_seats: int
    extra_seat_price_cents: int
    can_invite: bool


class UserSubscriptionPlan(BaseModel):
    """Plan with embedded limits for the subscription response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str
    price_cents: int
    billing_period: str
    promo_price_cents: Optional[int] = None
    promo_months: Optional[int] = None
    byollm_discount_cents: int = 0
    max_members: int
    price_per_extra_seat_cents: int
    upload_limit_daily: int
    max_file_size_mb: int
    max_conversations_daily: int
    max_tokens_daily: int
    features: Optional[dict[str, Any]] = None


class UserSubscriptionResponse(BaseModel):
    """Full subscription state for the current user."""

    has_subscription: bool
    plan: UserSubscriptionPlan
    subscription: Optional[SubscriptionDetail] = None
    usage_today: UsageTodayResponse
    seat_info: Optional[SeatInfoResponse] = None


class UpdateSeatsRequest(BaseModel):
    """Request to pre-purchase additional seats."""

    quantity: int = Field(..., ge=1, description="Total seat quantity desired")
