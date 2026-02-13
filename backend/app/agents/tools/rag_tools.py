"""
RAG tools para o agent LangGraph — search_rag_global e search_rag_local.
"""
from __future__ import annotations

from uuid import UUID

from langchain_core.tools import StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rag_service import RAGService


def create_search_rag_global_tool(db: AsyncSession) -> StructuredTool:
    """Cria tool de busca RAG global (documentacao de vendors)."""

    async def _search_rag_global(query: str) -> str:
        """
        Search vendor documentation (Cisco, Juniper, Arista) for networking topics.
        Use this tool when the user asks about protocol configuration, troubleshooting,
        best practices, or any vendor-specific command/feature.

        Args:
            query: Technical question or topic to search for.
        """
        svc = RAGService(db)
        results = await svc.search_global(query)
        if not results:
            return "No relevant vendor documentation found for this query."
        return svc.format_context(results)

    return StructuredTool.from_function(
        coroutine=_search_rag_global,
        name="search_rag_global",
        description=(
            "Search vendor documentation (Cisco, Juniper, Arista) for networking topics. "
            "Use when the user asks about protocol configuration (OSPF, BGP, EIGRP, STP, VLANs), "
            "troubleshooting, best practices, or vendor-specific commands and features."
        ),
    )


def create_search_rag_local_tool(db: AsyncSession, user_id: UUID) -> StructuredTool:
    """Cria tool de busca RAG local (documentos do usuario)."""

    async def _search_rag_local(query: str) -> str:
        """
        Search the user's uploaded documents (configs, logs, notes) for relevant information.
        Use this tool when the user asks about their own network, configs, or uploaded files.

        Args:
            query: Question or topic to search in user documents.
        """
        svc = RAGService(db)
        results = await svc.search_local(query, user_id)
        if not results:
            return "No relevant information found in your uploaded documents."
        return svc.format_context(results)

    return StructuredTool.from_function(
        coroutine=_search_rag_local,
        name="search_rag_local",
        description=(
            "Search the user's uploaded documents (configs, logs, notes) for relevant information. "
            "Use when the user asks about their own network, their specific configuration files, "
            "logs they uploaded, or mentions 'my config', 'my network', etc."
        ),
    )
