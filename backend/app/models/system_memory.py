"""
System memory model for curated global context shared across users.
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

from app.core.database import Base


class SystemMemory(Base):
    """
    Curated memory entries managed by admin/owner and applied globally as fallback.
    """

    __tablename__ = "system_memories"
    __table_args__ = (
        CheckConstraint(
            "scope = 'system'",
            name="ck_system_memories_scope_system",
        ),
        CheckConstraint(
            "scope_name IS NULL",
            name="ck_system_memories_scope_name_null",
        ),
    )

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)

    scope = Column(String(20), nullable=False, default="system", comment="system")
    scope_name = Column(String(120), nullable=True, index=True)

    memory_key = Column(String(120), nullable=False, index=True)
    memory_value = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True)

    ttl_seconds = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_by = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<SystemMemory(id={self.id}, scope='{self.scope}', "
            f"key='{self.memory_key}', version={self.version})>"
        )
