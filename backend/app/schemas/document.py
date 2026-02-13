"""
Pydantic schemas for documents and embeddings.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """
    Request schema for document metadata creation.
    """

    filename: str = Field(max_length=255)
    original_filename: str = Field(max_length=255)
    file_type: str = Field(max_length=50)
    file_size_bytes: int = Field(ge=0)
    storage_path: str
    mime_type: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] | None = None


class DocumentResponse(BaseModel):
    """
    API response for document resource.
    """

    id: UUID
    user_id: UUID
    filename: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    storage_path: str
    mime_type: str | None
    status: str
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="document_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class EmbeddingResponse(BaseModel):
    """
    API response for embedding record.
    """

    id: UUID
    user_id: UUID | None
    document_id: UUID | None
    chunk_text: str
    chunk_index: int
    embedding: list[float] | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="embedding_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PresignUploadRequest(BaseModel):
    """
    Request para gerar URL presigned de upload (R2).
    """

    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=100)
    file_size_bytes: int = Field(ge=0)
    file_type: str | None = Field(default=None, max_length=50)


class PresignUploadResponse(BaseModel):
    """
    Response com URL presigned e ID do documento criado.
    """

    document_id: UUID
    presigned_url: str
    object_key: str
    expires_in: int


class ConfirmUploadRequest(BaseModel):
    """
    Request para confirmar que o upload direto ao R2 foi concluido.
    """

    document_id: UUID


class FileUploadResponse(BaseModel):
    """
    API response after file upload creation.
    """

    id: UUID
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileItemResponse(BaseModel):
    """
    API response for file listing items.
    """

    id: UUID
    filename: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    status: str
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="document_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FilePagination(BaseModel):
    """
    Pagination metadata for file listing.
    """

    total: int
    page: int
    pages: int
    limit: int


class FileListResponse(BaseModel):
    """
    Paginated list response for user files.
    """

    files: list[FileItemResponse]
    pagination: FilePagination


class FileDetailResponse(FileItemResponse):
    """
    API response for a file detail resource.
    """

    download_url: str
