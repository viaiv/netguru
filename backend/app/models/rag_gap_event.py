"""
RagGapEvent model — tracks RAG queries that returned no relevant results.

Allows admins to identify documentation gaps and prioritize content ingestion.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID

from app.core.database import Base


class RagGapEvent(Base):
    """
    Records instances where RAG search tools found no relevant documentation.

    Used by admin dashboard to identify knowledge gaps and guide
    document ingestion priorities.
    """

    __tablename__ = "rag_gap_events"

    id = Column(
        SQLAlchemyUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name = Column(
        String(50),
        nullable=False,
        index=True,
        comment="search_rag_global | search_rag_local",
    )
    query = Column(
        Text,
        nullable=False,
        comment="Query enviada ao RAG que nao retornou resultados",
    )
    gap_type = Column(
        String(30),
        nullable=False,
        index=True,
        comment="no_results | low_similarity",
    )
    result_preview = Column(
        String(500),
        nullable=True,
        comment="Primeiros 500 chars do resultado do tool",
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<RagGapEvent(id={self.id}, tool='{self.tool_name}', "
            f"gap_type='{self.gap_type}')>"
        )
