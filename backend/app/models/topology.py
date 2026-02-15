"""
Topology model — persists generated network topologies.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID as SQLAlchemyUUID

from app.core.database import Base


class Topology(Base):
    """
    Network topology generated from configs/show commands.
    Stores nodes and edges as JSON for React Flow rendering.
    """

    __tablename__ = "topologies"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        nullable=True,
        comment="Message that triggered generation",
    )

    title = Column(String(255), nullable=False, default="Topologia de rede")
    source_type = Column(
        String(50),
        nullable=False,
        default="config",
        comment="config|show_command|mixed",
    )

    # Graph data
    nodes = Column(JSON, nullable=False, default=list, comment="React Flow nodes")
    edges = Column(JSON, nullable=False, default=list, comment="React Flow edges")
    summary = Column(Text, nullable=True, comment="Human-readable summary")

    # Metadata
    topology_metadata = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Topology(id={self.id}, title='{self.title}')>"
