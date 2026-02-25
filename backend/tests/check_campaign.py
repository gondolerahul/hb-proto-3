import asyncio
from uuid import UUID
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.ai.campaign_models import Campaign
from src.auth.models import Company, User
from src.ai.models import HierarchicalEntity
from src.streaming.models import VoiceSession

async def check_campaign():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == UUID('28275d98-8146-45b1-b9e2-9204d2140d84')))
        campaign = result.scalar_one_or_none()
        if campaign:
            print(f"Campaign {campaign.id}: Provider={campaign.provider}, Status={campaign.status}")
        else:
            print("Campaign not found")

if __name__ == "__main__":
    asyncio.run(check_campaign())
