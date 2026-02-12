"""
Authentication endpoints: register, login, refresh token.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.core.redis import get_redis
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    encrypt_api_key,
    decode_token,
)
from app.core.rbac import UserRole
from app.models.user import User
from app.schemas.user import (
    AccessTokenResponse,
    LoginRequest,
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserResponse,
)

router = APIRouter()


def _build_user_response(user: User) -> UserResponse:
    """
    Build a safe user response without sensitive fields.
    """
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan_tier=user.plan_tier,
        role=user.role,
        llm_provider=user.llm_provider,
        has_api_key=bool(user.encrypted_api_key),
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Register a new user with optional LLM API key.
    
    **BYO-LLM Model**: User provides their own OpenAI/Anthropic/Azure/Local API key.
    The key is encrypted using Fernet symmetric encryption before storage.
    """
    # Check if email already exists
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    
    # Encrypt API key if provided
    encrypted_api_key = None
    if user_in.api_key:
        encrypted_api_key = encrypt_api_key(user_in.api_key)

    # Bootstrap RBAC: first account becomes owner.
    first_user_stmt = select(User.id).limit(1)
    first_user_result = await db.execute(first_user_stmt)
    is_first_user = first_user_result.scalar_one_or_none() is None
    assigned_role = UserRole.OWNER.value if is_first_user else UserRole.MEMBER.value
    
    # Create user
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        encrypted_api_key=encrypted_api_key,
        llm_provider=user_in.llm_provider,
        plan_tier=user_in.plan_tier,
        role=assigned_role,
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _build_user_response(user)


@router.post("/login", response_model=Token)
async def login(
    login_request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Token:
    """
    Login with email/password (JSON body) and return JWT tokens.
    """
    # Find user
    stmt = select(User).where(User.email == login_request.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    await db.commit()
    
    # Create tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token_jti = uuid4().hex
    refresh_token = create_refresh_token(data={"sub": str(user.id), "jti": refresh_token_jti})

    # Store refresh token JTI for one-time use validation.
    refresh_ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    await redis.setex(
        f"refresh_token:{refresh_token_jti}",
        refresh_ttl_seconds,
        str(user.id),
    )
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(
    refresh_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AccessTokenResponse:
    """
    Refresh access token using a valid one-time refresh token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(refresh_request.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise credentials_exception

    user_id_raw = payload.get("sub")
    refresh_jti = payload.get("jti")
    if user_id_raw is None or refresh_jti is None:
        raise credentials_exception
    try:
        user_id = UUID(str(user_id_raw))
    except (TypeError, ValueError):
        raise credentials_exception

    # Validate refresh token JTI in Redis and consume it (one-time use).
    redis_key = f"refresh_token:{refresh_jti}"
    stored_user_id = await redis.get(redis_key)
    if stored_user_id is None or stored_user_id != str(user_id):
        raise credentials_exception
    await redis.delete(redis_key)

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    return AccessTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
