from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from src.common.database import get_db
from src.auth.dependencies import get_current_user, RoleChecker
from src.auth.models import User
from src.tenant import service
from src.tenant.schemas import PartnerCreate, PartnerResponse, TenantCreate, TenantResponse, TenantUpdate

router = APIRouter(tags=["tenant-partner"])

@router.post("/partners", response_model=PartnerResponse, dependencies=[Depends(RoleChecker(["app_admin"]))])
async def create_partner(partner: PartnerCreate, db: AsyncSession = Depends(get_db)):
    return await service.create_partner(db, partner)

@router.post("/partners/{partner_id}/tenants", response_model=TenantResponse, dependencies=[Depends(RoleChecker(["partner_admin", "app_admin"]))])
async def create_tenant(partner_id: str, tenant: TenantCreate, db: AsyncSession = Depends(get_db)):
    return await service.create_tenant_for_partner(db, partner_id, tenant)

@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    if current_user.role == "app_admin":
        return await service.get_tenants(db)
    elif current_user.role == "partner_admin":
        # Assuming we can find the partner_id from the user's tenant or a direct link
        # For now, let's assume the user's tenant is the 'Partner Workspace' and linked to the partner
        if not current_user.tenant.partner_id:
             raise HTTPException(status_code=400, detail="User is not associated with a partner")
        return await service.get_tenants(db, partner_id=current_user.tenant.partner_id)
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

@router.put("/tenants/{tenant_id}", response_model=TenantResponse, dependencies=[Depends(RoleChecker(["partner_admin", "app_admin"]))])
async def update_tenant(tenant_id: str, tenant_update: TenantUpdate, db: AsyncSession = Depends(get_db)):
    return await service.update_tenant(db, tenant_id, tenant_update)
