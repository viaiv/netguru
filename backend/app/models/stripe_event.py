"""
StripeEvent model — registro imutavel de todos os webhook events recebidos do Stripe.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class StripeEvent(Base):
    """
    Tracks every Stripe webhook event received (processed, ignored, or failed).

    Used for admin visibility and debugging billing issues.
    """

    __tablename__ = "stripe_events"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    event_id = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="evt_xxx do Stripe",
    )
    event_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment="checkout.session.completed|customer.subscription.updated|etc",
    )
    status = Column(
        String(20),
        nullable=False,
        index=True,
        comment="processed|failed|ignored",
    )
    customer_id = Column(String(255), nullable=True, comment="cus_xxx do Stripe")
    subscription_id = Column(String(255), nullable=True, comment="sub_xxx do Stripe")
    user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    payload_summary = Column(String(500), nullable=True, comment="str(data)[:500] truncado")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return (
            f"<StripeEvent(id={self.id}, event_type='{self.event_type}', "
            f"status='{self.status}')>"
        )
