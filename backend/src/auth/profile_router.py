from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import os
import shutil
from src.common.database import get_db
from src.auth.dependencies import get_current_user
from src.auth.models import User, Company
from src.auth.schemas import UserResponse, CompanyResponse
from src.common.config import settings

router = APIRouter(prefix="/profile", tags=["profile"])

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@router.post("/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload user profile picture"""
    file_ext = file.filename.split(".")[-1]
    file_path = f"{UPLOAD_DIR}/avatar_{current_user.id}.{file_ext}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Update user in DB
    current_user.profile_picture_url = f"/{file_path}"
    await db.commit()
    await db.refresh(current_user)
    
    return current_user

@router.post("/company-logo", response_model=CompanyResponse)
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload company logo (Admin only)"""
    if current_user.role not in ["app_admin", "partner_admin", "tenant_admin"]:
        raise HTTPException(status_code=403, detail="Only admins can upload company logos")
    
    file_ext = file.filename.split(".")[-1]
    file_path = f"{UPLOAD_DIR}/logo_{current_user.company_id}.{file_ext}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Update company in DB
    from sqlalchemy import select
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    company.logo_url = f"/{file_path}"
    await db.commit()
    await db.refresh(company)
    
    return company
