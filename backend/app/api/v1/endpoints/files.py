"""
File upload and management endpoints.
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, status
from fastapi import UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission
from app.models.document import Document
from app.models.user import User
from app.schemas.document import (
    ConfirmUploadRequest,
    FileDetailResponse,
    FileItemResponse,
    FileListResponse,
    FilePagination,
    FileUploadResponse,
    PresignUploadRequest,
    PresignUploadResponse,
    StorageUsageResponse,
)
from app.services.file_storage import (
    FileContentMismatchError,
    FileStorageError,
    FileTooLargeError,
    delete_stored_file,
    ensure_extension_allowed,
    persist_uploaded_file,
    resolve_storage_path,
    validate_magic_bytes,
    validate_mime_type,
)
from app.services.plan_limit_service import PlanLimitError, PlanLimitService
from app.services.r2_storage_service import (
    R2NotConfiguredError,
    R2OperationError,
    R2StorageService,
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


def _is_r2_path(storage_path: str) -> bool:
    """Retorna True se o storage_path e uma chave R2 (nao caminho absoluto)."""
    return storage_path.startswith("uploads/") and not Path(storage_path).is_absolute()


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


# ---------------------------------------------------------------------------
# Presigned upload (R2)
# ---------------------------------------------------------------------------


@router.post("/presign", response_model=PresignUploadResponse, status_code=status.HTTP_201_CREATED)
async def presign_upload(
    body: PresignUploadRequest,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> PresignUploadResponse:
    """
    Gera URL presigned para upload direto ao R2.

    Cria documento com status 'pending_upload'. O frontend faz PUT na URL
    retornada e depois chama POST /files/confirm.
    """
    # Plan limit enforcement
    try:
        await PlanLimitService.check_upload_limit(db, current_user)
        file_size_mb = body.file_size_bytes / (1024 * 1024)
        await PlanLimitService.check_file_size(db, current_user, file_size_mb)
    except PlanLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": exc.detail,
                "code": exc.code,
                "limit_name": exc.limit_name,
                "current": exc.current_value,
                "max": exc.max_value,
            },
        ) from exc

    try:
        extension = ensure_extension_allowed(body.filename)
    except FileStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # MIME policy check (valida Content-Type antes do upload ao R2)
    try:
        validate_mime_type(extension, body.content_type)
    except FileContentMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if body.file_size_bytes > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds limit of {settings.MAX_FILE_SIZE_MB} MB",
        )

    resolved_file_type = _resolve_file_type(body.file_type, extension)

    try:
        r2 = await R2StorageService.from_settings(db)
    except R2NotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    object_key = R2StorageService.generate_object_key(current_user.id, extension)
    expires_in = 600

    try:
        presigned_url = r2.generate_presigned_upload_url(
            object_key=object_key,
            content_type=body.content_type,
            expires_in=expires_in,
        )
    except R2OperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    document = Document(
        user_id=current_user.id,
        filename=object_key.rsplit("/", 1)[-1],
        original_filename=body.filename,
        file_type=resolved_file_type,
        file_size_bytes=body.file_size_bytes,
        storage_path=object_key,
        mime_type=body.content_type,
        status="pending_upload",
        document_metadata=None,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    return PresignUploadResponse(
        document_id=document.id,
        presigned_url=presigned_url,
        object_key=object_key,
        expires_in=expires_in,
    )


@router.post("/confirm", response_model=FileUploadResponse)
async def confirm_upload(
    body: ConfirmUploadRequest,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> FileUploadResponse:
    """
    Confirma que o upload direto ao R2 foi concluido.

    Verifica o objeto no R2 via HEAD, atualiza status para 'uploaded'
    e despacha processamento Celery se aplicavel.
    """
    document = await _get_owned_document(
        file_id=body.document_id, user_id=current_user.id, db=db,
    )

    if document.status != "pending_upload":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document status is '{document.status}', expected 'pending_upload'",
        )

    try:
        r2 = await R2StorageService.from_settings(db)
        metadata = r2.head_object(document.storage_path)
    except R2NotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except R2OperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Arquivo nao encontrado no R2: {exc}",
        ) from exc

    # Atualiza tamanho real do arquivo se diferente
    actual_size = metadata.get("content_length", document.file_size_bytes)
    document.file_size_bytes = actual_size
    document.status = "uploaded"
    await db.commit()
    await db.refresh(document)

    # Track usage
    await UsageTrackingService.increment_uploads(db, current_user.id)
    await db.commit()

    # Despacha processamento para Celery worker
    extension = Path(document.original_filename).suffix.lower().lstrip(".")
    if extension in PROCESSABLE_EXTENSIONS:
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


# ---------------------------------------------------------------------------
# Legacy upload (local disk — mantido para compatibilidade)
# ---------------------------------------------------------------------------


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
    # Plan limit enforcement
    try:
        await PlanLimitService.check_upload_limit(db, current_user)
    except PlanLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": exc.detail,
                "code": exc.code,
                "limit_name": exc.limit_name,
                "current": exc.current_value,
                "max": exc.max_value,
            },
        ) from exc

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

    # MIME policy check
    try:
        validate_mime_type(extension, file.content_type)
    except FileContentMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

    # Magic bytes validation (verifica assinatura do conteudo)
    try:
        validate_magic_bytes(Path(stored_file.storage_path), extension)
    except FileContentMismatchError as exc:
        delete_stored_file(stored_file.storage_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Plan-based file size check (may be stricter than global MAX_FILE_SIZE_MB)
    try:
        file_size_mb = stored_file.file_size_bytes / (1024 * 1024)
        await PlanLimitService.check_file_size(db, current_user, file_size_mb)
    except PlanLimitError as exc:
        delete_stored_file(stored_file.storage_path)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": exc.detail,
                "code": exc.code,
                "limit_name": exc.limit_name,
                "current": exc.current_value,
                "max": exc.max_value,
            },
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


@router.get("/storage-usage", response_model=StorageUsageResponse)
async def get_storage_usage(
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> StorageUsageResponse:
    """
    Retorna resumo de uso de storage do usuario atual.
    """

    stmt = select(
        func.coalesce(func.sum(Document.file_size_bytes), 0),
        func.count(),
    ).where(Document.user_id == current_user.id)
    result = await db.execute(stmt)
    total_bytes, total_files = result.one()

    return StorageUsageResponse(
        total_bytes=int(total_bytes),
        total_files=int(total_files),
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


@router.get("/{file_id}/download", response_model=None)
async def download_file(
    file_id: UUID,
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> FileResponse | JSONResponse:
    """
    Download original file content for a user-owned file.

    Para arquivos no R2, retorna JSON com URL presigned de download.
    Para arquivos locais, retorna FileResponse.
    """

    document = await _get_owned_document(file_id=file_id, user_id=current_user.id, db=db)

    if _is_r2_path(document.storage_path):
        try:
            r2 = await R2StorageService.from_settings(db)
            download_url = r2.generate_presigned_download_url(document.storage_path)
        except R2NotConfiguredError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc
        except R2OperationError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        return JSONResponse({"download_url": download_url})

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

    if _is_r2_path(storage_path):
        try:
            r2 = await R2StorageService.from_settings(db)
            r2.delete_object(storage_path)
        except (R2NotConfiguredError, R2OperationError):
            logger.warning("Falha ao deletar objeto R2: %s", storage_path)
    else:
        try:
            delete_stored_file(storage_path)
        except FileStorageError:
            pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
