"""
Chat service — orchestrates message persistence + agent invocation + streaming.
"""
import asyncio
from datetime import datetime
from typing import AsyncGenerator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.network_engineer_agent import NetworkEngineerAgent
from app.agents.tools import get_agent_tools
from app.core.config import settings
from app.core.security import decrypt_api_key
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.attachment_context_service import (
    AttachmentContextResolution,
    AttachmentContextService,
    ResolvedAttachment,
)
from app.services.llm_client import LLMProviderError
from app.services.memory_service import MemoryContextResolution, MemoryService
from app.services.system_settings_service import SystemSettingsService
from app.services.playbook_service import PlaybookResponse, PlaybookService
from app.services.usage_tracking_service import UsageTrackingService


class ChatServiceError(Exception):
    """Domain error with a machine-readable code."""

    def __init__(self, detail: str, code: str = "chat_error") -> None:
        self.detail = detail
        self.code = code
        super().__init__(detail)


class ChatService:
    """
    Orchestrates a single chat turn:
    1. Validate conversation ownership
    2. Save user message (flush)
    3. Load recent history
    4. Invoke agent with streaming (tools + text)
    5. Accumulate full response, save assistant message
    6. Commit
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def process_user_message(
        self,
        user: User,
        conversation_id: UUID,
        content: str,
        attachment_document_ids: list[UUID] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Process a user message end-to-end with streaming.

        Yields dicts matching the WS protocol:
            {"type": "stream_start", "message_id": "..."}
            {"type": "tool_call_start", "tool_call_id": "...", "tool_name": "...", "tool_input": "..."}
            {"type": "tool_call_state", "tool_call_id": "...", "tool_name": "...", "status": "..."}
            {"type": "tool_call_end", "tool_call_id": "...", "tool_name": "...", "result_preview": "...", "duration_ms": ...}
            {"type": "stream_chunk", "content": "..."}
            {"type": "stream_end",   "message_id": "...", "tokens_used": ...}

        On error mid-stream, yields:
            {"type": "error", "code": "...", "detail": "..."}
        """
        # 1. Validate conversation ownership
        conversation = await self._get_owned_conversation(conversation_id, user.id)

        # 2. Validate content length
        if len(content) > settings.CHAT_MAX_MESSAGE_LENGTH:
            raise ChatServiceError(
                f"Mensagem excede limite de {settings.CHAT_MAX_MESSAGE_LENGTH} caracteres.",
                code="message_too_long",
            )

        # 3. Resolve LLM provider (BYO-LLM ou free fallback via DB)
        if user.llm_provider and user.encrypted_api_key:
            provider_name = user.llm_provider
            api_key = decrypt_api_key(user.encrypted_api_key)
            using_free_llm = False
        else:
            free_enabled = await SystemSettingsService.get(self._db, "free_llm_enabled")
            if free_enabled == "true":
                free_key = await SystemSettingsService.get(self._db, "free_llm_api_key")
                if free_key:
                    provider_name = (
                        await SystemSettingsService.get(self._db, "free_llm_provider")
                    ) or "google"
                    api_key = free_key
                    using_free_llm = True
                else:
                    raise ChatServiceError(
                        "Configure seu provedor LLM e API key no perfil antes de usar o chat.",
                        code="llm_not_configured",
                    )
            else:
                raise ChatServiceError(
                    "Configure seu provedor LLM e API key no perfil antes de usar o chat.",
                    code="llm_not_configured",
                )

        # 4. Resolve attachment context for this turn (best-effort).
        attachment_resolution = await self._resolve_attachment_context(
            user_id=user.id,
            conversation_id=conversation_id,
            content=content,
            attachment_document_ids=attachment_document_ids,
        )
        active_vendor, vendor_source, suppress_vendor_prompt, raw_vendor = await self._resolve_active_vendor(
            conversation_id=conversation_id,
            content=content,
        )
        user_vendor_metadata: dict | None = None
        if vendor_source:
            user_vendor_metadata = {
                "vendor_context": {
                    "active_vendor": active_vendor,
                    "raw_vendor": raw_vendor or active_vendor,
                    "supported": bool(active_vendor),
                    "source": vendor_source,
                }
            }
        user_message_metadata = self._merge_message_metadata(
            attachment_resolution.user_message_metadata,
            user_vendor_metadata,
        )

        # 5. Save user message (flush to get ID, no commit yet)
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=content,
            message_metadata=user_message_metadata,
        )
        self._db.add(user_msg)
        await self._db.flush()

        # 5b. Auto-generate title from first user message
        title_event = None
        if conversation.title == "Nova Conversa":
            new_title = self._generate_title(content)
            conversation.title = new_title
            await self._db.flush()
            title_event = {"type": "title_updated", "title": new_title}

        attachment_metadata: dict | None = None
        if attachment_resolution.resolved_attachment is not None:
            attachment_metadata = {
                "attachment_context": {
                    "status": "resolved",
                    "resolved_attachment": self._serialize_resolved_attachment(
                        attachment_resolution.resolved_attachment
                    ),
                }
            }
        elif attachment_resolution.ambiguity_candidates:
            attachment_metadata = {
                "attachment_context": {
                    "status": "ambiguous",
                    "candidates": [
                        self._serialize_resolved_attachment(candidate)
                        for candidate in attachment_resolution.ambiguity_candidates
                    ],
                }
            }

        if attachment_resolution.ambiguity_prompt:
            async for event in self._emit_direct_response(
                conversation=conversation,
                conversation_id=conversation_id,
                user=user,
                content=attachment_resolution.ambiguity_prompt,
                metadata=attachment_metadata,
                title_event=title_event,
            ):
                yield event
            return

        playbook_response = await self._try_handle_playbook(conversation_id, content)
        if playbook_response is not None:
            playbook_metadata = {"playbook": playbook_response.metadata}
            if attachment_metadata:
                playbook_metadata.update(attachment_metadata)
            async for event in self._emit_direct_response(
                conversation=conversation,
                conversation_id=conversation_id,
                user=user,
                content=playbook_response.content,
                metadata=playbook_metadata,
                title_event=title_event,
            ):
                yield event
            return

        # 6. Load conversation history
        history = await self._load_history(conversation_id)
        memory_resolution = await self._resolve_memory_context(
            user_id=user.id,
            content_for_agent=attachment_resolution.content_for_agent,
            preferred_vendor=active_vendor,
            allow_vendor_prompt=not suppress_vendor_prompt,
        )
        if memory_resolution.vendor_ambiguity_prompt:
            ambiguity_metadata: dict = {
                "memory_context": {
                    "status": "vendor_ambiguous",
                    "vendors": memory_resolution.ambiguous_vendors,
                    "supported_vendors": MemoryService.supported_vendors(),
                }
            }
            if attachment_metadata:
                ambiguity_metadata.update(attachment_metadata)
            async for event in self._emit_direct_response(
                conversation=conversation,
                conversation_id=conversation_id,
                user=user,
                content=memory_resolution.vendor_ambiguity_prompt,
                metadata=ambiguity_metadata,
                title_event=title_event,
            ):
                yield event
            return

        if history and history[-1]["role"] == "user":
            enriched_content = attachment_resolution.content_for_agent
            if memory_resolution.context_block:
                enriched_content = (
                    f"{enriched_content}\n\n{memory_resolution.context_block}"
                )
            history[-1]["content"] = enriched_content

        # 7. Build agent with tools
        try:
            model_override = conversation.model_used
            if using_free_llm and not model_override:
                model_override = (
                    await SystemSettingsService.get(self._db, "free_llm_model")
                ) or settings.DEFAULT_LLM_MODEL_GOOGLE
            tools = get_agent_tools(
                db=self._db,
                user_id=user.id,
                user_role=getattr(user, "role", None),
                plan_tier=getattr(user, "plan_tier", None),
                user_message=content,
            )
            agent = NetworkEngineerAgent(
                provider_name=provider_name,
                api_key=api_key,
                model=model_override,
                tools=tools,
            )
        except Exception as exc:
            await self._db.rollback()
            raise ChatServiceError(
                f"Erro ao configurar provedor LLM: {exc}",
                code="llm_init_error",
            )

        # 8. Stream response
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="",
        )
        self._db.add(assistant_msg)
        await self._db.flush()

        stream_start_event: dict = {
            "type": "stream_start",
            "message_id": str(assistant_msg.id),
        }
        if using_free_llm:
            stream_start_event["using_free_llm"] = True
        yield stream_start_event

        if title_event:
            yield title_event

        accumulated = ""
        tool_calls_log: list[dict] = []
        active_tool_calls: dict[str, dict] = {}
        try:
            async for event in agent.stream_response(history):
                event_type = event.get("type")

                if event_type == "text":
                    accumulated += event["content"]
                    yield {"type": "stream_chunk", "content": event["content"]}

                elif event_type == "tool_call_start":
                    tool_call_id = str(event.get("tool_call_id", ""))
                    tool_name = str(event.get("tool_name", "unknown"))
                    tool_calls_log.append({
                        "tool_call_id": tool_call_id,
                        "tool": tool_name,
                        "input": event["tool_input"],
                        "status": "running",
                    })
                    active_tool_calls[tool_call_id] = {"tool_name": tool_name}
                    yield {
                        "type": "tool_call_start",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "tool_input": event["tool_input"],
                    }
                    # Estado detalhado para jobs assincronos (MVP #14).
                    yield {
                        "type": "tool_call_state",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "status": "queued",
                    }
                    yield {
                        "type": "tool_call_state",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "status": "running",
                    }

                elif event_type == "tool_call_progress":
                    tool_call_id = str(event.get("tool_call_id", ""))
                    tool_name = str(event.get("tool_name", "unknown"))
                    progress_pct = event.get("progress_pct")
                    elapsed_ms = int(event.get("elapsed_ms", 0) or 0)
                    eta_ms = event.get("eta_ms")
                    tc = self._find_tool_call_log(
                        tool_calls_log=tool_calls_log,
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                    )
                    if tc is not None:
                        tc["status"] = "running"
                        tc["elapsed_ms"] = elapsed_ms
                        if progress_pct is not None:
                            tc["progress_pct"] = int(progress_pct)
                        if eta_ms is not None:
                            tc["eta_ms"] = int(eta_ms)

                    yield {
                        "type": "tool_call_state",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "status": "progress",
                        "progress_pct": progress_pct,
                        "elapsed_ms": elapsed_ms,
                        "eta_ms": eta_ms,
                    }

                elif event_type == "tool_call_end":
                    tool_call_id = str(event.get("tool_call_id", ""))
                    tool_name = str(event.get("tool_name", "unknown"))
                    result_preview = str(event.get("result_preview", ""))
                    duration_ms = int(event.get("duration_ms", 0) or 0)
                    full_result = event.get("full_result")
                    status = (
                        "failed"
                        if self._is_tool_result_failure(result_preview, full_result)
                        else "completed"
                    )
                    tc = self._find_tool_call_log(
                        tool_calls_log=tool_calls_log,
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                    )
                    if tc is not None:
                        tc["result_preview"] = result_preview
                        tc["duration_ms"] = duration_ms
                        tc["status"] = status
                        if status == "completed":
                            tc["progress_pct"] = 100
                        if full_result:
                            tc["full_result"] = full_result
                    active_tool_calls.pop(tool_call_id, None)

                    yield {
                        "type": "tool_call_end",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "result_preview": result_preview,
                        "duration_ms": duration_ms,
                    }
                    state_event: dict = {
                        "type": "tool_call_state",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "status": status,
                        "duration_ms": duration_ms,
                    }
                    if status == "completed":
                        state_event["progress_pct"] = 100
                    else:
                        state_event["detail"] = (
                            "Tool reportou erro/timeout. Revise parâmetros e tente novamente."
                        )
                    yield state_event
        except asyncio.CancelledError:
            await self._db.rollback()
            raise
        except LLMProviderError as exc:
            await self._db.rollback()
            async for failure_event in self._emit_failed_tool_states(
                active_tool_calls=active_tool_calls,
                detail="Execucao interrompida por erro no provedor LLM.",
            ):
                yield failure_event
            yield {
                "type": "error",
                "code": "llm_error",
                "detail": str(exc),
            }
            return
        except Exception as exc:
            await self._db.rollback()
            async for failure_event in self._emit_failed_tool_states(
                active_tool_calls=active_tool_calls,
                detail="Execucao interrompida por erro interno durante o streaming.",
            ):
                yield failure_event
            yield {
                "type": "error",
                "code": "stream_error",
                "detail": f"Erro durante streaming: {exc}",
            }
            return

        # 9. Persist assistant message
        assistant_msg.content = accumulated
        assistant_metadata: dict = {}
        if tool_calls_log:
            assistant_metadata["tool_calls"] = tool_calls_log
        if attachment_metadata:
            assistant_metadata.update(attachment_metadata)
        if memory_resolution.entries:
            assistant_metadata["memory_context"] = MemoryService.build_context_metadata(
                memory_resolution.entries
            )
        assistant_msg.message_metadata = assistant_metadata or None
        conversation.updated_at = datetime.utcnow()

        try:
            await self._db.commit()
        except asyncio.CancelledError:
            await self._db.rollback()
            raise
        except Exception as exc:
            await self._db.rollback()
            yield {
                "type": "error",
                "code": "db_error",
                "detail": f"Erro ao salvar resposta: {exc}",
            }
            return

        # 10. Track usage metrics
        try:
            await UsageTrackingService.increment_messages(self._db, user.id)
            await self._db.commit()
        except Exception:
            pass  # Non-critical — don't fail the response

        stream_end_event = {
            "type": "stream_end",
            "message_id": str(assistant_msg.id),
            "tokens_used": None,
        }
        if assistant_msg.message_metadata is not None:
            stream_end_event["metadata"] = assistant_msg.message_metadata
        yield stream_end_event

    async def _try_handle_playbook(
        self,
        conversation_id: UUID,
        content: str,
    ) -> PlaybookResponse | None:
        """Try handling message as guided playbook flow."""
        try:
            playbook = PlaybookService()
            return await playbook.handle_message(
                conversation_id=conversation_id,
                content=content,
            )
        except Exception:
            # Never block chat if playbook subsystem fails.
            return None

    async def _emit_direct_response(
        self,
        conversation: Conversation,
        conversation_id: UUID,
        user: User,
        content: str,
        metadata: dict | None = None,
        title_event: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Emit a non-LLM assistant response through stream protocol and persist it.
        """
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="",
        )
        self._db.add(assistant_msg)
        await self._db.flush()

        yield {"type": "stream_start", "message_id": str(assistant_msg.id)}
        if title_event:
            yield title_event
        if content:
            yield {"type": "stream_chunk", "content": content}

        assistant_msg.content = content
        assistant_msg.message_metadata = metadata
        conversation.updated_at = datetime.utcnow()

        try:
            await self._db.commit()
        except asyncio.CancelledError:
            await self._db.rollback()
            raise
        except Exception as exc:
            await self._db.rollback()
            yield {
                "type": "error",
                "code": "db_error",
                "detail": f"Erro ao salvar resposta: {exc}",
            }
            return

        try:
            await UsageTrackingService.increment_messages(self._db, user.id)
            await self._db.commit()
        except Exception:
            pass

        stream_end_event = {
            "type": "stream_end",
            "message_id": str(assistant_msg.id),
            "tokens_used": None,
        }
        if metadata is not None:
            stream_end_event["metadata"] = metadata
        yield stream_end_event

    async def _resolve_attachment_context(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        attachment_document_ids: list[UUID] | None,
    ) -> AttachmentContextResolution:
        """
        Resolve attachment references for current turn.

        Never raises: if resolver fails, falls back to original content.
        """
        try:
            resolver = AttachmentContextService(self._db)
            return await resolver.resolve_context(
                user_id=user_id,
                conversation_id=conversation_id,
                content=content,
                explicit_document_ids=attachment_document_ids,
            )
        except Exception:
            return AttachmentContextResolution(content_for_agent=content)

    async def _resolve_memory_context(
        self,
        *,
        user_id: UUID,
        content_for_agent: str,
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
    ) -> MemoryContextResolution:
        """
        Resolve persistent memory context for current turn.

        Never raises: if resolver fails, falls back to empty context.
        """
        try:
            service = MemoryService(self._db)
            return await service.resolve_chat_context(
                user_id=user_id,
                message_content=content_for_agent,
                preferred_vendor=preferred_vendor,
                allow_vendor_prompt=allow_vendor_prompt,
            )
        except Exception:
            return MemoryContextResolution(
                entries=[],
                context_block=None,
                vendor_ambiguity_prompt=None,
                ambiguous_vendors=[],
            )

    async def _resolve_active_vendor(
        self,
        *,
        conversation_id: UUID,
        content: str,
    ) -> tuple[str | None, str | None, bool, str | None]:
        """
        Resolve active vendor for current turn from explicit message or persisted context.

        Returns:
            preferred_vendor: Canonical supported vendor (or None).
            source: Metadata source label.
            suppress_vendor_prompt: Skip vendor clarification prompts for this turn.
            raw_vendor: Raw user-facing vendor value persisted in metadata.
        """
        explicit_vendors = sorted(MemoryService.detect_vendors_in_text(content))
        if len(explicit_vendors) == 1:
            return explicit_vendors[0], "explicit", False, explicit_vendors[0]
        if len(explicit_vendors) > 1:
            return None, None, False, None

        awaiting_confirmation = await self._is_waiting_vendor_confirmation(
            conversation_id=conversation_id,
        )
        if awaiting_confirmation:
            raw_vendor = self._extract_vendor_answer(content)
            if raw_vendor:
                normalized_vendor = MemoryService.normalize_vendor(raw_vendor)
                if normalized_vendor:
                    return normalized_vendor, "explicit", False, raw_vendor
                return None, "explicit_unsupported", True, raw_vendor

        persisted_vendor = await self._load_persisted_vendor_context(
            conversation_id=conversation_id,
        )
        if persisted_vendor is not None:
            if persisted_vendor.get("supported") is False:
                raw_vendor = persisted_vendor.get("raw_vendor")
                return None, "conversation_unsupported", True, str(raw_vendor) if raw_vendor else None

            vendor = persisted_vendor.get("active_vendor")
            if isinstance(vendor, str) and vendor:
                raw_vendor = persisted_vendor.get("raw_vendor")
                return vendor, "conversation", False, str(raw_vendor) if raw_vendor else vendor

        return None, None, False, None

    async def _load_persisted_vendor_context(
        self,
        *,
        conversation_id: UUID,
    ) -> dict | None:
        """
        Load most recent persisted vendor context from conversation message metadata.
        """
        try:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(settings.CHAT_HISTORY_LIMIT)
            )
            result = await self._db.execute(stmt)
            recent_messages = result.scalars().all()
        except Exception:
            return None

        for message in recent_messages:
            metadata = message.message_metadata
            if not isinstance(metadata, dict):
                continue

            vendor_context = metadata.get("vendor_context")
            if not isinstance(vendor_context, dict):
                continue

            supported = vendor_context.get("supported")
            if supported is False:
                raw_vendor = vendor_context.get("raw_vendor")
                normalized_raw = " ".join(str(raw_vendor).split()) if raw_vendor else None
                return {
                    "supported": False,
                    "raw_vendor": normalized_raw,
                }

            vendor_raw = vendor_context.get("active_vendor")
            vendor = MemoryService.normalize_vendor(str(vendor_raw)) if vendor_raw else None
            if vendor:
                raw_vendor = vendor_context.get("raw_vendor")
                normalized_raw = " ".join(str(raw_vendor).split()) if raw_vendor else vendor
                return {
                    "supported": True,
                    "active_vendor": vendor,
                    "raw_vendor": normalized_raw,
                }
        return None

    async def _is_waiting_vendor_confirmation(
        self,
        *,
        conversation_id: UUID,
    ) -> bool:
        """
        Check whether previous assistant turn asked for vendor confirmation.
        """
        try:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            result = await self._db.execute(stmt)
            latest_message = result.scalar_one_or_none()
        except Exception:
            return False

        if latest_message is None or getattr(latest_message, "role", "") != "assistant":
            return False

        metadata = latest_message.message_metadata
        if not isinstance(metadata, dict):
            return False

        memory_context = metadata.get("memory_context")
        if not isinstance(memory_context, dict):
            return False

        return memory_context.get("status") == "vendor_ambiguous"

    @staticmethod
    def _extract_vendor_answer(content: str) -> str | None:
        """
        Extract a compact vendor answer from a clarification response.
        """
        normalized = " ".join(content.strip().split())
        if not normalized:
            return None
        if len(normalized.split()) > 6:
            return None
        if len(normalized) > 80:
            return None
        return normalized

    @staticmethod
    def _merge_message_metadata(
        base: dict | None,
        extra: dict | None,
    ) -> dict | None:
        """
        Merge two flat metadata payloads while preserving nested dicts by top-level key.
        """
        merged: dict = {}
        if isinstance(base, dict):
            merged.update(base)
        if isinstance(extra, dict):
            for key, value in extra.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    nested = dict(merged[key])
                    nested.update(value)
                    merged[key] = nested
                else:
                    merged[key] = value
        return merged or None

    @staticmethod
    def _serialize_resolved_attachment(attachment: ResolvedAttachment) -> dict:
        return {
            "document_id": str(attachment.document_id),
            "filename": attachment.filename,
            "file_type": attachment.file_type,
            "source": attachment.source,
        }

    @staticmethod
    def _find_tool_call_log(
        *,
        tool_calls_log: list[dict],
        tool_call_id: str,
        tool_name: str,
    ) -> dict | None:
        for tc in reversed(tool_calls_log):
            if tool_call_id and tc.get("tool_call_id") == tool_call_id:
                return tc
        for tc in reversed(tool_calls_log):
            if tc.get("tool") == tool_name:
                return tc
        return None

    @staticmethod
    def _is_tool_result_failure(result_preview: str, full_result: object) -> bool:
        preview = result_preview.lower().strip()
        full_text = str(full_result).lower().strip() if full_result is not None else ""
        candidates = [preview, full_text]
        return any(
            text.startswith("error")
            or "timeout" in text
            or "not found" in text
            for text in candidates
            if text
        )

    async def _emit_failed_tool_states(
        self,
        *,
        active_tool_calls: dict[str, dict],
        detail: str,
    ) -> AsyncGenerator[dict, None]:
        for tool_call_id, state in active_tool_calls.items():
            yield {
                "type": "tool_call_state",
                "tool_call_id": tool_call_id,
                "tool_name": state.get("tool_name", "unknown"),
                "status": "failed",
                "detail": detail,
            }

    async def _get_owned_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Conversation:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        result = await self._db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ChatServiceError(
                "Conversa nao encontrada.",
                code="conversation_not_found",
            )
        return conversation

    @staticmethod
    def _generate_title(content: str, max_length: int = 60) -> str:
        """Generate a conversation title from the first user message."""
        # Remove quebras de linha e espacos extras
        title = " ".join(content.split())
        if len(title) <= max_length:
            return title
        # Trunca na ultima palavra completa
        truncated = title[:max_length].rsplit(" ", 1)[0]
        return truncated + "..."

    async def _load_history(
        self,
        conversation_id: UUID,
    ) -> list[dict]:
        """Load the last N messages as plain dicts for the agent."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        result = await self._db.execute(stmt)
        all_messages = result.scalars().all()

        # Trim to history limit
        recent = all_messages[-settings.CHAT_HISTORY_LIMIT:]
        return [
            {"role": msg.role, "content": msg.content}
            for msg in recent
        ]
