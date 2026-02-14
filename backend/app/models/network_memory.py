"""
Network memory model for persistent contextual facts per user/scope.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class NetworkMemory(Base):
    """
    User memory entries used to enrich chat context automatically.

    Scope levels:
    - global: applies to all environments/devices
    - site: applies to one site scope_name
    - device: applies to one device scope_name
    """

    __tablename__ = "network_memories"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('global', 'site', 'device')",
            name="ck_network_memories_scope_valid",
        ),
        CheckConstraint(
            "(scope = 'global' AND scope_name IS NULL) OR "
            "(scope IN ('site', 'device') AND scope_name IS NOT NULL)",
            name="ck_network_memories_scope_name_required",
        ),
    )

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scope = Column(String(20), nullable=False, comment="global|site|device")
    scope_name = Column(String(120), nullable=True, index=True)

    memory_key = Column(String(120), nullable=False, index=True)
    memory_value = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True)

    ttl_seconds = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="network_memories")

    def __repr__(self) -> str:
        return (
            f"<NetworkMemory(id={self.id}, user_id={self.user_id}, "
            f"scope='{self.scope}', key='{self.memory_key}', version={self.version})>"
        )
