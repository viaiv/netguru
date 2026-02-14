"""
Attachment context resolver tests.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.attachment_context_service import (
    AttachmentContextService,
    ResolvedAttachment,
)


class StubAttachmentContextService(AttachmentContextService):
    """AttachmentContextService with in-memory candidates for deterministic tests."""

    def __init__(
        self,
        explicit_candidates: list[ResolvedAttachment] | None = None,
        recent_candidates: list[ResolvedAttachment] | None = None,
        excerpt_text: str | None = None,
    ) -> None:
        super().__init__(db=None)  # type: ignore[arg-type]
        self._explicit_candidates = explicit_candidates or []
        self._recent_candidates = recent_candidates or []
        self._excerpt_text = excerpt_text

    async def _load_documents_as_candidates(  # type: ignore[override]
        self,
        *,
        user_id: UUID,  # noqa: ARG002
        document_ids: list[UUID],  # noqa: ARG002
        source: str,  # noqa: ARG002
    ) -> list[ResolvedAttachment]:
        return list(self._explicit_candidates)

    async def _load_recent_attachment_candidates(  # type: ignore[override]
        self,
        *,
        user_id: UUID,  # noqa: ARG002
        conversation_id: UUID,  # noqa: ARG002
    ) -> list[ResolvedAttachment]:
        return list(self._recent_candidates)

    async def _load_text_excerpt(self, selected: ResolvedAttachment) -> str | None:  # type: ignore[override]
        _ = selected
        return self._excerpt_text


@pytest.mark.asyncio
async def test_attachment_context_resolves_single_explicit_pcap() -> None:
    """
    Explicit single attachment should resolve directly and enrich agent content.
    """
    doc_id = uuid4()
    service = StubAttachmentContextService(
        explicit_candidates=[
            ResolvedAttachment(
                document_id=doc_id,
                filename="capture-edge.pcap",
                file_type="pcap",
                source="explicit",
            )
        ],
    )

    result = await service.resolve_context(
        user_id=uuid4(),
        conversation_id=uuid4(),
        content="analise este pcap",
        explicit_document_ids=[doc_id],
    )

    assert result.ambiguity_prompt is None
    assert result.resolved_attachment is not None
    assert result.resolved_attachment.document_id == doc_id
    assert "document_id: " in result.content_for_agent
    assert "analyze_pcap" in result.content_for_agent
    assert result.user_message_metadata is not None
    attachments = result.user_message_metadata.get("attachments", [])
    assert len(attachments) == 1
    assert attachments[0]["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_attachment_context_requests_disambiguation_for_multiple_recent_candidates() -> None:
    """
    Multiple recent compatible files should return ambiguity prompt.
    """
    first = ResolvedAttachment(
        document_id=uuid4(),
        filename="branch-a.pcap",
        file_type="pcap",
        source="recent",
    )
    second = ResolvedAttachment(
        document_id=uuid4(),
        filename="branch-b.pcap",
        file_type="pcap",
        source="recent",
    )
    service = StubAttachmentContextService(recent_candidates=[first, second])

    result = await service.resolve_context(
        user_id=uuid4(),
        conversation_id=uuid4(),
        content="analise este pcap",
        explicit_document_ids=None,
    )

    assert result.resolved_attachment is None
    assert result.ambiguity_prompt is not None
    assert "branch-a.pcap" in result.ambiguity_prompt
    assert "branch-b.pcap" in result.ambiguity_prompt
    assert result.user_message_metadata is not None
    assert (
        result.user_message_metadata["attachment_resolution"]["status"]
        == "ambiguous"
    )


@pytest.mark.asyncio
async def test_attachment_context_includes_excerpt_for_config_intent() -> None:
    """
    Config intent should include file excerpt when available.
    """
    doc_id = uuid4()
    service = StubAttachmentContextService(
        explicit_candidates=[
            ResolvedAttachment(
                document_id=doc_id,
                filename="edge-router.cfg",
                file_type="config",
                source="explicit",
            )
        ],
        excerpt_text="router ospf 1\n network 10.0.0.0 0.0.0.255 area 0",
    )

    result = await service.resolve_context(
        user_id=uuid4(),
        conversation_id=uuid4(),
        content="valide essa config",
        explicit_document_ids=[doc_id],
    )

    assert result.resolved_attachment is not None
    assert "Conteudo do arquivo (trecho):" in result.content_for_agent
    assert "router ospf 1" in result.content_for_agent
