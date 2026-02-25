"""
Campaign Executor - Auto-dialer for bulk voice campaigns.

Handles:
- Campaign execution scheduling
- Call queue management
- Throttling and rate limiting
- Twilio/Tata Tele API integration for outbound calls
- Call status monitoring
"""
import logging
import asyncio
import httpx
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update

from src.ai.campaign_models import Campaign, CampaignCall
from src.streaming.models import VoiceSession
from src.streaming.number_router import NumberRouter
from src.config.service import ConfigService
from src.config.models import IntegrationRegistry
from src.common.security import decrypt_api_key
from src.common.config import settings

logger = logging.getLogger(__name__)


class CampaignExecutor:
    """
    Executes voice calling campaigns.
    
    Manages call queues, throttling, and status tracking.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize campaign executor.
        
        Args:
            db: Database session
        """
        self.db = db
        self.number_router = NumberRouter(db)
        self.active_campaigns: Dict[UUID, asyncio.Task] = {}
    
    async def start_campaign(self, campaign_id: UUID):
        """
        Start executing a campaign.
        
        Args:
            campaign_id: Campaign UUID
        """
        # Check if already running
        if campaign_id in self.active_campaigns:
            logger.warning(f"Campaign {campaign_id} is already running")
            return
        
        # Load campaign
        campaign = await self._get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        # Validate campaign can start
        if campaign.status not in ["draft", "scheduled", "paused", "running"]:
            raise ValueError(f"Campaign cannot be started from status: {campaign.status}")
        
        # Update status to running
        await self._update_campaign_status(campaign_id, "running")
        
        # Create execution task
        task = asyncio.create_task(self._execute_campaign(campaign_id))
        self.active_campaigns[campaign_id] = task
        
        logger.info(f"Started campaign {campaign_id}")
    
    async def pause_campaign(self, campaign_id: UUID):
        """
        Pause a running campaign.
        
        Args:
            campaign_id: Campaign UUID
        """
        if campaign_id not in self.active_campaigns:
            logger.warning(f"Campaign {campaign_id} is not running")
            return
        
        # Cancel execution task
        task = self.active_campaigns.pop(campaign_id)
        task.cancel()
        
        # Update status
        await self._update_campaign_status(campaign_id, "paused")
        
        logger.info(f"Paused campaign {campaign_id}")
    
    async def stop_campaign(self, campaign_id: UUID):
        """
        Stop a campaign completely.
        
        Args:
            campaign_id: Campaign UUID
        """
        if campaign_id in self.active_campaigns:
            task = self.active_campaigns.pop(campaign_id)
            task.cancel()
        
        # Update status
        await self._update_campaign_status(campaign_id, "completed")
        
        logger.info(f"Stopped campaign {campaign_id}")
    
    async def _execute_campaign(self, campaign_id: UUID):
        """
        Main execution loop for a campaign.
        
        Args:
            campaign_id: Campaign UUID
        """
        try:
            campaign = await self._get_campaign(campaign_id)
            
            # Get pending calls
            pending_calls = await self._get_pending_calls(campaign_id)
            
            logger.info(f"Executing campaign {campaign_id} with {len(pending_calls)} pending calls")
            
            # Create call queue
            call_queue = asyncio.Queue()
            for call in pending_calls:
                await call_queue.put(call)
            
            # Start worker tasks (respecting max_concurrent_calls)
            workers = []
            for i in range(campaign.max_concurrent_calls):
                worker = asyncio.create_task(
                    self._call_worker(campaign, call_queue)
                )
                workers.append(worker)
            
            # Wait for all workers to complete
            await asyncio.gather(*workers, return_exceptions=True)
            
            # Mark campaign as completed
            await self._update_campaign_status(campaign_id, "completed")
            
            logger.info(f"Campaign {campaign_id} completed")
            
        except asyncio.CancelledError:
            logger.info(f"Campaign {campaign_id} was cancelled")
        except Exception as e:
            logger.error(f"Error executing campaign {campaign_id}: {e}", exc_info=True)
            await self._update_campaign_status(campaign_id, "failed")
        finally:
            # Remove from active campaigns
            if campaign_id in self.active_campaigns:
                self.active_campaigns.pop(campaign_id)
    
    async def _call_worker(self, campaign: Campaign, call_queue: asyncio.Queue):
        """
        Worker task that processes calls from the queue.
        
        Args:
            campaign: Campaign object
            call_queue: Queue of CampaignCall objects
        """
        while True:
            try:
                # Get next call (with timeout to allow graceful shutdown)
                try:
                    call = await asyncio.wait_for(call_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # Check if queue is empty
                    if call_queue.empty():
                        break
                    continue
                
                # Place the call
                await self._place_call(campaign, call)
                
                # Mark task as done
                call_queue.task_done()
                
                # Small delay to respect rate limits
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error in call worker: {e}", exc_info=True)
    
    async def _place_call(self, campaign: Campaign, campaign_call: CampaignCall):
        """
        Place an outbound call to a contact.
        
        Args:
            campaign: Campaign object
            campaign_call: CampaignCall object
        """
        contact = campaign_call.contact_data
        phone = contact.get("phone")
        
        logger.info(f"Placing call to {phone} for campaign {campaign.id}")
        
        try:
            # Update call status to "calling"
            await self._update_call_status(campaign_call.id, "calling")
            
            # Get phone number assignment
            # For outbound calls, we need to get the company's assigned number
            assignment = await self.number_router.get_company_number(
                company_id=campaign.company_id,
                provider=campaign.provider
            )
            
            if not assignment:
                logger.error(f"No phone number assigned for company {campaign.company_id}")
                await self._update_call_status(campaign_call.id, "failed")
                return
            
            # Create voice session
            voice_session = VoiceSession(
                company_id=campaign.company_id,
                customer_id=uuid4(),  # Generate random UUID since customer_id is non-nullable
                agent_id=campaign.agent_id,
                phone_number=assignment.phone_number,
                provider=campaign.provider,
                direction="outbound",
                status="initiated",
                call_sid=f"pending_{uuid4()}",  # Temporary SID until provider returns real one
                session_metadata={
                    "campaign_id": str(campaign.id),
                    "campaign_call_id": str(campaign_call.id),
                    "contact_data": contact
                }
            )
            
            self.db.add(voice_session)
            await self.db.commit()
            await self.db.refresh(voice_session)
            
            # Link voice session to campaign call
            await self.db.execute(
                update(CampaignCall)
                .where(CampaignCall.id == campaign_call.id)
                .values(
                    voice_session_id=voice_session.id,
                    called_at=datetime.utcnow()
                )
            )
            await self.db.commit()
            
            # Place actual call via provider
            if campaign.provider == "twilio":
                call_sid = await self._place_twilio_call(
                    to=phone,
                    from_=assignment.phone_number,
                    voice_session_id=voice_session.id,
                    agent_id=campaign.agent_id,
                    company_id=campaign.company_id
                )
            elif campaign.provider == "tata_tele":
                call_sid = await self._place_tata_call(
                    to=phone,
                    from_=assignment.phone_number,
                    voice_session_id=voice_session.id,
                    agent_id=campaign.agent_id,
                    company_id=campaign.company_id
                )
            else:
                raise ValueError(f"Unknown provider: {campaign.provider}")
            
            # Update call_sid
            await self.db.execute(
                update(CampaignCall)
                .where(CampaignCall.id == campaign_call.id)
                .values(call_sid=call_sid)
            )
            await self.db.commit()
            
            # Update campaign stats
            await self._increment_campaign_stat(campaign.id, "calls_initiated")
            
            logger.info(f"Call placed successfully: {call_sid}")
            
        except Exception as e:
            logger.error(f"Error placing call to {phone}: {e}", exc_info=True)
            await self._update_call_status(campaign_call.id, "failed")
            await self._increment_campaign_stat(campaign.id, "calls_failed")
    
    async def _place_twilio_call(
        self,
        to: str,
        from_: str,
        voice_session_id: UUID,
        agent_id: UUID,
        company_id: Optional[UUID] = None
    ) -> str:
        """
        Place outbound call via Twilio REST API.
        
        Uses Twilio's Calls resource to initiate an outbound call.
        The call connects to a TwiML webhook that returns <Connect><Stream>
        to establish a WebSocket for bidirectional audio streaming.
        
        API: POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Calls.json
        
        Args:
            to: Destination phone number (E.164 format, e.g. +14155551234)
            from_: Caller ID (Twilio number, E.164 format)
            voice_session_id: VoiceSession UUID
            agent_id: Agent UUID
            company_id: Company UUID for credential lookup
            
        Returns:
            Call SID from Twilio
        """
        import os
        
        # 1. Retrieve Twilio credentials from integration registry
        config_service = ConfigService(self.db)
        
        # Try to get credentials from the integration registry
        result = await self.db.execute(
            select(IntegrationRegistry).where(
                IntegrationRegistry.company_id == company_id,
                IntegrationRegistry.provider_name == "twilio",
                IntegrationRegistry.status == "active"
            )
        )
        entry = result.scalars().first()
        
        # Extract credentials
        account_sid = None
        auth_token = None
        
        if entry:
            auth_token = decrypt_api_key(entry.encrypted_api_key) if entry.encrypted_api_key else None
            # Look for account_sid in service_metadata
            if entry.service_metadata:
                account_sid = entry.service_metadata.get("account_sid")
        
        # Fall back to environment variables if not found in registry
        account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        
        if not account_sid or not auth_token:
            raise ValueError(
                "Twilio credentials not found. Please ensure you have a 'twilio' "
                "integration configured in the Integration Registry (with account_sid "
                "in service_metadata and auth_token in api_key) or set environment variables."
            )
        
        # 2. Build the TwiML webhook URL
        # When Twilio connects the call, it will request this URL.
        # The webhook returns TwiML with <Connect><Stream> to establish
        # a WebSocket for bidirectional audio with our streaming service.
        streaming_host = settings.STREAMING_HOST or "localhost:8002"
        # Use HTTPS for production domains, HTTP only for localhost
        protocol = "http" if streaming_host.startswith("localhost") else "https"
        ws_protocol = "ws" if streaming_host.startswith("localhost") else "wss"
        
        # The TwiML URL that Twilio will fetch when the call connects
        twiml_url = (
            f"{protocol}://{streaming_host}/webhooks/voice/twilio/outbound-twiml"
            f"?session_id={voice_session_id}"
        )
        
        # Status callback URL for call completion events
        status_callback_url = f"{protocol}://{streaming_host}/webhooks/voice/twilio/status"
        
        # 3. Build request payload for Twilio REST API
        payload = {
            "To": to,
            "From": from_,
            "Url": twiml_url,
            "StatusCallback": status_callback_url,
            "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
            "StatusCallbackMethod": "POST",
            "Record": "false",
            "MachineDetection": "Enable",  # Detect answering machines
            "AsyncAmd": "true",  # Async answering machine detection
            "AsyncAmdStatusCallback": status_callback_url,
            "AsyncAmdStatusCallbackMethod": "POST",
        }
        
        # 4. Make API call to Twilio
        api_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
        
        logger.info(
            f"Twilio outbound call: {from_} → {to}, "
            f"session={voice_session_id}, twiml_url={twiml_url}"
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                data=payload,  # Twilio expects form-encoded data
                auth=(account_sid, auth_token),
                timeout=30.0
            )
        
        # 5. Parse response
        response_data = response.json()
        logger.info(f"Twilio API response: {response.status_code} - {response_data}")
        
        if response.status_code in [200, 201]:
            call_sid = response_data.get("sid")
            logger.info(f"Twilio call initiated successfully: {call_sid}")
            return call_sid
        else:
            error_msg = (
                response_data.get("message")
                or response_data.get("detail")
                or str(response_data)
            )
            raise Exception(
                f"Twilio API error (HTTP {response.status_code}): {error_msg}"
            )
    
    async def _place_tata_call(
        self,
        to: str,
        from_: str,
        voice_session_id: UUID,
        agent_id: UUID,
        company_id: Optional[UUID] = None
    ) -> str:
        """
        Place outbound call via Tata Tele Click-to-Call Support API.
        
        The Click-to-Call Support API works in reverse:
        1. Customer receives the call first
        2. Once customer answers, a second call connects to the destination/agent
        
        API: POST https://api-smartflo.tatateleservices.com/v1/click_to_call_support
        
        Args:
            to: Destination phone number (customer)
            from_: Caller ID (DID number)
            voice_session_id: VoiceSession UUID
            agent_id: Agent UUID
            company_id: Company UUID for API key lookup
            
        Returns:
            Call SID/reference from Tata Tele
        """
        # 1. Retrieve Tata Tele API key from integration registry
        config_service = ConfigService(self.db)
        api_key = await config_service.get_api_key_by_provider(
            company_id=company_id,
            provider_name="tata_tele"
        )
        
        if not api_key:
            raise ValueError(
                "Tata Tele API key not found. Please ensure you have a 'tata_tele' "
                "integration configured in the Integration Registry."
            )
        
        # 2. Clean phone numbers
        # Remove '+' prefix and country code formatting if present
        customer_number = to.lstrip("+")
        caller_id = from_.lstrip("+")
        
        # 3. Build request payload
        payload = {
            "customer_number": customer_number,
            "api_key": api_key,
            "async": 1,  # Non-blocking, allows concurrent calls
            "customer_ring_timeout": 30,  # Max ring time in seconds
            "caller_id": caller_id,
            "custom_identifier": str(voice_session_id),  # For correlating callbacks
        }
        
        # 4. Make API call
        api_url = "https://api-smartflo.tatateleservices.com/v1/click_to_call_support"
        
        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
        
        logger.info(
            f"Tata Tele Click-to-Call Support: {from_} → {to}, "
            f"session={voice_session_id}"
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=30.0
            )
        
        # 5. Parse response
        response_data = response.json()
        logger.info(f"Tata Tele API response: {response.status_code} - {response_data}")
        
        if response.status_code in [200, 201]:
            # Extract call reference/SID from response
            call_sid = (
                response_data.get("call_id")
                or response_data.get("callId")
                or response_data.get("id")
                or f"TT_{voice_session_id}"
            )
            logger.info(f"Tata Tele call initiated successfully: {call_sid}")
            return str(call_sid)
        else:
            error_msg = response_data.get("message") or response_data.get("error") or str(response_data)
            raise Exception(
                f"Tata Tele Click-to-Call Support API error "
                f"(HTTP {response.status_code}): {error_msg}"
            )
    
    async def _get_campaign(self, campaign_id: UUID) -> Optional[Campaign]:
        """Get campaign by ID."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        return result.scalar_one_or_none()
    
    async def _get_pending_calls(self, campaign_id: UUID):
        """Get all pending calls for a campaign."""
        result = await self.db.execute(
            select(CampaignCall)
            .where(
                and_(
                    CampaignCall.campaign_id == campaign_id,
                    CampaignCall.status == "pending"
                )
            )
            .order_by(CampaignCall.created_at.asc())
        )
        return result.scalars().all()
    
    async def _update_campaign_status(self, campaign_id: UUID, status: str):
        """Update campaign status."""
        updates = {"status": status, "updated_at": datetime.utcnow()}
        
        if status == "running":
            updates["started_at"] = datetime.utcnow()
        elif status == "completed":
            updates["completed_at"] = datetime.utcnow()
        
        await self.db.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(**updates)
        )
        await self.db.commit()
    
    async def _update_call_status(self, call_id: UUID, status: str):
        """Update campaign call status."""
        updates = {"status": status}
        
        if status == "completed":
            updates["completed_at"] = datetime.utcnow()
        
        await self.db.execute(
            update(CampaignCall)
            .where(CampaignCall.id == call_id)
            .values(**updates)
        )
        await self.db.commit()
    
    async def _increment_campaign_stat(self, campaign_id: UUID, stat: str):
        """Increment a campaign statistic counter."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if campaign:
            current_value = getattr(campaign, stat, 0)
            await self.db.execute(
                update(Campaign)
                .where(Campaign.id == campaign_id)
                .values({stat: current_value + 1})
            )
            await self.db.commit()
