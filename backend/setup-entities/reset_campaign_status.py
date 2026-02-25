"""
Script to reset campaign status from 'running' to 'draft' so it can be restarted.
"""
import asyncio
from sqlalchemy import text
from src.common.database import AsyncSessionLocal

async def reset_campaign_status(campaign_name: str = "sales"):
    """Reset campaign status to draft."""
    async with AsyncSessionLocal() as db:
        # Find campaign by name
        result = await db.execute(
            text("SELECT id, name, status FROM campaigns WHERE name = :name"),
            {"name": campaign_name}
        )
        campaign = result.fetchone()
        
        if not campaign:
            print(f"Campaign '{campaign_name}' not found")
            return
        
        print(f"Found campaign: {campaign.id}")
        print(f"Current status: {campaign.status}")
        
        # Reset status to draft
        await db.execute(
            text("UPDATE campaigns SET status = 'draft' WHERE id = :id"),
            {"id": campaign.id}
        )
        await db.commit()
        
        print(f"Campaign status reset to 'draft'")
        print(f"You can now restart the campaign from the UI")

if __name__ == "__main__":
    asyncio.run(reset_campaign_status())
