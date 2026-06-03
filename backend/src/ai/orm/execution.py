"""orm/execution.py — Execution-run ORM and its child interaction logs."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.common.database import Base

__all__ = [
    "ExecutionRun",
    "LLMInteractionLog",
    "ToolInteractionLog",
    "HumanApproval",
]


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
    idempotency_key = Column(String(255), nullable=True, index=True)  # Step-level dedup

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
    idempotency_key = Column(String(255), nullable=True, index=True)  # Step-level dedup
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ExecutionRun", back_populates="tool_logs")


class HumanApproval(Base):
    __tablename__ = "human_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=False)
    checkpoint_trigger = Column(String, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, APPROVED, REJECTED, TIMEOUT
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
