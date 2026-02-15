"""
WebSocket endpoint for real-time chat streaming.

Protocol:
  Client → Server:
    {"type": "message", "content": "..."} — send chat message
    {"type": "message", "content": "...", "attachments": [{"document_id": "..."}]} — message with uploaded attachments
    {"type": "cancel"}                    — cancel current processing
    {"type": "ping"}                      — keep-alive

  Server → Client:
    {"type": "stream_start", "message_id": "..."}
    {"type": "stream_chunk", "content": "..."}
    {"type": "stream_end",   "message_id": "...", "tokens_used": int|null}
    {"type": "tool_call_state", "tool_call_id": "...", "tool_name": "...", "status": "queued|running|progress|completed|failed"}
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

from sqlalchemy import select as sa_select

from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis_client
from app.core.security import decode_token
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.chat_service import ChatService, ChatServiceError
from app.services.llm_client import LLMProviderError

router = APIRouter()


async def _authenticate_websocket(
    websocket: WebSocket,
    token: str,
    db: AsyncSession,
    *,
    ticket: str = "",
) -> User | None:
    """
    Validate auth credential and return the User, or None if auth fails.

    Supports two methods (checked in order):
    1. Ephemeral ticket (preferred) — short-lived Redis token, one-time use.
    2. JWT access token (legacy fallback) — passed via query param.
    """
    user_id: UUID | None = None

    # 1. Try ephemeral ticket first
    if ticket:
        try:
            redis = get_redis_client()
            redis_key = f"ws_ticket:{ticket}"
            raw = await redis.get(redis_key)
            if raw:
                await redis.delete(redis_key)  # one-time use
                user_id = UUID(raw)
        except Exception:
            pass

    # 2. Fallback to JWT token
    if user_id is None and token:
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

    if user_id is None:
        return None

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None

    return user


async def _resolve_workspace(user: User, db: AsyncSession) -> Workspace | None:
    """Resolve o workspace ativo do usuario."""
    if not user.active_workspace_id:
        return None
    stmt = sa_select(Workspace).where(Workspace.id == user.active_workspace_id)
    result = await db.execute(stmt)
    workspace = result.scalar_one_or_none()
    if workspace is None:
        return None
    # Verificar membership
    member_stmt = sa_select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == user.id,
    )
    member_result = await db.execute(member_stmt)
    if member_result.scalar_one_or_none() is None:
        return None
    return workspace


async def _stream_events(
    service: ChatService,
    websocket: WebSocket,
    user: User,
    workspace: Workspace,
    conversation_id: UUID,
    content: str,
    attachment_document_ids: list[UUID] | None = None,
) -> None:
    """Consome o generator do ChatService e envia eventos pelo WebSocket."""
    async for event in service.process_user_message(
        user=user,
        workspace=workspace,
        conversation_id=conversation_id,
        content=content,
        attachment_document_ids=attachment_document_ids,
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
    ticket: str = "",
):
    """
    Main WebSocket endpoint for real-time chat with streaming LLM responses.

    Authentication: ?ticket=<ephemeral> (preferred) or ?token=<jwt> (legacy).
    """
    # Manual DB session — WebSocket connections are long-lived
    async with AsyncSessionLocal() as db:
        # Authenticate BEFORE accepting the connection
        user = await _authenticate_websocket(websocket, token, db, ticket=ticket)
        if user is None:
            await websocket.close(code=4001, reason="Authentication failed")
            return

        # Resolver workspace ativo
        workspace = await _resolve_workspace(user, db)
        if workspace is None:
            await websocket.close(code=4001, reason="No active workspace")
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

                if msg_type == "cancel":
                    # Cancel fora de streaming ativo — ignorar silenciosamente
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

                    attachment_document_ids: list[UUID] = []
                    raw_attachments = data.get("attachments")
                    if isinstance(raw_attachments, list):
                        invalid_attachment_id = False
                        for item in raw_attachments:
                            if not isinstance(item, dict):
                                continue
                            raw_doc_id = item.get("document_id")
                            if not raw_doc_id:
                                continue
                            try:
                                attachment_document_ids.append(UUID(str(raw_doc_id)))
                            except (TypeError, ValueError):
                                invalid_attachment_id = True
                                break
                        if invalid_attachment_id:
                            await websocket.send_json({
                                "type": "error",
                                "code": "invalid_attachment_id",
                                "detail": "Um ou mais document_id de anexo sao invalidos.",
                            })
                            continue

                    service = ChatService(db)

                    # Roda processamento e escuta cancel concorrentemente
                    stream_task = asyncio.create_task(
                        _stream_events(
                            service,
                            websocket,
                            user,
                            workspace,
                            conversation_id,
                            content,
                            attachment_document_ids or None,
                        )
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
