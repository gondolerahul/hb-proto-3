"""schemas/tools.py — Tool registry management DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel

__all__ = [
    "ToolRegistryEntryCreate",
    "ToolRegistryEntryUpdate",
    "ToolRegistryEntryResponse",
]


class ToolRegistryEntryCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    function_schema: Optional[Dict[str, Any]] = None
    is_enabled: bool = True
    configuration: Optional[Dict[str, Any]] = None


class ToolRegistryEntryUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    function_schema: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    configuration: Optional[Dict[str, Any]] = None


class ToolRegistryEntryResponse(BaseModel):
    id: UUID
    company_id: Optional[UUID] = None
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tool_type: str = "BUILT_IN"
    function_schema: Optional[Dict[str, Any]] = None
    is_enabled: bool = True
    configuration: Optional[Dict[str, Any]] = None
    created_by: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
