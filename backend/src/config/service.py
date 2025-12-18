import os
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from src.config.models import AIModel, SystemConfig
from src.config.schemas import AIModelCreate, AIModelUpdate, SystemConfigCreate, SystemConfigUpdate

# Get encryption key from env or generate a temporary one (for dev only)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # In production, this should raise an error. For now, we warn.
    print("WARNING: ENCRYPTION_KEY not found. Using a temporary key.")
    ENCRYPTION_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

class ConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # AI Model Methods
    async def create_ai_model(self, model_in: AIModelCreate) -> AIModel:
        model = AIModel(**model_in.model_dump())
        self.db.add(model)
        await self.db.commit()
        await self.db.refresh(model)
        return model

    async def get_ai_models(self) -> list[AIModel]:
        result = await self.db.execute(select(AIModel))
        return result.scalars().all()

    async def delete_ai_model(self, model_id: UUID) -> bool:
        result = await self.db.execute(select(AIModel).where(AIModel.id == model_id))
        model = result.scalar_one_or_none()
        if not model:
            return False
        
        await self.db.delete(model)
        await self.db.commit()
        return True

    # System Config Methods
    async def create_system_config(self, config_in: SystemConfigCreate) -> SystemConfig:
        value = config_in.value
        if config_in.is_encrypted:
            value = cipher_suite.encrypt(value.encode()).decode()
        
        config = SystemConfig(
            key=config_in.key,
            value=value,
            is_encrypted=config_in.is_encrypted,
            description=config_in.description
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def get_system_config(self, key: str) -> SystemConfig:
        result = await self.db.execute(select(SystemConfig).where(SystemConfig.key == key))
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=404, detail="Config not found")
        return config

    async def get_decrypted_value(self, key: str) -> str:
        config = await self.get_system_config(key)
        if config.is_encrypted:
            return cipher_suite.decrypt(config.value.encode()).decode()
        return config.value
