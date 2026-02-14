"""
Pydantic schemas for persistent network memories.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MemoryScope(str, Enum):
    """Supported memory scope levels."""

    GLOBAL = "global"
    SITE = "site"
    DEVICE = "device"


class SystemMemoryScope(str, Enum):
    """System memory scope (single level)."""

    SYSTEM = "system"


class MemoryCreate(BaseModel):
    """
    Request payload for creating a persistent memory.
    """

    scope: MemoryScope
    scope_name: str | None = Field(default=None, max_length=120)
    memory_key: str = Field(min_length=1, max_length=120)
    memory_value: str = Field(min_length=1, max_length=4000)
    tags: list[str] | None = Field(default=None)
    ttl_seconds: int | None = Field(default=None, ge=60, le=31536000)

    @field_validator("scope_name")
    @classmethod
    def normalize_scope_name(cls, value: str | None) -> str | None:
        """
        Normalize optional scope name.
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("memory_key")
    @classmethod
    def normalize_memory_key(cls, value: str) -> str:
        """
        Normalize memory key.
        """
        return value.strip().lower()

    @field_validator("memory_value")
    @classmethod
    def normalize_memory_value(cls, value: str) -> str:
        """
        Normalize memory value.
        """
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        """
        Normalize and de-duplicate tags.
        """
        if value is None:
            return None

        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in value:
            normalized = tag.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned or None

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "MemoryCreate":
        """
        Enforce scope-specific requirements.
        """
        if self.scope == MemoryScope.GLOBAL and self.scope_name is not None:
            raise ValueError("scope_name deve ser nulo para escopo global")
        if self.scope in {MemoryScope.SITE, MemoryScope.DEVICE} and not self.scope_name:
            raise ValueError("scope_name e obrigatorio para escopos site/device")
        return self


class MemoryUpdate(BaseModel):
    """
    Request payload for updating a persistent memory.
    """

    scope: MemoryScope | None = None
    scope_name: str | None = Field(default=None, max_length=120)
    memory_key: str | None = Field(default=None, min_length=1, max_length=120)
    memory_value: str | None = Field(default=None, min_length=1, max_length=4000)
    tags: list[str] | None = None
    ttl_seconds: int | None = Field(default=None, ge=60, le=31536000)
    clear_ttl: bool = False

    @field_validator("scope_name")
    @classmethod
    def normalize_scope_name(cls, value: str | None) -> str | None:
        """
        Normalize optional scope name.
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("memory_key")
    @classmethod
    def normalize_memory_key(cls, value: str | None) -> str | None:
        """
        Normalize memory key.
        """
        if value is None:
            return None
        return value.strip().lower()

    @field_validator("memory_value")
    @classmethod
    def normalize_memory_value(cls, value: str | None) -> str | None:
        """
        Normalize memory value.
        """
        if value is None:
            return None
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        """
        Normalize and de-duplicate tags.
        """
        if value is None:
            return None

        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in value:
            normalized = tag.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned or None


class MemoryResponse(BaseModel):
    """
    API response for memory resource.
    """

    id: UUID
    user_id: UUID
    scope: MemoryScope
    scope_name: str | None
    memory_key: str
    memory_value: str
    tags: list[str] | None
    ttl_seconds: int | None
    expires_at: datetime | None
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SystemMemoryCreate(BaseModel):
    """
    Request payload for creating a system memory.
    """

    memory_key: str = Field(min_length=1, max_length=120)
    memory_value: str = Field(min_length=1, max_length=4000)
    tags: list[str] | None = Field(default=None)
    ttl_seconds: int | None = Field(default=None, ge=60, le=31536000)

    @field_validator("memory_key")
    @classmethod
    def normalize_memory_key(cls, value: str) -> str:
        """Normalize memory key."""
        return value.strip().lower()

    @field_validator("memory_value")
    @classmethod
    def normalize_memory_value(cls, value: str) -> str:
        """Normalize memory value."""
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        """Normalize and de-duplicate tags."""
        if value is None:
            return None

        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in value:
            normalized = tag.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned or None


class SystemMemoryUpdate(BaseModel):
    """
    Request payload for updating a system memory.
    """

    memory_key: str | None = Field(default=None, min_length=1, max_length=120)
    memory_value: str | None = Field(default=None, min_length=1, max_length=4000)
    tags: list[str] | None = None
    ttl_seconds: int | None = Field(default=None, ge=60, le=31536000)
    clear_ttl: bool = False

    @field_validator("memory_key")
    @classmethod
    def normalize_memory_key(cls, value: str | None) -> str | None:
        """Normalize memory key."""
        if value is None:
            return None
        return value.strip().lower()

    @field_validator("memory_value")
    @classmethod
    def normalize_memory_value(cls, value: str | None) -> str | None:
        """Normalize memory value."""
        if value is None:
            return None
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        """Normalize and de-duplicate tags."""
        if value is None:
            return None

        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in value:
            normalized = tag.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned or None


class SystemMemoryResponse(BaseModel):
    """
    API response for system memory resource.
    """

    id: UUID
    scope: SystemMemoryScope
    scope_name: str | None
    memory_key: str
    memory_value: str
    tags: list[str] | None
    ttl_seconds: int | None
    expires_at: datetime | None
    version: int
    is_active: bool
    created_by: UUID | None
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
