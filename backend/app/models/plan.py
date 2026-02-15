"""
Plan model — subscription tiers with Stripe integration.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Plan(Base):
    """
    Subscription plan definition with pricing and usage limits.
    """

    __tablename__ = "plans"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    name = Column(String(50), unique=True, nullable=False, comment="slug: solo, team, enterprise")
    display_name = Column(String(100), nullable=False)

    # Stripe integration
    stripe_product_id = Column(String(255), nullable=True)
    stripe_price_id = Column(String(255), nullable=True)

    # Pricing
    price_cents = Column(Integer, nullable=False, default=0, comment="Price in cents (BRL)")
    billing_period = Column(
        String(20),
        nullable=False,
        default="monthly",
        comment="monthly|yearly",
    )

    # Promotional pricing
    promo_price_cents = Column(Integer, nullable=True, comment="Promotional price in cents (BRL)")
    promo_months = Column(Integer, nullable=True, comment="Duration of promo in months")
    stripe_promo_coupon_id = Column(String(255), nullable=True, comment="Stripe Coupon ID for promo")

    # Seat limits
    max_members = Column(Integer, nullable=False, default=1, comment="Seats included in base price")
    price_per_extra_seat_cents = Column(
        Integer, nullable=False, default=0, comment="Price per extra seat in cents (informational)"
    )

    # Usage limits
    upload_limit_daily = Column(Integer, nullable=False, default=10)
    max_file_size_mb = Column(Integer, nullable=False, default=100)
    max_conversations_daily = Column(Integer, nullable=False, default=50)
    max_tokens_daily = Column(Integer, nullable=False, default=100000)

    # Feature flags (JSON)
    features = Column(JSON, nullable=True, comment="Feature flags per plan")

    # Status / ordering
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")

    def __repr__(self) -> str:
        return f"<Plan(id={self.id}, name='{self.name}', price={self.price_cents})>"
