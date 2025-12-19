from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from src.config.models import IntegrationRegistry
from src.config.schemas import IntegrationRegistryCreate, IntegrationRegistryUpdate
from src.common.security import encrypt_api_key, decrypt_api_key

class ConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_registry_entry(self, entry_in: IntegrationRegistryCreate) -> IntegrationRegistry:
        encrypted_key = encrypt_api_key(entry_in.api_key)
        
        entry_data = entry_in.model_dump(exclude={"api_key"})
        entry = IntegrationRegistry(
            **entry_data,
            encrypted_api_key=encrypted_key
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_registry_entries(self, company_id: Optional[UUID] = None) -> list[IntegrationRegistry]:
        query = select(IntegrationRegistry)
        if company_id:
            query = query.where(IntegrationRegistry.company_id == company_id)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_registry_entry(self, entry_id: UUID) -> IntegrationRegistry:
        result = await self.db.execute(
            select(IntegrationRegistry).where(IntegrationRegistry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status_code=404, detail="Registry entry not found")
        return entry

    async def update_registry_entry(self, entry_id: UUID, entry_in: IntegrationRegistryUpdate) -> IntegrationRegistry:
        entry = await self.get_registry_entry(entry_id)
        
        update_data = entry_in.model_dump(exclude_unset=True)
        if "api_key" in update_data:
            update_data["encrypted_api_key"] = encrypt_api_key(update_data.pop("api_key"))
        
        for field, value in update_data.items():
            setattr(entry, field, value)
        
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete_registry_entry(self, entry_id: UUID) -> bool:
        entry = await self.get_registry_entry(entry_id)
        await self.db.delete(entry)
        await self.db.commit()
        return True

    async def get_decrypted_api_key(self, entry_id: UUID) -> str:
        entry = await self.get_registry_entry(entry_id)
        return decrypt_api_key(entry.encrypted_api_key)

    async def get_api_key_by_sku(self, company_id: UUID, service_sku: str) -> str:
        result = await self.db.execute(
            select(IntegrationRegistry).where(
                IntegrationRegistry.company_id == company_id,
                IntegrationRegistry.service_sku == service_sku,
                IntegrationRegistry.status == "active"
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return None
        return decrypt_api_key(entry.encrypted_api_key)
