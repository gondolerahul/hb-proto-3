"""
WebSocket Stream Handler for Twilio Media Streams.

Handles:
- WebSocket protocol (connected, start, media, stop events)
- Bidirectional audio streaming
- Integration with Gemini Live API (mock for Phase 2)
- Conversation logging
"""
import logging
import asyncio
import json
import base64
from collections import deque
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.streaming.audio_processor import AudioProcessor
from src.streaming.session_manager import SessionManager
from src.streaming.agent_loader import AgentContextLoader
from src.streaming.gemini_live import get_client_with_fallback
from src.streaming.conversation_logger import ConversationLogger
from src.streaming.models import ConversationHistory, VoiceSession
from src.streaming.number_router import NumberRouter
from src.streaming.usage_logger import VoiceUsageLogger
from src.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class TwilioStreamHandler:
    """
    Handles Twilio Media Stream WebSocket protocol.
    
    Twilio sends events:
    - connected: WebSocket established
    - start: Call started, includes metadata
    - media: Audio chunk (base64-encoded mulaw)
    - stop: Call ended
    
    We respond with:
    - media: Audio chunks to play (base64-encoded mulaw)
    - mark: Markers for synchronization
    """
    
    def __init__(
        self,
        websocket: WebSocket,
        session_id: UUID,
        db: AsyncSession
    ):
        """
        Initialize handler.
        
        Args:
            websocket: FastAPI WebSocket connection
            session_id: VoiceSession UUID
            db: Database session
        """
        self.websocket = websocket
        self.session_id = session_id
        self.db = db
        
        self.session_manager = SessionManager(db)
        self.agent_loader = AgentContextLoader(db)
        self.audio_processor = AudioProcessor()
        self.conversation_logger = ConversationLogger(db)
        
        # State
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.voice_session: Optional[VoiceSession] = None
        self.gemini_session = None
        self.is_running = False
        
        # Audio buffers
        self.incoming_audio_buffer = deque()
        self.outgoing_audio_queue = asyncio.Queue()
        
        # Conversation tracking
        self.turn_number = 0
        
        logger.info(f"TwilioStreamHandler initialized for session {session_id}")
    
    async def handle(self):
        """
        Main handler loop.
        
        Manages WebSocket connection and concurrent tasks:
        - Receive from Twilio
        - Send to Gemini
        - Receive from Gemini
        - Send to Twilio
        """
        try:
            # Load voice session
            self.voice_session = await self.session_manager.get_voice_session(self.session_id)
            if not self.voice_session:
                logger.error(f"Session not found: {self.session_id}")
                await self.websocket.close()
                return
            
            # Load agent context
            agent_context = await self.agent_loader.load_agent_for_session(
                agent_id=self.voice_session.agent_id,
                customer_id=self.voice_session.customer_id,
                channel="voice"
            )
            
            # Initialize Gemini client (real with fallback to mock)
            gemini_client = get_client_with_fallback(
                api_key=agent_context.api_key,
                system_instruction=agent_context.system_instruction,
                generation_config=agent_context.llm_config.get("parameters", {}),
                conversation_history=agent_context.conversation_history
            )
            
            self.is_running = True
            
            # Create Gemini session
            model_name = agent_context.llm_config.get("model", "gemini-2.0-flash-exp")
            logger.info(f"Connecting to Gemini model: {model_name}")
            
            async with await gemini_client.connect(model=model_name) as gemini_session:
                self.gemini_session = gemini_session
                
                logger.info(f"Gemini session established for {self.session_id}")
                
                # Run concurrent tasks
                async with asyncio.TaskGroup() as tg:
                    # Task 1: Receive from Twilio WebSocket
                    tg.create_task(self._receive_from_twilio())
                    
                    # Task 2: Process incoming audio and send to Gemini
                    tg.create_task(self._process_incoming_audio())
                    
                    # Task 3: Receive from Gemini and queue for Twilio
                    tg.create_task(self._receive_from_gemini())
                    
                    # Task 4: Send queued audio to Twilio
                    tg.create_task(self._send_to_twilio())
        
        except Exception as e:
            logger.error(f"Error in stream handler: {e}", exc_info=True)
        
        finally:
            self.is_running = False
            await self._cleanup()
    
    async def _receive_from_twilio(self):
        """
        Receive events from Twilio Media Stream.
        
        Processes connected, start, media, stop events.
        """
        try:
            while self.is_running:
                # Receive message from Twilio
                message = await self.websocket.receive_text()
                event = json.loads(message)
                
                event_type = event.get("event")
                
                if event_type == "connected":
                    logger.info(f"Twilio connected: {event}")
                
                elif event_type == "start":
                    self._handle_start_event(event)
                
                elif event_type == "media":
                    await self._handle_media_event(event)
                
                elif event_type == "stop":
                    logger.info(f"Twilio call stopped: {event}")
                    self.is_running = False
                    break
                
                else:
                    logger.warning(f"Unknown Twilio event: {event_type}")
        
        except Exception as e:
            logger.error(f"Error receiving from Twilio: {e}")
            self.is_running = False
    
    def _handle_start_event(self, event: Dict[str, Any]):
        """
        Handle 'start' event from Twilio.
        
        Extracts metadata and updates session.
        """
        start_data = event.get("start", {})
        self.stream_sid = start_data.get("streamSid")
        self.call_sid = start_data.get("callSid")
        
        logger.info(f"Call started: stream_sid={self.stream_sid}, call_sid={self.call_sid}")
        
        # Update session with stream_sid
        asyncio.create_task(
            self.session_manager.update_voice_session(
                self.session_id,
                {"stream_sid": self.stream_sid, "status": "active"}
            )
        )
    
    async def _handle_media_event(self, event: Dict[str, Any]):
        """
        Handle 'media' event from Twilio.
        
        Extracts audio payload and adds to incoming buffer.
        """
        media_data = event.get("media", {})
        payload = media_data.get("payload")  # Base64-encoded mulaw
        
        if payload:
            # Decode base64
            mulaw_bytes = base64.b64decode(payload)
            
            # Add to buffer (deque for O(1) operations)
            self.incoming_audio_buffer.append(mulaw_bytes)
    
    async def _process_incoming_audio(self):
        """
        Process incoming audio buffer and send to Gemini.
        
        Converts mulaw → PCM16 and streams to Gemini immediately.
        Optimized for minimal latency - no buffering threshold.
        """
        try:
            while self.is_running:
                if self.incoming_audio_buffer:
                    # Get chunk from buffer (O(1) with deque)
                    mulaw_chunk = self.incoming_audio_buffer.popleft()
                    
                    # Convert mulaw → PCM16
                    pcm16_chunk = self.audio_processor.mulaw_to_pcm16(mulaw_chunk)
                    
                    if pcm16_chunk and self.gemini_session:
                        try:
                            audio_payload = {"data": pcm16_chunk, "mime_type": "audio/pcm"}
                            
                            # Use send_realtime_input for lowest latency
                            # (sends as real-time stream, not as a turn)
                            await self.gemini_session.send_realtime_input(audio=audio_payload)
                                
                        except Exception as e:
                            logger.error(f"Error sending audio to Gemini: {e}")
                            break
                else:
                    # No audio available, yield briefly
                    await asyncio.sleep(0.005)
        
        except Exception as e:
            logger.error(f"Error processing incoming audio: {e}")
    
    async def _receive_from_gemini(self):
        """
        Receive responses from Gemini and queue for Twilio.
        
        Converts PCM24 → mulaw and adds to outgoing queue.
        
        Following Google's reference pattern: call receive() per turn in a loop,
        then clear queue after each turn for barge-in support.
        """
        try:
            if not self.gemini_session:
                return
            
            while self.is_running:
                # Get a turn from Gemini - this is an async iterator for one model turn
                turn = self.gemini_session.receive()
                
                async for response in turn:
                    # Extract audio and text from response
                    if hasattr(response, 'server_content') and response.server_content:
                        model_turn = response.server_content.model_turn
                        
                        if model_turn:
                            for part in model_turn.parts:
                                # Text response (log for transcript, fire-and-forget)
                                if part.text:
                                    logger.info(f"Gemini response: {part.text}")
                                    # Fire-and-forget: don't await DB write
                                    asyncio.create_task(
                                        self._log_conversation_turn(
                                            speaker="agent",
                                            content=part.text
                                        )
                                    )
                                
                                # Audio response - send immediately
                                if part.inline_data and part.inline_data.data:
                                    pcm24_audio = part.inline_data.data
                                    
                                    # Convert PCM24 → mulaw
                                    mulaw_audio = self.audio_processor.pcm24_to_mulaw(pcm24_audio)
                                    
                                    # Add to outgoing queue immediately (no_wait for speed)
                                    if mulaw_audio:
                                        self.outgoing_audio_queue.put_nowait(mulaw_audio)
                
                # Clear queue after turn ends (barge-in support)
                # When the model finishes a turn and starts listening again,
                # any remaining queued audio is stale and should be discarded
                # to prevent old audio playing over the user's new input.
                while not self.outgoing_audio_queue.empty():
                    try:
                        self.outgoing_audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
        
        except Exception as e:
            logger.error(f"Error receiving from Gemini: {e}")
    
    async def _send_to_twilio(self):
        """
        Send queued audio to Twilio via WebSocket.
        
        Converts mulaw chunks to base64 and sends as 'media' events.
        """
        try:
            while self.is_running:
                # Wait for audio in queue (with short timeout for responsiveness)
                try:
                    mulaw_chunk = await asyncio.wait_for(
                        self.outgoing_audio_queue.get(),
                        timeout=0.01  # 10ms timeout for fast audio delivery
                    )
                    
                    # Encode to base64
                    payload = base64.b64encode(mulaw_chunk).decode('utf-8')
                    
                    # Send to Twilio/Tata
                    media_message = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": payload
                        }
                    }
                    
                    await self.websocket.send_text(json.dumps(media_message))
                
                except asyncio.TimeoutError:
                    # No audio available, continue
                    continue
        
        except Exception as e:
            logger.error(f"Error sending to Twilio: {e}")
    
    async def _log_conversation_turn(self, speaker: str, content: str):
        """
        Log conversation turn to database using ConversationLogger.
        
        Args:
            speaker: 'customer' or 'agent'
            content: Message content
        """
        self.turn_number += 1
        
        await self.conversation_logger.log_turn(
            company_id=self.voice_session.company_id,
            customer_id=self.voice_session.customer_id,
            agent_id=self.voice_session.agent_id,
            session_id=self.session_id,
            channel="voice",
            turn_number=self.turn_number,
            speaker=speaker,
            content=content,
            message_type="text"
        )
    
    async def _cleanup(self):
        """
        Clean up resources, end session, and log usage/costs.
        """
        logger.info(f"Cleaning up session {self.session_id}")
        
        # Calculate duration
        if self.voice_session:
            duration = int((datetime.utcnow() - self.voice_session.started_at).total_seconds())
            
            try:
                # Use a fresh session for cleanup to ensure it succeeds even if main session is broken
                async with AsyncSessionLocal() as session:
                    # End the voice session
                    cleanup_manager = SessionManager(session)
                    await cleanup_manager.end_voice_session(
                        self.session_id,
                        duration_seconds=duration
                    )
                    
                    # Log usage and calculate costs
                    usage_logger = VoiceUsageLogger(session)
                    total_cost = await usage_logger.log_voice_session_usage(
                        session_id=self.session_id,
                        company_id=self.voice_session.company_id,
                        provider=self.voice_session.provider,
                        duration_seconds=duration,
                        metadata={
                            "agent_id": str(self.voice_session.agent_id),
                            "customer_id": str(self.voice_session.customer_id),
                            "phone_number": self.voice_session.phone_number,
                            "turn_count": self.turn_number
                        }
                    )
                    logger.info(f"Session {self.session_id} total cost: ${total_cost}")
                    
            except Exception as e:
                logger.error(f"Error during cleanup DB update: {e}")
        
        # Close WebSocket
        try:
            await self.websocket.close()
        except:
            pass

class TataStreamHandler(TwilioStreamHandler):
    """
    Handles Tata Tele Media Stream WebSocket protocol.
    
    Since Tata Tele uses a protocol identical to Twilio's Media Stream,
    we inherit from TwilioStreamHandler but override the session discovery
    logic to create a session from the 'start' event metadata.
    """
    
    def __init__(
        self,
        websocket: WebSocket,
        db: AsyncSession
    ):
        """
        Initialize Tata handler. Note that session_id is discovered later.
        """
        self.websocket = websocket
        self.db = db
        
        self.session_manager = SessionManager(db)
        self.number_router = NumberRouter(db)
        self.agent_loader = AgentContextLoader(db)
        self.audio_processor = AudioProcessor()
        self.conversation_logger = ConversationLogger(db)
        
        # State (discovered during 'start' event)
        self.session_id: Optional[UUID] = None
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.voice_session: Optional[VoiceSession] = None
        self.gemini_session = None
        self.is_running = False
        
        # Audio buffers
        self.incoming_audio_buffer = deque()
        self.outgoing_audio_queue = asyncio.Queue()
        
        # Conversation tracking
        self.turn_number = 0
        
        logger.info("TataStreamHandler initialized")

    async def handle_direct(self):
        """
        Main handler loop for direct WebSocket connections from Tata Tele.
        Wait for 'start' event to create session, then proceed like Twilio.
        """
        try:
            self.is_running = True
            
            # Start a background task to receive events until session is created
            while self.is_running and not self.session_id:
                message = await self.websocket.receive_text()
                event = json.loads(message)
                
                event_type = event.get("event")
                
                if event_type == "connected":
                    logger.info("Tata Tele connected")
                
                elif event_type == "start":
                    await self._handle_tata_start_event(event)
                
                elif event_type == "stop":
                    logger.info("Tata Tele call stopped before start")
                    self.is_running = False
                    return
            
            if not self.session_id:
                logger.error("Failed to establish session for Tata Tele call")
                await self.websocket.close()
                return

            # Once session is created, we can proceed with standard Twilio-like tasks
            # Re-use logic from TwilioStreamHandler
            
            # Load agent context
            agent_context = await self.agent_loader.load_agent_for_session(
                agent_id=self.voice_session.agent_id,
                customer_id=self.voice_session.customer_id,
                channel="voice"
            )
            
            # Initialize Gemini client
            gemini_client = get_client_with_fallback(
                api_key=agent_context.api_key,
                system_instruction=agent_context.system_instruction,
                generation_config=agent_context.llm_config.get("parameters", {}),
                conversation_history=agent_context.conversation_history
            )
            
            # Create Gemini session
            model_name = agent_context.llm_config.get("model", "gemini-2.0-flash-exp")
            logger.info(f"Connecting to Gemini model: {model_name}")
            
            async with await gemini_client.connect(model=model_name) as gemini_session:
                self.gemini_session = gemini_session
                logger.info(f"Gemini session established for Tata session {self.session_id}")
                
                # Run concurrent tasks
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._receive_from_twilio()) # Works for Tata too
                    tg.create_task(self._process_incoming_audio())
                    tg.create_task(self._receive_from_gemini())
                    tg.create_task(self._send_to_twilio()) # Works for Tata too
        
        except Exception as e:
            logger.error(f"Error in Tata stream handler: {e}", exc_info=True)
        finally:
            self.is_running = False
            await self._cleanup()

    async def _handle_tata_start_event(self, event: Dict[str, Any]):
        """
        Extract metadata from Tata Tele 'start' event and resolve/create a VoiceSession.
        
        For OUTBOUND calls (campaigns): The campaign executor already created a VoiceSession
        with direction='outbound' and status='initiated'. We look it up by matching the DID 
        (from_number) and resume it — this preserves the campaign's agent_id.
        
        For INBOUND calls: We look up the DID in customer_phone_numbers and create a new session.
        """
        start_data = event.get("start", {})
        self.stream_sid = start_data.get("streamSid")
        self.call_sid = start_data.get("callSid")
        from_number = start_data.get("from")
        to_number = start_data.get("to")
        custom_identifier = start_data.get("customParameters", {}).get("custom_identifier") if start_data.get("customParameters") else None
        
        logger.info(f"Tata start event: call_sid={self.call_sid}, from={from_number}, to={to_number}, custom_id={custom_identifier}")
        
        # ---- Strategy 1: Resume existing outbound session (Campaign flow) ----
        # For outbound calls, the campaign executor has already created a VoiceSession
        # with phone_number=DID, direction='outbound', status='initiated'.
        # The 'from' number in the start event is our DID.
        
        # Try custom_identifier first (if Tata Tele passes it in WebSocket customParameters)
        if custom_identifier:
            try:
                from uuid import UUID as _UUID
                session_id = _UUID(custom_identifier)
                existing_session = await self.session_manager.get_voice_session(session_id)
                if existing_session:
                    logger.info(f"Resuming outbound session via custom_identifier: {session_id}")
                    self.voice_session = existing_session
                    self.session_id = existing_session.id
                    
                    # Update call_sid and status
                    await self.session_manager.update_voice_session(
                        self.session_id,
                        {
                            "call_sid": self.call_sid,
                            "stream_sid": self.stream_sid,
                            "status": "active"
                        }
                    )
                    logger.info(f"Resumed outbound Tata session: {self.session_id} (agent={existing_session.agent_id})")
                    return
            except (ValueError, Exception) as e:
                logger.warning(f"Could not resume via custom_identifier: {e}")
        
        # Try to find a pending outbound session by matching the DID (from_number)
        # The campaign executor creates sessions with phone_number=DID and status='initiated'
        result = await self.db.execute(
            select(VoiceSession).where(
                and_(
                    VoiceSession.phone_number == from_number,
                    VoiceSession.provider == "tata_tele",
                    VoiceSession.direction == "outbound",
                    VoiceSession.status == "initiated",
                    VoiceSession.call_sid.like("pending_%")
                )
            ).order_by(VoiceSession.started_at.desc()).limit(1)
        )
        existing_session = result.scalar_one_or_none()
        
        if existing_session:
            logger.info(f"Found pending outbound session: {existing_session.id} (agent={existing_session.agent_id})")
            self.voice_session = existing_session
            self.session_id = existing_session.id
            
            # Update with real call_sid and mark as active
            await self.session_manager.update_voice_session(
                self.session_id,
                {
                    "call_sid": self.call_sid,
                    "stream_sid": self.stream_sid,
                    "status": "active"
                }
            )
            logger.info(f"Resumed outbound Tata session: {self.session_id}")
            return
        
        # ---- Strategy 2: Inbound call - Find DID in customer_phone_numbers ----
        # For inbound calls, 'to' is our DID. For outbound click-to-call, 
        # 'from' might be our DID. Check both.
        customer_assignment = await self.number_router.find_customer_by_number(to_number)
        
        if not customer_assignment:
            # Try from_number as well (Tata may swap from/to in some flows)
            customer_assignment = await self.number_router.find_customer_by_number(from_number)
        
        if not customer_assignment:
            logger.error(f"No session or customer assignment found for call: from={from_number}, to={to_number}")
            return
            
        # Create new inbound session
        self.voice_session = await self.session_manager.create_voice_session(
            company_id=customer_assignment.company_id,
            customer_id=customer_assignment.customer_id,
            agent_id=customer_assignment.agent_id,
            phone_number=from_number if customer_assignment.phone_number == to_number else to_number,
            provider="tata_tele",
            call_sid=self.call_sid,
            direction="inbound",
            metadata=start_data
        )
        
        self.session_id = self.voice_session.id
        
        # Update session with stream_sid
        await self.session_manager.update_voice_session(
            self.session_id,
            {"stream_sid": self.stream_sid, "status": "active"}
        )
        
        logger.info(f"Created new inbound Tata voice session: {self.session_id} (agent={customer_assignment.agent_id})")
