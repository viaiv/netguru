"""
EmailLog model — registro imutavel de todos os emails enviados pelo sistema.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class EmailLog(Base):
    """
    Tracks every email sent (or attempted) by the system.

    Used for admin visibility, debugging delivery issues and future Stripe receipts.
    """

    __tablename__ = "email_logs"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    recipient_email = Column(String(255), nullable=False, index=True)
    recipient_user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="verification|password_reset|welcome|test",
    )
    subject = Column(String(255), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        index=True,
        comment="sent|failed|skipped",
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    recipient = relationship("User", foreign_keys=[recipient_user_id])

    def __repr__(self) -> str:
        return (
            f"<EmailLog(id={self.id}, type='{self.email_type}', "
            f"to='{self.recipient_email}', status='{self.status}')>"
        )
