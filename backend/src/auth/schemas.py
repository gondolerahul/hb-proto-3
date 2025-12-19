from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserCreateAdmin(UserCreate):
    company_id: UUID
    role: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class OAuthRequest(BaseModel):
    code: str
    redirect_uri: str

class TokenData(BaseModel):
    email: Optional[str] = None

class CompanyBase(BaseModel):
    name: str
    type: str # APP, PARTNER, TENANT
    status: str = "active"

class CompanyCreate(CompanyBase):
    parent_id: Optional[UUID] = None

class CompanyResponse(CompanyBase):
    id: UUID
    logo_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    company_id: UUID
    role: str
    is_active: bool
    profile_picture_url: Optional[str] = None

    class Config:
        from_attributes = True
