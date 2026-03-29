"""
API Router for managing customer phone number assignments.

Provides endpoints for:
- Creating phone number assignments
- Listing phone numbers
- Updating assignments
- Deleting assignments
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Optional
from datetime import datetime

from src.database import get_db
from src.auth.dependencies import get_current_user
from src.voice.models import CustomerPhoneNumber
from src.ai.models import HierarchicalEntity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/phone-numbers", tags=["Phone Numbers"])


# Pydantic models
class PhoneNumberCreate(BaseModel):
    """Phone number assignment creation request."""
    customer_id: UUID
    customer_name: str
    phone_number: str
    provider: str  # 'twilio' | 'tata_tele'
    agent_id: UUID
    customer_metadata: Optional[dict] = None


class PhoneNumberUpdate(BaseModel):
    """Phone number assignment update request."""
    customer_name: Optional[str] = None
    agent_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    customer_metadata: Optional[dict] = None


class PhoneNumberResponse(BaseModel):
    """Phone number assignment response."""
    id: str
    customer_id: str
    customer_name: str
    phone_number: str
    provider: str
    agent_id: str
    agent_name: Optional[str] = None
    is_active: bool
    assigned_at: str
    customer_metadata: Optional[dict] = None


@router.post("")
async def create_phone_number(
    data: PhoneNumberCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Create a new phone number assignment.
    
    Args:
        data: Phone number assignment data
        
    Returns:
        Created phone number assignment
    """
    try:
        # Check if phone number already exists
        result = await db.execute(
            select(CustomerPhoneNumber).where(
                CustomerPhoneNumber.phone_number == data.phone_number
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Phone number {data.phone_number} is already assigned"
            )
        
        # Verify agent exists
        agent_result = await db.execute(
            select(HierarchicalEntity).where(
                and_(
                    HierarchicalEntity.id == data.agent_id,
                    HierarchicalEntity.company_id == current_user.company_id
                )
            )
        )
        agent = agent_result.scalar_one_or_none()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Create phone number assignment
        phone_number = CustomerPhoneNumber(
            company_id=current_user.company_id,
            customer_id=data.customer_id,
            customer_name=data.customer_name,
            phone_number=data.phone_number,
            provider=data.provider,
            agent_id=data.agent_id,
            customer_metadata=data.customer_metadata or {},
            is_active=True
        )
        
        db.add(phone_number)
        await db.commit()
        await db.refresh(phone_number)
        
        return {
            "id": str(phone_number.id),
            "customer_id": str(phone_number.customer_id),
            "customer_name": phone_number.customer_name,
            "phone_number": phone_number.phone_number,
            "provider": phone_number.provider,
            "agent_id": str(phone_number.agent_id),
            "agent_name": agent.name,
            "is_active": phone_number.is_active,
            "assigned_at": phone_number.assigned_at.isoformat(),
            "customer_metadata": phone_number.customer_metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating phone number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_phone_numbers(
    is_active: Optional[bool] = None,
    provider: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    List phone number assignments for current company.
    
    Args:
        is_active: Filter by active status
        provider: Filter by provider
        limit: Max results
        offset: Pagination offset
        
    Returns:
        List of phone number assignments
    """
    try:
        # Build query
        query = select(CustomerPhoneNumber).where(
            CustomerPhoneNumber.company_id == current_user.company_id
        )
        
        if is_active is not None:
            query = query.where(CustomerPhoneNumber.is_active == is_active)
        
        if provider:
            query = query.where(CustomerPhoneNumber.provider == provider)
        
        query = query.order_by(CustomerPhoneNumber.assigned_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        phone_numbers = result.scalars().all()
        
        # Get agent names
        agent_ids = [pn.agent_id for pn in phone_numbers]
        agents_result = await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id.in_(agent_ids)
            )
        )
        agents = {agent.id: agent.name for agent in agents_result.scalars().all()}
        
        return {
            "total": len(phone_numbers),
            "phone_numbers": [
                {
                    "id": str(pn.id),
                    "customer_id": str(pn.customer_id),
                    "customer_name": pn.customer_name,
                    "phone_number": pn.phone_number,
                    "provider": pn.provider,
                    "agent_id": str(pn.agent_id),
                    "agent_name": agents.get(pn.agent_id, "Unknown"),
                    "is_active": pn.is_active,
                    "assigned_at": pn.assigned_at.isoformat(),
                    "customer_metadata": pn.customer_metadata
                }
                for pn in phone_numbers
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing phone numbers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{phone_number_id}")
async def get_phone_number(
    phone_number_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get phone number assignment details."""
    try:
        result = await db.execute(
            select(CustomerPhoneNumber).where(
                and_(
                    CustomerPhoneNumber.id == phone_number_id,
                    CustomerPhoneNumber.company_id == current_user.company_id
                )
            )
        )
        phone_number = result.scalar_one_or_none()
        
        if not phone_number:
            raise HTTPException(status_code=404, detail="Phone number not found")
        
        # Get agent name
        agent_result = await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == phone_number.agent_id
            )
        )
        agent = agent_result.scalar_one_or_none()
        
        return {
            "id": str(phone_number.id),
            "customer_id": str(phone_number.customer_id),
            "customer_name": phone_number.customer_name,
            "phone_number": phone_number.phone_number,
            "provider": phone_number.provider,
            "agent_id": str(phone_number.agent_id),
            "agent_name": agent.name if agent else "Unknown",
            "is_active": phone_number.is_active,
            "assigned_at": phone_number.assigned_at.isoformat(),
            "customer_metadata": phone_number.customer_metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting phone number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{phone_number_id}")
async def update_phone_number(
    phone_number_id: UUID,
    data: PhoneNumberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update phone number assignment."""
    try:
        result = await db.execute(
            select(CustomerPhoneNumber).where(
                and_(
                    CustomerPhoneNumber.id == phone_number_id,
                    CustomerPhoneNumber.company_id == current_user.company_id
                )
            )
        )
        phone_number = result.scalar_one_or_none()
        
        if not phone_number:
            raise HTTPException(status_code=404, detail="Phone number not found")
        
        # Update fields
        if data.customer_name is not None:
            phone_number.customer_name = data.customer_name
        
        if data.agent_id is not None:
            # Verify agent exists
            agent_result = await db.execute(
                select(HierarchicalEntity).where(
                    and_(
                        HierarchicalEntity.id == data.agent_id,
                        HierarchicalEntity.company_id == current_user.company_id
                    )
                )
            )
            agent = agent_result.scalar_one_or_none()
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            phone_number.agent_id = data.agent_id
        
        if data.is_active is not None:
            phone_number.is_active = data.is_active
        
        if data.customer_metadata is not None:
            phone_number.customer_metadata = data.customer_metadata
        
        await db.commit()
        await db.refresh(phone_number)
        
        return {
            "id": str(phone_number.id),
            "customer_id": str(phone_number.customer_id),
            "customer_name": phone_number.customer_name,
            "phone_number": phone_number.phone_number,
            "provider": phone_number.provider,
            "agent_id": str(phone_number.agent_id),
            "is_active": phone_number.is_active,
            "assigned_at": phone_number.assigned_at.isoformat(),
            "customer_metadata": phone_number.customer_metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating phone number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{phone_number_id}")
async def delete_phone_number(
    phone_number_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete phone number assignment."""
    try:
        result = await db.execute(
            select(CustomerPhoneNumber).where(
                and_(
                    CustomerPhoneNumber.id == phone_number_id,
                    CustomerPhoneNumber.company_id == current_user.company_id
                )
            )
        )
        phone_number = result.scalar_one_or_none()
        
        if not phone_number:
            raise HTTPException(status_code=404, detail="Phone number not found")
        
        await db.delete(phone_number)
        await db.commit()
        
        return {"message": "Phone number deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting phone number: {e}")
        raise HTTPException(status_code=500, detail=str(e))
