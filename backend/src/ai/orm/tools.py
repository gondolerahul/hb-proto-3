"""orm/tools.py — Tool registry ORM."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.common.database import Base

__all__ = ["ToolRegistryEntry"]


class ToolRegistryEntry(Base):
    """Persistent registry of both built-in and custom tools.

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
