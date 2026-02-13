"""
Pydantic schemas for Admin API.
"""
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Pagination (reutilizavel)
# ---------------------------------------------------------------------------

class PaginationMeta(BaseModel):
    total: int
    page: int
    pages: int
    limit: int


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

class PlanCreate(BaseModel):
    name: str = Field(..., max_length=50)
    display_name: str = Field(..., max_length=100)
    stripe_product_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    price_cents: int = Field(default=0, ge=0)
    billing_period: str = Field(default="monthly", pattern="^(monthly|yearly)$")
    upload_limit_daily: int = Field(default=10, ge=0)
    max_file_size_mb: int = Field(default=100, ge=1)
    max_conversations_daily: int = Field(default=50, ge=0)
    max_tokens_daily: int = Field(default=100000, ge=0)
    features: Optional[dict[str, Any]] = None
    is_active: bool = True
    sort_order: int = 0


class PlanUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100)
    stripe_product_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    price_cents: Optional[int] = Field(None, ge=0)
    billing_period: Optional[str] = Field(None, pattern="^(monthly|yearly)$")
    upload_limit_daily: Optional[int] = Field(None, ge=0)
    max_file_size_mb: Optional[int] = Field(None, ge=1)
    max_conversations_daily: Optional[int] = Field(None, ge=0)
    max_tokens_daily: Optional[int] = Field(None, ge=0)
    features: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str
    stripe_product_id: Optional[str]
    stripe_price_id: Optional[str]
    price_cents: int
    billing_period: str
    upload_limit_daily: int
    max_file_size_mb: int
    max_conversations_daily: int
    max_tokens_daily: int
    features: Optional[dict[str, Any]]
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    plan_id: UUID
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    status: str
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    canceled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: Optional[UUID]
    actor_email: Optional[str] = None
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    changes: Optional[dict[str, Any]]
    ip_address: Optional[str]
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Dashboard / System Health
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_users: int
    active_users: int
    total_conversations: int
    total_messages: int
    total_documents: int
    users_by_plan: dict[str, int]
    users_by_role: dict[str, int]
    recent_signups_7d: int
    messages_today: int


class ServiceStatus(BaseModel):
    name: str
    status: str = Field(description="healthy|degraded|down")
    latency_ms: Optional[float] = None
    details: Optional[str] = None


class SystemHealthResponse(BaseModel):
    overall: str = Field(description="healthy|degraded|down")
    services: list[ServiceStatus]
    uptime_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Admin Users
# ---------------------------------------------------------------------------

class UsageSummary(BaseModel):
    uploads_today: int = 0
    messages_today: int = 0
    tokens_today: int = 0


class AdminUserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: Optional[str]
    plan_tier: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime]


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    pagination: PaginationMeta


class AdminUserDetailResponse(AdminUserListItem):
    llm_provider: Optional[str]
    has_api_key: bool
    usage: UsageSummary
    subscription: Optional[SubscriptionResponse] = None


class AdminUserUpdate(BaseModel):
    role: Optional[str] = Field(None, pattern="^(owner|admin|member|viewer)$")
    is_active: Optional[bool] = None
    plan_tier: Optional[str] = Field(None, pattern="^(solo|team|enterprise)$")


# ---------------------------------------------------------------------------
# Email Logs
# ---------------------------------------------------------------------------

class EmailLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recipient_email: str
    recipient_user_id: Optional[UUID]
    email_type: str
    subject: str
    status: str
    error_message: Optional[str]
    created_at: datetime


class EmailLogListResponse(BaseModel):
    items: list[EmailLogResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# System Settings
# ---------------------------------------------------------------------------

class SystemSettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    value: str = Field(description="Plain value or masked if encrypted")
    is_encrypted: bool
    description: Optional[str]
    updated_at: datetime


class SystemSettingUpdate(BaseModel):
    value: str = Field(..., max_length=2000)
    description: Optional[str] = Field(None, max_length=255)


# ---------------------------------------------------------------------------
# Billing (Stripe)
# ---------------------------------------------------------------------------

class CheckoutSessionRequest(BaseModel):
    plan_id: UUID
    success_url: str
    cancel_url: str


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class CustomerPortalResponse(BaseModel):
    portal_url: str


# ---------------------------------------------------------------------------
# Email Templates
# ---------------------------------------------------------------------------

class EmailTemplateVariable(BaseModel):
    name: str
    description: str


class EmailTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email_type: str
    subject: str
    body_html: str
    variables: list[EmailTemplateVariable]
    is_active: bool
    updated_at: datetime
    updated_by: Optional[UUID]


class EmailTemplateUpdate(BaseModel):
    subject: Optional[str] = Field(None, max_length=255)
    body_html: Optional[str] = None
    is_active: Optional[bool] = None


class EmailTemplatePreviewRequest(BaseModel):
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Variaveis de exemplo para preview (ex: {'action_url': 'https://...'})",
    )


class EmailTemplatePreviewResponse(BaseModel):
    subject: str
    html: str
