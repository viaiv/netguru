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
from app.services.llm_client import LLMProviderError
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
    ) -> AsyncGenerator[dict, None]:
        """
        Process a user message end-to-end with streaming.

        Yields dicts matching the WS protocol:
            {"type": "stream_start", "message_id": "..."}
            {"type": "tool_call_start", "tool_name": "...", "tool_input": "..."}
            {"type": "tool_call_end", "tool_name": "...", "result_preview": "...", "duration_ms": ...}
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

        # 3. Validate user has LLM configured
        if not user.llm_provider or not user.encrypted_api_key:
            raise ChatServiceError(
                "Configure seu provedor LLM e API key no perfil antes de usar o chat.",
                code="llm_not_configured",
            )

        # 4. Save user message (flush to get ID, no commit yet)
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=content,
        )
        self._db.add(user_msg)
        await self._db.flush()

        # 4b. Auto-generate title from first user message
        title_event = None
        if conversation.title == "Nova Conversa":
            new_title = self._generate_title(content)
            conversation.title = new_title
            await self._db.flush()
            title_event = {"type": "title_updated", "title": new_title}

        # 5. Load conversation history
        history = await self._load_history(conversation_id)

        # 6. Build agent with tools
        try:
            api_key = decrypt_api_key(user.encrypted_api_key)
            tools = get_agent_tools(db=self._db, user_id=user.id)
            agent = NetworkEngineerAgent(
                provider_name=user.llm_provider,
                api_key=api_key,
                model=conversation.model_used,
                tools=tools,
            )
        except Exception as exc:
            await self._db.rollback()
            raise ChatServiceError(
                f"Erro ao configurar provedor LLM: {exc}",
                code="llm_init_error",
            )

        # 7. Stream response
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

        accumulated = ""
        tool_calls_log: list[dict] = []
        try:
            async for event in agent.stream_response(history):
                event_type = event.get("type")

                if event_type == "text":
                    accumulated += event["content"]
                    yield {"type": "stream_chunk", "content": event["content"]}

                elif event_type == "tool_call_start":
                    tool_calls_log.append({
                        "tool": event["tool_name"],
                        "input": event["tool_input"],
                    })
                    yield {
                        "type": "tool_call_start",
                        "tool_name": event["tool_name"],
                        "tool_input": event["tool_input"],
                    }

                elif event_type == "tool_call_end":
                    # Atualiza log com resultado
                    for tc in reversed(tool_calls_log):
                        if tc["tool"] == event["tool_name"] and "result_preview" not in tc:
                            tc["result_preview"] = event["result_preview"]
                            tc["duration_ms"] = event["duration_ms"]
                            if event.get("full_result"):
                                tc["full_result"] = event["full_result"]
                            break
                    yield {
                        "type": "tool_call_end",
                        "tool_name": event["tool_name"],
                        "result_preview": event["result_preview"],
                        "duration_ms": event["duration_ms"],
                    }
        except asyncio.CancelledError:
            await self._db.rollback()
            raise
        except LLMProviderError as exc:
            await self._db.rollback()
            yield {
                "type": "error",
                "code": "llm_error",
                "detail": str(exc),
            }
            return
        except Exception as exc:
            await self._db.rollback()
            yield {
                "type": "error",
                "code": "stream_error",
                "detail": f"Erro durante streaming: {exc}",
            }
            return

        # 8. Persist assistant message
        assistant_msg.content = accumulated
        assistant_msg.message_metadata = {"tool_calls": tool_calls_log} if tool_calls_log else None
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

        # 9. Track usage metrics
        try:
            await UsageTrackingService.increment_messages(self._db, user.id)
            await self._db.commit()
        except Exception:
            pass  # Non-critical — don't fail the response

        yield {
            "type": "stream_end",
            "message_id": str(assistant_msg.id),
            "tokens_used": None,
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
