"""
API Router for viewing voice and WhatsApp streaming session data.

Provides endpoints for:
- Viewing voice sessions
- Viewing WhatsApp sessions  
- Viewing conversation history
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta

from src.database import get_db
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.streaming.models import VoiceSession, WhatsAppSession, ConversationHistory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/streaming", tags=["Streaming Sessions"])


@router.get("/voice-sessions")
async def list_voice_sessions(
    status: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List voice call sessions for current company.
    
    Args:
        status: Filter by status
        provider: Filter by provider
        limit: Max results
        offset: Pagination offset
        
    Returns:
        List of voice sessions
    """
    try:
        query = select(VoiceSession).where(
            VoiceSession.company_id == current_user.company_id
        )
        
        if status:
            query = query.where(VoiceSession.status == status)
        
        if provider:
            query = query.where(VoiceSession.provider == provider)
        
        query = query.order_by(desc(VoiceSession.started_at))
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        return {
            "total": len(sessions),
            "sessions": [
                {
                    "id": str(s.id),
                    "customer_id": str(s.customer_id),
                    "agent_id": str(s.agent_id),
                    "phone_number": s.phone_number,
                    "provider": s.provider,
                    "call_sid": s.call_sid,
                    "direction": s.direction,
                    "status": s.status,
                    "started_at": s.started_at.isoformat(),
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "duration_seconds": s.duration_seconds,
                    "total_cost_usd": float(s.total_cost_usd) if s.total_cost_usd else 0,
                    "has_transcript": bool(s.conversation_log)
                }
                for s in sessions
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing voice sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voice-sessions/{session_id}")
async def get_voice_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed voice session information including transcript."""
    try:
        result = await db.execute(
            select(VoiceSession).where(
                and_(
                    VoiceSession.id == session_id,
                    VoiceSession.company_id == current_user.company_id
                )
            )
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "id": str(session.id),
            "customer_id": str(session.customer_id),
            "agent_id": str(session.agent_id),
            "phone_number": session.phone_number,
            "provider": session.provider,
            "call_sid": session.call_sid,
            "stream_sid": session.stream_sid,
            "direction": session.direction,
            "status": session.status,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "duration_seconds": session.duration_seconds,
            "total_cost_usd": float(session.total_cost_usd) if session.total_cost_usd else 0,
            "conversation_log": session.conversation_log or [],
            "context_state": session.context_state or {},
            "session_metadata": session.session_metadata or {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting voice session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whatsapp-sessions")
async def list_whatsapp_sessions(
    status: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List WhatsApp conversation sessions."""
    try:
        query = select(WhatsAppSession).where(
            WhatsAppSession.company_id == current_user.company_id
        )
        
        if status:
            query = query.where(WhatsAppSession.status == status)
        
        if provider:
            query = query.where(WhatsAppSession.provider == provider)
        
        query = query.order_by(desc(WhatsAppSession.started_at))
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        return {
            "total": len(sessions),
            "sessions": [
                {
                    "id": str(s.id),
                    "customer_id": str(s.customer_id),
                    "agent_id": str(s.agent_id),
                    "phone_number": s.phone_number,
                    "provider": s.provider,
                    "conversation_id": s.conversation_id,
                    "status": s.status,
                    "started_at": s.started_at.isoformat(),
                    "last_message_at": s.last_message_at.isoformat() if s.last_message_at else None,
                    "message_count": s.message_count,
                    "total_cost_usd": float(s.total_cost_usd) if s.total_cost_usd else 0,
                    "session_window_expires": s.session_window_expires.isoformat() if s.session_window_expires else None
                }
                for s in sessions
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing WhatsApp sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whatsapp-sessions/{session_id}")
async def get_whatsapp_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed WhatsApp session information."""
    try:
        result = await db.execute(
            select(WhatsAppSession).where(
                and_(
                    WhatsAppSession.id == session_id,
                    WhatsAppSession.company_id == current_user.company_id
                )
            )
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "id": str(session.id),
            "customer_id": str(session.customer_id),
            "agent_id": str(session.agent_id),
            "phone_number": session.phone_number,
            "provider": session.provider,
            "conversation_id": session.conversation_id,
            "status": session.status,
            "started_at": session.started_at.isoformat(),
            "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None,
            "message_count": session.message_count,
            "total_cost_usd": float(session.total_cost_usd) if session.total_cost_usd else 0,
            "session_window_expires": session.session_window_expires.isoformat() if session.session_window_expires else None,
            "conversation_log": session.conversation_log or [],
            "session_metadata": session.session_metadata or {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting WhatsApp session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation-history")
async def list_conversation_history(
    customer_id: Optional[UUID] = None,
    agent_id: Optional[UUID] = None,
    channel: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List conversation history across voice and WhatsApp."""
    try:
        query = select(ConversationHistory).where(
            ConversationHistory.company_id == current_user.company_id
        )
        
        if customer_id:
            query = query.where(ConversationHistory.customer_id == customer_id)
        
        if agent_id:
            query = query.where(ConversationHistory.agent_id == agent_id)
        
        if channel:
            query = query.where(ConversationHistory.channel == channel)
        
        query = query.order_by(desc(ConversationHistory.timestamp))
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        history = result.scalars().all()
        
        return {
            "total": len(history),
            "history": [
                {
                    "id": str(h.id),
                    "customer_id": str(h.customer_id),
                    "agent_id": str(h.agent_id),
                    "session_id": str(h.session_id) if h.session_id else None,
                    "channel": h.channel,
                    "turn_number": h.turn_number,
                    "speaker": h.speaker,
                    "message_type": h.message_type,
                    "content": h.content,
                    "audio_duration_ms": h.audio_duration_ms,
                    "timestamp": h.timestamp.isoformat(),
                    "message_metadata": h.message_metadata or {}
                }
                for h in history
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_streaming_stats(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get streaming statistics for the company."""
    try:
        since = datetime.utcnow() - timedelta(days=days)
        company_id = current_user.company_id
        
        # Voice sessions stats
        voice_result = await db.execute(
            select(VoiceSession).where(
                and_(
                    VoiceSession.company_id == company_id,
                    VoiceSession.started_at >= since
                )
            )
        )
        voice_sessions = voice_result.scalars().all()
        
        # WhatsApp sessions stats
        whatsapp_result = await db.execute(
            select(WhatsAppSession).where(
                and_(
                    WhatsAppSession.company_id == company_id,
                    WhatsAppSession.started_at >= since
                )
            )
        )
        whatsapp_sessions = whatsapp_result.scalars().all()
        
        return {
            "period_days": days,
            "voice": {
                "total_calls": len(voice_sessions),
                "completed_calls": len([s for s in voice_sessions if s.status == "ended"]),
                "total_duration_minutes": sum(s.duration_seconds or 0 for s in voice_sessions) / 60,
                "total_cost_usd": sum(float(s.total_cost_usd or 0) for s in voice_sessions),
                "by_provider": {
                    "twilio": len([s for s in voice_sessions if s.provider == "twilio"]),
                    "tata_tele": len([s for s in voice_sessions if s.provider == "tata_tele"])
                }
            },
            "whatsapp": {
                "total_sessions": len(whatsapp_sessions),
                "active_sessions": len([s for s in whatsapp_sessions if s.status == "active"]),
                "total_messages": sum(s.message_count for s in whatsapp_sessions),
                "total_cost_usd": sum(float(s.total_cost_usd or 0) for s in whatsapp_sessions),
                "by_provider": {
                    "twilio": len([s for s in whatsapp_sessions if s.provider == "twilio"]),
                    "tata_tele": len([s for s in whatsapp_sessions if s.provider == "tata_tele"])
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting streaming stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
