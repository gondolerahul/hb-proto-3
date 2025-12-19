from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from decimal import Decimal

class IntegrationRegistryBase(BaseModel):
    provider_name: str
    model_name: Optional[str] = None
    service_sku: str
    component_type: str
    internal_cost: Decimal
    cost_unit: str
    status: str = "active"

class IntegrationRegistryCreate(IntegrationRegistryBase):
    company_id: UUID
    api_key: str = Field(..., alias="api_key")

class IntegrationRegistryUpdate(BaseModel):
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    service_sku: Optional[str] = None
    component_type: Optional[str] = None
    internal_cost: Optional[Decimal] = None
    cost_unit: Optional[str] = None
    status: Optional[str] = None
    api_key: Optional[str] = None

class IntegrationRegistryResponse(IntegrationRegistryBase):
    id: UUID
    company_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
