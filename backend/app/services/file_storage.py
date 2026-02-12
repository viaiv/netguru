"""
File storage helpers for upload and retrieval workflows.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import settings


class FileStorageError(Exception):
    """
    Base exception for storage workflow errors.
    """


class FileTooLargeError(FileStorageError):
    """
    Raised when uploaded file exceeds configured max size.
    """


@dataclass(slots=True)
class StoredFile:
    """
    Metadata returned after persisting an uploaded file.
    """

    storage_path: str
    stored_filename: str
    file_size_bytes: int


def get_allowed_extensions() -> set[str]:
    """
    Return normalized list of allowed file extensions.
    """

    return {
        ext.lower().lstrip(".")
        for ext in settings.allowed_file_extensions_list
        if ext.strip()
    }


def get_file_extension(filename: str) -> str:
    """
    Extract normalized extension from filename.
    """

    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix


def ensure_extension_allowed(filename: str) -> str:
    """
    Validate and return file extension for an upload.
    """

    extension = get_file_extension(filename)
    if not extension:
        raise FileStorageError("File must include an extension")
    if extension not in get_allowed_extensions():
        raise FileStorageError(f"File extension .{extension} is not allowed")
    return extension


def resolve_storage_path(storage_path: str) -> Path:
    """
    Resolve a storage path and enforce it is inside configured upload dir.
    """

    base_dir = Path(settings.UPLOAD_DIR).resolve()
    resolved_path = Path(storage_path).resolve()
    if not resolved_path.is_relative_to(base_dir):
        raise FileStorageError("Invalid storage path")
    return resolved_path


async def persist_uploaded_file(
    user_id: UUID,
    upload_file: UploadFile,
    *,
    max_size_bytes: int,
) -> StoredFile:
    """
    Persist uploaded file to disk with size validation.
    """

    original_name = Path(upload_file.filename or "").name
    extension = ensure_extension_allowed(original_name)

    user_dir = Path(settings.UPLOAD_DIR) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4().hex}.{extension}"
    destination_path = (user_dir / stored_filename).resolve()

    written_bytes = 0
    try:
        with destination_path.open("wb") as output_file:
            while True:
                chunk = await upload_file.read(1024 * 1024)
                if not chunk:
                    break
                written_bytes += len(chunk)
                if written_bytes > max_size_bytes:
                    raise FileTooLargeError(
                        f"File exceeds maximum size of {max_size_bytes} bytes"
                    )
                output_file.write(chunk)
    except Exception:
        if destination_path.exists():
            destination_path.unlink()
        raise
    finally:
        await upload_file.close()

    return StoredFile(
        storage_path=str(destination_path),
        stored_filename=stored_filename,
        file_size_bytes=written_bytes,
    )


def delete_stored_file(storage_path: str) -> None:
    """
    Delete an existing file from storage if present.
    """

    path = resolve_storage_path(storage_path)
    if path.exists():
        path.unlink()
