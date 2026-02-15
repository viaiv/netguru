"""
RAGService — Busca pgvector com cosine similarity para RAG Global e Local.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.embedding_service import EmbeddingService


@dataclass
class RAGResult:
    """Resultado de uma busca RAG."""

    chunk_text: str
    similarity: float
    source: str  # "global" | "local"
    metadata: dict | None = None
    document_id: str | None = None
    document_name: str | None = None


class RAGService:
    """
    Busca vetorial pgvector para Global RAG (vendor docs) e Local RAG (docs do usuario).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._embedding = EmbeddingService.get_instance()

    async def search_global(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RAGResult]:
        """Busca embeddings globais (user_id IS NULL)."""
        top_k = top_k or settings.RAG_TOP_K_GLOBAL
        vector = self._embedding.encode(query)
        return await self._search(
            vector=vector,
            top_k=top_k,
            source="global",
            user_filter=None,
        )

    async def search_local(
        self,
        query: str,
        workspace_id: UUID,
        top_k: int | None = None,
    ) -> list[RAGResult]:
        """Busca embeddings do workspace (workspace_id = :wid)."""
        top_k = top_k or settings.RAG_TOP_K_LOCAL
        vector = self._embedding.encode(query)
        return await self._search(
            vector=vector,
            top_k=top_k,
            source="local",
            workspace_filter=workspace_id,
        )

    async def search_hybrid(
        self,
        query: str,
        workspace_id: UUID,
    ) -> list[RAGResult]:
        """Combina busca global + local, ordenada por similarity."""
        global_results = await self.search_global(query)
        local_results = await self.search_local(query, workspace_id)
        combined = global_results + local_results
        combined.sort(key=lambda r: r.similarity, reverse=True)
        return combined

    def format_context(self, results: list[RAGResult]) -> str:
        """Formata resultados RAG como contexto para o LLM."""
        if not results:
            return ""
        parts: list[str] = []
        for i, r in enumerate(results, 1):
            source_label = "Vendor Docs" if r.source == "global" else "Your Documents"
            doc_ref = f", doc={r.document_name}" if r.document_name else ""
            parts.append(
                f"[{i}] ({source_label}, similarity={r.similarity:.2f}{doc_ref})\n{r.chunk_text}"
            )
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def extract_citations(results: list[RAGResult]) -> list[dict]:
        """Extrai citacoes estruturadas dos resultados RAG para o metadata."""
        citations: list[dict] = []
        for i, r in enumerate(results, 1):
            citation: dict = {
                "index": i,
                "source_type": f"rag_{r.source}",
                "excerpt": r.chunk_text[:200],
                "similarity": round(r.similarity, 3),
            }
            if r.document_id:
                citation["document_id"] = r.document_id
            if r.document_name:
                citation["document_name"] = r.document_name
            citations.append(citation)
        return citations

    async def _search(
        self,
        vector: list[float],
        top_k: int,
        source: str,
        workspace_filter: UUID | None = None,
    ) -> list[RAGResult]:
        """Executa query pgvector com cosine similarity."""
        if workspace_filter is None:
            # Global: docs sem workspace (vendor docs)
            where_clause = "e.workspace_id IS NULL"
            params = {
                "vec": str(vector),
                "min_sim": settings.RAG_MIN_SIMILARITY,
                "top_k": top_k,
            }
        else:
            where_clause = "e.workspace_id = :wid"
            params = {
                "vec": str(vector),
                "wid": str(workspace_filter),
                "min_sim": settings.RAG_MIN_SIMILARITY,
                "top_k": top_k,
            }

        # Usa CAST() em vez de ::vector para evitar conflito com bind params do asyncpg
        # LEFT JOIN documents para trazer document_id e filename (citacoes)
        sql = text(f"""
            SELECT
                e.chunk_text,
                1 - (e.embedding <=> CAST(:vec AS vector)) AS similarity,
                e.metadata,
                e.document_id,
                d.filename AS document_name
            FROM embeddings e
            LEFT JOIN documents d ON d.id = e.document_id
            WHERE {where_clause}
              AND e.embedding IS NOT NULL
              AND 1 - (e.embedding <=> CAST(:vec AS vector)) >= :min_sim
            ORDER BY similarity DESC
            LIMIT :top_k
        """)

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        return [
            RAGResult(
                chunk_text=row.chunk_text,
                similarity=float(row.similarity),
                source=source,
                metadata=row.metadata,
                document_id=str(row.document_id) if row.document_id else None,
                document_name=row.document_name,
            )
            for row in rows
        ]
