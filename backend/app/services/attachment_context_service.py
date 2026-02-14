"""
AttachmentContextService — resolve referencias implicitas de anexos no chat.

Responsabilidades:
- registrar anexos explicitos recebidos no turno atual
- recuperar anexos recentes da conversa
- resolver "este pcap/essa config" para um documento concreto
- pedir desambiguacao quando houver multiplos candidatos
- enriquecer o prompt do agent com contexto do arquivo selecionado
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message
from app.models.document import Document
from app.services.r2_storage_service import R2StorageService

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}\b"
)

ATTACHMENT_REFERENCE_HINTS = (
    "anexo",
    "anexado",
    "arquivo",
    "este pcap",
    "esse pcap",
    "esta captura",
    "essa captura",
    "esta config",
    "essa config",
    "este log",
    "esse log",
)

PCAP_HINTS = (
    "pcap",
    "pcapng",
    "captura",
    "packet capture",
    "wireshark",
    "trafego",
    "pacotes",
)

CONFIG_HINTS = (
    "config",
    "configuracao",
    "configuração",
    "valida",
    "validação",
    "validation",
    "audit",
    "review",
    "parse",
    "analisar",
    "analise",
    "log",
)

TEXTUAL_FILE_TYPES = {"txt", "conf", "cfg", "log", "md", "pdf", "config"}

DEFAULT_EXCERPT_CHARS = 6000
RECENT_MESSAGES_LOOKBACK = 40
RECENT_ATTACHMENTS_LIMIT = 8


@dataclass(frozen=True)
class ResolvedAttachment:
    """Documento selecionado para contexto automatico."""

    document_id: UUID
    filename: str
    file_type: str
    source: str  # explicit | recent


@dataclass
class AttachmentContextResolution:
    """Resultado da resolucao de contexto de anexos."""

    content_for_agent: str
    user_message_metadata: dict | None = None
    resolved_attachment: ResolvedAttachment | None = None
    ambiguity_prompt: str | None = None
    ambiguity_candidates: list[ResolvedAttachment] | None = None


class AttachmentContextService:
    """Resolve contexto de anexos (documentos) para o turno atual do chat."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve_context(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        explicit_document_ids: list[UUID] | None = None,
    ) -> AttachmentContextResolution:
        """
        Resolve anexos implicitos/explicitos e devolve conteudo enriquecido para o agent.

        Args:
            user_id: Usuario dono da conversa.
            conversation_id: Conversa atual.
            content: Mensagem original do usuario.
            explicit_document_ids: IDs recebidos explicitamente do frontend WS.
        """
        normalized = " ".join(content.lower().split())

        explicit_ids = self._merge_explicit_ids(
            explicit_document_ids=explicit_document_ids or [],
            content=content,
        )
        intent = self._infer_intent(normalized)

        if not explicit_ids and not self._looks_like_attachment_reference(normalized):
            return AttachmentContextResolution(content_for_agent=content)

        candidates: list[ResolvedAttachment] = []
        if explicit_ids:
            candidates = await self._load_documents_as_candidates(
                user_id=user_id,
                document_ids=explicit_ids,
                source="explicit",
            )
        else:
            candidates = await self._load_recent_attachment_candidates(
                user_id=user_id,
                conversation_id=conversation_id,
            )

        if intent == "pcap":
            candidates = [c for c in candidates if c.file_type in {"pcap", "pcapng"}]
        elif intent == "config":
            candidates = [c for c in candidates if c.file_type in TEXTUAL_FILE_TYPES]

        if not candidates:
            return AttachmentContextResolution(
                content_for_agent=content,
                user_message_metadata=self._build_user_metadata(
                    registered_attachments=[],
                    resolution_status="no_candidates",
                ),
            )

        if len(candidates) > 1 and not explicit_ids:
            return AttachmentContextResolution(
                content_for_agent=content,
                user_message_metadata=self._build_user_metadata(
                    registered_attachments=[],
                    resolution_status="ambiguous",
                    ambiguity_candidates=candidates,
                ),
                ambiguity_prompt=self._build_ambiguity_prompt(candidates),
                ambiguity_candidates=candidates,
            )

        selected = candidates[0]
        registered_attachments: list[ResolvedAttachment] = []
        if explicit_ids:
            # Registra todos anexos explicitos do turno no metadata da mensagem do usuario.
            registered_attachments = candidates

        content_for_agent = await self._augment_content_for_agent(
            content=content,
            selected=selected,
            intent=intent,
        )

        return AttachmentContextResolution(
            content_for_agent=content_for_agent,
            user_message_metadata=self._build_user_metadata(
                registered_attachments=registered_attachments,
                resolution_status="resolved",
                selected=selected,
                intent=intent,
            ),
            resolved_attachment=selected,
        )

    def _merge_explicit_ids(
        self,
        *,
        explicit_document_ids: list[UUID],
        content: str,
    ) -> list[UUID]:
        merged: list[UUID] = []
        seen: set[UUID] = set()

        for doc_id in explicit_document_ids:
            if doc_id not in seen:
                seen.add(doc_id)
                merged.append(doc_id)

        for match in UUID_RE.findall(content):
            try:
                doc_id = UUID(match)
            except ValueError:
                continue
            if doc_id not in seen:
                seen.add(doc_id)
                merged.append(doc_id)

        return merged

    @staticmethod
    def _looks_like_attachment_reference(normalized_text: str) -> bool:
        return any(hint in normalized_text for hint in ATTACHMENT_REFERENCE_HINTS)

    @staticmethod
    def _infer_intent(normalized_text: str) -> str | None:
        if any(hint in normalized_text for hint in PCAP_HINTS):
            return "pcap"
        if any(hint in normalized_text for hint in CONFIG_HINTS):
            return "config"
        if any(hint in normalized_text for hint in ATTACHMENT_REFERENCE_HINTS):
            return "generic"
        return None

    async def _load_documents_as_candidates(
        self,
        *,
        user_id: UUID,
        document_ids: list[UUID],
        source: str,
    ) -> list[ResolvedAttachment]:
        if not document_ids:
            return []

        stmt = select(Document).where(
            Document.user_id == user_id,
            Document.id.in_(document_ids),
        )
        result = await self._db.execute(stmt)
        docs = result.scalars().all()
        docs_by_id = {doc.id: doc for doc in docs}

        ordered: list[ResolvedAttachment] = []
        for doc_id in document_ids:
            doc = docs_by_id.get(doc_id)
            if doc is None:
                continue
            ordered.append(
                ResolvedAttachment(
                    document_id=doc.id,
                    filename=doc.original_filename,
                    file_type=(doc.file_type or "").lower(),
                    source=source,
                )
            )
        return ordered

    async def _load_recent_attachment_candidates(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
    ) -> list[ResolvedAttachment]:
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .limit(RECENT_MESSAGES_LOOKBACK)
        )
        result = await self._db.execute(stmt)
        messages = result.scalars().all()

        ordered_ids: list[UUID] = []
        seen: set[UUID] = set()

        for message in messages:
            metadata = message.message_metadata or {}
            attachments = metadata.get("attachments", [])
            if isinstance(attachments, list):
                for item in attachments:
                    if not isinstance(item, dict):
                        continue
                    raw_id = item.get("document_id")
                    if not raw_id:
                        continue
                    try:
                        doc_id = UUID(str(raw_id))
                    except ValueError:
                        continue
                    if doc_id in seen:
                        continue
                    seen.add(doc_id)
                    ordered_ids.append(doc_id)

            # Backward compatibility: older messages may carry UUID inline in content.
            for match in UUID_RE.findall(message.content or ""):
                try:
                    doc_id = UUID(match)
                except ValueError:
                    continue
                if doc_id in seen:
                    continue
                seen.add(doc_id)
                ordered_ids.append(doc_id)

            if len(ordered_ids) >= RECENT_ATTACHMENTS_LIMIT:
                break

        if not ordered_ids:
            return []

        return await self._load_documents_as_candidates(
            user_id=user_id,
            document_ids=ordered_ids[:RECENT_ATTACHMENTS_LIMIT],
            source="recent",
        )

    async def _augment_content_for_agent(
        self,
        *,
        content: str,
        selected: ResolvedAttachment,
        intent: str | None,
    ) -> str:
        parts: list[str] = [content.strip()]
        parts.append("")
        parts.append("[CONTEXTO_AUTOMATICO_DE_ANEXO]")
        parts.append(f"document_id: {selected.document_id}")
        parts.append(f"filename: {selected.filename}")
        parts.append(f"file_type: {selected.file_type}")

        if intent == "pcap":
            parts.append(
                f"Para analisar este PCAP, chame analyze_pcap(document_id=\"{selected.document_id}\"). "
                "IMPORTANTE: passe exatamente o UUID acima, nunca o filename."
            )

        if intent in {"config", "generic"} and selected.file_type in TEXTUAL_FILE_TYPES:
            excerpt = await self._load_text_excerpt(selected)
            if excerpt:
                parts.append("")
                parts.append("Conteudo do arquivo (trecho):")
                parts.append("```")
                parts.append(excerpt)
                parts.append("```")

        return "\n".join(parts).strip()

    async def _load_text_excerpt(self, selected: ResolvedAttachment) -> str | None:
        """
        Carrega trecho textual de um documento (local ou R2) para contexto do agent.
        """
        stmt = select(Document).where(Document.id == selected.document_id)
        result = await self._db.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            return None

        suffix = Path(document.original_filename).suffix.lower()
        is_pdf = document.file_type == "pdf" or suffix == ".pdf"
        try:
            if self._is_r2_path(document.storage_path):
                r2 = await R2StorageService.from_settings(self._db)
                tmp_path = await asyncio.to_thread(
                    r2.download_to_tempfile,
                    document.storage_path,
                    suffix or f".{document.file_type}",
                )
                try:
                    return await asyncio.to_thread(
                        self._read_excerpt_from_path,
                        tmp_path,
                        is_pdf,
                    )
                finally:
                    tmp_path.unlink(missing_ok=True)
            return await asyncio.to_thread(
                self._read_excerpt_from_path,
                Path(document.storage_path),
                is_pdf,
            )
        except Exception:
            # Contexto de anexo nao pode quebrar o chat.
            return None

    @staticmethod
    def _read_excerpt_from_path(path: Path, is_pdf: bool) -> str | None:
        if not path.exists():
            return None

        if is_pdf:
            try:
                import pymupdf

                text_parts: list[str] = []
                with pymupdf.open(str(path)) as doc:
                    for page in doc:
                        text_parts.append(page.get_text())
                text = "\n".join(text_parts)
            except Exception:
                return None
        else:
            text = path.read_text(encoding="utf-8", errors="replace")

        text = text.strip()
        if not text:
            return None
        return text[:DEFAULT_EXCERPT_CHARS]

    @staticmethod
    def _is_r2_path(storage_path: str) -> bool:
        return storage_path.startswith("uploads/") and not Path(storage_path).is_absolute()

    @staticmethod
    def _build_ambiguity_prompt(candidates: list[ResolvedAttachment]) -> str:
        lines: list[str] = [
            "Encontrei mais de um anexo compatível nesta conversa.",
            "Escolha qual arquivo devo usar (responda com número, nome ou UUID):",
            "",
        ]
        for index, item in enumerate(candidates, 1):
            lines.append(
                f"{index}. {item.filename} ({item.file_type}) — {item.document_id}"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_user_metadata(
        *,
        registered_attachments: list[ResolvedAttachment],
        resolution_status: str,
        selected: ResolvedAttachment | None = None,
        intent: str | None = None,
        ambiguity_candidates: list[ResolvedAttachment] | None = None,
    ) -> dict | None:
        metadata: dict = {}

        if registered_attachments:
            metadata["attachments"] = [
                {
                    "document_id": str(item.document_id),
                    "filename": item.filename,
                    "file_type": item.file_type,
                    "source": item.source,
                }
                for item in registered_attachments
            ]

        resolution_payload: dict = {
            "status": resolution_status,
            "intent": intent,
        }
        if selected is not None:
            resolution_payload["resolved_attachment"] = {
                "document_id": str(selected.document_id),
                "filename": selected.filename,
                "file_type": selected.file_type,
                "source": selected.source,
            }
        if ambiguity_candidates:
            resolution_payload["candidates"] = [
                {
                    "document_id": str(item.document_id),
                    "filename": item.filename,
                    "file_type": item.file_type,
                    "source": item.source,
                }
                for item in ambiguity_candidates
            ]

        metadata["attachment_resolution"] = resolution_payload
        return metadata or None
