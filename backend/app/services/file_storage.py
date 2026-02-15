"""
File storage helpers for upload and retrieval workflows.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)


class FileStorageError(Exception):
    """
    Base exception for storage workflow errors.
    """


class FileTooLargeError(FileStorageError):
    """
    Raised when uploaded file exceeds configured max size.
    """


class FileContentMismatchError(FileStorageError):
    """
    Raised when file content (magic bytes) does not match its extension.
    """


@dataclass(slots=True)
class StoredFile:
    """
    Metadata returned after persisting an uploaded file.
    """

    storage_path: str
    stored_filename: str
    file_size_bytes: int


# ---------------------------------------------------------------------------
#  Magic bytes / file signature validation
# ---------------------------------------------------------------------------

# Mapa de extensao → lista de assinaturas aceitas (prefixo dos primeiros bytes)
_MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF"],
    "pcap": [
        b"\xd4\xc3\xb2\xa1",  # pcap little-endian
        b"\xa1\xb2\xc3\xd4",  # pcap big-endian
    ],
    "pcapng": [
        b"\x0a\x0d\x0d\x0a",  # pcapng Section Header Block
    ],
    "cap": [
        b"\xd4\xc3\xb2\xa1",  # pcap little-endian
        b"\xa1\xb2\xc3\xd4",  # pcap big-endian
    ],
}

# Extensoes de texto que nao tem magic bytes — aceitar qualquer conteudo legivel
_TEXT_EXTENSIONS: set[str] = {"txt", "conf", "cfg", "log", "md"}

# Mapa de extensao → MIME types aceitos (do Content-Type do upload)
MIME_POLICY: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "pcap": {
        "application/vnd.tcpdump.pcap",
        "application/octet-stream",
        "application/x-pcap",
    },
    "cap": {
        "application/vnd.tcpdump.pcap",
        "application/octet-stream",
        "application/x-pcap",
    },
    "pcapng": {
        "application/octet-stream",
        "application/x-pcapng",
    },
    "txt": {"text/plain", "application/octet-stream"},
    "conf": {"text/plain", "application/octet-stream"},
    "cfg": {"text/plain", "application/octet-stream"},
    "log": {"text/plain", "application/octet-stream"},
    "md": {"text/plain", "text/markdown", "application/octet-stream"},
}


def validate_magic_bytes(file_path: Path, extension: str) -> None:
    """
    Validate file content matches expected magic bytes for the extension.

    Text-based formats (txt, conf, cfg, log, md) are checked for
    non-binary content instead. Binary formats are checked against
    known magic byte signatures.

    Raises FileContentMismatchError if validation fails.
    """
    if extension in _TEXT_EXTENSIONS:
        # Texto: verificar que nao contem bytes nulos (indicativo de binario)
        with file_path.open("rb") as f:
            sample = f.read(8192)
        if b"\x00" in sample:
            logger.warning(
                "upload_rejected: magic_bytes reason=binary_in_text ext=%s path=%s",
                extension, file_path.name,
            )
            raise FileContentMismatchError(
                f"Arquivo .{extension} contem conteudo binario — esperado texto."
            )
        return

    signatures = _MAGIC_SIGNATURES.get(extension)
    if not signatures:
        # Extensao sem assinatura conhecida — aceitar (cap redireciona para pcap)
        return

    with file_path.open("rb") as f:
        header = f.read(8)

    for sig in signatures:
        if header[: len(sig)] == sig:
            return

    logger.warning(
        "upload_rejected: magic_bytes reason=signature_mismatch ext=%s header=%s path=%s",
        extension, header[:8].hex(), file_path.name,
    )
    raise FileContentMismatchError(
        f"Conteudo do arquivo nao corresponde a extensao .{extension}. "
        f"Verifique se o arquivo esta correto."
    )


def validate_magic_bytes_buffer(data: bytes, extension: str) -> None:
    """
    Validate file content from a bytes buffer against expected magic bytes.

    Same logic as validate_magic_bytes but operates on an in-memory buffer
    instead of a file path. Used for R2 presigned upload confirmation.

    Raises FileContentMismatchError if validation fails.
    """
    if extension in _TEXT_EXTENSIONS:
        sample = data[:8192]
        if b"\x00" in sample:
            logger.warning(
                "upload_rejected: magic_bytes reason=binary_in_text ext=%s",
                extension,
            )
            raise FileContentMismatchError(
                f"Arquivo .{extension} contem conteudo binario — esperado texto."
            )
        return

    signatures = _MAGIC_SIGNATURES.get(extension)
    if not signatures:
        return

    header = data[:8]
    for sig in signatures:
        if header[: len(sig)] == sig:
            return

    logger.warning(
        "upload_rejected: magic_bytes reason=signature_mismatch ext=%s header=%s",
        extension, header[:8].hex(),
    )
    raise FileContentMismatchError(
        f"Conteudo do arquivo nao corresponde a extensao .{extension}. "
        f"Verifique se o arquivo esta correto."
    )


def validate_mime_type(extension: str, content_type: str | None) -> None:
    """
    Validate Content-Type against MIME policy for the extension.

    Raises FileContentMismatchError if the MIME type is not allowed.
    """
    if not content_type:
        return  # Sem Content-Type — aceitar (fallback para magic bytes)

    allowed = MIME_POLICY.get(extension)
    if not allowed:
        return  # Sem politica — aceitar

    normalized = content_type.split(";")[0].strip().lower()
    if normalized not in allowed:
        logger.warning(
            "upload_rejected: mime_mismatch ext=%s mime=%s allowed=%s",
            extension, normalized, allowed,
        )
        raise FileContentMismatchError(
            f"Tipo MIME '{normalized}' nao e compativel com extensao .{extension}."
        )


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
