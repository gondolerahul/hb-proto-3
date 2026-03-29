"""
Number Router for dynamic phone number assignment and routing.

Phase 1: Static 1:1 mapping (one dedicated number per customer).
Phase 2+: Dynamic pooling with number sharing.
"""
import logging
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.voice.models import CustomerPhoneNumber

logger = logging.getLogger(__name__)


class NumberRouter:
    """
    Manages phone number assignments and routing logic.
    
    Phase 1: Simple 1:1 customer-to-number mapping
    Phase 2: Dynamic number pooling
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_customer_by_number(
        self,
        phone_number: str
    ) -> Optional[CustomerPhoneNumber]:
        """
        Find customer assignment for a given phone number.
        Used by incoming call webhooks to determine routing.
        
        Args:
            phone_number: Phone number that was called (e.g., "+911234567890")
            
        Returns:
            CustomerPhoneNumber object if found, None otherwise
        """
        result = await self.db.execute(
            select(CustomerPhoneNumber).where(
                CustomerPhoneNumber.phone_number == phone_number,
                CustomerPhoneNumber.is_active == True
            )
        )
        assignment = result.scalar_one_or_none()
        
        if assignment:
            logger.info(f"Found customer {assignment.customer_id} for number {phone_number}")
        else:
            logger.warning(f"No customer assignment found for number {phone_number}")
        
        return assignment
    
    async def assign_number_to_customer(
        self,
        company_id: UUID,
        customer_id: UUID,
        customer_name: str,
        agent_id: UUID,
        phone_number: str,
        provider: Optional[str] = None,
        customer_metadata: Optional[dict] = None
    ) -> CustomerPhoneNumber:
        """
        Assign a phone number to a customer.
        
        Args:
            company_id: Company UUID
            customer_id: Customer UUID
            customer_name: Customer name for reference
            agent_id: Agent (HierarchicalEntity) to handle calls
            phone_number: Phone number to assign
            provider: 'twilio' or 'tata_tele' (auto-detected if None)
            customer_metadata: Additional customer information
            
        Returns:
            Created CustomerPhoneNumber assignment
        """
        # Auto-detect provider based on country code if not specified
        if provider is None:
            provider = self._detect_provider(phone_number)
        
        assignment = CustomerPhoneNumber(
            company_id=company_id,
            customer_id=customer_id,
            customer_name=customer_name,
            phone_number=phone_number,
            provider=provider,
            agent_id=agent_id,
            customer_metadata=customer_metadata or {},
            is_active=True
        )
        
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        
        logger.info(
            f"Assigned number {phone_number} ({provider}) to "
            f"customer {customer_id} with agent {agent_id}"
        )
        
        return assignment
    
    def _detect_provider(self, phone_number: str) -> str:
        """
        Detect provider based on phone number country code.
        
        Args:
            phone_number: Phone number with country code
            
        Returns:
            'twilio' or 'tata_tele'
        """
        # Remove spaces and dashes
        clean_number = phone_number.replace(" ", "").replace("-", "")
        
        # India: +91
        if clean_number.startswith("+91"):
            return "tata_tele"
        
        # Default to Twilio for other countries
        return "twilio"
    
    async def get_customer_number(
        self,
        customer_id: UUID
    ) -> Optional[CustomerPhoneNumber]:
        """
        Get assigned phone number for a customer.
        
        Args:
            customer_id: Customer UUID
            
        Returns:
            CustomerPhoneNumber if assigned, None otherwise
        """
        result = await self.db.execute(
            select(CustomerPhoneNumber).where(
                CustomerPhoneNumber.customer_id == customer_id,
                CustomerPhoneNumber.is_active == True
            )
        )
        return result.scalar_one_or_none()
    
    async def deactivate_number_assignment(
        self,
        phone_number: str
    ) -> None:
        """
        Deactivate a number assignment (soft delete).
        
        Args:
            phone_number: Phone number to deactivate
        """
        result = await self.db.execute(
            select(CustomerPhoneNumber).where(
                CustomerPhoneNumber.phone_number == phone_number
            )
        )
        assignment = result.scalar_one_or_none()
        
        if assignment:
            assignment.is_active = False
            await self.db.commit()
            logger.info(f"Deactivated number assignment: {phone_number}")
    
    async def get_company_number(
        self,
        company_id: UUID,
        provider: str = "twilio"
    ) -> Optional[CustomerPhoneNumber]:
        """
        Get company's assigned phone number for outbound calls.
        
        For campaigns, we use the company's first active number as caller ID.
        
        Args:
            company_id: Company UUID
            provider: Provider ('twilio' or 'tata_tele')
            
        Returns:
            CustomerPhoneNumber if available, None otherwise
        """
        result = await self.db.execute(
            select(CustomerPhoneNumber).where(
                CustomerPhoneNumber.company_id == company_id,
                CustomerPhoneNumber.provider == provider,
                CustomerPhoneNumber.is_active == True
            ).limit(1)
        )
        assignment = result.scalar_one_or_none()
        
        if not assignment:
            logger.warning(
                f"No active {provider} number found for company {company_id}"
            )
        
        return assignment
    
    async def list_active_assignments(
        self,
        company_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> list[CustomerPhoneNumber]:
        """
        List all active number assignments for a company.
        
        Args:
            company_id: Company UUID
            limit: Maximum results to return
            offset: Pagination offset
            
        Returns:
            List of CustomerPhoneNumber assignments
        """
        result = await self.db.execute(
            select(CustomerPhoneNumber)
            .where(
                CustomerPhoneNumber.company_id == company_id,
                CustomerPhoneNumber.is_active == True
            )
            .limit(limit)
            .offset(offset)
            .order_by(CustomerPhoneNumber.assigned_at.desc())
        )
        return result.scalars().all()
    
    # ========== Future: Dynamic Pooling Methods ==========
    
    async def acquire_available_number(
        self,
        provider: str,
        country_code: str = "+91"
    ) -> Optional[str]:
        """
        Future: Acquire an available number from the pool.
        For Phase 2+ when implementing dynamic pooling.
        
        Args:
            provider: 'twilio' or 'tata_tele'
            country_code: Required country code
            
        Returns:
            Available phone number or None
        """
        # TODO: Implement dynamic pooling in Phase 2
        # - Query phone_number_pool table
        # - Find available number
        # - Mark as in-use
        # - Return number
        logger.warning("Dynamic pooling not yet implemented")
        return None
    
    async def release_number(self, phone_number: str) -> None:
        """
        Future: Release a number back to the pool.
        For Phase 2+ when implementing dynamic pooling.
        
        Args:
            phone_number: Number to release
        """
        # TODO: Implement in Phase 2
        logger.warning("Dynamic pooling not yet implemented")
        pass
