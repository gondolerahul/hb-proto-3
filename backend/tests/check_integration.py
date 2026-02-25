import asyncio
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Import models to ensure they are registered
from src.auth.models import User, Company # Assuming User and Company are here
from src.config.models import IntegrationRegistry

from src.common.config import settings

# Create async engine
engine = create_async_engine(settings.DATABASE_URL, echo=True)
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def check():
    async with async_session_maker() as session:
        # Check all integrations for this company
        company_id = UUID('c8865856-8496-4054-80e3-3d9cdd79788e')
        result = await session.execute(
            select(IntegrationRegistry).where(IntegrationRegistry.company_id == company_id)
        )
        entries = result.scalars().all()
        print(f"Found {len(entries)} entries for company {company_id}")
        for entry in entries:
            print(f"ID: {entry.id}")
            print(f"  Provider: '{entry.provider_name}'")
            print(f"  Model: '{entry.model_name}'")
            print(f"  Status: '{entry.status}'")
            print(f"  SKU: '{entry.service_sku}'")
            print("-" * 20)

if __name__ == "__main__":
    asyncio.run(check())
