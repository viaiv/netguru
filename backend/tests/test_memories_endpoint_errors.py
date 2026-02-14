"""
Memory endpoint error mapping tests.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException, status

from app.api.v1.endpoints.memories import _raise_memory_http_error
from app.services.memory_service import MemoryServiceError


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("memory_not_found", status.HTTP_404_NOT_FOUND),
        ("memory_conflict", status.HTTP_409_CONFLICT),
        ("memory_schema_missing", status.HTTP_503_SERVICE_UNAVAILABLE),
        ("memory_error", status.HTTP_400_BAD_REQUEST),
    ],
)
def test_raise_memory_http_error_maps_service_codes(
    code: str,
    expected_status: int,
) -> None:
    """
    Domain memory errors must be translated to deterministic HTTP responses.
    """
    with pytest.raises(HTTPException) as exc_info:
        _raise_memory_http_error(MemoryServiceError("erro", code=code))

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == "erro"
