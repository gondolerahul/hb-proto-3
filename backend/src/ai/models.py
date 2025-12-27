import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Text, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.common.database import Base
import pgvector.sqlalchemy


from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Text, JSON, Numeric, Enum, Integer
import enum

class EntityType(str, enum.Enum):
    ACTION = "ACTION"
    SKILL = "SKILL"
    AGENT = "AGENT"
    PROCESS = "PROCESS"

class RunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REPAIRING = "REPAIRING"

class HierarchicalEntity(Base):
    __tablename__ = "hierarchical_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    type = Column(String, nullable=False) # ACTION, SKILL, AGENT, PROCESS
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    static_plan = Column(JSON, nullable=True) # { "steps": [...], "rules": [...] }
    llm_config = Column(JSON, nullable=True) # { "provider": "openai", "model": "gpt-4", ... }
    toolkit = Column(JSON, nullable=True) # [ { "name": "web_search", ... } ]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("src.auth.models.Company")
    parent = relationship("HierarchicalEntity", remote_side=[id], backref="children")
    execution_runs = relationship("ExecutionRun", back_populates="entity")

class ExecutionRun(Base):
    __tablename__ = "execution_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    parent_run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    status = Column(String, default="PENDING")
    input_data = Column(JSON, nullable=True)
    dynamic_plan = Column(JSON, nullable=True)
    result_data = Column(JSON, nullable=True)
    context_state = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("src.auth.models.Company")
    entity = relationship("HierarchicalEntity", back_populates="execution_runs")
    parent_run = relationship("ExecutionRun", remote_side=[id], backref="child_runs")
    llm_logs = relationship("LLMInteractionLog", back_populates="run")
    usage_logs = relationship("UsageLog", back_populates="run")

class LLMInteractionLog(Base):
    __tablename__ = "llm_interaction_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=False)
    model_provider = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    input_prompt = Column(Text, nullable=False)
    output_response = Column(Text, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ExecutionRun", back_populates="llm_logs")

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)
    sku_id = Column(UUID(as_uuid=True), ForeignKey("integration_registry.id"), nullable=False)
    raw_quantity = Column(Numeric(18, 6), nullable=False)
    calculated_cost = Column(Numeric(18, 6), nullable=False)
    log_metadata = Column(JSON, nullable=True)

    company = relationship("src.auth.models.Company")
    run = relationship("ExecutionRun", back_populates="usage_logs")
    sku = relationship("src.config.models.IntegrationRegistry")

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

    company = relationship("src.auth.models.Company")
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
