"""
Agent tools registry — retorna tools disponiveis para o agent.
"""
from __future__ import annotations

from uuid import UUID

from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.rag_tools import (
    create_search_rag_global_tool,
    create_search_rag_local_tool,
)


def get_agent_tools(db: AsyncSession, user_id: UUID) -> list[BaseTool]:
    """
    Retorna lista de tools disponiveis para o agent.

    Args:
        db: Sessao async do banco (compartilhada com o request).
        user_id: UUID do usuario autenticado.
    """
    return [
        create_search_rag_global_tool(db),
        create_search_rag_local_tool(db, user_id),
    ]
