"""
Trial 15-day lifecycle tests.

Covers: registration with trial, /me response during trial,
auto-downgrade on expiry, paid user immunity, and Celery safety-net task.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import InMemoryUserStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_user(
    client: AsyncClient,
    email: str = "trial@example.com",
) -> dict[str, Any]:
    """Register a user and return the response JSON."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123",
            "full_name": "Trial Tester",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _login_user(
    client: AsyncClient,
    email: str,
    password: str = "StrongPass123",
) -> dict[str, Any]:
    """Authenticate and return the JWT payload."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_starts_with_trial_team_plan(client: AsyncClient) -> None:
    """New users must start on plan_tier=team with an active trial."""
    data = await _register_user(client)

    assert data["plan_tier"] == "team"
    assert data["trial_ends_at"] is not None
    assert data["is_on_trial"] is True


@pytest.mark.asyncio
async def test_me_shows_trial_active_during_trial_period(client: AsyncClient) -> None:
    """GET /me must expose trial status while trial is active."""
    await _register_user(client, email="me-trial@example.com")
    tokens = await _login_user(client, email="me-trial@example.com")

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_tier"] == "team"
    assert body["is_on_trial"] is True
    assert body["trial_ends_at"] is not None


@pytest.mark.asyncio
async def test_trial_auto_downgrade_on_expiry(client: AsyncClient) -> None:
    """
    When the trial has expired, GET /me must auto-downgrade the user
    to plan_tier=free via the lazy check in get_current_user.
    """
    await _register_user(client, email="expire@example.com")
    tokens = await _login_user(client, email="expire@example.com")

    future = datetime.utcnow() + timedelta(days=16)
    with patch("app.core.dependencies.datetime") as mock_dt:
        mock_dt.utcnow.return_value = future
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_tier"] == "free"
    assert body["is_on_trial"] is False
    assert body["trial_ends_at"] is None


@pytest.mark.asyncio
async def test_paid_user_not_affected_by_trial_check(
    client_with_store: tuple[AsyncClient, InMemoryUserStore],
) -> None:
    """
    A paid subscriber (trial_ends_at=None) must NOT be downgraded
    even when the datetime mock is far in the future.
    """
    client, store = client_with_store

    await _register_user(client, email="paid@example.com")
    tokens = await _login_user(client, email="paid@example.com")

    # Simulate paid subscriber: clear trial_ends_at while keeping team plan
    user = store.by_email["paid@example.com"]
    user.trial_ends_at = None

    future = datetime.utcnow() + timedelta(days=365)
    with patch("app.core.dependencies.datetime") as mock_dt:
        mock_dt.utcnow.return_value = future
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_tier"] == "team"


# ---------------------------------------------------------------------------
# Celery task tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_downgrade_expired_trials_task() -> None:
    """
    The Celery safety-net task must downgrade users whose trial has expired.
    """
    expired_user = MagicMock()
    expired_user.plan_tier = "team"
    expired_user.trial_ends_at = datetime.utcnow() - timedelta(days=1)

    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [expired_user]

    fake_db = MagicMock()
    fake_db.execute.return_value = fake_result
    fake_db.__enter__ = MagicMock(return_value=fake_db)
    fake_db.__exit__ = MagicMock(return_value=False)

    with patch(
        "app.core.database_sync.get_sync_db",
        return_value=fake_db,
    ):
        from importlib import reload
        import app.workers.tasks.maintenance_tasks as mt
        reload(mt)
        result = mt.downgrade_expired_trials()

    assert result == {"downgraded": 1}
    assert expired_user.plan_tier == "free"
    assert expired_user.trial_ends_at is None


@pytest.mark.asyncio
async def test_downgrade_expired_trials_ignores_active() -> None:
    """
    The Celery task must not downgrade users with active trials (query returns empty).
    """
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []

    fake_db = MagicMock()
    fake_db.execute.return_value = fake_result
    fake_db.__enter__ = MagicMock(return_value=fake_db)
    fake_db.__exit__ = MagicMock(return_value=False)

    with patch(
        "app.core.database_sync.get_sync_db",
        return_value=fake_db,
    ):
        from importlib import reload
        import app.workers.tasks.maintenance_tasks as mt
        reload(mt)
        result = mt.downgrade_expired_trials()

    assert result == {"downgraded": 0}
