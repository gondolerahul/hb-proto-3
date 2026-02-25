"""
Campaign execution worker - ARQ background task for campaign execution.

Runs campaigns in the background using ARQ task queue.
"""
import logging
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.ai.campaign_executor import CampaignExecutor

logger = logging.getLogger(__name__)


async def execute_campaign_task(ctx: dict, campaign_id: str):
    """
    ARQ background task to execute a campaign.
    
    Args:
        ctx: ARQ context
        campaign_id: Campaign UUID as string
    """
    logger.info(f"Starting campaign execution task for {campaign_id}")
    
    try:
        # Get database session
        async for db in get_db():
            # Create executor
            executor = CampaignExecutor(db)
            
            # Start campaign
            await executor.start_campaign(UUID(campaign_id))
            
            break
            
    except Exception as e:
        logger.error(f"Error in campaign execution task: {e}", exc_info=True)
        raise


async def pause_campaign_task(ctx: dict, campaign_id: str):
    """
    ARQ background task to pause a campaign.
    
    Args:
        ctx: ARQ context
        campaign_id: Campaign UUID as string
    """
    logger.info(f"Pausing campaign {campaign_id}")
    
    try:
        async for db in get_db():
            executor = CampaignExecutor(db)
            await executor.pause_campaign(UUID(campaign_id))
            break
            
    except Exception as e:
        logger.error(f"Error pausing campaign: {e}", exc_info=True)
        raise


async def stop_campaign_task(ctx: dict, campaign_id: str):
    """
    ARQ background task to stop a campaign.
    
    Args:
        ctx: ARQ context
        campaign_id: Campaign UUID as string
    """
    logger.info(f"Stopping campaign {campaign_id}")
    
    try:
        async for db in get_db():
            executor = CampaignExecutor(db)
            await executor.stop_campaign(UUID(campaign_id))
            break
            
    except Exception as e:
        logger.error(f"Error stopping campaign: {e}", exc_info=True)
        raise
