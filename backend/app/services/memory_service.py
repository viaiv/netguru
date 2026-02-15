"""
MemoryService — CRUD and contextual retrieval for user/system persistent memories.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import unicodedata
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.network_memory import NetworkMemory
from app.models.system_memory import SystemMemory
from app.schemas.memory import (
    MemoryCreate,
    MemoryScope,
    MemoryUpdate,
    SystemMemoryCreate,
    SystemMemoryUpdate,
)

SCOPE_PRIORITY: dict[str, int] = {
    "system": 1,
    MemoryScope.GLOBAL.value: 2,
    MemoryScope.SITE.value: 3,
    MemoryScope.DEVICE.value: 4,
}

VENDOR_HINTS: dict[str, tuple[str, ...]] = {
    "cisco": ("cisco", "ios", "ios xe", "ios-xe", "nx os", "nx-os", "catalyst"),
    "juniper": ("juniper", "junos"),
    "arista": ("arista", "eos"),
    "mikrotik": ("mikrotik", "mikro tik", "routeros", "router os", "mtk"),
}

SUPPORTED_VENDOR_ORDER: tuple[str, ...] = (
    "cisco",
    "juniper",
    "arista",
    "mikrotik",
)


class MemoryServiceError(Exception):
    """Domain error for memory operations."""

    def __init__(self, detail: str, code: str = "memory_error") -> None:
        self.detail = detail
        self.code = code
        super().__init__(detail)


@dataclass(frozen=True)
class AppliedMemory:
    """One memory applied to the current chat context."""

    memory_id: UUID
    origin: str
    scope: str
    scope_name: str | None
    memory_key: str
    memory_value: str
    version: int
    expires_at: datetime | None


@dataclass(frozen=True)
class MemoryContextResolution:
    """Resolved contextual memories for a chat turn."""

    entries: list[AppliedMemory]
    context_block: str | None
    vendor_ambiguity_prompt: str | None = None
    ambiguous_vendors: list[str] = field(default_factory=list)


class MemoryService:
    """Manage persistent memory CRUD and context resolution."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_memories(
        self,
        *,
        workspace_id: UUID,
        scope: MemoryScope | None = None,
        scope_name: str | None = None,
        include_inactive: bool = False,
    ) -> list[NetworkMemory]:
        """
        List workspace memories with optional filters.
        """
        stmt = select(NetworkMemory).where(NetworkMemory.workspace_id == workspace_id)
        if not include_inactive:
            stmt = stmt.where(NetworkMemory.is_active.is_(True))
        if scope is not None:
            stmt = stmt.where(NetworkMemory.scope == scope.value)
        if scope_name is not None:
            stmt = stmt.where(NetworkMemory.scope_name == scope_name)

        stmt = stmt.order_by(NetworkMemory.updated_at.desc())
        return (await self._safe_execute(stmt)).scalars().all()

    async def get_memory(
        self,
        *,
        workspace_id: UUID,
        memory_id: UUID,
        include_inactive: bool = False,
    ) -> NetworkMemory | None:
        """
        Get one workspace memory by ID.
        """
        stmt = select(NetworkMemory).where(
            NetworkMemory.id == memory_id,
            NetworkMemory.workspace_id == workspace_id,
        )
        if not include_inactive:
            stmt = stmt.where(NetworkMemory.is_active.is_(True))
        return (await self._safe_execute(stmt)).scalar_one_or_none()

    async def create_memory(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        payload: MemoryCreate,
    ) -> NetworkMemory:
        """
        Create a workspace memory entry.
        """
        await self._ensure_workspace_identity_is_available(
            workspace_id=workspace_id,
            scope=payload.scope.value,
            scope_name=payload.scope_name,
            memory_key=payload.memory_key,
        )

        now = datetime.utcnow()
        expires_at = self._resolve_expiration(now=now, ttl_seconds=payload.ttl_seconds)
        memory = NetworkMemory(
            workspace_id=workspace_id,
            user_id=user_id,
            scope=payload.scope.value,
            scope_name=payload.scope_name,
            memory_key=payload.memory_key,
            memory_value=payload.memory_value,
            tags=payload.tags,
            ttl_seconds=payload.ttl_seconds,
            expires_at=expires_at,
            version=1,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._db.add(memory)
        await self._db.flush()
        await self._db.refresh(memory)
        return memory

    async def update_memory(
        self,
        *,
        workspace_id: UUID,
        memory_id: UUID,
        payload: MemoryUpdate,
    ) -> NetworkMemory:
        """
        Update a workspace memory and increment version on meaningful changes.
        """
        memory = await self.get_memory(workspace_id=workspace_id, memory_id=memory_id)
        if memory is None:
            raise MemoryServiceError("Memoria nao encontrada.", code="memory_not_found")

        scope = payload.scope.value if payload.scope is not None else memory.scope
        scope_name = (
            payload.scope_name
            if "scope_name" in payload.model_fields_set
            else memory.scope_name
        )
        memory_key = payload.memory_key if payload.memory_key is not None else memory.memory_key

        if (
            scope != memory.scope
            or scope_name != memory.scope_name
            or memory_key != memory.memory_key
        ):
            await self._ensure_workspace_identity_is_available(
                workspace_id=workspace_id,
                scope=scope,
                scope_name=scope_name,
                memory_key=memory_key,
                exclude_memory_id=memory.id,
            )

        changed = self._apply_common_memory_updates(
            memory=memory,
            payload=payload,
        )
        if changed:
            memory.updated_at = datetime.utcnow()
            await self._db.flush()
            await self._db.refresh(memory)

        return memory

    async def delete_memory(
        self,
        *,
        workspace_id: UUID,
        memory_id: UUID,
    ) -> NetworkMemory:
        """
        Soft-delete a workspace memory.
        """
        memory = await self.get_memory(workspace_id=workspace_id, memory_id=memory_id)
        if memory is None:
            raise MemoryServiceError("Memoria nao encontrada.", code="memory_not_found")

        memory.is_active = False
        memory.updated_at = datetime.utcnow()
        await self._db.flush()
        await self._db.refresh(memory)
        return memory

    async def list_system_memories(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[SystemMemory]:
        """
        List system memories.
        """
        stmt = select(SystemMemory)
        if not include_inactive:
            stmt = stmt.where(SystemMemory.is_active.is_(True))

        stmt = stmt.order_by(SystemMemory.updated_at.desc())
        return (await self._safe_execute(stmt)).scalars().all()

    async def get_system_memory(
        self,
        *,
        memory_id: UUID,
        include_inactive: bool = False,
    ) -> SystemMemory | None:
        """
        Get one system memory by ID.
        """
        stmt = select(SystemMemory).where(SystemMemory.id == memory_id)
        if not include_inactive:
            stmt = stmt.where(SystemMemory.is_active.is_(True))
        return (await self._safe_execute(stmt)).scalar_one_or_none()

    async def create_system_memory(
        self,
        *,
        actor_id: UUID,
        payload: SystemMemoryCreate,
    ) -> SystemMemory:
        """
        Create one system memory entry.
        """
        await self._ensure_system_identity_is_available(
            memory_key=payload.memory_key,
        )

        now = datetime.utcnow()
        expires_at = self._resolve_expiration(now=now, ttl_seconds=payload.ttl_seconds)
        memory = SystemMemory(
            scope="system",
            scope_name=None,
            memory_key=payload.memory_key,
            memory_value=payload.memory_value,
            tags=payload.tags,
            ttl_seconds=payload.ttl_seconds,
            expires_at=expires_at,
            version=1,
            is_active=True,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        self._db.add(memory)
        await self._db.flush()
        await self._db.refresh(memory)
        return memory

    async def update_system_memory(
        self,
        *,
        actor_id: UUID,
        memory_id: UUID,
        payload: SystemMemoryUpdate,
    ) -> SystemMemory:
        """
        Update a system memory and increment version on meaningful changes.
        """
        memory = await self.get_system_memory(memory_id=memory_id)
        if memory is None:
            raise MemoryServiceError("Memoria de sistema nao encontrada.", code="memory_not_found")

        memory_key = payload.memory_key if payload.memory_key is not None else memory.memory_key

        if memory_key != memory.memory_key:
            await self._ensure_system_identity_is_available(
                memory_key=memory_key,
                exclude_memory_id=memory.id,
            )

        changed = self._apply_system_memory_updates(
            memory=memory,
            payload=payload,
        )
        if changed:
            memory.updated_by = actor_id
            memory.updated_at = datetime.utcnow()
            await self._db.flush()
            await self._db.refresh(memory)

        return memory

    async def delete_system_memory(
        self,
        *,
        actor_id: UUID,
        memory_id: UUID,
    ) -> SystemMemory:
        """
        Soft-delete a system memory entry.
        """
        memory = await self.get_system_memory(memory_id=memory_id)
        if memory is None:
            raise MemoryServiceError("Memoria de sistema nao encontrada.", code="memory_not_found")

        memory.is_active = False
        memory.updated_by = actor_id
        memory.updated_at = datetime.utcnow()
        await self._db.flush()
        await self._db.refresh(memory)
        return memory

    async def resolve_chat_context(
        self,
        *,
        workspace_id: UUID,
        message_content: str,
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
        limit: int = 8,
    ) -> MemoryContextResolution:
        """
        Resolve relevant workspace+system memories for a chat turn.
        """
        now = datetime.utcnow()
        user_stmt = (
            select(NetworkMemory)
            .where(
                NetworkMemory.workspace_id == workspace_id,
                NetworkMemory.is_active.is_(True),
                or_(
                    NetworkMemory.expires_at.is_(None),
                    NetworkMemory.expires_at > now,
                ),
            )
            .order_by(NetworkMemory.updated_at.desc())
        )
        system_stmt = (
            select(SystemMemory)
            .where(
                SystemMemory.is_active.is_(True),
                or_(
                    SystemMemory.expires_at.is_(None),
                    SystemMemory.expires_at > now,
                ),
            )
            .order_by(SystemMemory.updated_at.desc())
        )

        user_rows = (await self._safe_execute(user_stmt)).scalars().all()
        system_rows = (await self._safe_execute(system_stmt)).scalars().all()

        candidates: list[tuple[NetworkMemory | SystemMemory, str]] = [
            (row, "user") for row in user_rows
        ] + [
            (row, "system") for row in system_rows
        ]
        entries, ambiguous_vendors = self._select_relevant_with_diagnostics(
            candidates=candidates,
            message_content=message_content,
            preferred_vendor=preferred_vendor,
            allow_vendor_prompt=allow_vendor_prompt,
            limit=limit,
        )
        context_block = self.build_context_block(entries)
        return MemoryContextResolution(
            entries=entries,
            context_block=context_block,
            vendor_ambiguity_prompt=self.build_vendor_ambiguity_prompt(ambiguous_vendors),
            ambiguous_vendors=ambiguous_vendors,
        )

    @staticmethod
    def build_context_block(entries: list[AppliedMemory]) -> str | None:
        """
        Build textual context block appended to current user message.
        """
        if not entries:
            return None

        lines = [
            "[MEMORIA_PERSISTENTE]",
            "Use os fatos abaixo como contexto do ambiente do cliente.",
            "Prioridade: device > site > global > system.",
            "",
        ]
        for entry in entries:
            scope_label = entry.scope
            if entry.scope_name:
                scope_label = f"{entry.scope}:{entry.scope_name}"
            compact_value = " ".join(entry.memory_value.split())
            lines.append(
                f"- [{entry.origin}][{scope_label}] {entry.memory_key}: {compact_value}"
            )
        lines.append("[/MEMORIA_PERSISTENTE]")
        return "\n".join(lines)

    @staticmethod
    def build_context_metadata(entries: list[AppliedMemory]) -> dict:
        """
        Build metadata payload for stream_end observability.
        """
        return {
            "applied_count": len(entries),
            "entries": [
                {
                    "memory_id": str(entry.memory_id),
                    "origin": entry.origin,
                    "scope": entry.scope,
                    "scope_name": entry.scope_name,
                    "memory_key": entry.memory_key,
                    "version": entry.version,
                    "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
                }
                for entry in entries
            ],
        }

    @classmethod
    def select_relevant_memories(
        cls,
        *,
        rows: list[NetworkMemory],
        message_content: str,
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
        limit: int = 8,
    ) -> list[AppliedMemory]:
        """
        Select relevant memories for user-owned rows only.
        """
        return cls.select_relevant_from_candidates(
            candidates=[(row, "user") for row in rows],
            message_content=message_content,
            preferred_vendor=preferred_vendor,
            allow_vendor_prompt=allow_vendor_prompt,
            limit=limit,
        )

    @classmethod
    def select_relevant_from_candidates(
        cls,
        *,
        candidates: list[tuple[Any, str]],
        message_content: str,
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
        limit: int = 8,
    ) -> list[AppliedMemory]:
        """
        Select relevant memories and resolve key conflicts by hierarchy.
        """
        entries, _ = cls._select_relevant_with_diagnostics(
            candidates=candidates,
            message_content=message_content,
            preferred_vendor=preferred_vendor,
            allow_vendor_prompt=allow_vendor_prompt,
            limit=limit,
        )
        return entries

    @classmethod
    def detect_ambiguous_vendors_from_candidates(
        cls,
        *,
        candidates: list[tuple[Any, str]],
        message_content: str,
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
        limit: int = 8,
    ) -> list[str]:
        """
        Return vendor list that requires explicit confirmation in current message.
        """
        _, ambiguous_vendors = cls._select_relevant_with_diagnostics(
            candidates=candidates,
            message_content=message_content,
            preferred_vendor=preferred_vendor,
            allow_vendor_prompt=allow_vendor_prompt,
            limit=limit,
        )
        return ambiguous_vendors

    @classmethod
    def _select_relevant_with_diagnostics(
        cls,
        *,
        candidates: list[tuple[Any, str]],
        message_content: str,
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
        limit: int = 8,
    ) -> tuple[list[AppliedMemory], list[str]]:
        """
        Select relevant memories and return vendor ambiguity diagnostics.
        """
        normalized_message = cls._normalize_text(message_content)
        message_tokens = cls._tokenize_text(message_content)
        message_vendors = cls.detect_vendors_in_text(message_content)
        normalized_preferred_vendor = cls.normalize_vendor(preferred_vendor)
        if normalized_preferred_vendor:
            message_vendors.add(normalized_preferred_vendor)
        grouped: dict[str, list[tuple[Any, str, int, int]]] = {}
        ambiguous_vendors: set[str] = set()

        for row, origin in candidates:
            scope = str(getattr(row, "scope", ""))
            scope_priority = SCOPE_PRIORITY.get(scope, 0)
            if scope_priority == 0:
                continue

            scope_name_raw = getattr(row, "scope_name", None)
            scope_name = str(scope_name_raw) if scope_name_raw is not None else None
            scope_name_match = False
            if scope_name:
                scope_name_match = cls._normalize_text(scope_name) in normalized_message

            memory_key = str(getattr(row, "memory_key", ""))
            memory_key_normalized = cls._normalize_key(memory_key)
            key_match = bool(memory_key_normalized and memory_key_normalized in normalized_message)
            key_token_match_count = cls._token_overlap(
                message_tokens=message_tokens,
                candidate_text=memory_key,
            )

            tags = cls._normalize_tags(getattr(row, "tags", None))
            tag_match_count = sum(1 for tag in tags if tag in normalized_message)
            tag_token_match_count = cls._token_overlap(
                message_tokens=message_tokens,
                candidate_tokens=tags,
            )
            value_token_match_count = cls._token_overlap(
                message_tokens=message_tokens,
                candidate_text=str(getattr(row, "memory_value", "")),
            )
            memory_vendors = cls._detect_memory_vendors(
                memory_key=memory_key,
                memory_value=str(getattr(row, "memory_value", "")),
                tags=tags,
            )

            include = scope in {MemoryScope.GLOBAL.value, "system"} or scope_name_match
            if not include:
                continue
            if memory_vendors:
                if message_vendors:
                    if not (memory_vendors & message_vendors):
                        continue
                else:
                    if (
                        scope_name_match
                        or key_match
                        or key_token_match_count > 0
                        or tag_match_count > 0
                        or tag_token_match_count > 0
                        or value_token_match_count > 0
                    ):
                        if allow_vendor_prompt:
                            ambiguous_vendors.update(memory_vendors)
                    continue

            relevance = scope_priority
            if scope_name_match:
                relevance += 5
            if key_match:
                relevance += 3
            relevance += min(key_token_match_count, 2)
            relevance += min(value_token_match_count, 1)
            relevance += min(tag_match_count, 2)
            relevance += min(tag_token_match_count, 2)
            if memory_vendors and message_vendors and (memory_vendors & message_vendors):
                relevance += 2

            key_group = memory_key.lower()
            grouped.setdefault(key_group, []).append(
                (row, origin, relevance, scope_priority)
            )

        selected_with_score: list[tuple[AppliedMemory, int, int, datetime]] = []
        for grouped_candidates in grouped.values():
            best_row = max(
                grouped_candidates,
                key=lambda item: (
                    item[2],  # relevance
                    item[3],  # scope priority
                    int(getattr(item[0], "version", 1)),
                    getattr(item[0], "updated_at", datetime.min),
                    getattr(item[0], "created_at", datetime.min),
                ),
            )
            row, origin, relevance, scope_priority = best_row
            selected_with_score.append(
                (
                    AppliedMemory(
                        memory_id=getattr(row, "id"),
                        origin=origin,
                        scope=getattr(row, "scope"),
                        scope_name=getattr(row, "scope_name"),
                        memory_key=getattr(row, "memory_key"),
                        memory_value=getattr(row, "memory_value"),
                        version=int(getattr(row, "version", 1)),
                        expires_at=getattr(row, "expires_at"),
                    ),
                    relevance,
                    scope_priority,
                    getattr(row, "updated_at", datetime.min),
                )
            )

        selected_with_score.sort(
            key=lambda item: (item[1], item[2], item[3]),
            reverse=True,
        )
        return [item[0] for item in selected_with_score[:limit]], sorted(ambiguous_vendors)

    async def _ensure_workspace_identity_is_available(
        self,
        *,
        workspace_id: UUID,
        scope: str,
        scope_name: str | None,
        memory_key: str,
        exclude_memory_id: UUID | None = None,
    ) -> None:
        self._validate_scope_fields(scope=scope, scope_name=scope_name)
        stmt = select(NetworkMemory).where(
            NetworkMemory.workspace_id == workspace_id,
            NetworkMemory.scope == scope,
            NetworkMemory.scope_name == scope_name,
            NetworkMemory.memory_key == memory_key,
            NetworkMemory.is_active.is_(True),
        )
        existing = (await self._safe_execute(stmt)).scalar_one_or_none()
        if existing is None:
            return
        if exclude_memory_id is not None and existing.id == exclude_memory_id:
            return
        raise MemoryServiceError(
            "Ja existe uma memoria ativa com mesmo escopo e chave.",
            code="memory_conflict",
        )

    async def _ensure_system_identity_is_available(
        self,
        *,
        memory_key: str,
        exclude_memory_id: UUID | None = None,
    ) -> None:
        stmt = select(SystemMemory).where(
            SystemMemory.scope == "system",
            SystemMemory.scope_name.is_(None),
            SystemMemory.memory_key == memory_key,
            SystemMemory.is_active.is_(True),
        )
        existing = (await self._safe_execute(stmt)).scalar_one_or_none()
        if existing is None:
            return
        if exclude_memory_id is not None and existing.id == exclude_memory_id:
            return
        raise MemoryServiceError(
            "Ja existe uma memoria de sistema ativa com mesmo escopo e chave.",
            code="memory_conflict",
        )

    @staticmethod
    def _apply_common_memory_updates(
        *,
        memory: Any,
        payload: MemoryUpdate,
    ) -> bool:
        changed = False
        now = datetime.utcnow()

        scope = payload.scope.value if payload.scope is not None else memory.scope
        scope_name = (
            payload.scope_name
            if "scope_name" in payload.model_fields_set
            else memory.scope_name
        )
        MemoryService._validate_scope_fields(scope=scope, scope_name=scope_name)

        if payload.scope is not None and memory.scope != scope:
            memory.scope = scope
            changed = True

        if "scope_name" in payload.model_fields_set and memory.scope_name != scope_name:
            memory.scope_name = scope_name
            changed = True

        if payload.memory_key is not None and payload.memory_key != memory.memory_key:
            memory.memory_key = payload.memory_key
            changed = True

        if payload.memory_value is not None and payload.memory_value != memory.memory_value:
            memory.memory_value = payload.memory_value
            changed = True

        if payload.tags is not None and payload.tags != memory.tags:
            memory.tags = payload.tags
            changed = True

        if payload.clear_ttl:
            if memory.ttl_seconds is not None or memory.expires_at is not None:
                memory.ttl_seconds = None
                memory.expires_at = None
                changed = True
        elif payload.ttl_seconds is not None:
            expires_at = MemoryService._resolve_expiration(now=now, ttl_seconds=payload.ttl_seconds)
            if memory.ttl_seconds != payload.ttl_seconds or memory.expires_at != expires_at:
                memory.ttl_seconds = payload.ttl_seconds
                memory.expires_at = expires_at
                changed = True

        if changed:
            memory.version = int(getattr(memory, "version", 1)) + 1

        return changed

    @staticmethod
    def _apply_system_memory_updates(
        *,
        memory: Any,
        payload: SystemMemoryUpdate,
    ) -> bool:
        changed = False
        now = datetime.utcnow()

        # System-level memories are fixed as scope=system (no scope_name dimension).
        if memory.scope != "system":
            memory.scope = "system"
            changed = True
        if memory.scope_name is not None:
            memory.scope_name = None
            changed = True

        if payload.memory_key is not None and payload.memory_key != memory.memory_key:
            memory.memory_key = payload.memory_key
            changed = True

        if payload.memory_value is not None and payload.memory_value != memory.memory_value:
            memory.memory_value = payload.memory_value
            changed = True

        if payload.tags is not None and payload.tags != memory.tags:
            memory.tags = payload.tags
            changed = True

        if payload.clear_ttl:
            if memory.ttl_seconds is not None or memory.expires_at is not None:
                memory.ttl_seconds = None
                memory.expires_at = None
                changed = True
        elif payload.ttl_seconds is not None:
            expires_at = MemoryService._resolve_expiration(now=now, ttl_seconds=payload.ttl_seconds)
            if memory.ttl_seconds != payload.ttl_seconds or memory.expires_at != expires_at:
                memory.ttl_seconds = payload.ttl_seconds
                memory.expires_at = expires_at
                changed = True

        if changed:
            memory.version = int(getattr(memory, "version", 1)) + 1

        return changed

    @staticmethod
    def _validate_scope_fields(*, scope: str, scope_name: str | None) -> None:
        valid_scopes = {MemoryScope.GLOBAL.value, MemoryScope.SITE.value, MemoryScope.DEVICE.value}
        if scope not in valid_scopes:
            raise MemoryServiceError("Escopo de memoria invalido.", code="scope_invalid")
        if scope == MemoryScope.GLOBAL.value and scope_name is not None:
            raise MemoryServiceError("scope_name deve ser nulo para escopo global.", code="scope_invalid")
        if scope in {MemoryScope.SITE.value, MemoryScope.DEVICE.value} and not scope_name:
            raise MemoryServiceError("scope_name e obrigatorio para escopos site/device.", code="scope_invalid")

    @staticmethod
    def _resolve_expiration(*, now: datetime, ttl_seconds: int | None) -> datetime | None:
        if ttl_seconds is None:
            return None
        return now + timedelta(seconds=ttl_seconds)

    async def _safe_execute(self, statement: Any):
        """
        Execute DB statement translating missing memory tables into actionable domain errors.
        """
        try:
            return await self._db.execute(statement)
        except Exception as exc:
            self._raise_if_memory_schema_missing(exc)
            raise

    @staticmethod
    def _raise_if_memory_schema_missing(exc: Exception) -> None:
        """
        Convert missing memory table errors into a deterministic service error.
        """
        detail = str(exc).lower()
        missing_network = "network_memories" in detail and (
            "does not exist" in detail or "undefinedtable" in detail
        )
        missing_system = "system_memories" in detail and (
            "does not exist" in detail or "undefinedtable" in detail
        )
        if missing_network or missing_system:
            raise MemoryServiceError(
                "Schema de memorias indisponivel. Execute `alembic upgrade head`.",
                code="memory_schema_missing",
            ) from exc

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.strip().lower().split())

    @classmethod
    def _normalize_key(cls, value: str) -> str:
        normalized = cls._normalize_text(value).replace("_", " ").replace("-", " ")
        return " ".join(normalized.split())

    @classmethod
    def _normalize_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [cls._normalize_text(str(tag)) for tag in value if cls._normalize_text(str(tag))]
        if isinstance(value, dict):
            return [cls._normalize_text(str(tag)) for tag in value.keys() if cls._normalize_text(str(tag))]
        normalized = cls._normalize_text(str(value))
        return [normalized] if normalized else []

    @classmethod
    def build_vendor_ambiguity_prompt(cls, vendors: list[str]) -> str | None:
        """
        Build a direct clarification prompt when vendor-specific memory is ambiguous.
        """
        if not vendors:
            return None

        supported = ", ".join(cls.supported_vendor_display_names())
        return (
            "Antes de aplicar memorias especificas de vendor, preciso confirmar o fabricante "
            f"do equipamento. Qual vendor devo considerar? Opcoes suportadas: {supported}."
        )

    @classmethod
    def _detect_memory_vendors(
        cls,
        *,
        memory_key: str,
        memory_value: str,
        tags: list[str],
    ) -> set[str]:
        detected: set[str] = set()
        for fragment in [memory_key, memory_value, *tags]:
            detected.update(cls.detect_vendors_in_text(fragment))
        return detected

    @classmethod
    def detect_vendors_in_text(cls, value: str | None) -> set[str]:
        """
        Detect canonical vendor identifiers from free text.
        """
        normalized = cls._normalize_key(value or "")
        if not normalized:
            return set()

        tokens = set(normalized.split())
        detected: set[str] = set()
        for vendor, hints in VENDOR_HINTS.items():
            for hint in hints:
                normalized_hint = cls._normalize_key(hint)
                if not normalized_hint:
                    continue

                if " " in normalized_hint:
                    if normalized_hint in normalized:
                        detected.add(vendor)
                        break
                elif normalized_hint in tokens:
                    detected.add(vendor)
                    break
        return detected

    @classmethod
    def normalize_vendor(cls, value: str | None) -> str | None:
        """
        Normalize one vendor token into canonical value.
        """
        if not value:
            return None

        normalized_value = cls._normalize_key(value)
        if normalized_value in VENDOR_HINTS:
            return normalized_value

        detected = cls.detect_vendors_in_text(value)
        if len(detected) == 1:
            return next(iter(detected))
        return None

    @classmethod
    def supported_vendors(cls) -> list[str]:
        """
        Return canonical vendor identifiers supported by vendor-aware memory routing.
        """
        return [vendor for vendor in SUPPORTED_VENDOR_ORDER if vendor in VENDOR_HINTS]

    @classmethod
    def supported_vendor_display_names(cls) -> list[str]:
        """
        Return supported vendor labels for user-facing prompts.
        """
        return [cls._vendor_display_name(vendor) for vendor in cls.supported_vendors()]

    @staticmethod
    def _vendor_display_name(vendor: str) -> str:
        normalized = vendor.strip().lower()
        if normalized == "cisco":
            return "Cisco"
        if normalized == "juniper":
            return "Juniper"
        if normalized == "arista":
            return "Arista"
        if normalized == "mikrotik":
            return "MikroTik"
        return vendor.strip().title()

    @classmethod
    def _token_overlap(
        cls,
        *,
        message_tokens: set[str],
        candidate_text: str | None = None,
        candidate_tokens: list[str] | None = None,
    ) -> int:
        """
        Count token overlaps between user message and candidate memory fragments.
        """
        tokens: set[str] = set()
        if candidate_text is not None:
            tokens.update(cls._tokenize_text(candidate_text))
        if candidate_tokens is not None:
            for candidate in candidate_tokens:
                tokens.update(cls._tokenize_text(candidate))
        return len(tokens & message_tokens)

    @classmethod
    def _tokenize_text(cls, value: str | None) -> set[str]:
        """
        Normalize text into comparable tokens with simple plural folding.
        """
        normalized = cls._normalize_key(value or "")
        if not normalized:
            return set()

        raw_tokens = normalized.split()
        tokens: set[str] = set()
        for raw_token in raw_tokens:
            token = cls._strip_accents(raw_token)
            if not token or token in cls._stopwords():
                continue

            tokens.add(token)
            folded = cls._fold_plural(token)
            if folded != token:
                tokens.add(folded)
        return tokens

    @staticmethod
    def _strip_accents(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @staticmethod
    def _fold_plural(token: str) -> str:
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            return token[:-1]
        return token

    @staticmethod
    def _stopwords() -> set[str]:
        return {
            "a",
            "o",
            "os",
            "as",
            "de",
            "do",
            "da",
            "dos",
            "das",
            "e",
            "em",
            "no",
            "na",
            "nos",
            "nas",
            "para",
            "por",
            "com",
            "sem",
            "uma",
            "um",
            "the",
            "to",
            "for",
            "and",
            "of",
            "in",
            "on",
        }
