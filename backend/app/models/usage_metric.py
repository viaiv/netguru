"""
UsageMetric model — daily usage tracking per user within a workspace.
"""
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class UsageMetric(Base):
    """
    Daily usage counters per user per workspace for plan limit enforcement.
    One row per (workspace, user, day).
    """

    __tablename__ = "usage_metrics"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", "metric_date", name="uq_usage_workspace_user_date"),
    )

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    workspace_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_date = Column(Date, nullable=False, default=date.today, index=True)

    # Counters
    uploads_count = Column(Integer, nullable=False, default=0)
    messages_count = Column(Integer, nullable=False, default=0)
    tokens_used = Column(BigInteger, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    user = relationship("User", backref="usage_metrics")
    workspace = relationship("Workspace", back_populates="usage_metrics")

    def __repr__(self) -> str:
        return (
            f"<UsageMetric(workspace={self.workspace_id}, user={self.user_id}, "
            f"date={self.metric_date}, uploads={self.uploads_count}, msgs={self.messages_count})>"
        )
