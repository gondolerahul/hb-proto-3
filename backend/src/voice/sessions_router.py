"""
API Router for viewing voice and WhatsApp streaming session data.

Provides endpoints for:
- Viewing voice sessions
- Viewing WhatsApp sessions  
- Viewing conversation history
"""
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta

from src.database import get_db
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.voice.models import VoiceSession, WhatsAppSession, ConversationHistory
from src.ai.artifact_models import Artifact
from src.billing.billing_service import BillingService, calculate_tb

# google-genai used for LLM call summaries (best-effort — silently skipped if unavailable)
try:
    import google.genai as _genai  # type: ignore
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    _genai = None  # type: ignore

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

        # Fix #2: Compute billed_amount via TB formula for each session
        billing_svc = BillingService(db)
        config = await billing_svc.get_billing_config(current_user.company_id)
        if config:
            mf = Decimal(str(config.multiplier_factor))
            pf = Decimal(str(config.platform_fee_pct))
            spf = Decimal(str(config.sales_partner_fee_pct))
            d = Decimal(str(config.discount_pct))
        else:
            mf, pf, spf, d = Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0")

        def _billed(raw_cost):
            c = Decimal(str(raw_cost)) if raw_cost else Decimal("0")
            return float(calculate_tb(c, mf, pf, spf, d)["total_billing"])

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
                    "billed_amount": _billed(s.total_cost_usd),
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
        
        # Fetch transcript from ConversationHistory (primary source)
        transcript_result = await db.execute(
            select(ConversationHistory)
            .where(
                and_(
                    ConversationHistory.session_id == session_id,
                    ConversationHistory.company_id == current_user.company_id
                )
            )
            .order_by(ConversationHistory.turn_number)
        )
        transcript_rows = transcript_result.scalars().all()
        
        # Build transcript list from ConversationHistory or fallback to conversation_log.
        # De-duplicate adjacent turns by same speaker with identical content (can happen when
        # Gemini emits both a model_turn text part AND an output_transcription for the same utterance).
        if transcript_rows:
            raw_transcript = [
                {
                    "turn_number": t.turn_number,
                    "speaker": t.speaker,
                    "content": t.content,
                    "message_type": t.message_type,
                    "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                    "audio_duration_ms": t.audio_duration_ms,
                }
                for t in transcript_rows
            ]
            # Deduplicate: keep only unique (speaker, content) combinations, preserving order
            seen = set()
            transcript = []
            for turn in raw_transcript:
                key = (turn["speaker"], turn["content"].strip())
                if key not in seen:
                    seen.add(key)
                    transcript.append(turn)
        else:
            # Fallback to conversation_log JSONB
            transcript = session.conversation_log or []
        
        # Generate a brief AI call summary from the transcript if turns are available
        call_summary = None
        if transcript and len(transcript) >= 2 and _GENAI_AVAILABLE and _genai:
            try:
                formatted = "\n".join(
                    f"{t['speaker'].capitalize()}: {t['content']}"
                    for t in transcript
                    if t.get("content")
                )
                if formatted:
                    from src.common.genai_factory import build_vertex_genai_client
                    try:
                        _client = await build_vertex_genai_client(db, current_user.company_id)
                    except (RuntimeError, ValueError) as _cfg_err:
                        logger.debug(f"Vertex AI client not available for summary: {_cfg_err}")
                        _client = None

                    if _client:
                        _prompt = (
                            "You are a helpful assistant. Analyze the following call transcript and provide:\n"
                            "1. A 2-3 sentence summary highlighting key topics discussed and outcomes.\n"
                            "2. A bullet list of 'Next Actions' the caller/agent should take.\n\n"
                            "Format your response as:\n"
                            "SUMMARY: <your summary>\n\n"
                            "NEXT ACTIONS:\n"
                            "- <action 1>\n"
                            "- <action 2>\n\n"
                            f"Transcript:\n{formatted}"
                        )
                        import asyncio
                        # Use run_in_executor to avoid blocking the event loop
                        # since the genai client's generate_content is synchronous
                        loop = asyncio.get_event_loop()
                        _resp = await loop.run_in_executor(
                            None,
                            lambda: _client.models.generate_content(
                                model="gemini-2.0-flash",
                                contents=_prompt,
                            ),
                        )
                        call_summary = _resp.text.strip() if _resp and _resp.text else None
            except Exception as _se:
                logger.warning(f"Summary generation failed for session {session_id}: {_se}")

        
        # Fetch associated recording artifacts — try three strategies:
        # 1) session_id in artifact_metadata (preferred)
        # 2) call_sid in artifact_metadata (Twilio saves by call_sid)
        # 3) Nearest 'recordings' artifact for this company around session time (fallback)
        recording_artifact = None
        try:
            # Strategy 1: session_id match
            r1 = await db.execute(
                select(Artifact).where(
                    Artifact.company_id == current_user.company_id,
                    Artifact.file_category.in_(["recordings", "recording", "audio"]),
                    Artifact.artifact_metadata["session_id"].as_string() == str(session_id)
                ).order_by(Artifact.created_at.desc()).limit(1)
            )
            recording_artifact = r1.scalar_one_or_none()

            # Strategy 2: call_sid match
            if not recording_artifact and session.call_sid:
                r2 = await db.execute(
                    select(Artifact).where(
                        Artifact.company_id == current_user.company_id,
                        Artifact.file_category.in_(["recordings", "recording", "audio"]),
                        Artifact.artifact_metadata["call_sid"].as_string() == str(session.call_sid)
                    ).order_by(Artifact.created_at.desc()).limit(1)
                )
                recording_artifact = r2.scalar_one_or_none()

            # Strategy 3: proximity — any recording artifact near the session start time
            if not recording_artifact and session.started_at:
                from datetime import timedelta as _td
                r3 = await db.execute(
                    select(Artifact).where(
                        Artifact.company_id == current_user.company_id,
                        Artifact.file_category.in_(["recordings", "recording", "audio"]),
                        Artifact.created_at >= session.started_at - _td(minutes=1),
                        Artifact.created_at <= (session.ended_at or session.started_at) + _td(minutes=5)
                    ).order_by(Artifact.created_at.desc()).limit(1)
                )
                recording_artifact = r3.scalar_one_or_none()
        except Exception as _re:
            logger.warning(f"Recording lookup failed: {_re}")
            recording_artifact = None
        
        # Fix #2: Compute billed_amount for session detail view
        raw_cost = Decimal(str(session.total_cost_usd)) if session.total_cost_usd else Decimal("0")
        billing_svc = BillingService(db)
        config = await billing_svc.get_billing_config(current_user.company_id)
        if config:
            mf = Decimal(str(config.multiplier_factor))
            pf = Decimal(str(config.platform_fee_pct))
            spf = Decimal(str(config.sales_partner_fee_pct))
            d_val = Decimal(str(config.discount_pct))
        else:
            mf, pf, spf, d_val = Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0")
        billed = float(calculate_tb(raw_cost, mf, pf, spf, d_val)["total_billing"])

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
            "billed_amount": billed,
            "transcript": transcript,
            "call_summary": call_summary,
            "conversation_log": session.conversation_log or [],
            "context_state": session.context_state or {},
            "session_metadata": session.session_metadata or {},
            "recording_url": f"/api/v1/artifacts/{recording_artifact.id}/download" if recording_artifact else None,
            "recording_file_name": recording_artifact.file_name if recording_artifact else None,
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
        
        # Fix #2: Compute billed_amount for WhatsApp sessions
        billing_svc = BillingService(db)
        config = await billing_svc.get_billing_config(current_user.company_id)
        if config:
            mf = Decimal(str(config.multiplier_factor))
            pf = Decimal(str(config.platform_fee_pct))
            spf = Decimal(str(config.sales_partner_fee_pct))
            d = Decimal(str(config.discount_pct))
        else:
            mf, pf, spf, d = Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0")

        def _billed(raw_cost):
            c = Decimal(str(raw_cost)) if raw_cost else Decimal("0")
            return float(calculate_tb(c, mf, pf, spf, d)["total_billing"])

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
                    "billed_amount": _billed(s.total_cost_usd),
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
        
        # Fix #2: Compute billed_amount for WhatsApp session detail
        raw_cost = Decimal(str(session.total_cost_usd)) if session.total_cost_usd else Decimal("0")
        billing_svc = BillingService(db)
        config = await billing_svc.get_billing_config(current_user.company_id)
        if config:
            mf = Decimal(str(config.multiplier_factor))
            pf = Decimal(str(config.platform_fee_pct))
            spf = Decimal(str(config.sales_partner_fee_pct))
            d_val = Decimal(str(config.discount_pct))
        else:
            mf, pf, spf, d_val = Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0")
        billed = float(calculate_tb(raw_cost, mf, pf, spf, d_val)["total_billing"])

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
            "billed_amount": billed,
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
        
        # Fix #2: Compute billed totals via TB formula for stats
        billing_svc = BillingService(db)
        config = await billing_svc.get_billing_config(company_id)
        if config:
            mf = Decimal(str(config.multiplier_factor))
            pf = Decimal(str(config.platform_fee_pct))
            spf = Decimal(str(config.sales_partner_fee_pct))
            d = Decimal(str(config.discount_pct))
        else:
            mf, pf, spf, d = Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0")

        voice_raw = sum(float(s.total_cost_usd or 0) for s in voice_sessions)
        whatsapp_raw = sum(float(s.total_cost_usd or 0) for s in whatsapp_sessions)
        voice_billed = float(calculate_tb(Decimal(str(voice_raw)), mf, pf, spf, d)["total_billing"])
        whatsapp_billed = float(calculate_tb(Decimal(str(whatsapp_raw)), mf, pf, spf, d)["total_billing"])

        return {
            "period_days": days,
            "voice": {
                "total_calls": len(voice_sessions),
                "completed_calls": len([s for s in voice_sessions if s.status == "ended"]),
                "total_duration_minutes": sum(s.duration_seconds or 0 for s in voice_sessions) / 60,
                "total_cost_usd": voice_raw,
                "total_billed": voice_billed,
                "by_provider": {
                    "twilio": len([s for s in voice_sessions if s.provider == "twilio"]),
                    "tata_tele": len([s for s in voice_sessions if s.provider == "tata_tele"])
                }
            },
            "whatsapp": {
                "total_sessions": len(whatsapp_sessions),
                "active_sessions": len([s for s in whatsapp_sessions if s.status == "active"]),
                "total_messages": sum(s.message_count for s in whatsapp_sessions),
                "total_cost_usd": whatsapp_raw,
                "total_billed": whatsapp_billed,
                "by_provider": {
                    "twilio": len([s for s in whatsapp_sessions if s.provider == "twilio"]),
                    "tata_tele": len([s for s in whatsapp_sessions if s.provider == "tata_tele"])
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting streaming stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
