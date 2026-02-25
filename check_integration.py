import asyncio
import logging
from uuid import UUID
from sqlalchemy import select
from src.database import async_session_maker
from src.config.models import IntegrationRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_integration():
    company_id = UUID('c8865856-8496-4054-80e3-3d9cdd79788e')
    async with async_session_maker() as session:
        result = await session.execute(
            select(IntegrationRegistry).where(
                IntegrationRegistry.company_id == company_id
            )
        )
        entries = result.scalars().all()
        for entry in entries:
            print(f"ID: {entry.id}, Provider: '{entry.provider_name}', Model: '{entry.model_name}', Status: '{entry.status}'")

if __name__ == "__main__":
    asyncio.run(check_integration())
