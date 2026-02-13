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
        user_id: UUID,
        top_k: int | None = None,
    ) -> list[RAGResult]:
        """Busca embeddings do usuario (user_id = :uid)."""
        top_k = top_k or settings.RAG_TOP_K_LOCAL
        vector = self._embedding.encode(query)
        return await self._search(
            vector=vector,
            top_k=top_k,
            source="local",
            user_filter=user_id,
        )

    async def search_hybrid(
        self,
        query: str,
        user_id: UUID,
    ) -> list[RAGResult]:
        """Combina busca global + local, ordenada por similarity."""
        global_results = await self.search_global(query)
        local_results = await self.search_local(query, user_id)
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
            parts.append(
                f"[{i}] ({source_label}, similarity={r.similarity:.2f})\n{r.chunk_text}"
            )
        return "\n\n---\n\n".join(parts)

    async def _search(
        self,
        vector: list[float],
        top_k: int,
        source: str,
        user_filter: UUID | None,
    ) -> list[RAGResult]:
        """Executa query pgvector com cosine similarity."""
        if user_filter is None:
            where_clause = "e.user_id IS NULL"
            params = {
                "vec": str(vector),
                "min_sim": settings.RAG_MIN_SIMILARITY,
                "top_k": top_k,
            }
        else:
            where_clause = "e.user_id = :uid"
            params = {
                "vec": str(vector),
                "uid": str(user_filter),
                "min_sim": settings.RAG_MIN_SIMILARITY,
                "top_k": top_k,
            }

        sql = text(f"""
            SELECT
                e.chunk_text,
                1 - (e.embedding <=> :vec::vector) AS similarity,
                e.metadata
            FROM embeddings e
            WHERE {where_clause}
              AND e.embedding IS NOT NULL
              AND 1 - (e.embedding <=> :vec::vector) >= :min_sim
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
            )
            for row in rows
        ]
