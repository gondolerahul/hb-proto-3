"""orm/document.py — Document + DocumentChunk (pgvector-backed) ORM."""
from __future__ import annotations

import uuid
from datetime import datetime

import pgvector.sqlalchemy
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.common.database import Base

__all__ = ["Document", "DocumentChunk"]


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, docx, txt
    file_size = Column(String, nullable=True)
    upload_status = Column(String, default="processing")  # processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company")
    entity = relationship("HierarchicalEntity")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(String, nullable=False)  # Position in document
    content = Column(Text, nullable=False)
    embedding = Column(pgvector.sqlalchemy.Vector(768), nullable=True)  # 768 for Gemini embeddings
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")
