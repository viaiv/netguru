"""
File upload and management endpoints.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, status
from fastapi import UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission
from app.models.document import Document
from app.models.user import User
from app.schemas.document import (
    FileDetailResponse,
    FileItemResponse,
    FileListResponse,
    FilePagination,
    FileUploadResponse,
)
from app.services.file_storage import (
    FileStorageError,
    FileTooLargeError,
    delete_stored_file,
    ensure_extension_allowed,
    persist_uploaded_file,
    resolve_storage_path,
)
from app.services.usage_tracking_service import UsageTrackingService

logger = logging.getLogger(__name__)

router = APIRouter()

PROCESSABLE_EXTENSIONS = {"txt", "conf", "cfg", "log", "md", "pdf"}


SUPPORTED_FILE_TYPES = {
    "config",
    "log",
    "pcap",
    "pcapng",
    "txt",
    "conf",
    "cfg",
    "pdf",
    "md",
}

EXTENSION_DEFAULT_FILE_TYPE = {
    "txt": "config",
    "conf": "config",
    "cfg": "config",
    "log": "log",
    "pcap": "pcap",
    "pcapng": "pcap",
    "cap": "pcap",
    "pdf": "pdf",
    "md": "md",
}


def _build_file_item(document: Document) -> FileItemResponse:
    """
    Build safe API response for file metadata.
    """

    return FileItemResponse(
        id=document.id,
        filename=document.original_filename,
        original_filename=document.original_filename,
        file_type=document.file_type,
        file_size_bytes=document.file_size_bytes,
        status=document.status,
        metadata=document.document_metadata,
        created_at=document.created_at,
        processed_at=document.processed_at,
    )


def _resolve_file_type(file_type: str | None, extension: str) -> str:
    """
    Resolve canonical file type from form data or extension.
    """

    if file_type is None:
        return EXTENSION_DEFAULT_FILE_TYPE.get(extension, extension)

    normalized = file_type.strip().lower()
    if normalized not in SUPPORTED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file_type '{normalized}'",
        )
    return normalized


async def _get_owned_document(
    file_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Document:
    """
    Return a user-owned document or raise 404.
    """

    stmt = select(Document).where(Document.id == file_id, Document.user_id == user_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return document


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    file_type: str | None = Form(default=None),
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> FileUploadResponse:
    """
    Upload a file and persist metadata for current user.
    """

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    try:
        extension = ensure_extension_allowed(file.filename)
    except FileStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    resolved_file_type = _resolve_file_type(file_type, extension)
    max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    try:
        stored_file = await persist_uploaded_file(
            user_id=current_user.id,
            upload_file=file,
            max_size_bytes=max_size_bytes,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds limit of {settings.MAX_FILE_SIZE_MB} MB",
        ) from exc
    except FileStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    document = Document(
        user_id=current_user.id,
        filename=stored_file.stored_filename,
        original_filename=file.filename,
        file_type=resolved_file_type,
        file_size_bytes=stored_file.file_size_bytes,
        storage_path=stored_file.storage_path,
        mime_type=file.content_type,
        status="uploaded",
        document_metadata=None,
    )
    db.add(document)

    try:
        await db.commit()
        await db.refresh(document)
    except Exception:
        await db.rollback()
        delete_stored_file(stored_file.storage_path)
        raise

    # Track usage
    await UsageTrackingService.increment_uploads(db, current_user.id)
    await db.commit()

    # Despacha processamento para Celery worker
    ext = extension.lower()
    if ext in PROCESSABLE_EXTENSIONS:
        from app.workers.tasks.document_tasks import process_document

        process_document.delay(str(document.id))

    return FileUploadResponse(
        id=document.id,
        filename=document.original_filename,
        file_type=document.file_type,
        file_size_bytes=document.file_size_bytes,
        status=document.status,
        created_at=document.created_at,
    )


@router.get("", response_model=FileListResponse)
async def list_files(
    file_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> FileListResponse:
    """
    List files uploaded by current user.
    """

    filters = [Document.user_id == current_user.id]
    if file_type is not None:
        filters.append(Document.file_type == file_type.strip().lower())

    count_stmt = select(func.count()).select_from(Document).where(*filters)
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar_one())

    offset = (page - 1) * limit
    stmt = (
        select(Document)
        .where(*filters)
        .order_by(desc(Document.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    documents = result.scalars().all()

    pages = (total + limit - 1) // limit if total else 0
    return FileListResponse(
        files=[_build_file_item(document) for document in documents],
        pagination=FilePagination(
            total=total,
            page=page,
            pages=pages,
            limit=limit,
        ),
    )


@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: UUID,
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> FileDetailResponse:
    """
    Return metadata for a specific uploaded file.
    """

    document = await _get_owned_document(file_id=file_id, user_id=current_user.id, db=db)
    file_item = _build_file_item(document)
    return FileDetailResponse(
        **file_item.model_dump(),
        download_url=f"/api/v1/files/{document.id}/download",
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Download original file content for a user-owned file.
    """

    document = await _get_owned_document(file_id=file_id, user_id=current_user.id, db=db)

    try:
        path = resolve_storage_path(document.storage_path)
    except FileStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file not found",
        )

    return FileResponse(
        path=path,
        filename=document.original_filename,
        media_type=document.mime_type or "application/octet-stream",
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: UUID,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Delete a user-owned file and related metadata.
    """

    document = await _get_owned_document(file_id=file_id, user_id=current_user.id, db=db)
    storage_path = document.storage_path

    await db.delete(document)
    await db.commit()

    try:
        delete_stored_file(storage_path)
    except FileStorageError:
        # Record deletion must succeed even if file is already missing on disk.
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
