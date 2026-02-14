"""
Pydantic schemas for RAG admin API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.admin import PaginationMeta


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class FileTypeDistribution(BaseModel):
    file_type: str
    count: int


class StatusDistribution(BaseModel):
    status: str
    count: int


class RagStatsResponse(BaseModel):
    total_documents: int = 0
    total_chunks: int = 0
    global_documents: int = 0
    global_chunks: int = 0
    local_documents: int = 0
    local_chunks: int = 0
    by_file_type: list[FileTypeDistribution] = []
    by_status: list[StatusDistribution] = []


# ---------------------------------------------------------------------------
# Document list
# ---------------------------------------------------------------------------

class RagDocumentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    filename: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    status: str
    chunk_count: int = 0
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime
    processed_at: Optional[datetime] = None


class RagDocumentListResponse(BaseModel):
    items: list[RagDocumentItem]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Upload / Ingest
# ---------------------------------------------------------------------------

class RagUploadResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    created_at: datetime


class RagIngestUrlRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    title: Optional[str] = Field(None, max_length=255)


class RagIngestUrlResponse(BaseModel):
    id: UUID
    original_filename: str
    file_type: str
    file_size_bytes: int
    status: str
    source_url: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Reprocess
# ---------------------------------------------------------------------------

class RagReprocessResponse(BaseModel):
    id: UUID
    status: str
    message: str


# ---------------------------------------------------------------------------
# RAG Gap Tracking
# ---------------------------------------------------------------------------

class TopGapQuery(BaseModel):
    query: str
    count: int
    last_seen: datetime


class RagGapItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    conversation_id: Optional[UUID] = None
    tool_name: str
    query: str
    gap_type: str
    result_preview: Optional[str] = None
    created_at: datetime


class RagGapListResponse(BaseModel):
    items: list[RagGapItem]
    pagination: PaginationMeta


class RagGapStatsResponse(BaseModel):
    total_gaps: int = 0
    global_gaps: int = 0
    local_gaps: int = 0
    top_queries: list[TopGapQuery] = []
