"""orm/entity.py — HierarchicalEntity ORM (the agent kernel's primary table)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.common.database import Base

__all__ = ["HierarchicalEntity"]


class HierarchicalEntity(Base):
    __tablename__ = "hierarchical_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    version = Column(String, nullable=False, default="1.0.0")
    type = Column(String, nullable=False)  # ACTION, SKILL, AGENT, PROCESS
    status = Column(String, nullable=False, default="ACTIVE")  # DRAFT, ACTIVE, DEPRECATED, ARCHIVED
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    goal = Column(Text, nullable=True)  # Entity's objective, used in prompt generation
    tags = Column(JSON, nullable=True)

    # Template fields
    is_template = Column(Boolean, default=False)  # True = blueprint, not executable
    template_source_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Unified structure fields
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
    deleted_at = Column(DateTime, nullable=True)  # Soft-delete timestamp; NULL = active

    company = relationship("Company")
    parent = relationship(
        "HierarchicalEntity",
        remote_side=[id],
        backref="children",
        foreign_keys=[parent_id],
    )
    template_source = relationship(
        "HierarchicalEntity",
        remote_side=[id],
        foreign_keys=[template_source_id],
    )
    creator = relationship("User", foreign_keys=[created_by])
    execution_runs = relationship("ExecutionRun", back_populates="entity")
