"""
SystemSettingsService — CRUD for system_settings with Fernet encryption.

Provides both async (FastAPI) and sync (Celery) database access.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.security import decrypt_api_key, encrypt_api_key
from app.models.system_setting import SystemSetting

# Keys that must always be stored encrypted
ENCRYPTED_KEYS = frozenset({
    "mailtrap_api_key",
    "r2_access_key_id",
    "r2_secret_access_key",
    "stripe_secret_key",
    "stripe_webhook_secret",
})


class SystemSettingsService:
    """Reads and writes system_settings rows."""

    # ------------------------------------------------------------------
    # Async helpers (FastAPI endpoints)
    # ------------------------------------------------------------------

    @staticmethod
    async def get(db: AsyncSession, key: str) -> Optional[str]:
        """
        Retrieve a setting value by key (decrypts if needed).

        Args:
            db: Async database session.
            key: Setting key.

        Returns:
            Decrypted plain-text value, or None if not found.
        """
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        if row.is_encrypted:
            return decrypt_api_key(row.value)
        return row.value

    @staticmethod
    async def get_all(db: AsyncSession) -> list[SystemSetting]:
        """Return all settings rows (values still encrypted in model)."""
        stmt = select(SystemSetting).order_by(SystemSetting.key)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def upsert(
        db: AsyncSession,
        key: str,
        value: str,
        *,
        description: Optional[str] = None,
        updated_by: Optional[UUID] = None,
    ) -> SystemSetting:
        """
        Insert or update a setting.

        Args:
            db: Async database session.
            key: Setting key.
            value: Plain-text value (will be encrypted if key is sensitive).
            description: Optional human-readable description.
            updated_by: UUID of the user making the change.

        Returns:
            The upserted SystemSetting row.
        """
        should_encrypt = key in ENCRYPTED_KEYS

        stmt = select(SystemSetting).where(SystemSetting.key == key)
        row = (await db.execute(stmt)).scalar_one_or_none()

        stored_value = encrypt_api_key(value) if should_encrypt else value

        if row is None:
            row = SystemSetting(
                key=key,
                value=stored_value,
                is_encrypted=should_encrypt,
                description=description,
                updated_by=updated_by,
            )
            db.add(row)
        else:
            row.value = stored_value
            row.is_encrypted = should_encrypt
            if description is not None:
                row.description = description
            row.updated_by = updated_by
            row.updated_at = datetime.utcnow()

        await db.flush()
        await db.refresh(row)
        return row

    # ------------------------------------------------------------------
    # Sync helpers (Celery workers)
    # ------------------------------------------------------------------

    @staticmethod
    def get_sync(db: Session, key: str) -> Optional[str]:
        """
        Synchronous version of ``get`` for Celery workers.

        Args:
            db: Sync database session.
            key: Setting key.

        Returns:
            Decrypted plain-text value, or None if not found.
        """
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        row = db.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        if row.is_encrypted:
            return decrypt_api_key(row.value)
        return row.value
