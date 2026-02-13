"""
WebSocket endpoint for real-time chat streaming.

Protocol:
  Client → Server:
    {"type": "message", "content": "..."} — send chat message
    {"type": "ping"}                      — keep-alive

  Server → Client:
    {"type": "stream_start", "message_id": "..."}
    {"type": "stream_chunk", "content": "..."}
    {"type": "stream_end",   "message_id": "...", "tokens_used": int|null}
    {"type": "error",        "code": "...", "detail": "..."}
    {"type": "pong"}

Close codes:
    4001 — authentication failed
    4002 — protocol error
    1011 — internal server error
"""
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

                    # Process through ChatService
                    service = ChatService(db)
                    try:
                        async for event in service.process_user_message(
                            user=user,
                            conversation_id=conversation_id,
                            content=content,
                        ):
                            await websocket.send_json(event)
                    except ChatServiceError as exc:
                        await websocket.send_json({
                            "type": "error",
                            "code": exc.code,
                            "detail": exc.detail,
                        })
                    except LLMProviderError as exc:
                        await websocket.send_json({
                            "type": "error",
                            "code": "llm_error",
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
