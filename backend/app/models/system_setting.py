"""
SystemSetting model — key-value store with optional Fernet encryption.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class SystemSetting(Base):
    """
    Key-value settings table for system-wide configuration.

    Sensitive values (e.g. API keys) are stored encrypted via Fernet.
    """

    __tablename__ = "system_settings"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False, default="")
    is_encrypted = Column(Boolean, default=False, nullable=False)
    description = Column(String(255), nullable=True)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    updated_by = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self) -> str:
        return f"<SystemSetting(key='{self.key}', encrypted={self.is_encrypted})>"
