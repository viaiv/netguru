"""
Subscription model — workspace-plan relationship with Stripe billing.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Subscription(Base):
    """
    Tracks active and historical subscriptions per workspace.
    """

    __tablename__ = "subscriptions"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    workspace_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Stripe IDs
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, unique=True, index=True)

    # Seat billing
    seat_quantity = Column(
        Integer, nullable=False, default=1, comment="Quantity billed on Stripe"
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="active|past_due|canceled|incomplete|trialing|unpaid",
    )

    # Promotional
    promo_applied = Column(Boolean, default=False, nullable=False, comment="True if promo coupon was applied")

    # BYO-LLM discount
    byollm_discount_applied = Column(
        Boolean, default=False, nullable=False, comment="True if BYO-LLM coupon was applied at checkout"
    )
    byollm_grace_notified_at = Column(
        DateTime, nullable=True,
        comment="When BYO-LLM removal warning was sent; NULL = no pending grace",
    )

    # Billing period
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    canceled_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")

    def __repr__(self) -> str:
        return (
            f"<Subscription(id={self.id}, workspace_id={self.workspace_id}, "
            f"status='{self.status}')>"
        )
