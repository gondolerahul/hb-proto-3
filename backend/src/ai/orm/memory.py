"""orm/memory.py — Legacy EpisodicMemory ORM (v1 episodic backing table)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.common.database import Base

__all__ = ["EpisodicMemory"]


class EpisodicMemory(Base):
    """S1: Short-term interaction record.

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

    metadata_info = Column(JSON, nullable=True)  # avoiding 'metadata' reserved word
    channel = Column(String(50), nullable=True)
    tree_id = Column(UUID(as_uuid=True), ForeignKey("cortex_trees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
