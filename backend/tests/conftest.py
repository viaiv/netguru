"""
Pytest fixtures for backend API tests.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.api.v1.endpoints import auth as auth_endpoints
from app.main import app


class FakeRedis:
    """
    Minimal async Redis stub for one-time token tests.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class FakeResult:
    """
    Minimal SQLAlchemy-like result object.
    """

    def __init__(
        self,
        user: object | None = None,
        items: list[object] | None = None,
    ) -> None:
        self._user = user
        self._items = items or []

    def scalar_one_or_none(self) -> object | None:
        return self._user

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[object]:
        return list(self._items)


class InMemoryUserStore:
    """
    Shared in-memory state used by fake DB sessions.
    """

    def __init__(self) -> None:
        self.by_email: dict[str, object] = {}
        self.by_id: dict[UUID, object] = {}


class FakeDBSession:
    """
    Minimal async session implementing required methods for auth tests.
    """

    def __init__(self, store: InMemoryUserStore) -> None:
        self._store = store

    async def execute(self, statement: object) -> FakeResult:
        where_criteria = list(getattr(statement, "_where_criteria", []))
        if not where_criteria:
            column_descriptions = list(getattr(statement, "column_descriptions", []))
            first_column_name = (
                str(column_descriptions[0].get("name"))
                if column_descriptions
                else ""
            )

            if first_column_name == "id":
                if not self._store.by_id:
                    return FakeResult(None)
                first_user_id = sorted(self._store.by_id.keys(), key=str)[0]
                return FakeResult(first_user_id)

            users = [
                self._store.by_id[user_id]
                for user_id in sorted(self._store.by_id, key=str)
            ]
            return FakeResult(items=users)

        criterion = where_criteria[0]
        column_name = getattr(getattr(criterion, "left", None), "name", None)
        value = getattr(getattr(criterion, "right", None), "value", None)

        if column_name == "email":
            return FakeResult(self._store.by_email.get(str(value)))
        if column_name == "id":
            try:
                user_id = value if isinstance(value, UUID) else UUID(str(value))
                return FakeResult(self._store.by_id.get(user_id))
            except (TypeError, ValueError):
                return FakeResult(None)

        return FakeResult(None)

    def add(self, user: object) -> None:
        user_id = getattr(user, "id", None)
        if user_id is None:
            setattr(user, "id", uuid4())
        elif isinstance(user_id, str):
            setattr(user, "id", UUID(user_id))

        now = datetime.utcnow()
        if getattr(user, "created_at", None) is None:
            setattr(user, "created_at", now)
        if getattr(user, "updated_at", None) is None:
            setattr(user, "updated_at", now)
        if getattr(user, "is_active", None) is None:
            setattr(user, "is_active", True)
        if getattr(user, "is_verified", None) is None:
            setattr(user, "is_verified", False)
        if getattr(user, "role", None) is None:
            setattr(user, "role", "member")

        normalized_user_id = getattr(user, "id")
        if not isinstance(normalized_user_id, UUID):
            normalized_user_id = UUID(str(normalized_user_id))
            setattr(user, "id", normalized_user_id)

        self._store.by_email[str(getattr(user, "email"))] = user
        self._store.by_id[normalized_user_id] = user

    async def commit(self) -> None:
        return None

    async def refresh(self, _user: object) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client with dependency overrides.
    """
    fake_redis = FakeRedis()
    store = InMemoryUserStore()

    # Isolate tests from bcrypt backend differences in local environments.
    original_get_password_hash = auth_endpoints.get_password_hash
    original_verify_password = auth_endpoints.verify_password
    auth_endpoints.get_password_hash = lambda password: f"hashed::{password}"
    auth_endpoints.verify_password = (
        lambda plain_password, hashed_password: hashed_password == f"hashed::{plain_password}"
    )

    async def override_get_db() -> AsyncGenerator[FakeDBSession, None]:
        yield FakeDBSession(store)

    async def override_get_redis() -> AsyncGenerator[FakeRedis, None]:
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()
    auth_endpoints.get_password_hash = original_get_password_hash
    auth_endpoints.verify_password = original_verify_password
