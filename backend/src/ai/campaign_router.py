"""
Campaign API Router for frontend integration.

Provides endpoints for:
- Creating campaigns
- Uploading contact lists
- Managing campaign execution
- Retrieving status and metrics
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.database import get_db
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.ai.campaign_service import CampaignService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


# Pydantic models for request/response
class CampaignCreate(BaseModel):
    """Campaign creation request."""
    agent_id: UUID
    name: str
    description: Optional[str] = None
    contact_list: List[Dict[str, Any]]
    provider: str = "twilio"
    call_script_template: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    max_concurrent_calls: int = 5
    max_calls_per_hour: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class CampaignResponse(BaseModel):
    """Campaign response model."""
    id: str
    name: str
    description: Optional[str]
    status: str
    total_contacts: int
    calls_initiated: int
    calls_completed: int
    calls_failed: int
    created_at: str


@router.post("")
async def create_campaign(
    campaign_data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new voice calling campaign.
    
    Args:
        campaign_data: Campaign configuration and contact list
        
    Returns:
        Created campaign
    """
    service = CampaignService(db)
    
    try:
        campaign = await service.create_campaign(
            company_id=UUID(str(current_user.company_id)),
            created_by=UUID(str(current_user.id)),
            agent_id=campaign_data.agent_id,
            name=campaign_data.name,
            contact_list=campaign_data.contact_list,
            description=campaign_data.description,
            provider=campaign_data.provider,
            call_script_template=campaign_data.call_script_template,
            scheduled_start=campaign_data.scheduled_start,
            scheduled_end=campaign_data.scheduled_end,
            max_concurrent_calls=campaign_data.max_concurrent_calls,
            max_calls_per_hour=campaign_data.max_calls_per_hour,
            metadata=campaign_data.metadata
        )
        
        return {
            "id": str(campaign.id),
            "name": campaign.name,
            "description": campaign.description,
            "status": campaign.status,
            "total_contacts": campaign.total_contacts,
            "calls_initiated": campaign.calls_initiated,
            "calls_completed": campaign.calls_completed,
            "calls_failed": campaign.calls_failed,
            "created_at": campaign.created_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Parse and validate uploaded CSV file.
    
    Args:
        file: CSV file with contacts
        
    Returns:
        Parsed contacts with validation results
    """
    service = CampaignService(db)
    
    try:
        # Parse CSV
        contacts = await service.parse_csv(file)
        
        # Validate contacts
        validation = await service.validate_contacts(contacts)
        
        return {
            "total": len(contacts),
            "valid": validation["valid"],
            "invalid": validation["invalid"],
            "errors": validation["errors"],
            "contacts": validation["contacts"][:10],  # Return first 10 for preview
            "all_contacts": validation["contacts"]  # Full list for form submission
        }
        
    except Exception as e:
        logger.error(f"Error parsing CSV: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_campaigns(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List campaigns with real-time call status counts.
    """
    from src.ai.campaign_models import CampaignCall
    from sqlalchemy import func

    service = CampaignService(db)
    
    try:
        campaigns = await service.list_campaigns(
            company_id=UUID(str(current_user.company_id)),
            status=status,
            limit=limit,
            offset=offset
        )

        # Fetch real-time call counts for all campaigns in one query
        campaign_ids = [c.id for c in campaigns]
        if campaign_ids:
            counts_result = await db.execute(
                select(
                    CampaignCall.campaign_id,
                    CampaignCall.status,
                    func.count(CampaignCall.id).label("count"),
                )
                .where(CampaignCall.campaign_id.in_(campaign_ids))
                .group_by(CampaignCall.campaign_id, CampaignCall.status)
            )
            # Build a nested dict: {campaign_id: {status: count}}
            counts_map: dict = {}
            for row in counts_result:
                counts_map.setdefault(row.campaign_id, {})[row.status] = row.count
        else:
            counts_map = {}

        result = []
        for c in campaigns:
            sc = counts_map.get(c.id, {})
            completed = sc.get("completed", 0)
            failed = sc.get("failed", 0)
            calling = sc.get("calling", 0)
            pending = sc.get("pending", 0)

            # Derive effective status
            effective_status = c.status
            if c.status == "completed" and pending > 0:
                effective_status = "running"

            result.append({
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "status": effective_status,
                "total_contacts": c.total_contacts,
                "calls_initiated": completed + failed + calling,
                "calls_completed": completed,
                "calls_failed": failed,
                "calls_calling": calling,
                "calls_pending": pending,
                "provider": c.provider,
                "created_at": c.created_at.isoformat()
            })

        return {
            "total": len(result),
            "campaigns": result,
        }
        
    except Exception as e:
        logger.error(f"Error listing campaigns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get campaign details with real-time call status counts and individual call records.
    """
    from src.ai.campaign_models import CampaignCall
    from sqlalchemy import func

    service = CampaignService(db)
    
    try:
        campaign = await service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Real-time call status counts from CampaignCall table
        status_result = await db.execute(
            select(
                CampaignCall.status,
                func.count(CampaignCall.id).label("count"),
            )
            .where(CampaignCall.campaign_id == campaign_id)
            .group_by(CampaignCall.status)
        )
        status_counts = {row.status: row.count for row in status_result}

        # Fetch individual call records
        calls_result = await db.execute(
            select(CampaignCall)
            .where(CampaignCall.campaign_id == campaign_id)
            .order_by(CampaignCall.created_at.asc())
        )
        calls = calls_result.scalars().all()

        # Derive effective campaign status from call states
        total = campaign.total_contacts
        completed = status_counts.get("completed", 0)
        failed = status_counts.get("failed", 0)
        calling = status_counts.get("calling", 0)
        pending = status_counts.get("pending", 0)

        # If campaign is marked "completed" but has pending calls, it was prematurely closed
        effective_status = campaign.status
        if campaign.status == "completed" and pending > 0:
            effective_status = "running"

        return {
            "id": str(campaign.id),
            "name": campaign.name,
            "description": campaign.description,
            "status": effective_status,
            "total_contacts": total,
            "calls_initiated": completed + failed + calling,
            "calls_completed": completed,
            "calls_failed": failed,
            "calls_calling": calling,
            "calls_pending": pending,
            "max_concurrent_calls": campaign.max_concurrent_calls,
            "max_calls_per_hour": campaign.max_calls_per_hour,
            "scheduled_start": campaign.scheduled_start.isoformat() if campaign.scheduled_start else None,
            "scheduled_end": campaign.scheduled_end.isoformat() if campaign.scheduled_end else None,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
            "provider": campaign.provider,
            "agent_id": str(campaign.agent_id) if campaign.agent_id else None,
            "created_at": campaign.created_at.isoformat(),
            "calls": [
                {
                    "id": str(c.id),
                    "contact_name": c.contact_data.get("name", "Unknown") if c.contact_data else "Unknown",
                    "contact_phone": c.contact_data.get("phone", "") if c.contact_data else "",
                    "contact_company": c.contact_data.get("company", "") if c.contact_data else "",
                    "status": c.status,
                    "outcome": c.outcome,
                    "outcome_notes": c.outcome_notes,
                    "called_at": c.called_at.isoformat() if c.called_at else None,
                    "completed_at": c.completed_at.isoformat() if c.completed_at else None,
                    "duration_seconds": c.duration_seconds,
                    "voice_session_id": str(c.voice_session_id) if c.voice_session_id else None,
                    "call_sid": c.call_sid,
                }
                for c in calls
            ],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{campaign_id}/status")
async def get_campaign_status(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get real-time campaign status and metrics.
    
    Args:
        campaign_id: Campaign UUID
        
    Returns:
        Real-time metrics
    """
    service = CampaignService(db)
    
    try:
        status = await service.get_campaign_status(campaign_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{campaign_id}/active-calls")
async def get_active_calls(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get currently active calls for a campaign.
    
    Args:
        campaign_id: Campaign UUID
        
    Returns:
        List of active calls
    """
    service = CampaignService(db)
    
    try:
        calls = await service.get_active_calls(campaign_id)
        
        return {
            "campaign_id": str(campaign_id),
            "active_calls": calls
        }
        
    except Exception as e:
        logger.error(f"Error getting active calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{campaign_id}/status")
async def update_campaign_status(
    campaign_id: UUID,
    status: str = Query(..., description="New campaign status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update campaign status (start, pause, resume, stop).
    
    Args:
        campaign_id: Campaign UUID
        status: New status ('running', 'paused', 'completed')
        
    Returns:
        Updated campaign
    """
    service = CampaignService(db)
    
    try:
        await service.update_campaign_status(campaign_id, status)
        
        # Enqueue background task if starting campaign
        if status == "running":
            from arq import create_pool
            from arq.connections import RedisSettings
            from src.common.config import settings
            from urllib.parse import urlparse
            
            parsed = urlparse(settings.REDIS_URL or "redis://localhost:6379")
            redis_settings = RedisSettings(host=parsed.hostname or "localhost", port=parsed.port or 6379)
            
            redis = await create_pool(redis_settings)
            await redis.enqueue_job(
                'execute_campaign_task',
                str(campaign_id)
            )
            await redis.close()
            
            logger.info(f"Enqueued campaign execution task for {campaign_id}")
        
        return {
            "campaign_id": str(campaign_id),
            "status": status,
            "message": f"Campaign status updated to {status}"
        }
        
    except Exception as e:
        logger.error(f"Error updating campaign status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
