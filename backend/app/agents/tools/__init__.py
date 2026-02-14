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
from app.agents.tools.config_tools import (
    create_diff_config_risk_tool,
    create_parse_config_tool,
    create_pre_change_review_tool,
    create_validate_config_tool,
)
from app.agents.tools.show_command_tools import create_parse_show_commands_tool
from app.agents.tools.pcap_tools import create_analyze_pcap_tool


def get_agent_tools(db: AsyncSession, user_id: UUID) -> list[BaseTool]:
    """
    Retorna lista de tools disponiveis para o agent.

    Args:
        db: Sessao async do banco (compartilhada com o request).
        user_id: UUID do usuario autenticado.
    """
    return [
        # RAG (Phase 3-4)
        create_search_rag_global_tool(db),
        create_search_rag_local_tool(db, user_id),
        # Config Analysis (Phase 5-6)
        create_parse_config_tool(),
        create_validate_config_tool(),
        create_diff_config_risk_tool(),
        create_pre_change_review_tool(),
        # Show Commands (Phase 5-6)
        create_parse_show_commands_tool(),
        # PCAP Analysis (Phase 5-6)
        create_analyze_pcap_tool(db, user_id),
    ]
