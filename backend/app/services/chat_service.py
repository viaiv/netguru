"""
Chat service — orchestrates message persistence + agent invocation + streaming.
"""
from datetime import datetime
from typing import AsyncGenerator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.network_engineer_agent import NetworkEngineerAgent
from app.core.config import settings
from app.core.security import decrypt_api_key
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.llm_client import LLMProviderError


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
    4. Invoke agent with streaming
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

        # 5. Load conversation history
        history = await self._load_history(conversation_id)

        # 6. Build agent
        try:
            api_key = decrypt_api_key(user.encrypted_api_key)
            agent = NetworkEngineerAgent(
                provider_name=user.llm_provider,
                api_key=api_key,
                model=conversation.model_used,
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

        accumulated = ""
        try:
            async for chunk in agent.stream_response(history):
                accumulated += chunk
                yield {"type": "stream_chunk", "content": chunk}
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
        conversation.updated_at = datetime.utcnow()

        try:
            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            yield {
                "type": "error",
                "code": "db_error",
                "detail": f"Erro ao salvar resposta: {exc}",
            }
            return

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
