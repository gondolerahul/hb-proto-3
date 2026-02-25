import asyncio
import sys
from uuid import UUID

from sqlalchemy import select, update
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

async def fix():
    async with async_session_maker() as session:
        # Check all integrations for this company
        company_id = UUID('c8865856-8496-4054-80e3-3d9cdd79788e')
        
        # update Tata -> tata_tele
        await session.execute(
            update(IntegrationRegistry)
            .where(
                IntegrationRegistry.company_id == company_id,
                IntegrationRegistry.provider_name == 'Tata'
            )
            .values(provider_name='tata_tele')
        )
        await session.commit()
        print("Updated Provider: 'Tata' -> 'tata_tele'")
        
        # update Twilio -> twilio 
        await session.execute(
            update(IntegrationRegistry)
            .where(
                IntegrationRegistry.company_id == company_id,
                IntegrationRegistry.provider_name == 'Twilio'
            )
            .values(provider_name='twilio')
        )
        await session.commit()
        print("Updated Provider: 'Twilio' -> 'twilio'")


if __name__ == "__main__":
    asyncio.run(fix())
