from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.database import get_db
from src.config.schemas import (
    IntegrationRegistryCreate, 
    IntegrationRegistryUpdate, 
    IntegrationRegistryResponse
)
from src.config.service import ConfigService
from src.auth.dependencies import get_current_user, RoleChecker
from src.auth.models import User

router = APIRouter(tags=["Integrations"])

@router.post("/integrations", response_model=IntegrationRegistryResponse)
async def create_integration(
    entry_in: IntegrationRegistryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Only admins can create integrations
    if current_user.role not in ["app_admin", "partner_admin", "tenant_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Ensure they are creating for their own company or are app_admin
    if current_user.role != "app_admin" and str(entry_in.company_id) != str(current_user.company_id):
        raise HTTPException(status_code=403, detail="Cannot create integration for another company")
        
    service = ConfigService(db)
    return await service.create_registry_entry(entry_in)

@router.get("/integrations", response_model=list[IntegrationRegistryResponse])
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    # App admins see everything, others see only leur own company
    company_id = None if current_user.role == "app_admin" else current_user.company_id
    return await service.get_registry_entries(company_id=company_id)

@router.get("/integrations/{entry_id}", response_model=IntegrationRegistryResponse)
async def get_integration(
    entry_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    entry = await service.get_registry_entry(entry_id)
    
    # Check access
    if current_user.role != "app_admin" and str(entry.company_id) != str(current_user.company_id):
        raise HTTPException(status_code=403, detail="Access denied")
        
    return entry

@router.patch("/integrations/{entry_id}", response_model=IntegrationRegistryResponse)
async def update_integration(
    entry_id: UUID,
    entry_in: IntegrationRegistryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    # Check access before update
    entry = await service.get_registry_entry(entry_id)
    if current_user.role != "app_admin" and str(entry.company_id) != str(current_user.company_id):
        raise HTTPException(status_code=403, detail="Access denied")
        
    return await service.update_registry_entry(entry_id, entry_in)

@router.delete("/integrations/{entry_id}", status_code=204)
async def delete_integration(
    entry_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    # Check access before delete
    entry = await service.get_registry_entry(entry_id)
    if current_user.role != "app_admin" and str(entry.company_id) != str(current_user.company_id):
        raise HTTPException(status_code=403, detail="Access denied")
        
    await service.delete_registry_entry(entry_id)
    return None
