"""
Workspace and WorkspaceMember models for multi-tenant workspace support.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Workspace(Base):
    """
    Workspace container for team collaboration.

    Every user belongs to at least one workspace.
    Solo users get an auto-created personal workspace.
    Plan/subscription are workspace-level, not user-level.
    """

    __tablename__ = "workspaces"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    owner_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_tier = Column(
        String(20),
        nullable=False,
        default="free",
        comment="free|solo|team|enterprise",
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship(
        "WorkspaceMember",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    subscriptions = relationship(
        "Subscription",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    documents = relationship(
        "Document",
        back_populates="workspace",
    )
    conversations = relationship(
        "Conversation",
        back_populates="workspace",
    )
    usage_metrics = relationship(
        "UsageMetric",
        back_populates="workspace",
    )
    network_memories = relationship(
        "NetworkMemory",
        back_populates="workspace",
    )
    topologies = relationship(
        "Topology",
        back_populates="workspace",
    )

    def __repr__(self) -> str:
        return (
            f"<Workspace(id={self.id}, name='{self.name}', "
            f"slug='{self.slug}', plan_tier='{self.plan_tier}')>"
        )


class WorkspaceMember(Base):
    """
    Many-to-many relationship between users and workspaces with role.
    """

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
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
    workspace_role = Column(
        String(20),
        nullable=False,
        default="member",
        comment="owner|admin|member|viewer",
    )
    invited_by = Column(SQLAlchemyUUID(as_uuid=True), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<WorkspaceMember(workspace_id={self.workspace_id}, "
            f"user_id={self.user_id}, role='{self.workspace_role}')>"
        )
