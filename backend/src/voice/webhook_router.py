"""
Webhook router for Twilio and Tata Tele voice/WhatsApp integrations.

Handles incoming call webhooks and generates appropriate TwiML/JSON responses.
"""
import logging
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import os

from src.database import get_db
from src.voice.session_manager import SessionManager
from src.voice.session_manager import SessionManager
from src.voice.number_router import NumberRouter
from src.common.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/voice", tags=["Voice Webhooks"])


async def get_session_manager(db: AsyncSession = Depends(get_db)) -> SessionManager:
    """Dependency to get SessionManager instance."""
    return SessionManager(db)


async def get_number_router(db: AsyncSession = Depends(get_db)) -> NumberRouter:
    """Dependency to get NumberRouter instance."""
    return NumberRouter(db)


@router.post("/twilio/incoming")
async def twilio_incoming_call(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager),
    number_router: NumberRouter = Depends(get_number_router)
):
    """
    Webhook called by Twilio when an inbound call arrives.
    Must return TwiML to establish Media Stream.
    
    Twilio sends form data with:
    - CallSid: Unique call identifier
    - From: Caller's phone number
    - To: Called number (our Twilio number)
    - CallStatus: Call status (ringing, in-progress, etc.)
    """
    form_data = await request.form()
    
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    call_status = form_data.get("CallStatus")
    
    logger.info(f"Twilio incoming call: {call_sid} from {from_number} to {to_number}")
    
    # 1. Find customer by phone number
    customer_assignment = await number_router.find_customer_by_number(to_number)
    
    if not customer_assignment:
        logger.warning(f"No customer found for number {to_number}")
        # Return TwiML to reject call or play error message
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Sorry, this number is not configured. Please contact support.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
    
    # 2. Create session in database
    session = await session_manager.create_voice_session(
        company_id=customer_assignment.company_id,
        customer_id=customer_assignment.customer_id,
        agent_id=customer_assignment.agent_id,
        phone_number=to_number,
        provider="twilio",
        call_sid=call_sid,
        direction="inbound",
        metadata={
            "from": from_number,
            "to": to_number,
            "call_status": call_status
        }
    )
    
    # 3. Fetch agent to determine greeting strategy (Issue 6: Option A for incoming)
    from src.ai.models import HierarchicalEntity
    agent = await session_manager.db.get(HierarchicalEntity, customer_assignment.agent_id)
    
    greeting_xml = '<Say voice="alice">Please wait while we connect you.</Say>'
    if agent:
        metadata = agent.metadata_extensions or {}
        identity = agent.identity or {}
        
        # Option A: Pre-recorded audio for Incoming Calls
        greeting_audio_url = metadata.get("greeting_audio_url")
        if greeting_audio_url:
            greeting_xml = f'<Play>{greeting_audio_url}</Play>'
        else:
            greeting_text = identity.get("greeting") or metadata.get("greeting_text")
            if greeting_text:
                greeting_xml = f'<Say voice="alice">{greeting_text}</Say>'

    # 4. Generate WebSocket URL for streaming
    streaming_host = settings.STREAMING_HOST or "localhost:8002"
    # Use configured protocol or auto-detect
    ws_protocol = settings.STREAMING_PROTOCOL or ("wss" if "https" in streaming_host or not streaming_host.startswith("localhost") else "ws")
    ws_url = f"{ws_protocol}://{streaming_host}/stream/twilio/{session.id}"
    
    logger.info(f"Created session {session.id}, streaming to {ws_url}")
    
    # 5. Return TwiML with <Connect><Stream>
    # This establishes the WebSocket connection for bidirectional audio
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {greeting_xml}
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
    
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status_callback(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Webhook called by Twilio for call status updates.
    
    Twilio sends:
    - CallSid: Call identifier
    - CallStatus: completed, busy, failed, no-answer, canceled
    - CallDuration: Duration in seconds
    """
    form_data = await request.form()
    
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    call_duration = form_data.get("CallDuration")
    recording_url = form_data.get("RecordingUrl")
    
    logger.info(f"Twilio status callback: {call_sid} status={call_status} duration={call_duration} recording={bool(recording_url)}")
    
    # Find session by call_sid
    session = await session_manager.get_voice_session_by_call_sid(call_sid)
    
    if session:
        # Save recording reference if available
        if recording_url:
            try:
                from src.ai.artifact_models import Artifact
                db = session_manager.db
                # Store the Twilio recording URL as an artifact record (actual audio bytes
                # are hosted by Twilio — we store the metadata and URL)
                recording_artifact = Artifact(
                    company_id=session.company_id,
                    origin="system-generated",
                    file_category="recordings",
                    file_name=f"recording_{call_sid}.wav",
                    file_path=recording_url,  # Twilio-hosted URL
                    mime_type="audio/wav",
                    purpose=f"Call recording for session {session.id}",
                    generated_by="twilio:recording",
                    artifact_metadata={"session_id": str(session.id), "call_sid": call_sid, "source": "twilio"}
                )
                db.add(recording_artifact)
                await db.commit()
            except Exception as e:
                logger.warning(f"Failed to save recording artifact: {e}")
                await db.rollback()
                
        # Update session with final status
        if call_status in ["completed", "busy", "failed", "no-answer", "canceled"]:
            await session_manager.end_voice_session(
                session.id,
                duration_seconds=int(call_duration) if call_duration else None
            )
    
    # Twilio doesn't expect a response, but we return 200 OK
    return {"status": "ok"}


@router.post("/twilio/outbound-twiml")
async def twilio_outbound_twiml(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    TwiML webhook for outbound Twilio calls.
    
    When the campaign executor places an outbound call via Twilio,
    it specifies this URL. Twilio fetches this URL when the call connects.
    
    We return TwiML with <Connect><Stream> to establish a WebSocket
    for bidirectional audio streaming, similar to inbound call handling.
    
    Query params:
    - session_id: VoiceSession UUID (created by campaign executor)
    """
    # Get session_id from query params
    session_id = request.query_params.get("session_id")
    
    if not session_id:
        logger.error("No session_id in outbound TwiML request")
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">An error occurred. Please try again later.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
    
    # Parse form data from Twilio
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    
    logger.info(f"Twilio outbound TwiML: session_id={session_id}, call_sid={call_sid}, from={from_number}, to={to_number}")
    
    try:
        session_uuid = UUID(session_id)
        session = await session_manager.get_voice_session(session_uuid)
        
        if not session:
            logger.error(f"Session not found: {session_id}")
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Sorry, this session is no longer available.</Say>
    <Hangup/>
</Response>"""
            return Response(content=twiml, media_type="application/xml")
        
        # Update session with the real call_sid from Twilio
        if session.call_sid and session.call_sid.startswith("pending_"):
            await session_manager.update_session_call_sid(session.id, call_sid)
        
        # Generate WebSocket URL for streaming
        streaming_host = settings.STREAMING_HOST or "localhost:8002"
        # Use configured protocol or auto-detect
        ws_protocol = settings.STREAMING_PROTOCOL or ("wss" if "https" in streaming_host or not streaming_host.startswith("localhost") else "ws")
        ws_url = f"{ws_protocol}://{streaming_host}/stream/twilio/{session.id}"
        
        logger.info(f"Outbound call connected, streaming to {ws_url}")
        
        # Determine Greeting XML
        from src.ai.models import HierarchicalEntity
        agent = await session_manager.db.get(HierarchicalEntity, session.agent_id)
        
        greeting_xml = ''
        if agent:
            metadata = agent.metadata_extensions or {}
            identity = agent.identity or {}
            
            # Option B: Use TTS for Outgoing Calls
            greeting_text = identity.get("greeting") or metadata.get("greeting_text")
            if greeting_text:
                greeting_xml = f'<Say voice="alice">{greeting_text}</Say>'
        
        # Return TwiML with <Connect><Stream> for bidirectional audio
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {greeting_xml}
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
        
        return Response(content=twiml, media_type="application/xml")
        
    except ValueError as e:
        logger.error(f"Invalid session_id format: {session_id}")
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">An error occurred. Please try again later.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error in outbound TwiML webhook: {e}", exc_info=True)
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">An error occurred. Please try again later.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")


@router.post("/tata/incoming")
async def tata_incoming_call(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager),
    number_router: NumberRouter = Depends(get_number_router)
):
    """
    Webhook called by Tata Tele when inbound call arrives.
    Must return JSON with WebSocket URL (Dynamic Endpoint).
    
    Tata Tele sends JSON with:
    - callId: Unique call identifier
    - fromNumber: Caller's phone number
    - toNumber: Called number
    - status: Call status
    """
    data = await request.json()
    
    call_id = data.get("callId")
    from_number = data.get("fromNumber")
    to_number = data.get("toNumber")
    status = data.get("status")
    custom_identifier = data.get("custom_identifier")
    
    logger.info(f"Tata Tele incoming call: {call_id} from {from_number} to {to_number}, custom_id={custom_identifier}")
    
    # 1. Try to resume existing session (Outbound Campaign)
    if custom_identifier and custom_identifier != "null":
        try:
            session_id = UUID(custom_identifier)
            session = await session_manager.get_voice_session(session_id)
            if session:
                logger.info(f"Resuming existing session {session.id} for outbound campaign")
                
                # Update session with call_sid if it was temporary
                if session.call_sid and session.call_sid.startswith("pending_"):
                    await session_manager.update_session_call_sid(session.id, call_id)
                
                # Generate WebSocket URL
                streaming_host = settings.STREAMING_HOST or "localhost:8002"
                ws_protocol = settings.STREAMING_PROTOCOL or ("wss" if "https" in streaming_host or not streaming_host.startswith("localhost") else "ws")
                ws_url = f"{ws_protocol}://{streaming_host}/stream/tata/{session.id}"
                
                return {
                    "sucess": True,
                    "wss_url": ws_url
                }
        except ValueError:
            logger.warning(f"Invalid custom_identifier format: {custom_identifier}")
        except Exception as e:
            logger.error(f"Error resuming session: {e}")

    # 2. Find context by phone number (Inbound)
    # Check both numbers to see which one is our DID
    customer_assignment = await number_router.find_customer_by_number(to_number)
    
    # If not found by to_number, try from_number (in case of directionality confusion or click-to-call logic)
    if not customer_assignment:
         customer_assignment = await number_router.find_customer_by_number(from_number)

    if not customer_assignment:
        logger.warning(f"No configured number found for call {from_number} -> {to_number}")
        return {
            "sucess": False,
            "error": "Number not configured"
        }
    
    # 3. Create NEW session (Inbound Flow)
    session = await session_manager.create_voice_session(
        company_id=customer_assignment.company_id,
        customer_id=customer_assignment.customer_id,
        agent_id=customer_assignment.agent_id,
        phone_number=from_number if customer_assignment.phone_number == to_number else to_number,
        provider="tata_tele",
        call_sid=call_id,
        direction="inbound",
        metadata=data
    )
    
    # 4. Generate WebSocket URL
    streaming_host = settings.STREAMING_HOST or "localhost:8002"
    ws_protocol = settings.STREAMING_PROTOCOL or ("wss" if "https" in streaming_host or not streaming_host.startswith("localhost") else "ws")
    ws_url = f"{ws_protocol}://{streaming_host}/stream/tata/{session.id}"
    
    logger.info(f"Created new Tata session {session.id}, streaming to {ws_url}")
    
    return {
        "sucess": True,
        "wss_url": ws_url
    }


@router.post("/whatsapp/incoming")
async def whatsapp_incoming_message(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Webhook called by Twilio when WhatsApp message arrives.
    Process message and respond via Gemini.
    """
    from src.voice.whatsapp_handler import WhatsAppHandler
    from twilio.twiml.messaging_response import MessagingResponse
    
    logger.info("Processing Twilio webhook request")
    try:
        form_data = await request.form()
    except Exception as e:
        logger.error(f"Error parsing form data: {e}")
        return Response(content="Error parsing form data", status_code=400)
    
    from_number = form_data.get("From", "")
    to_number = form_data.get("To", "")
    message_body = form_data.get("Body", "")
    media_url = form_data.get("MediaUrl0")
    media_type = form_data.get("MediaContentType0")
    message_sid = form_data.get("MessageSid")
    
    logger.info(f"WhatsApp message (Twilio): {message_sid} from {from_number}")
    
    # Create handler
    handler = WhatsAppHandler(db)
    
    # Process message and get response
    response_text = await handler.handle_incoming_message(
        from_number=from_number,
        to_number=to_number,
        message_body=message_body,
        media_url=media_url,
        media_type=media_type,
        message_sid=message_sid,
        provider="twilio"
    )
    
    # Create TwiML response
    resp = MessagingResponse()
    resp.message(response_text)
    
    return Response(content=str(resp), media_type="application/xml")


@router.post("/tata/whatsapp/incoming")
async def tata_whatsapp_incoming(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Webhook called by Tata Tele for WhatsApp messages.
    """
    from src.voice.whatsapp_handler import WhatsAppHandler
    
    data = await request.json()
    logger.debug(f"Tata Tele WhatsApp payload: {data}")
    
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        
        if not messages:
            return {"status": "ok"} # Just a status notification
            
        message = messages[0]
        from_number = message.get("from") # E.g., "919876543210"
        
        # Tata sends metadata with display_phone_number which is our business number
        # Need to make sure we parse it correctly
        metadata = value.get("metadata", {})
        to_number = metadata.get("display_phone_number") or metadata.get("phone_number_id")
        
        message_id = message.get("id")
        msg_type = message.get("type")
        
        # Extract body based on type
        message_body = ""
        media_url = None
        media_type = None
        
        if msg_type == "text":
            message_body = message.get("text", {}).get("body", "")
        elif msg_type in ["image", "document", "audio", "video"]:
            media_obj = message.get(msg_type, {})
            # Note: For full implementation, we'd fetch media URL using media ID.
            # Assuming caption or placeholder for now.
            message_body = media_obj.get("caption", "[Media Message]")
            media_type = media_obj.get("mime_type")
            # media_url = ... (requires extra API call to get URL)
        
        logger.info(f"WhatsApp message (Tata): {message_id} from {from_number}")
        
        handler = WhatsAppHandler(db)
        
        # Tata handler sends response asynchronously via Messaging Service
        await handler.handle_incoming_message(
            from_number=from_number,
            to_number=to_number,
            message_body=message_body,
            media_url=media_url,
            media_type=media_type,
            message_sid=message_id,
            provider="tata_tele"
        )
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing Tata webhook: {e}", exc_info=True)
        # Always return 200 to Tata/Meta so they don't retry indefinitely on logic errors
        return {"status": "error", "message": str(e)}
