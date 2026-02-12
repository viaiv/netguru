"""
Document and embedding models for RAG storage.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class Document(Base):
    """
    User-uploaded file metadata for processing and retrieval.
    """

    __tablename__ = "documents"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False, comment="pcap|pcapng|txt|conf|cfg|log|pdf")
    file_size_bytes = Column(BigInteger, nullable=False)
    storage_path = Column(Text, nullable=False)
    mime_type = Column(String(100), nullable=True)
    status = Column(
        String(20),
        nullable=False,
        default="uploaded",
        comment="uploaded|processing|completed|failed",
    )
    document_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="documents")
    embeddings = relationship(
        "Embedding",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Document(id={self.id}, user_id={self.user_id}, "
            f"filename='{self.filename}', status='{self.status}')>"
        )


class Embedding(Base):
    """
    Text chunks and embedding vectors used by RAG retrieval.
    """

    __tablename__ = "embeddings"

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    user_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_id = Column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Vector(384), nullable=True)
    embedding_model = Column(String(120), nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    embedding_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="embeddings")
    document = relationship("Document", back_populates="embeddings")

    def __repr__(self) -> str:
        return (
            f"<Embedding(id={self.id}, document_id={self.document_id}, "
            f"chunk_index={self.chunk_index})>"
        )
