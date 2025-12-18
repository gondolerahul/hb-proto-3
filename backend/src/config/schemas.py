from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID

class AIModelBase(BaseModel):
    model_key: str
    model_name: str
    provider: str
    model_type: str
    is_active: bool = True

class AIModelCreate(AIModelBase):
    pass

class AIModelUpdate(BaseModel):
    model_key: Optional[str] = None
    model_name: Optional[str] = None
    provider: Optional[str] = None
    model_type: Optional[str] = None
    is_active: Optional[bool] = None

class AIModelResponse(AIModelBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SystemConfigBase(BaseModel):
    key: str
    value: str
    is_encrypted: bool = True
    description: Optional[str] = None

class SystemConfigCreate(SystemConfigBase):
    pass

class SystemConfigUpdate(BaseModel):
    value: Optional[str] = None
    is_encrypted: Optional[bool] = None
    description: Optional[str] = None

class SystemConfigResponse(BaseModel):
    id: UUID
    key: str
    # Value is intentionally omitted for security, or returned masked
    is_encrypted: bool
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
