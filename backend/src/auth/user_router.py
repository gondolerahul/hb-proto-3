from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID
from src.common.database import get_db
from src.auth.models import User, Company
from src.auth.schemas import UserCreateAdmin, UserResponse
from src.auth.dependencies import get_current_user, RoleChecker
from src.auth.service import create_user_as_admin

router = APIRouter(prefix="/users", tags=["users"])

@router.get("", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # App Admin can see all users
    if current_user.role == "app_admin":
        result = await db.execute(select(User))
    # Partner Admin can see their users and their tenants' users
    elif current_user.role == "partner_admin":
        # Get all companies that are either the partner's company or have the partner's company as parent
        comp_result = await db.execute(
            select(Company.id).where(
                (Company.id == current_user.company_id) | (Company.parent_id == current_user.company_id)
            )
        )
        company_ids = comp_result.scalars().all()
        result = await db.execute(select(User).where(User.company_id.in_(company_ids)))
    # Tenant Admin can only see their own users
    elif current_user.role == "tenant_admin":
        result = await db.execute(select(User).where(User.company_id == current_user.company_id))
    else:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return result.scalars().all()

@router.post("", response_model=UserResponse)
async def create_user(
    user_in: UserCreateAdmin,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["app_admin", "partner_admin", "tenant_admin"]))
):
    return await create_user_as_admin(db, user_in, current_user)
