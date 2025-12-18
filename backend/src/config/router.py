from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.database import get_db
from src.config.schemas import AIModelCreate, AIModelResponse, SystemConfigCreate, SystemConfigResponse
from src.config.service import ConfigService

router = APIRouter(tags=["System Configuration"])

@router.post("/config/models", response_model=AIModelResponse)
async def create_ai_model(
    model_in: AIModelCreate,
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    return await service.create_ai_model(model_in)

@router.get("/config/models", response_model=list[AIModelResponse])
async def list_ai_models(
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    return await service.get_ai_models()

@router.delete("/config/models/{model_id}", status_code=204)
async def delete_ai_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    success = await service.delete_ai_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="AI Model not found")
    return None

@router.post("/config/system", response_model=SystemConfigResponse)
async def create_system_config(
    config_in: SystemConfigCreate,
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    return await service.create_system_config(config_in)

@router.get("/config/system/{key}", response_model=SystemConfigResponse)
async def get_system_config(
    key: str,
    db: AsyncSession = Depends(get_db)
):
    service = ConfigService(db)
    return await service.get_system_config(key)
