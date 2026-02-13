"""
WebSocket protocol schemas for chat streaming.

These are used for documentation/validation of the JSON messages
exchanged over the WebSocket connection.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# --- Client → Server ---

class WsClientMessage(BaseModel):
    """User sends a chat message."""

    type: str = Field("message", pattern="^message$")
    content: str = Field(min_length=1, max_length=10000)


class WsClientPing(BaseModel):
    """Keep-alive ping from client."""

    type: str = Field("ping", pattern="^ping$")


# --- Server → Client ---

class WsStreamStart(BaseModel):
    """Signals the beginning of a streamed assistant response."""

    type: str = "stream_start"
    message_id: str


class WsStreamChunk(BaseModel):
    """A chunk of the streamed response."""

    type: str = "stream_chunk"
    content: str


class WsStreamEnd(BaseModel):
    """Signals the end of the streamed assistant response."""

    type: str = "stream_end"
    message_id: str
    tokens_used: int | None = None


class WsError(BaseModel):
    """Error notification from server."""

    type: str = "error"
    code: str
    detail: str


class WsPong(BaseModel):
    """Keep-alive pong response."""

    type: str = "pong"
