import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Text, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.common.database import Base
import pgvector.sqlalchemy


from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Text, JSON, Numeric, Enum, Integer
from src.auth.models import Company, User
from src.config.models import IntegrationRegistry

# Import enums from schemas to avoid duplication
from src.ai.schemas import EntityType, RunStatus

class EpisodicMemory(Base):
    """
    S1: Short-term interaction record.
    One row per completed ExecutionRun (for top-level runs only).
    """
    __tablename__ = "episodic_memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)

    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)

    status = Column(String(50), nullable=True)
    total_cost_usd = Column(String(20), nullable=True)
    total_tokens = Column(Integer, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)

    metadata_info = Column(JSON, nullable=True) # avoiding 'metadata' reserved word
    channel = Column(String(50), nullable=True)
    tree_id = Column(UUID(as_uuid=True), ForeignKey("cortex_trees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class HierarchicalEntity(Base):
    __tablename__ = "hierarchical_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    version = Column(String, nullable=False, default="1.0.0")
    type = Column(String, nullable=False) # ACTION, SKILL, AGENT, PROCESS
    status = Column(String, nullable=False, default="ACTIVE") # DRAFT, ACTIVE, DEPRECATED, ARCHIVED
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    goal = Column(Text, nullable=True)  # Entity's objective, used in prompt generation
    tags = Column(JSON, nullable=True)

    # Template fields
    is_template = Column(Boolean, default=False)  # True = blueprint, not executable
    template_source_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # New unified structure fields
    identity = Column(JSON, nullable=True)
    hierarchy = Column(JSON, nullable=True)
    logic_gate = Column(JSON, nullable=True)
    planning = Column(JSON, nullable=True)
    capabilities = Column(JSON, nullable=True)
    governance = Column(JSON, nullable=True)
    io_contract = Column(JSON, nullable=True)
    observability = Column(JSON, nullable=True)
    metadata_extensions = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company")
    parent = relationship("HierarchicalEntity", remote_side=[id], backref="children",
                          foreign_keys=[parent_id])
    template_source = relationship("HierarchicalEntity", remote_side=[id],
                                   foreign_keys=[template_source_id])
    creator = relationship("User", foreign_keys=[created_by])
    execution_runs = relationship("ExecutionRun", back_populates="entity")

class ExecutionRun(Base):
    __tablename__ = "execution_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    parent_run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String, default="PENDING")
    input_data = Column(JSON, nullable=True)
    dynamic_plan = Column(JSON, nullable=True)
    result_data = Column(JSON, nullable=True)
    context_state = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Metrics and Tracing
    total_cost_usd = Column(Numeric(10, 4), default=0)
    billed_amount = Column(Numeric(14, 6), nullable=True)  # TB formula result — the user-facing charge
    total_tokens = Column(Integer, default=0)
    execution_time_ms = Column(Integer, nullable=True)
    trace_id = Column(UUID(as_uuid=True), nullable=True)
    span_id = Column(String, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company")
    entity = relationship("HierarchicalEntity", back_populates="execution_runs")
    parent_run = relationship("ExecutionRun", remote_side=[id], backref="child_runs")
    llm_logs = relationship("LLMInteractionLog", back_populates="run")
    usage_logs = relationship("UsageLog", back_populates="run")
    human_approvals = relationship("HumanApproval", back_populates="run")
    tool_logs = relationship("ToolInteractionLog", back_populates="run")

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
    cost_usd = Column(Numeric(10, 6), default=0)
    reasoning_mode = Column(String, nullable=True)
    step_name = Column(String, nullable=True)  # Associates this log with a specific plan step
    log_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ExecutionRun", back_populates="llm_logs")

class ToolInteractionLog(Base):
    __tablename__ = "tool_interaction_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=False)
    tool_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    provider = Column(String, nullable=True)
    input_parameters = Column(JSON, nullable=True)
    output_result = Column(JSON, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    log_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ExecutionRun", back_populates="tool_logs")

class HumanApproval(Base):
    __tablename__ = "human_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=False)
    checkpoint_trigger = Column(String, nullable=False)
    status = Column(String, default="PENDING") # PENDING, APPROVED, REJECTED, TIMEOUT
    requested_by = Column(String, nullable=True)
    responded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    context_snapshot = Column(JSON, nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    notification_channels = Column(JSON, nullable=True)
    timeout_ms = Column(Integer, nullable=True)
    requested_at = Column(DateTime, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)

    run = relationship("ExecutionRun", back_populates="human_approvals")
    reviewer = relationship("User")

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

    company = relationship("Company")
    run = relationship("ExecutionRun", back_populates="usage_logs")
    sku = relationship("IntegrationRegistry")

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


class ToolRegistryEntry(Base):
    """
    Persistent registry of both built-in and custom tools.

    Built-in tools are seeded at startup. Custom tools are created/managed
    by Application Admins via the Tool Management API.
    """
    __tablename__ = "tool_registry_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)  # null = system-wide
    name = Column(String, nullable=False, unique=True)  # Tool identifier (matches Tool.name)
    display_name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)  # e.g., "browser", "social", "document", "utility"
    tool_type = Column(String, nullable=False, default="BUILT_IN")  # BUILT_IN | CUSTOM
    function_schema = Column(JSON, nullable=True)  # OpenAI-compatible function schema
    is_enabled = Column(Boolean, default=True)
    configuration = Column(JSON, nullable=True)  # Custom config (API keys ref, etc.)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company")
    creator = relationship("User", foreign_keys=[created_by])
