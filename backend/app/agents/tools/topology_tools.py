"""
Agent tool — generate_topology: builds visual network topology from configs.
"""
from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.topology import Topology
from app.services.topology_service import TopologyService

logger = logging.getLogger(__name__)


class GenerateTopologyInput(BaseModel):
    """Input schema for generate_topology tool."""
    config_text: str = Field(
        ...,
        description=(
            "One or more network device configurations (Cisco IOS/Juniper). "
            "Separate multiple configs with '---' on its own line."
        ),
    )
    title: str = Field(
        default="Topologia de rede",
        description="Title for the generated topology.",
    )


async def _generate_topology(
    config_text: str,
    title: str = "Topologia de rede",
    *,
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
) -> str:
    """
    Generate a network topology diagram from device configuration(s).

    Parses the config text, extracts devices/interfaces/neighbors,
    and builds a visual topology graph.
    """
    try:
        result = TopologyService.generate_from_config_text(config_text)
    except Exception as exc:
        logger.exception("Topology generation failed")
        return f"Erro ao gerar topologia: {exc}"

    nodes = result["nodes"]
    edges = result["edges"]
    summary = result["summary"]
    metadata = result["metadata"]

    if not nodes:
        return (
            "Nao foi possivel extrair dispositivos da configuracao fornecida. "
            "Verifique se o texto contem configs validas de Cisco IOS ou Juniper."
        )

    # Persist topology
    topo = Topology(
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        title=title,
        source_type="config",
        nodes=nodes,
        edges=edges,
        summary=summary,
        topology_metadata=metadata,
    )
    db.add(topo)
    await db.flush()

    return (
        f"Topologia gerada com sucesso!\n\n"
        f"**{title}**\n"
        f"- {metadata['device_count']} dispositivo(s)\n"
        f"- {metadata['link_count']} link(s)\n"
        f"- Vendors: {', '.join(metadata.get('vendors', [])) or 'N/A'}\n\n"
        f"ID da topologia: `{topo.id}`\n"
        f"Visualize em: /topology/{topo.id}"
    )


def create_generate_topology_tool(
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
) -> StructuredTool:
    """Factory that creates the generate_topology tool with injected context."""

    async def run_tool(config_text: str, title: str = "Topologia de rede") -> str:
        return await _generate_topology(
            config_text,
            title,
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )

    return StructuredTool.from_function(
        coroutine=run_tool,
        name="generate_topology",
        description=(
            "Generate a visual network topology diagram from device configurations. "
            "Input: Cisco IOS or Juniper config text (one or multiple devices separated by '---'). "
            "Use when the user asks to visualize network topology, create a network diagram, "
            "or map device interconnections from configs or show command outputs."
        ),
        args_schema=GenerateTopologyInput,
    )
