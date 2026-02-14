"""
User model with encrypted API key support.
"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.rbac import UserRole


class User(Base):
    """
    User model for authentication and API key management.
    
    Each user has their own encrypted LLM API key (BYO-LLM model).
    """
    __tablename__ = "users"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    
    # BYO-LLM: User's own API key (encrypted with Fernet)
    encrypted_api_key = Column(Text, nullable=True)
    llm_provider = Column(
        String(50), 
        nullable=True,
        comment="openai|anthropic|azure|local"
    )
    
    # Plan tier for RBAC
    plan_tier = Column(
        String(20),
        default="free",
        nullable=False,
        comment="free|solo|team|enterprise"
    )

    # User authorization role (system-level RBAC)
    role = Column(
        String(20),
        default=UserRole.MEMBER.value,
        nullable=False,
        comment="owner|admin|member|viewer",
    )
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    last_login_at = Column(DateTime, nullable=True)
    
    # Relationships
    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    documents = relationship(
        "Document",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    embeddings = relationship(
        "Embedding",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    network_memories = relationship(
        "NetworkMemory",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self):
        return (
            f"<User(id={self.id}, email='{self.email}', "
            f"plan='{self.plan_tier}', role='{self.role}')>"
        )
