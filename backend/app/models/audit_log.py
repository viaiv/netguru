"""
AuditLog model — immutable record of admin actions.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class AuditLog(Base):
    """
    Tracks administrative actions for compliance and debugging.
    """

    __tablename__ = "audit_logs"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    actor_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(100), nullable=False, index=True, comment="e.g. user.role_changed")
    target_type = Column(String(50), nullable=True, comment="e.g. user, plan, subscription")
    target_id = Column(String(36), nullable=True, comment="UUID of the target entity")
    changes = Column(JSON, nullable=True, comment="Before/after snapshot")
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    actor = relationship("User", foreign_keys=[actor_id])

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', actor={self.actor_id})>"
