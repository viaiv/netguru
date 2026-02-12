"""
Unit tests for file storage service helpers.
"""
from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.services.file_storage import (
    FileStorageError,
    FileTooLargeError,
    ensure_extension_allowed,
    persist_uploaded_file,
    resolve_storage_path,
)


def test_ensure_extension_allowed_uses_configured_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Allowed extension list must be resolved from application settings.
    """

    monkeypatch.setattr(settings, "ALLOWED_FILE_EXTENSIONS", "txt,log")
    assert ensure_extension_allowed("router.log") == "log"

    with pytest.raises(FileStorageError):
        ensure_extension_allowed("capture.pcap")


@pytest.mark.asyncio
async def test_persist_uploaded_file_enforces_max_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Upload persistence must reject files above configured limit.
    """

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ALLOWED_FILE_EXTENSIONS", "txt")

    upload = UploadFile(filename="oversize.txt", file=io.BytesIO(b"x" * 32))
    with pytest.raises(FileTooLargeError):
        await persist_uploaded_file(
            user_id=uuid4(),
            upload_file=upload,
            max_size_bytes=8,
        )


@pytest.mark.asyncio
async def test_persist_uploaded_file_writes_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Upload persistence must store file and return metadata.
    """

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ALLOWED_FILE_EXTENSIONS", "txt")

    upload = UploadFile(filename="config.txt", file=io.BytesIO(b"router ospf 1"))
    stored = await persist_uploaded_file(
        user_id=uuid4(),
        upload_file=upload,
        max_size_bytes=1024,
    )

    stored_path = Path(stored.storage_path)
    assert stored.file_size_bytes == 13
    assert stored_path.exists()
    assert stored_path.read_bytes() == b"router ospf 1"


def test_resolve_storage_path_rejects_outside_upload_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Storage resolver must block paths outside upload root.
    """

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    inside_path = tmp_path / "user" / "file.txt"
    inside_path.parent.mkdir(parents=True, exist_ok=True)
    inside_path.touch()
    assert resolve_storage_path(str(inside_path)) == inside_path.resolve()

    outside_path = tmp_path.parent / "outside.txt"
    outside_path.touch()
    with pytest.raises(FileStorageError):
        resolve_storage_path(str(outside_path))
