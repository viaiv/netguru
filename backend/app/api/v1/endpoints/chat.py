"""
Chat endpoints for conversation and message persistence.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_workspace, require_permissions
from app.core.rbac import Permission
from app.models.conversation import Conversation, Message
from app.models.llm_model import LlmModel
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)

router = APIRouter()


def _build_conversation_response(conversation: Conversation) -> ConversationResponse:
    """
    Build API response for conversation resource.
    """

    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        model_used=conversation.model_used,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _build_message_response(message: Message) -> MessageResponse:
    """
    Build API response for message resource.
    """

    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        tokens_used=message.tokens_used,
        metadata=message.message_metadata,
        created_at=message.created_at,
    )


async def _get_owned_conversation(
    conversation_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Conversation:
    """
    Load a conversation ensuring ownership by current user.
    """

    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """
    Create a conversation for current user within active workspace.
    """

    # Validar model_used contra catalogo de modelos ativos
    validated_model = None
    if payload.model_used:
        result = await db.execute(
            select(LlmModel).where(
                LlmModel.model_id == payload.model_used,
                LlmModel.is_active.is_(True),
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Modelo '{payload.model_used}' nao encontrado no catalogo ou esta inativo.",
            )
        validated_model = payload.model_used

    conversation = Conversation(
        user_id=current_user.id,
        workspace_id=workspace.id,
        title=payload.title,
        model_used=validated_model,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return _build_conversation_response(conversation)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """
    Rename a conversation owned by the current user.
    """
    conversation = await _get_owned_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        db=db,
    )
    conversation.title = payload.title
    conversation.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(conversation)
    return _build_conversation_response(conversation)


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    """
    List conversations from current user within active workspace.
    """

    stmt = (
        select(Conversation)
        .where(
            Conversation.user_id == current_user.id,
            Conversation.workspace_id == workspace.id,
        )
        .order_by(desc(Conversation.updated_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()
    return [_build_conversation_response(conversation) for conversation in conversations]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Delete a conversation and all its messages (cascade).
    """

    conversation = await _get_owned_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        db=db,
    )
    await db.delete(conversation)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID,
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """
    List all messages for a conversation owned by current user.
    """

    _ = await _get_owned_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        db=db,
    )
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return [_build_message_response(message) for message in messages]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: UUID,
    payload: MessageCreate,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Append a message to a user-owned conversation.
    """

    conversation = await _get_owned_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        db=db,
    )

    message = Message(
        conversation_id=conversation.id,
        role=payload.role,
        content=payload.content,
        tokens_used=payload.tokens_used,
        message_metadata=payload.metadata,
    )
    db.add(message)
    conversation.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(message)
    return _build_message_response(message)


_PCAP_DATA_RE = re.compile(r"<!-- PCAP_DATA:(.*?) -->", re.DOTALL)


@router.get("/messages/{message_id}/pcap-data")
async def get_pcap_data(
    message_id: UUID,
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Extract structured PCAP analysis data from a message's tool call metadata.
    """
    stmt = select(Message).where(Message.id == message_id)
    result = await db.execute(stmt)
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    # Validate ownership via conversation (raises 404 if not owned)
    await _get_owned_conversation(
        conversation_id=message.conversation_id,
        user_id=current_user.id,
        db=db,
    )

    metadata = message.message_metadata or {}
    tool_calls = metadata.get("tool_calls", [])

    for tc in tool_calls:
        if tc.get("tool") != "analyze_pcap":
            continue
        full_result = tc.get("full_result", "")
        match = _PCAP_DATA_RE.search(full_result)
        if match:
            try:
                raw_json = match.group(1)
                # Fix invalid \' escapes that leak from Python/SQL serialization
                raw_json = raw_json.replace("\\'", "'")
                return json.loads(raw_json)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to parse PCAP data",
                )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No PCAP analysis data found in this message",
    )
