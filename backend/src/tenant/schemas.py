from pydantic import BaseModel, EmailStr
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class PartnerCreate(BaseModel):
    name: str
    admin_email: EmailStr
    admin_name: str
    admin_password: str

class PartnerResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime

    class Config:
        from_attributes = True

class TenantCreate(BaseModel):
    name: str
    admin_email: EmailStr
    admin_name: str
    admin_password: str

class TenantResponse(BaseModel):
    id: UUID
    name: str
    status: str
    partner_id: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True

class TenantUpdate(BaseModel):
    status: Optional[str] = None
    name: Optional[str] = None

class UserInvite(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "user"
