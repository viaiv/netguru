"""
Chat service — orchestrates message persistence + agent invocation + streaming.
"""
import asyncio
import logging
import time
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
from app.models.rag_gap_event import RagGapEvent
from app.models.user import User
from app.models.workspace import Workspace
from app.services.attachment_context_service import (
    AttachmentContextResolution,
    AttachmentContextService,
    ResolvedAttachment,
)
from app.services.llm_model_resolver_service import LLMModelResolverService
from app.services.llm_client import LLMProviderError
from app.services.memory_service import MemoryContextResolution, MemoryService
from app.services.system_settings_service import SystemSettingsService
from app.services.plan_limit_service import PlanLimitError, PlanLimitService
from app.services.playbook_service import PlaybookResponse, PlaybookService
from app.services.usage_tracking_service import UsageTrackingService

logger = logging.getLogger(__name__)


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
        workspace: Workspace,
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

        # 2b. Plan limit enforcement — daily messages and tokens (workspace-level)
        try:
            await PlanLimitService.check_message_limit(self._db, workspace)
            await PlanLimitService.check_token_limit(self._db, workspace)
        except PlanLimitError as exc:
            raise ChatServiceError(
                exc.detail,
                code=exc.code or "plan_limit_exceeded",
            ) from exc

        # 3. Resolve LLM provider (BYO-LLM ou free fallback via DB)
        #    Consulta Plan.features.allow_system_fallback para determinar se
        #    o plano do workspace permite uso do LLM gratuito do sistema.
        plan_allows_fallback = await self._plan_allows_fallback(workspace)
        _plan_model: tuple[str, str] | None = None
        _used_plan_provider = False  # True when plan-specific provider path succeeded
        using_free_llm = False

        if user.llm_provider and user.encrypted_api_key:
            provider_name = user.llm_provider
            api_key = decrypt_api_key(user.encrypted_api_key)
            using_free_llm = False
            # Resolve plan model for BYO-LLM provider match
            _plan = await PlanLimitService.get_workspace_plan(self._db, workspace)
            _plan_model = await LLMModelResolverService.resolve_plan_model(self._db, _plan)
        elif plan_allows_fallback:
            # Try plan-specific provider/model first, then global fallback
            _plan = await PlanLimitService.get_workspace_plan(self._db, workspace)
            _plan_model = await LLMModelResolverService.resolve_plan_model(self._db, _plan)

            if _plan_model:
                _plan_provider, _plan_model_id = _plan_model
                _plan_key = await SystemSettingsService.get(
                    self._db, f"free_llm_api_key_{_plan_provider}"
                )
                if _plan_key:
                    provider_name = _plan_provider
                    api_key = _plan_key
                    using_free_llm = True
                    _used_plan_provider = True

            if not using_free_llm:
                # Global fallback (current behavior)
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
        else:
            raise ChatServiceError(
                "Seu plano requer uma API key propria (BYO-LLM). "
                "Configure seu provedor e API key em Perfil > BYO-LLM.",
                code="byo_required",
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
            workspace_id=workspace.id,
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

        # 7. Build tools + fallback plan
        try:
            model_override = conversation.model_used
            # Validar override contra catalogo ativo
            if model_override:
                from app.models.llm_model import LlmModel
                _valid = (await self._db.execute(
                    select(LlmModel).where(
                        LlmModel.model_id == model_override,
                        LlmModel.is_active.is_(True),
                    )
                )).scalar_one_or_none()
                if _valid is None:
                    logger.warning(
                        "model_override rejected: model=%s user=%s",
                        model_override, user.id,
                    )
                    model_override = None
            if not model_override:
                # Try plan default if plan-specific provider was used or BYO provider matches
                if _plan_model and (_used_plan_provider or _plan_model[0] == provider_name):
                    model_override = _plan_model[1]
                else:
                    model_override = await LLMModelResolverService.resolve_model(
                        self._db,
                        provider_name,
                        legacy_keys=("free_llm_model",) if using_free_llm else (),
                    )
            tools = get_agent_tools(
                db=self._db,
                user_id=user.id,
                workspace_id=workspace.id,
                user_role=getattr(user, "role", None),
                workspace_plan_tier=workspace.plan_tier,
                user_message=content,
            )
            llm_attempts = await self._build_llm_attempt_chain(
                primary_provider=provider_name,
                primary_api_key=api_key,
                primary_model=model_override,
                using_free_llm=using_free_llm,
                plan_allows_fallback=plan_allows_fallback,
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
            "llm_provider": provider_name,
        }
        if using_free_llm:
            stream_start_event["using_free_llm"] = True
        yield stream_start_event

        if title_event:
            yield title_event

        accumulated = ""
        tool_calls_log: list[dict] = []
        active_tool_calls: dict[str, dict] = {}
        llm_attempt_audit: list[dict] = []
        selected_llm_attempt: dict | None = None
        total_tokens_used: int = 0

        total_attempts = len(llm_attempts)
        logger.info(
            "chat_stream user=%s conv=%s attempts=%d providers=%s",
            user.id, conversation_id, total_attempts,
            [(a.get("provider_name"), a.get("model"), a.get("source")) for a in llm_attempts],
        )
        for attempt_index, llm_attempt in enumerate(llm_attempts):
            attempt_started_at = time.monotonic()
            output_emitted = False
            attempt_provider = str(llm_attempt.get("provider_name", "unknown"))
            attempt_model = llm_attempt.get("model")
            attempt_source = str(llm_attempt.get("source", "unknown"))
            logger.debug(
                "chat_stream attempt=%d/%d provider=%s model=%s source=%s",
                attempt_index + 1, total_attempts, attempt_provider, attempt_model, attempt_source,
            )

            try:
                agent = NetworkEngineerAgent(
                    provider_name=attempt_provider,
                    api_key=str(llm_attempt.get("api_key", "")),
                    model=attempt_model if isinstance(attempt_model, str) else None,
                    tools=tools,
                    plan_tier=getattr(user, "plan_tier", None),
                )
            except Exception as exc:
                attempt_duration_ms = int((time.monotonic() - attempt_started_at) * 1000)
                eligible, eligibility_reason = self._is_fallback_eligible_error(exc)
                llm_attempt_audit.append(
                    self._build_llm_attempt_audit_entry(
                        provider_name=attempt_provider,
                        model=attempt_model if isinstance(attempt_model, str) else None,
                        source=attempt_source,
                        status="failed_init",
                        duration_ms=attempt_duration_ms,
                        error=str(exc),
                        eligible_fallback=eligible,
                        eligibility_reason=eligibility_reason,
                    )
                )

                can_retry = eligible and attempt_index < total_attempts - 1
                if can_retry:
                    delay_seconds = self._fallback_delay_seconds(attempt_index)
                    logger.warning(
                        "LLM fallback (init) user=%s conv=%s from=%s/%s reason=%s next_attempt=%s delay=%.2fs",
                        user.id,
                        conversation_id,
                        attempt_provider,
                        attempt_model,
                        eligibility_reason,
                        attempt_index + 2,
                        delay_seconds,
                    )
                    if delay_seconds > 0:
                        await asyncio.sleep(delay_seconds)
                    continue

                await self._db.rollback()
                yield {
                    "type": "error",
                    "code": "llm_init_error",
                    "detail": f"Erro ao configurar provedor LLM: {exc}",
                }
                return

            try:
                async for event in agent.stream_response(history):
                    event_type = event.get("type")

                    if event_type == "text":
                        output_emitted = True
                        accumulated += event["content"]
                        yield {"type": "stream_chunk", "content": event["content"]}

                    elif event_type == "tool_call_start":
                        output_emitted = True
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
                        output_emitted = True
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
                        output_emitted = True
                        tool_call_id = str(event.get("tool_call_id", ""))
                        tool_name = str(event.get("tool_name", "unknown"))
                        result_preview = str(event.get("result_preview", ""))
                        duration_ms = int(event.get("duration_ms", 0) or 0)
                        full_result = event.get("full_result")
                        if "BLOCKED_BY_GUARDRAIL" in result_preview and "confirmation_required" in result_preview:
                            status = "awaiting_confirmation"
                        elif self._is_tool_result_failure(result_preview, full_result):
                            status = "failed"
                        else:
                            status = "completed"
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
                        elif status == "awaiting_confirmation":
                            state_event["detail"] = (
                                "Essa ação requer sua confirmação para prosseguir."
                            )
                        else:
                            state_event["detail"] = (
                                "Tool reportou erro/timeout. Revise parâmetros e tente novamente."
                            )
                        yield state_event

                        # -- RAG Gap Tracking --
                        if tool_name in ("search_rag_global", "search_rag_local"):
                            _gap_text = str(full_result or result_preview).lower()
                            if "no relevant" in _gap_text:
                                _tc_gap = self._find_tool_call_log(
                                    tool_calls_log=tool_calls_log,
                                    tool_call_id=tool_call_id,
                                    tool_name=tool_name,
                                )
                                _gap_query = (
                                    str(_tc_gap.get("input", ""))
                                    if _tc_gap
                                    else ""
                                )
                                self._db.add(
                                    RagGapEvent(
                                        user_id=user.id,
                                        conversation_id=conversation_id,
                                        tool_name=tool_name,
                                        query=_gap_query[:2000],
                                        gap_type="no_results",
                                        result_preview=result_preview[:500],
                                    )
                                )

                    elif event_type == "usage":
                        total_tokens_used += int(event.get("total_tokens", 0) or 0)

                attempt_duration_ms = int((time.monotonic() - attempt_started_at) * 1000)
                if not accumulated:
                    logger.warning(
                        "chat_stream EMPTY_RESPONSE user=%s conv=%s provider=%s model=%s "
                        "tool_calls=%d tokens=%d duration_ms=%d",
                        user.id, conversation_id, attempt_provider, attempt_model,
                        len(tool_calls_log), total_tokens_used, attempt_duration_ms,
                    )
                else:
                    logger.info(
                        "chat_stream ok user=%s conv=%s provider=%s model=%s "
                        "chars=%d tool_calls=%d tokens=%d duration_ms=%d",
                        user.id, conversation_id, attempt_provider, attempt_model,
                        len(accumulated), len(tool_calls_log), total_tokens_used, attempt_duration_ms,
                    )
                llm_attempt_audit.append(
                    self._build_llm_attempt_audit_entry(
                        provider_name=attempt_provider,
                        model=attempt_model if isinstance(attempt_model, str) else None,
                        source=attempt_source,
                        status="success",
                        duration_ms=attempt_duration_ms,
                    )
                )
                selected_llm_attempt = llm_attempt
                if attempt_index > 0:
                    logger.info(
                        "LLM fallback sucesso user=%s conv=%s selected=%s/%s attempt=%s/%s",
                        user.id,
                        conversation_id,
                        attempt_provider,
                        attempt_model,
                        attempt_index + 1,
                        total_attempts,
                    )
                break
            except asyncio.CancelledError:
                await self._db.rollback()
                raise
            except Exception as exc:
                attempt_duration_ms = int((time.monotonic() - attempt_started_at) * 1000)
                eligible, eligibility_reason = self._is_fallback_eligible_error(exc)
                llm_attempt_audit.append(
                    self._build_llm_attempt_audit_entry(
                        provider_name=attempt_provider,
                        model=attempt_model if isinstance(attempt_model, str) else None,
                        source=attempt_source,
                        status="failed_stream",
                        duration_ms=attempt_duration_ms,
                        error=str(exc),
                        eligible_fallback=eligible,
                        eligibility_reason=eligibility_reason,
                    )
                )

                can_retry = eligible and (not output_emitted) and attempt_index < total_attempts - 1
                if can_retry:
                    delay_seconds = self._fallback_delay_seconds(attempt_index)
                    logger.warning(
                        "LLM fallback (stream) user=%s conv=%s from=%s/%s reason=%s next_attempt=%s delay=%.2fs",
                        user.id,
                        conversation_id,
                        attempt_provider,
                        attempt_model,
                        eligibility_reason,
                        attempt_index + 2,
                        delay_seconds,
                    )
                    if delay_seconds > 0:
                        await asyncio.sleep(delay_seconds)
                    continue

                await self._db.rollback()
                async for failure_event in self._emit_failed_tool_states(
                    active_tool_calls=active_tool_calls,
                    detail="Execucao interrompida por erro no provedor LLM.",
                ):
                    yield failure_event
                if isinstance(exc, LLMProviderError):
                    logger.error("stream llm_error: %s", exc)
                    yield {
                        "type": "error",
                        "code": "llm_error",
                        "detail": "Erro no provedor LLM. Tente novamente.",
                    }
                else:
                    logger.exception("stream internal_error")
                    yield {
                        "type": "error",
                        "code": "stream_error",
                        "detail": "Erro interno durante streaming. Tente novamente.",
                    }
                return

        if selected_llm_attempt is None:
            await self._db.rollback()
            yield {
                "type": "error",
                "code": "llm_error",
                "detail": "Falha ao obter resposta apos tentativas de fallback de provedor/modelo.",
            }
            return

        # 8b. Token count — real from provider or estimated fallback
        if total_tokens_used <= 0 and accumulated:
            total_tokens_used = max(1, len(accumulated) // 4)

        # 9. Persist assistant message
        assistant_msg.content = accumulated
        assistant_msg.tokens_used = total_tokens_used or None
        assistant_metadata: dict = {}
        if tool_calls_log:
            assistant_metadata["tool_calls"] = tool_calls_log
        if attachment_metadata:
            assistant_metadata.update(attachment_metadata)
        if memory_resolution.entries:
            assistant_metadata["memory_context"] = MemoryService.build_context_metadata(
                memory_resolution.entries
            )
        assistant_metadata["llm_execution"] = {
            "selected_provider": selected_llm_attempt.get("provider_name"),
            "selected_model": selected_llm_attempt.get("model"),
            "using_free_llm": using_free_llm,
            "fallback_triggered": len(llm_attempt_audit) > 1,
            "attempt_count": len(llm_attempt_audit),
            "attempts": llm_attempt_audit,
        }
        assistant_msg.message_metadata = self._augment_response_metadata(
            metadata=assistant_metadata or None,
            response_content=accumulated,
            tool_calls_log=tool_calls_log,
            attachment_metadata=attachment_metadata,
            memory_resolution=memory_resolution,
        )
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
            await UsageTrackingService.increment_messages(self._db, workspace.id, user.id)
            if total_tokens_used > 0:
                await UsageTrackingService.increment_tokens(self._db, workspace.id, user.id, total_tokens_used)
            await self._db.commit()
        except Exception:
            pass  # Non-critical — don't fail the response

        stream_end_event = {
            "type": "stream_end",
            "message_id": str(assistant_msg.id),
            "tokens_used": total_tokens_used or None,
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
            await UsageTrackingService.increment_messages(self._db, workspace.id, user.id)
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
        workspace_id: UUID,
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
                workspace_id=workspace_id,
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

    async def _build_llm_attempt_chain(
        self,
        *,
        primary_provider: str,
        primary_api_key: str,
        primary_model: str | None,
        using_free_llm: bool,
        plan_allows_fallback: bool = True,
    ) -> list[dict]:
        """
        Build ordered LLM attempts (provider/model) for automatic fallback.

        Se plan_allows_fallback=False e o primario eh BYO, nao inclui tentativas
        de fallback via LLM gratuito do sistema.
        """
        attempts: list[dict] = []
        seen: set[tuple[str, str, str]] = set()

        async def _safe_get_setting(key: str) -> str | None:
            try:
                return await SystemSettingsService.get(self._db, key)
            except Exception:
                return None

        def _add_attempt(
            *,
            provider_name: str,
            api_key: str,
            model: str | None,
            source: str,
        ) -> None:
            provider = provider_name.lower().strip()
            if not provider or not api_key:
                return
            resolved_model = model or self._default_model_for_provider(provider)
            key = (provider, resolved_model or "", api_key)
            if key in seen:
                return
            seen.add(key)
            attempts.append(
                {
                    "provider_name": provider,
                    "api_key": api_key,
                    "model": resolved_model,
                    "source": source,
                }
            )

        normalized_primary_provider = primary_provider.lower().strip()
        resolved_primary_model = (
            primary_model
            or await LLMModelResolverService.resolve_model(
                self._db,
                normalized_primary_provider,
                legacy_keys=("free_llm_model",) if using_free_llm else (),
            )
        )
        _add_attempt(
            provider_name=normalized_primary_provider,
            api_key=primary_api_key,
            model=resolved_primary_model,
            source="primary",
        )

        default_primary_model = await LLMModelResolverService.resolve_model(
            self._db,
            normalized_primary_provider,
            legacy_keys=("free_llm_model",) if using_free_llm else (),
        )
        if (
            resolved_primary_model
            and default_primary_model
            and resolved_primary_model != default_primary_model
        ):
            _add_attempt(
                provider_name=normalized_primary_provider,
                api_key=primary_api_key,
                model=default_primary_model,
                source="primary_default_model",
            )

        free_enabled = await _safe_get_setting("free_llm_enabled")
        free_primary_key: str | None = None
        free_primary_provider: str | None = None
        free_primary_model: str | None = None
        if free_enabled == "true":
            free_primary_key = await _safe_get_setting("free_llm_api_key")
            free_primary_provider = (
                await _safe_get_setting("free_llm_provider")
            ) or "google"
            free_primary_model = await LLMModelResolverService.resolve_model(
                self._db,
                free_primary_provider,
                legacy_keys=("free_llm_model",),
            )

        # Fallback via LLM gratuito — somente se o plano permite
        if plan_allows_fallback and not using_free_llm and free_primary_key and free_primary_provider:
            _add_attempt(
                provider_name=free_primary_provider,
                api_key=free_primary_key,
                model=free_primary_model,
                source="fallback_free_primary",
            )

        secondary_provider = await _safe_get_setting("free_llm_fallback_provider")
        secondary_model = await _safe_get_setting("free_llm_fallback_model")
        secondary_key = await _safe_get_setting("free_llm_fallback_api_key")
        if plan_allows_fallback and secondary_provider:
            resolved_secondary_key = (
                secondary_key
                or free_primary_key
                or (primary_api_key if using_free_llm else None)
            )
            if resolved_secondary_key:
                resolved_secondary_model = (
                    secondary_model.strip()
                    if secondary_model and secondary_model.strip()
                    else await LLMModelResolverService.resolve_model(
                        self._db,
                        secondary_provider,
                        legacy_keys=("free_llm_fallback_model",),
                    )
                )
                _add_attempt(
                    provider_name=secondary_provider,
                    api_key=resolved_secondary_key,
                    model=resolved_secondary_model,
                    source="fallback_secondary",
                )

        if not attempts:
            _add_attempt(
                provider_name=normalized_primary_provider,
                api_key=primary_api_key,
                model=resolved_primary_model,
                source="primary",
            )
        return attempts

    async def _plan_allows_fallback(self, workspace: Workspace) -> bool:
        """Verifica se o plano do workspace permite fallback para LLM gratuito."""
        try:
            plan = await PlanLimitService.get_workspace_plan(self._db, workspace)
            features = plan.features if plan.features else {}
            # Default conservador: se nao definido, permite fallback
            return bool(features.get("allow_system_fallback", True))
        except Exception:
            logger.warning(
                "Falha ao resolver allow_system_fallback user=%s, default=True",
                user.id,
            )
            return True

    @staticmethod
    def _default_model_for_provider(provider_name: str) -> str:
        return LLMModelResolverService.default_model_for_provider(provider_name)

    @staticmethod
    def _build_llm_attempt_audit_entry(
        *,
        provider_name: str,
        model: str | None,
        source: str,
        status: str,
        duration_ms: int,
        error: str | None = None,
        eligible_fallback: bool | None = None,
        eligibility_reason: str | None = None,
    ) -> dict:
        payload = {
            "provider": provider_name,
            "model": model,
            "source": source,
            "status": status,
            "duration_ms": duration_ms,
        }
        if error:
            payload["error"] = error[:300]
        if eligible_fallback is not None:
            payload["eligible_fallback"] = bool(eligible_fallback)
        if eligibility_reason:
            payload["eligibility_reason"] = eligibility_reason
        return payload

    @staticmethod
    def _is_fallback_eligible_error(exc: Exception) -> tuple[bool, str]:
        """
        Decide if an LLM failure should trigger fallback.

        Non-eligible examples:
        - invalid API key / auth
        - unsupported provider / missing config
        """
        details = f"{type(exc).__name__}: {exc}".lower()

        non_eligible_markers = (
            "invalid api key",
            "incorrect api key",
            "authentication",
            "unauthorized",
            "forbidden",
            "api key is required",
            "not configured",
            "unsupported provider",
            "permission denied",
        )
        if any(marker in details for marker in non_eligible_markers):
            return False, "non_eligible_configuration"

        eligible_markers = (
            "rate limit",
            "too many requests",
            "timeout",
            "timed out",
            "temporarily unavailable",
            "service unavailable",
            "overloaded",
            "connection",
            "internal server error",
            "server error",
            "bad gateway",
            "gateway timeout",
            "model not found",
            "no such model",
            "429",
            "500",
            "502",
            "503",
            "504",
        )
        if any(marker in details for marker in eligible_markers):
            return True, "eligible_transient_provider_error"

        if isinstance(exc, LLMProviderError):
            return True, "eligible_provider_error"
        return False, "non_eligible_unknown"

    @staticmethod
    def _fallback_delay_seconds(failed_attempt_index: int) -> float:
        """
        Exponential backoff delay before the next fallback attempt.
        """
        return min(2.5, 0.35 * (2 ** max(0, failed_attempt_index)))

    @classmethod
    def _augment_response_metadata(
        cls,
        *,
        metadata: dict | None,
        response_content: str,
        tool_calls_log: list[dict],
        attachment_metadata: dict | None,
        memory_resolution: MemoryContextResolution | None,
    ) -> dict | None:
        """
        Enrich assistant metadata with evidence block, confidence heuristics
        and RAG citations.
        """
        payload: dict = {}
        if isinstance(metadata, dict):
            payload.update(metadata)

        evidence_items = cls._build_evidence_items(
            tool_calls_log=tool_calls_log,
            attachment_metadata=attachment_metadata,
            memory_resolution=memory_resolution,
        )
        evidence_summary = cls._summarize_evidence_strength(evidence_items)
        payload["evidence"] = {
            "items": evidence_items,
            **evidence_summary,
        }
        payload["confidence"] = cls._build_confidence_block(
            evidence_items=evidence_items,
            evidence_summary=evidence_summary,
            response_content=response_content,
        )

        # Extrair citacoes RAG dos tool results
        citations = cls._extract_rag_citations(tool_calls_log)
        if citations:
            payload["citations"] = citations

        return payload or None

    @classmethod
    def _build_evidence_items(
        cls,
        *,
        tool_calls_log: list[dict],
        attachment_metadata: dict | None,
        memory_resolution: MemoryContextResolution | None,
    ) -> list[dict]:
        """
        Build normalized evidence items from tools, memory and attachment context.
        """
        items: list[dict] = []

        for idx, tool_call in enumerate(tool_calls_log):
            tool_name = str(tool_call.get("tool", "unknown"))
            status = str(tool_call.get("status", "completed"))
            result_preview = cls._compact_text(str(tool_call.get("result_preview", "")))
            tool_input = cls._compact_text(str(tool_call.get("input", "")))
            full_result = cls._compact_text(str(tool_call.get("full_result", "")))
            strength = cls._resolve_tool_strength(tool_name=tool_name, status=status)
            summary = f"Tool '{tool_name}' executada com status '{status}'."
            if result_preview:
                summary = f"{summary} Resultado: {result_preview[:180]}"

            items.append(
                {
                    "id": f"tool:{idx}",
                    "type": "tool_call",
                    "source": tool_name,
                    "status": status,
                    "strength": strength,
                    "summary": summary,
                    "details": {
                        "input": tool_input[:400],
                        "result_preview": result_preview[:400],
                        "output": full_result[:400] if full_result else result_preview[:400],
                        "duration_ms": tool_call.get("duration_ms"),
                    },
                }
            )

        if memory_resolution is not None and memory_resolution.entries:
            items.append(
                {
                    "id": "memory:context",
                    "type": "memory",
                    "source": "memory_context",
                    "status": "applied",
                    "strength": "medium",
                    "summary": (
                        f"{len(memory_resolution.entries)} memoria(s) persistentes aplicadas "
                        "ao contexto da resposta."
                    ),
                    "details": {
                        "applied_count": len(memory_resolution.entries),
                        "keys": [entry.memory_key for entry in memory_resolution.entries],
                    },
                }
            )

        if isinstance(attachment_metadata, dict):
            attachment_context = attachment_metadata.get("attachment_context")
            if isinstance(attachment_context, dict):
                status = str(attachment_context.get("status", "resolved"))
                if status == "resolved":
                    resolved = attachment_context.get("resolved_attachment", {})
                    filename = (
                        resolved.get("filename")
                        if isinstance(resolved, dict)
                        else None
                    )
                    summary = "Contexto de anexo resolvido para esta resposta."
                    if filename:
                        summary = f"{summary} Arquivo: {filename}"
                    items.append(
                        {
                            "id": "attachment:resolved",
                            "type": "attachment",
                            "source": "attachment_context",
                            "status": status,
                            "strength": "weak",
                            "summary": summary,
                            "details": attachment_context,
                        }
                    )
                elif status == "ambiguous":
                    items.append(
                        {
                            "id": "attachment:ambiguous",
                            "type": "attachment",
                            "source": "attachment_context",
                            "status": status,
                            "strength": "weak",
                            "summary": (
                                "Contexto de anexo ambiguo; resposta depende de confirmacao do usuario."
                            ),
                            "details": attachment_context,
                        }
                    )
        return items

    @staticmethod
    def _resolve_tool_strength(*, tool_name: str, status: str) -> str:
        if status != "completed":
            return "weak"

        strong_tools = {
            "search_rag_global",
            "search_rag_local",
            "diff_config_risk",
            "pre_change_review",
        }
        medium_tools = {
            "parse_config",
            "validate_config",
            "parse_show_commands",
            "analyze_pcap",
        }
        if tool_name in strong_tools:
            return "strong"
        if tool_name in medium_tools:
            return "medium"
        return "weak"

    @staticmethod
    def _summarize_evidence_strength(evidence_items: list[dict]) -> dict:
        strong_count = sum(1 for item in evidence_items if item.get("strength") == "strong")
        medium_count = sum(1 for item in evidence_items if item.get("strength") == "medium")
        weak_count = sum(1 for item in evidence_items if item.get("strength") == "weak")
        failed_count = sum(1 for item in evidence_items if item.get("status") == "failed")
        return {
            "total_count": len(evidence_items),
            "strong_count": strong_count,
            "medium_count": medium_count,
            "weak_count": weak_count,
            "failed_count": failed_count,
        }

    @classmethod
    def _build_confidence_block(
        cls,
        *,
        evidence_items: list[dict],
        evidence_summary: dict,
        response_content: str,
    ) -> dict:
        """
        Compute transparent confidence score from evidence quality/quantity.
        """
        strong_count = int(evidence_summary.get("strong_count", 0))
        medium_count = int(evidence_summary.get("medium_count", 0))
        weak_count = int(evidence_summary.get("weak_count", 0))
        failed_count = int(evidence_summary.get("failed_count", 0))
        total_count = int(evidence_summary.get("total_count", 0))
        tool_call_count = sum(
            1 for item in evidence_items if item.get("type") == "tool_call"
        )

        base_score = 30
        strong_bonus = min(strong_count * 22, 44)
        medium_bonus = min(medium_count * 10, 20)
        weak_bonus = min(weak_count * 4, 8)
        failure_penalty = min(failed_count * 14, 28)
        no_evidence_penalty = 12 if total_count == 0 else 0
        short_answer_penalty = (
            6
            if cls._compact_text(response_content)
            and len(cls._compact_text(response_content)) < 80
            else 0
        )

        score = (
            base_score
            + strong_bonus
            + medium_bonus
            + weak_bonus
            - failure_penalty
            - no_evidence_penalty
            - short_answer_penalty
        )

        score = max(5, min(score, 95))
        if score >= 80:
            level = "high"
        elif score >= 55:
            level = "medium"
        else:
            level = "low"

        reasons: list[str] = []
        if strong_count > 0:
            reasons.append(f"{strong_count} evidencia(s) forte(s) de ferramentas/fontes.")
        if medium_count > 0:
            reasons.append(f"{medium_count} evidencia(s) complementar(es).")
        if tool_call_count > 0:
            reasons.append(f"{tool_call_count} tool call(s) observavel(is) na resposta.")
        if failed_count > 0:
            reasons.append(f"{failed_count} tool call(s) falharam durante a geracao.")
        if total_count == 0:
            reasons.append("Nenhuma evidencia observavel foi registrada nesta resposta.")

        warning: str | None = None
        if strong_count == 0:
            warning = (
                "Sinal de cautela: faltam evidencias fortes; valide comandos/sintaxe antes da execucao."
            )
        if failed_count > 0 and warning is None:
            warning = (
                "Uma ou mais ferramentas falharam; considere repetir a consulta para elevar confianca."
            )

        return {
            "score": score,
            "level": level,
            "reasons": reasons,
            "warning": warning,
            "heuristics": {
                "base_score": base_score,
                "strong_bonus": strong_bonus,
                "medium_bonus": medium_bonus,
                "weak_bonus": weak_bonus,
                "failure_penalty": failure_penalty,
                "no_evidence_penalty": no_evidence_penalty,
                "short_answer_penalty": short_answer_penalty,
            },
        }

    @staticmethod
    def _compact_text(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _extract_rag_citations(tool_calls_log: list[dict]) -> list[dict]:
        """Extrai citacoes RAG do full_result dos tool calls de search_rag_*."""
        import json as _json

        from app.agents.tools.rag_tools import CITATIONS_SEPARATOR

        citations: list[dict] = []
        seen_docs: set[str] = set()

        for tc in tool_calls_log:
            tool_name = str(tc.get("tool", ""))
            if not tool_name.startswith("search_rag_"):
                continue
            full_result = str(tc.get("full_result", ""))
            sep_idx = full_result.find(CITATIONS_SEPARATOR)
            if sep_idx < 0:
                continue
            json_str = full_result[sep_idx + len(CITATIONS_SEPARATOR) :].rstrip(" ->")
            try:
                parsed = _json.loads(json_str)
                if isinstance(parsed, list):
                    for c in parsed:
                        if not isinstance(c, dict):
                            continue
                        dedup_key = f"{c.get('source_type')}:{c.get('document_name', '')}:{c.get('excerpt', '')[:50]}"
                        if dedup_key in seen_docs:
                            continue
                        seen_docs.add(dedup_key)
                        citations.append(c)
            except (_json.JSONDecodeError, ValueError):
                continue

        return citations

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
