"""
Pydantic schemas for User API.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings
from app.core.rbac import UserRole

# Pattern regex gerado a partir da fonte unica de providers
_PROVIDER_PATTERN = "^(" + "|".join(settings.SUPPORTED_LLM_PROVIDERS) + ")$"


class UserBase(BaseModel):
    """Base schema with common user fields."""
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(BaseModel):
    """
    Schema for user registration.

    User must provide their own LLM API key (BYO-LLM model).
    Registration always starts with a trial period (plan_tier set server-side).
    """
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)

    # BYO-LLM: User's own API key
    api_key: Optional[str] = Field(
        None,
        description="LLM API key (OpenAI, Anthropic, Azure, Google, Groq, DeepSeek, OpenRouter)",
        min_length=10,
        max_length=500
    )
    llm_provider: Optional[str] = Field(
        None,
        description="LLM provider name",
        pattern=_PROVIDER_PATTERN,
    )


class UserUpdate(BaseModel):
    """Schema for updating user profile."""
    full_name: Optional[str] = Field(None, max_length=255)
    
    # Allow updating API key
    api_key: Optional[str] = Field(
        None,
        description="New LLM API key",
        min_length=10,
        max_length=500
    )
    llm_provider: Optional[str] = Field(
        None,
        pattern=_PROVIDER_PATTERN,
    )


class UserResponse(UserBase):
    """
    Schema for user data in responses.

    NEVER include encrypted_api_key or hashed_password.
    """
    id: UUID
    plan_tier: str
    role: UserRole = Field(description="owner|admin|member|viewer")
    llm_provider: Optional[str]
    has_api_key: bool = Field(
        description="Whether user has configured an API key"
    )
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime]
    trial_ends_at: Optional[datetime] = None
    is_on_trial: bool = False

    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str = Field(description="Long-lived refresh token")
    token_type: str = "bearer"
    expires_in: int = Field(
        description="Access token expiration in seconds",
        default=1800,
    )


class LoginRequest(BaseModel):
    """Schema for user login request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""
    refresh_token: str = Field(..., min_length=10)


class AccessTokenResponse(BaseModel):
    """Response schema for access token refresh."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        description="Access token expiration in seconds",
        default=1800,
    )


class ApiKeyMetadataResponse(BaseModel):
    """Safe API key metadata response without plaintext key."""
    llm_provider: Optional[str]
    has_api_key: bool
    masked_key: Optional[str] = None


class UserByoLlmTotals(BaseModel):
    """Aggregated BYO-LLM totals for user-facing summary."""

    messages: int = 0
    tokens: int = 0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    error_rate_pct: float = 0.0


class UserByoLlmProviderItem(BaseModel):
    """Provider/model row in user BYO-LLM summary."""

    provider: str
    model: str
    messages: int
    tokens: int
    avg_latency_ms: float
    error_rate_pct: float


class UserByoLlmAlert(BaseModel):
    """Simple budget/quality alert shown to end users."""

    code: str
    severity: str
    message: str


class UserByoLlmUsageSummaryResponse(BaseModel):
    """User-facing BYO-LLM usage summary for a date window."""

    period_days: int
    provider_filter: Optional[str] = None
    totals: UserByoLlmTotals
    by_provider_model: list[UserByoLlmProviderItem]
    alerts: list[UserByoLlmAlert]


class UserRoleUpdate(BaseModel):
    """Schema for admin role updates."""

    role: UserRole = Field(description="owner|admin|member|viewer")


class UserStatusUpdate(BaseModel):
    """Schema for admin account status updates."""

    is_active: bool


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: UUID = Field(description="User UUID")
    exp: datetime = Field(description="Expiration timestamp")
    type: Optional[str] = Field(None, description="access|refresh")
    jti: Optional[str] = Field(None, description="Token unique identifier")


# ---------------------------------------------------------------------------
# Email verification / Password reset
# ---------------------------------------------------------------------------

class VerifyEmailRequest(BaseModel):
    """Schema para verificacao de email."""
    token: str = Field(..., min_length=10, max_length=200)


class ForgotPasswordRequest(BaseModel):
    """Schema para solicitar redefinicao de senha."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema para redefinir senha com token."""
    token: str = Field(..., min_length=10, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=100)
