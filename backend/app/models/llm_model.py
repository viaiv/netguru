"""
LlmModel — catalog of available LLM models per provider.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID

from app.core.database import Base


class LlmModel(Base):
    """
    Catalog entry for a specific LLM model from a provider.
    """

    __tablename__ = "llm_models"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    provider = Column(String(50), nullable=False, comment="openai, anthropic, google, etc")
    model_id = Column(String(150), nullable=False, comment="gpt-4o, claude-opus-4-20250514, etc")
    display_name = Column(String(200), nullable=False, comment="GPT-4o, Claude Opus 4, etc")
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_llm_models_provider_model"),
    )

    def __repr__(self) -> str:
        return f"<LlmModel(id={self.id}, provider='{self.provider}', model_id='{self.model_id}')>"
