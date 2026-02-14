"""
WebSocket endpoint for real-time chat streaming.

Protocol:
  Client → Server:
    {"type": "message", "content": "..."} — send chat message
    {"type": "cancel"}                    — cancel current processing
    {"type": "ping"}                      — keep-alive

  Server → Client:
    {"type": "stream_start", "message_id": "..."}
    {"type": "stream_chunk", "content": "..."}
    {"type": "stream_end",   "message_id": "...", "tokens_used": int|null}
    {"type": "stream_cancelled", "reason": "..."}
    {"type": "error",        "code": "...", "detail": "..."}
    {"type": "pong"}

Close codes:
    4001 — authentication failed
    4002 — protocol error
    1011 — internal server error
"""
import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.user import User
from app.services.chat_service import ChatService, ChatServiceError
from app.services.llm_client import LLMProviderError

router = APIRouter()


async def _authenticate_websocket(
    websocket: WebSocket,
    token: str,
    db: AsyncSession,
) -> User | None:
    """
    Validate JWT token and return the User, or None if auth fails.
    """
    payload = decode_token(token)
    if payload is None:
        return None

    if payload.get("type") != "access":
        return None

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        return None

    try:
        user_id = UUID(str(raw_user_id))
    except (TypeError, ValueError):
        return None

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None

    return user


async def _stream_events(
    service: ChatService,
    websocket: WebSocket,
    user: User,
    conversation_id: UUID,
    content: str,
) -> None:
    """Consome o generator do ChatService e envia eventos pelo WebSocket."""
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content=content,
    ):
        await websocket.send_json(event)


async def _wait_for_cancel(websocket: WebSocket) -> None:
    """Aguarda mensagem de cancel ou ping enquanto o agent processa."""
    while True:
        raw = await websocket.receive_text()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        msg_type = data.get("type")
        if msg_type == "cancel":
            return
        if msg_type == "ping":
            await websocket.send_json({"type": "pong"})


@router.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: UUID,
    token: str = "",
):
    """
    Main WebSocket endpoint for real-time chat with streaming LLM responses.

    Authentication is via query parameter: ?token=<jwt_access_token>
    """
    # Manual DB session — WebSocket connections are long-lived
    async with AsyncSessionLocal() as db:
        # Authenticate BEFORE accepting the connection
        user = await _authenticate_websocket(websocket, token, db)
        if user is None:
            await websocket.close(code=4001, reason="Authentication failed")
            return

        await websocket.accept()

        try:
            while True:
                raw = await websocket.receive_text()

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "code": "invalid_json",
                        "detail": "Mensagem nao e JSON valido.",
                    })
                    continue

                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if msg_type == "message":
                    content = data.get("content", "").strip()
                    if not content:
                        await websocket.send_json({
                            "type": "error",
                            "code": "empty_message",
                            "detail": "Conteudo da mensagem nao pode ser vazio.",
                        })
                        continue

                    service = ChatService(db)

                    # Roda processamento e escuta cancel concorrentemente
                    stream_task = asyncio.create_task(
                        _stream_events(service, websocket, user, conversation_id, content)
                    )
                    cancel_task = asyncio.create_task(
                        _wait_for_cancel(websocket)
                    )

                    done, pending = await asyncio.wait(
                        {stream_task, cancel_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass

                    user_cancelled = cancel_task in done and stream_task.cancelled()

                    # Se cancelou, garante cleanup transacional e notifica frontend
                    if user_cancelled:
                        try:
                            await db.rollback()
                        except Exception:
                            pass
                        await websocket.send_json({
                            "type": "stream_cancelled",
                            "reason": "cancelled_by_user",
                        })

                    # Se o stream_task falhou com erro nao tratado
                    if stream_task in done and not stream_task.cancelled():
                        exc = stream_task.exception()
                        if not exc:
                            continue
                        if isinstance(exc, ChatServiceError):
                            await websocket.send_json({
                                "type": "error",
                                "code": exc.code,
                                "detail": exc.detail,
                            })
                        elif isinstance(exc, LLMProviderError):
                            await websocket.send_json({
                                "type": "error",
                                "code": "llm_error",
                                "detail": str(exc),
                            })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "code": "internal_error",
                                "detail": str(exc),
                            })

                    continue

                # Unknown message type
                await websocket.send_json({
                    "type": "error",
                    "code": "unknown_type",
                    "detail": f"Tipo de mensagem desconhecido: {msg_type}",
                })

        except WebSocketDisconnect:
            pass
        except Exception:
            try:
                await websocket.close(code=1011, reason="Internal server error")
            except Exception:
                pass
