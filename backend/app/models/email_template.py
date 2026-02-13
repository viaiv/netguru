"""
EmailTemplate model — templates editaveis para emails transacionais.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class EmailTemplate(Base):
    """
    Stores editable email templates for transactional emails.

    Each email_type (verification, password_reset, welcome, test) has exactly
    one row. Admins can edit subject/body_html via the admin panel.
    """

    __tablename__ = "email_templates"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    email_type = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="verification|password_reset|welcome|test",
    )
    subject = Column(String(255), nullable=False)
    body_html = Column(Text, nullable=False)
    variables = Column(
        JSONB,
        nullable=False,
        default=list,
        comment='[{"name": "action_url", "description": "Link de acao"}, ...]',
    )
    is_active = Column(Boolean, default=True, nullable=False)

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
        return f"<EmailTemplate(type='{self.email_type}', active={self.is_active})>"
