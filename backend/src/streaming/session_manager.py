"""
Session Manager for Voice and WhatsApp sessions.

Phase 1: PostgreSQL-only implementation (no Redis).
Suitable for <50 concurrent calls/sessions.
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from src.streaming.models import VoiceSession, WhatsAppSession

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages active voice and WhatsApp sessions.
    
    Phase 1: Uses PostgreSQL only for session storage.
    Phase 2+: Can add Redis caching layer for higher concurrency.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ========== Voice Session Methods ==========
    
    async def create_voice_session(
        self,
        company_id: UUID,
        customer_id: UUID,
        agent_id: UUID,
        phone_number: str,
        provider: str,
        call_sid: str,
        direction: str = "inbound",
        metadata: Optional[Dict[str, Any]] = None
    ) -> VoiceSession:
        """
        Create a new voice session in the database.
        
        Args:
            company_id: Company UUID
            customer_id: Customer UUID
            agent_id: HierarchicalEntity (agent) UUID
            phone_number: Phone number being called
            provider: 'twilio' or 'tata_tele'
            call_sid: Unique call identifier from provider
            direction: 'inbound' or 'outbound'
            metadata: Additional call metadata
            
        Returns:
            Created VoiceSession object
        """
        session = VoiceSession(
            company_id=company_id,
            customer_id=customer_id,
            agent_id=agent_id,
            phone_number=phone_number,
            provider=provider,
            call_sid=call_sid,
            direction=direction,
            status="active",
            session_metadata=metadata or {},
            context_state={}  # Initialize empty context
        )
        
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        
        logger.info(f"Created voice session: {session.id} for call_sid={call_sid}")
        return session
    
    async def get_voice_session(self, session_id: UUID) -> Optional[VoiceSession]:
        """Get voice session by ID."""
        result = await self.db.execute(
            select(VoiceSession).where(VoiceSession.id == session_id)
        )
        return result.scalar_one_or_none()
    
    async def get_voice_session_by_call_sid(self, call_sid: str) -> Optional[VoiceSession]:
        """
        Get active voice session by call_sid (indexed query).
        Used by WebSocket handler to look up session.
        """
        result = await self.db.execute(
            select(VoiceSession).where(
                VoiceSession.call_sid == call_sid,
                VoiceSession.status == "active"
            )
        )
        return result.scalar_one_or_none()
    
    async def update_voice_session(
        self,
        session_id: UUID,
        updates: Dict[str, Any]
    ) -> None:
        """
        Update voice session fields.
        
        Args:
            session_id: Session UUID
            updates: Dictionary of fields to update
        """
        await self.db.execute(
            update(VoiceSession)
            .where(VoiceSession.id == session_id)
            .values(**updates)
        )
        await self.db.commit()
        logger.debug(f"Updated voice session: {session_id}")

    async def update_session_call_sid(
        self,
        session_id: UUID,
        call_sid: str
    ) -> None:
        """
        Update call_sid for a voice session.
        Used when replacing temporary SID with real provider SID.
        """
        await self.update_voice_session(session_id, {"call_sid": call_sid})
    
    async def update_context(
        self,
        session_id: UUID,
        context: Dict[str, Any]
    ) -> None:
        """
        Update conversation context state (JSONB field).
        Used to maintain conversation state across turns.
        """
        await self.db.execute(
            update(VoiceSession)
            .where(VoiceSession.id == session_id)
            .values(context_state=context)
        )
        await self.db.commit()
    
    async def end_voice_session(
        self,
        session_id: UUID,
        duration_seconds: Optional[int] = None,
        conversation_log: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        End a voice session and save final state.
        
        Args:
            session_id: Session UUID
            duration_seconds: Call duration
            conversation_log: Full transcript/conversation log
        """
        updates = {
            "status": "completed",
            "ended_at": datetime.utcnow()
        }
        
        if duration_seconds is not None:
            updates["duration_seconds"] = duration_seconds
        
        if conversation_log is not None:
            updates["conversation_log"] = conversation_log
        
        await self.update_voice_session(session_id, updates)
        logger.info(f"Ended voice session: {session_id}")
    
    async def get_active_sessions_count(self) -> int:
        """Get count of currently active voice sessions."""
        result = await self.db.execute(
            select(VoiceSession).where(VoiceSession.status == "active")
        )
        return len(result.scalars().all())
    
    # ========== WhatsApp Session Methods ==========
    
    async def create_whatsapp_session(
        self,
        company_id: UUID,
        customer_id: UUID,
        agent_id: UUID,
        phone_number: str,
        provider: str,
        conversation_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> WhatsAppSession:
        """
        Create a new WhatsApp session.
        
        Args:
            company_id: Company UUID
            customer_id: Customer UUID
            agent_id: HierarchicalEntity (agent) UUID
            phone_number: WhatsApp phone number
            provider: 'twilio' or 'tata_tele'
            conversation_id: Unique conversation identifier
            metadata: Additional metadata
            
        Returns:
            Created WhatsAppSession object
        """
        # 24-hour session window
        session_window_expires = datetime.utcnow() + timedelta(hours=24)
        
        session = WhatsAppSession(
            company_id=company_id,
            customer_id=customer_id,
            agent_id=agent_id,
            phone_number=phone_number,
            provider=provider,
            conversation_id=conversation_id,
            session_window_expires=session_window_expires,
            session_metadata=metadata or {}
        )
        
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        
        logger.info(f"Created WhatsApp session: {session.id}")
        return session
    
    async def get_whatsapp_session_by_conversation(
        self,
        conversation_id: str
    ) -> Optional[WhatsAppSession]:
        """Get WhatsApp session by conversation ID."""
        result = await self.db.execute(
            select(WhatsAppSession).where(
                WhatsAppSession.conversation_id == conversation_id,
                WhatsAppSession.status == "active"
            )
        )
        return result.scalar_one_or_none()
    
    async def get_or_create_whatsapp_session(
        self,
        company_id: UUID,
        customer_id: UUID,
        agent_id: UUID,
        customer_phone: str,
        provider: str
    ) -> WhatsAppSession:
        """
        Get existing WhatsApp session or create new one.
        Checks if session window is still valid (24 hours).
        """
        # Use phone as conversation ID for simplicity
        conversation_id = f"{provider}:{customer_phone}"
        
        # Try to get existing session
        existing = await self.get_whatsapp_session_by_conversation(conversation_id)
        
        if existing:
            # Check if session window is still valid
            if existing.session_window_expires > datetime.utcnow():
                # Extend window by 24 hours
                await self.update_whatsapp_session(
                    existing.id,
                    {"session_window_expires": datetime.utcnow() + timedelta(hours=24)}
                )
                return existing
            else:
                # Session expired, end it
                await self.update_whatsapp_session(
                    existing.id,
                    {"status": "expired"}
                )
        
        # Create new session
        return await self.create_whatsapp_session(
            company_id=company_id,
            customer_id=customer_id,
            agent_id=agent_id,
            phone_number=customer_phone,
            provider=provider,
            conversation_id=conversation_id
        )
    
    async def update_whatsapp_session(
        self,
        session_id: UUID,
        updates: Dict[str, Any]
    ) -> None:
        """Update WhatsApp session fields."""
        await self.db.execute(
            update(WhatsAppSession)
            .where(WhatsAppSession.id == session_id)
            .values(**updates)
        )
        await self.db.commit()
        logger.debug(f"Updated WhatsApp session: {session_id}")
    
    async def increment_message_count(self, session_id: UUID) -> None:
        """Increment message count for WhatsApp session."""
        session = await self.db.get(WhatsAppSession, session_id)
        if session:
            session.message_count += 1
            session.last_message_at = datetime.utcnow()
            await self.db.commit()
