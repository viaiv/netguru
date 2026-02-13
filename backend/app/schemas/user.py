"""
Pydantic schemas for User API.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from app.core.rbac import UserRole


class UserBase(BaseModel):
    """Base schema with common user fields."""
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(BaseModel):
    """
    Schema for user registration.
    
    User must provide their own LLM API key (BYO-LLM model).
    """
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    
    # BYO-LLM: User's own API key
    api_key: Optional[str] = Field(
        None,
        description="OpenAI, Anthropic, Azure, or local LLM API key",
        min_length=10,
        max_length=500
    )
    llm_provider: Optional[str] = Field(
        None,
        description="openai|anthropic|azure|local",
        pattern="^(openai|anthropic|azure|local)$"
    )
    
    plan_tier: str = Field(
        default="solo",
        description="solo|team|enterprise",
        pattern="^(solo|team|enterprise)$"
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
        pattern="^(openai|anthropic|azure|local)$"
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
