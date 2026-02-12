"""
Pydantic schemas for conversations and messages.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    """
    Request schema for creating a conversation.
    """

    title: str = Field(default="Nova Conversa", max_length=255)
    model_used: str | None = Field(default=None, max_length=100)
    model_config = ConfigDict(protected_namespaces=())


class ConversationResponse(BaseModel):
    """
    API response for conversation resource.
    """

    id: UUID
    user_id: UUID
    title: str
    model_used: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class MessageCreate(BaseModel):
    """
    Request schema for appending a message into a conversation.
    """

    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1)
    tokens_used: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    """
    API response for message resource.
    """

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    tokens_used: int | None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="message_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
