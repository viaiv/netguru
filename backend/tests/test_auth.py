"""
Authentication API tests.
"""
from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


async def _register_user(
    client: AsyncClient,
    email: str = "test@example.com",
) -> dict[str, Any]:
    """
    Register a user for authentication tests.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _login_user(
    client: AsyncClient,
    email: str,
    password: str = "StrongPass123",
) -> dict[str, Any]:
    """
    Authenticate a user and return JWT payload.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_login_accepts_json_body(client: AsyncClient) -> None:
    """
    Login must use JSON payload and return JWT token pair.
    """
    await _register_user(client)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "StrongPass123"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["expires_in"] > 0


@pytest.mark.asyncio
async def test_first_registered_user_is_owner_role(client: AsyncClient) -> None:
    """
    First registered account must be bootstrapped as owner.
    """
    await _register_user(client, email="owner@example.com")
    tokens = await _login_user(client, email="owner@example.com")

    profile_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert profile_response.status_code == 200, profile_response.text
    assert profile_response.json()["role"] == "owner"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_conflict(client: AsyncClient) -> None:
    """
    Register must return 409 when email is already in use.
    """
    await _register_user(client, email="duplicate@example.com")

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "StrongPass123",
            "full_name": "Duplicate User",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Email already registered"


@pytest.mark.asyncio
async def test_refresh_token_is_one_time_use(client: AsyncClient) -> None:
    """
    Refresh token can only be consumed once.
    """
    await _register_user(client, email="refresh@example.com")

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "StrongPass123"},
    )
    assert login_response.status_code == 200, login_response.text
    refresh_token = login_response.json()["refresh_token"]

    first_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert first_refresh.status_code == 200, first_refresh.text
    first_payload = first_refresh.json()
    assert first_payload["token_type"] == "bearer"
    assert first_payload["access_token"]
    assert first_payload["expires_in"] > 0
    assert "refresh_token" not in first_payload

    second_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert second_refresh.status_code == 401, second_refresh.text


@pytest.mark.asyncio
async def test_refresh_token_cannot_access_protected_routes(client: AsyncClient) -> None:
    """
    Refresh token must be rejected by protected endpoints.
    """
    await _register_user(client, email="protected@example.com")

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "protected@example.com", "password": "StrongPass123"},
    )
    assert login_response.status_code == 200, login_response.text
    tokens = login_response.json()

    access_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert access_response.status_code == 200, access_response.text

    refresh_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert refresh_response.status_code == 401, refresh_response.text


@pytest.mark.asyncio
async def test_member_cannot_access_admin_user_listing(client: AsyncClient) -> None:
    """
    Member users must be denied from admin-only user list endpoint.
    """
    await _register_user(client, email="owner-list@example.com")
    await _register_user(client, email="member-list@example.com")
    member_tokens = await _login_user(client, email="member-list@example.com")

    list_response = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {member_tokens['access_token']}"},
    )

    assert list_response.status_code == 403, list_response.text
    assert "users:list" in list_response.json()["detail"]


@pytest.mark.asyncio
async def test_owner_can_list_and_manage_users(client: AsyncClient) -> None:
    """
    Owner can list users and update role/status of other users.
    """
    await _register_user(client, email="owner-manage@example.com")
    member_payload = await _register_user(client, email="member-manage@example.com")
    owner_tokens = await _login_user(client, email="owner-manage@example.com")

    list_response = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
    )
    assert list_response.status_code == 200, list_response.text
    listed_users = list_response.json()
    assert len(listed_users) == 2
    assert {user["role"] for user in listed_users} == {"owner", "member"}

    target_user_id = member_payload["id"]
    role_response = await client.patch(
        f"/api/v1/users/{target_user_id}/role",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
    )
    assert role_response.status_code == 200, role_response.text
    assert role_response.json()["role"] == "viewer"

    status_response = await client.patch(
        f"/api/v1/users/{target_user_id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
    )
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_admin_cannot_promote_user_to_owner(client: AsyncClient) -> None:
    """
    Admin role is not allowed to assign owner role.
    """
    await _register_user(client, email="owner-rbac@example.com")
    admin_payload = await _register_user(client, email="admin-rbac@example.com")
    target_payload = await _register_user(client, email="target-rbac@example.com")

    owner_tokens = await _login_user(client, email="owner-rbac@example.com")
    promote_admin_response = await client.patch(
        f"/api/v1/users/{admin_payload['id']}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
    )
    assert promote_admin_response.status_code == 200, promote_admin_response.text

    admin_tokens = await _login_user(client, email="admin-rbac@example.com")
    promote_owner_response = await client.patch(
        f"/api/v1/users/{target_payload['id']}/role",
        json={"role": "owner"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    assert promote_owner_response.status_code == 403, promote_owner_response.text
    assert "not allowed" in promote_owner_response.json()["detail"].lower()
