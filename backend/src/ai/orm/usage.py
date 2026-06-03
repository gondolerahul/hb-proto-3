"""orm/usage.py — UsageLog ORM (billing source-of-truth)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.common.database import Base

__all__ = ["UsageLog"]


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
    # Structured attribution tag for cost breakdown (see services/cost_attribution.py).
    attribution = Column(String(40), nullable=False, server_default="tool")

    company = relationship("Company")
    run = relationship("ExecutionRun", back_populates="usage_logs")
    sku = relationship("IntegrationRegistry")

    __table_args__ = (
        Index("ix_usage_logs_attribution", "attribution"),
    )
