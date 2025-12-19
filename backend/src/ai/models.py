import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Text, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.common.database import Base
import pgvector.sqlalchemy


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # System Prompt
    llm_config = Column(JSON, nullable=False)  # { "provider": "openai", "model": "gpt-4", ... }
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("src.auth.models.Company")
    executions = relationship("Execution", back_populates="agent")

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False)
    dag_structure = Column(JSON, nullable=False)  # { "nodes": [...], "edges": [...] }
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("src.auth.models.Company")
    executions = relationship("Execution", back_populates="workflow")

class Execution(Base):
    __tablename__ = "executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=True)
    status = Column(String, default="pending")  # pending, running, completed, failed
    input_data = Column(JSON, nullable=True)
    result_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("src.auth.models.Company")
    agent = relationship("Agent", back_populates="executions")
    workflow = relationship("Workflow", back_populates="executions")
    usage_logs = relationship("UsageLog", back_populates="execution")

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True)
    sku_id = Column(UUID(as_uuid=True), ForeignKey("integration_registry.id"), nullable=False)
    raw_quantity = Column(Numeric(18, 6), nullable=False)
    calculated_cost = Column(Numeric(18, 6), nullable=False)
    log_metadata = Column(JSON, nullable=True)

    company = relationship("src.auth.models.Company")
    execution = relationship("Execution", back_populates="usage_logs")
    sku = relationship("src.config.models.IntegrationRegistry")

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)  # Optional: associate with agent
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, docx, txt
    file_size = Column(String, nullable=True)
    upload_status = Column(String, default="processing")  # processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("src.auth.models.Company")
    agent = relationship("Agent")
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
