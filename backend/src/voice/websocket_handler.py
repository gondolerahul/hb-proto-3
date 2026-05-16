"""
WebSocket Stream Handler for Twilio / Tata Tele Media Streams.

Architecture:
  BaseStreamHandler  ← shared state, audio pipeline, transcript, cleanup
    ├── TwilioStreamHandler  ← Twilio-specific session lookup + handle()
    └── TataStreamHandler    ← Tata-specific start-event parsing + handle_direct()

Fixes applied (Architectural Evolution Report):
  P0.1  Eliminated 300-line duplication via BaseStreamHandler
  P0.4  Audio recording streamed to temp disk file, not in-memory bytearray
  P1.5  _send_to_twilio no longer busy-loops with 10 ms timeout
  P1.6  incoming_audio_buffer capped at maxlen=200 (~1 sec backpressure)
"""
import logging
import time
import asyncio
import json
import base64
import os
import tempfile
import wave
from collections import deque
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.voice.audio_processor import AudioProcessor
from src.voice.session_manager import SessionManager
from src.voice.agent_loader import AgentContextLoader
from src.voice.live_client_factory import LiveClientFactory
from src.voice.conversation_logger import ConversationLogger
from src.voice.models import ConversationHistory, VoiceSession
from src.voice.number_router import NumberRouter
from src.voice.usage_logger import VoiceUsageLogger
from src.billing.credit_service import CreditService
from src.billing.billing_service import BillingService
from src.database import AsyncSessionLocal
from decimal import Decimal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BaseStreamHandler — shared pipeline for all providers
# ---------------------------------------------------------------------------

class BaseStreamHandler:
    """
    Provider-agnostic bidirectional audio streaming handler.

    Subclasses supply provider-specific session discovery and call the
    shared _setup_live_and_run() once a VoiceSession is resolved.
    """

    def __init__(self, websocket: WebSocket, db: AsyncSession):
        self.websocket = websocket
        self.db = db

        self.session_manager = SessionManager(db)
        self.agent_loader = AgentContextLoader(db)
        self.audio_processor = AudioProcessor()
        self.conversation_logger = ConversationLogger(db)

        # Identity — resolved by subclasses before _setup_live_and_run
        self.session_id: Optional[UUID] = None
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.voice_session: Optional[VoiceSession] = None
        self.gemini_session = None
        self.is_running = False
        self.call_ended_at: Optional[datetime] = None
        self.started_at: Optional[datetime] = None

        # Audio — P1.6: cap incoming buffer to prevent unbounded growth
        # 100 packets ≈ 500ms at 8kHz / 20ms packets — favors responsiveness
        self.incoming_audio_buffer: deque = deque(maxlen=100)
        self.outgoing_audio_queue: asyncio.Queue = asyncio.Queue(maxsize=500)  # ~2.5s at 20ms/frame

        # Conversation tracking
        self.turn_number = 0
        self.outbound_chunk_counter = 0  # Required by Tata Tele spec: media.chunk counter
        self._agent_transcript_buffer = ""
        self._customer_transcript_buffer = ""
        self._last_transcript_time = 0.0

        # Phase 4: Telemetry — TTFB and interruption tracking
        self._user_speech_end_time: Optional[float] = None
        self._ttfb_logged = False

        # P0.4: Recording — streamed to a temp file not a bytearray
        # A 10-min 8k PCM call ≈ 9.6 MB; held entirely in RAM was an OOM risk
        self._recording_tmp_path: Optional[str] = None
        self._recording_tmp_file = None          # raw binary file handle
        self._outbound_recording_buffer = bytearray()   # small rolling buffer for mix

    # ------------------------------------------------------------------
    # Recording helpers (P0.4)
    # ------------------------------------------------------------------

    def _open_recording_file(self):
        """Open a temp file that receives mixed PCM16 (8KHz mono) chunks."""
        try:
            fd, path = tempfile.mkstemp(suffix="_recording.pcm")
            self._recording_tmp_path = path
            self._recording_tmp_file = os.fdopen(fd, "wb")
            logger.info(f"Opened recording temp file: {path}")
        except Exception as e:
            logger.warning(f"Could not open recording temp file: {e}")

    def _write_recording_chunk(self, pcm_chunk: bytes):
        """Append a PCM chunk to the temp file (non-blocking best-effort)."""
        if self._recording_tmp_file:
            try:
                self._recording_tmp_file.write(pcm_chunk)
            except Exception:
                pass

    def _close_recording_file(self) -> Optional[str]:
        """Flush + close the temp file. Returns path, or None on failure."""
        if self._recording_tmp_file:
            try:
                self._recording_tmp_file.flush()
                self._recording_tmp_file.close()
                self._recording_tmp_file = None
            except Exception as e:
                logger.warning(f"Error closing recording file: {e}")
        return self._recording_tmp_path

    async def _save_recording_artifact(self, session: AsyncSession):
        """Convert raw PCM temp file to WAV and persist as an Artifact."""
        pcm_path = self._close_recording_file()
        if not pcm_path:
            return

        wav_path = pcm_path.replace(".pcm", ".wav")
        try:
            with open(pcm_path, "rb") as pcm_f:
                pcm_data = pcm_f.read()

            if not pcm_data:
                return

            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(pcm_data)

            from src.ai.artifact_service import ArtifactService
            art_svc = ArtifactService(session)
            with open(wav_path, "rb") as f:
                await art_svc.save_artifact(
                    company_id=self.voice_session.company_id,
                    file_name=f"recording_{self.session_id}.wav",
                    file_bytes=f.read(),
                    mime_type="audio/wav",
                    file_category="recordings",
                    origin="system-generated",
                    purpose="Call Voice Recording",
                    generated_by="system",
                    extra_metadata={
                        "session_id": str(self.session_id),
                        "call_sid": str(self.call_sid),
                    },
                )
            logger.info(f"Saved recording artifact for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to save recording for session {self.session_id}: {e}")
        finally:
            for p in (pcm_path, wav_path):
                try:
                    os.unlink(p)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Core pipeline — runs once VoiceSession is resolved
    # ------------------------------------------------------------------

    async def _setup_live_and_run(self):
        """
        Load agent context, resolve the configured speech_to_speech model via
        LiveClientFactory, connect to the live session, and launch the pipeline.
        Supports both Gemini Live and Azure OpenAI Realtime providers.
        """
        # Open recording temp file before audio starts flowing
        self._open_recording_file()

        agent_context = await self.agent_loader.load_agent_for_session(
            agent_id=self.voice_session.agent_id,
            customer_id=self.voice_session.customer_id,
            channel="voice",
        )

        # Resolve the correct live streaming client from task defaults
        factory = LiveClientFactory(
            db=self.db,
            company_id=self.voice_session.company_id,
        )
        live_client_or_tuple, provider = await factory.create_client(
            system_instruction=agent_context.system_instruction,
            voice_config=agent_context.voice_config,
            generation_config=agent_context.llm_config.get("parameters", {}),
            conversation_history=agent_context.conversation_history,
        )

        logger.info(f"[{provider}] Connecting live session for session {self.session_id}")

        if provider == "azure_openai":
            # Azure Realtime returns (client, config) tuple
            azure_client, azure_config = live_client_or_tuple
            await azure_client.connect(azure_config)
            self.gemini_session = azure_client
        else:
            gemini_client = live_client_or_tuple
            # connect() returns an async context manager; we must enter it
            # to get the actual live session with .receive()/.send_realtime_input()
            # Phase 3: Pass loaded tools into the Gemini session config
            voice_tools = agent_context.tools or []
            session_cm = await gemini_client.connect(tools=voice_tools)
            self._live_session_cm = session_cm
            self.gemini_session = await session_cm.__aenter__()

        self.started_at = self.voice_session.started_at
            
        # Send greeting trigger immediately
        greeting = (
            "[Call connected. Greet the customer to begin the conversation.]"
            if self.voice_session.direction == "outbound"
            else "[Call connected. Greet the caller to begin the conversation.]"
        )
        try:
            # For gemini-3.1-flash-live-preview, send_client_content is only for
            # seeding history. Must use send_realtime_input for live messages.
            await self.gemini_session.send_realtime_input(text=greeting)
            logger.info(f"Sent greeting trigger for session {self.session_id}")
        except Exception as _ge:
            logger.warning(f"Greeting trigger failed (non-fatal): {_ge}")

        tasks = [
            asyncio.create_task(self._receive_from_provider()),
            asyncio.create_task(self._process_incoming_audio()),
            asyncio.create_task(self._receive_from_live_client()),
            asyncio.create_task(self._send_to_provider()),
            asyncio.create_task(self._flush_transcripts()),
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        except Exception as _te:
            logger.warning(f"Task error during streaming: {_te}")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Close the Gemini Live session context manager
            if hasattr(self, '_live_session_cm') and self._live_session_cm:
                try:
                    await self._live_session_cm.__aexit__(None, None, None)
                except Exception:
                    pass

    # Legacy Azure block removed - using generic BaseLiveClient flow


    # ------------------------------------------------------------------
    # Abstract-ish: provider event reception (overridden by subclasses)
    # ------------------------------------------------------------------

    async def _receive_from_provider(self):
        """
        Receive events from the telephony provider WebSocket.
        Default implementation handles Twilio Media Stream protocol.
        Override for Tata Tele or other providers if protocol differs.
        """
        try:
            while self.is_running:
                message = await self.websocket.receive_text()
                event = json.loads(message)
                event_type = event.get("event")

                if event_type == "connected":
                    logger.info(f"Provider connected: {event}")

                elif event_type == "start":
                    await self._handle_start_event(event)

                elif event_type == "media":
                    await self._handle_media_event(event)

                elif event_type == "stop":
                    logger.info(f"Provider call stopped: {event}")
                    self.call_ended_at = datetime.utcnow()
                    self.is_running = False
                    break

                else:
                    logger.warning(f"Unknown provider event: {event_type}")

        except Exception as e:
            logger.error(f"Error receiving from provider: {e}")
            self.is_running = False

    async def _handle_start_event(self, event: Dict[str, Any]):
        """Handle provider 'start' event — update stream_sid and play ringback."""
        start_data = event.get("start", {})
        self.stream_sid = start_data.get("streamSid")
        self.call_sid = start_data.get("callSid")
        logger.info(f"Call started: stream_sid={self.stream_sid}, call_sid={self.call_sid}")

        await self.session_manager.update_voice_session(
            self.session_id,
            {"stream_sid": self.stream_sid, "status": "active"},
        )
        await self._play_initial_ringback()

    async def _handle_media_event(self, event: Dict[str, Any]):
        """Decode base64 mulaw payload and push to incoming buffer."""
        payload = event.get("media", {}).get("payload")
        if payload:
            mulaw_bytes = base64.b64decode(payload)
            self.incoming_audio_buffer.append(mulaw_bytes)

    # ------------------------------------------------------------------
    # Audio pipeline
    # ------------------------------------------------------------------

    async def _play_initial_ringback(self):
        """Play ringback tone while Gemini connects (reduces perceived latency)."""
        try:
            ringback_mulaw = self.audio_processor.generate_ringback_tone(4)
            chunks = self.audio_processor.ensure_chunk_size(ringback_mulaw)
            for chunk in chunks:
                b64_chunk = base64.b64encode(chunk).decode("ascii")
                await self.websocket.send_text(json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": b64_chunk},
                }))
            logger.info("Sent initial ringback tone.")
        except Exception as e:
            logger.error(f"Failed to send ringback: {e}")

    async def _process_incoming_audio(self):
        """
        Drain incoming buffer → convert mulaw→PCM16 → send to Gemini.
        Also mixes inbound + outbound audio into the recording file (P0.4).
        """
        try:
            while self.is_running:
                if self.incoming_audio_buffer:
                    mulaw_chunk = self.incoming_audio_buffer.popleft()

                    # Recording mix: inbound linear + outbound linear → write to file
                    try:
                        import audioop
                        inbound_lin = audioop.ulaw2lin(mulaw_chunk, 2)
                        mix_len = len(inbound_lin)
                        out_chunk = self._outbound_recording_buffer[:mix_len]
                        del self._outbound_recording_buffer[:mix_len]
                        if len(out_chunk) < mix_len:
                            out_chunk += b"\x00" * (mix_len - len(out_chunk))
                        mixed_chunk = audioop.add(inbound_lin, out_chunk, 2)
                        # P0.4: write to disk, not memory
                        self._write_recording_chunk(mixed_chunk)
                    except Exception:
                        pass

                    pcm16_chunk = self.audio_processor.mulaw_to_pcm16(mulaw_chunk)
                    if pcm16_chunk and self.gemini_session:
                        try:
                            # google-genai SDK v1.71.0+ — use send_realtime_input
                            from google.genai import types as genai_types
                            await self.gemini_session.send_realtime_input(
                                audio=genai_types.Blob(
                                    data=pcm16_chunk,
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )
                        except Exception as e:
                            logger.error(f"Error sending audio to upstream provider: {e}")
                            break
                else:
                    await asyncio.sleep(0.005)

        except Exception as e:
            logger.error(f"Error processing incoming audio: {e}")

    async def _receive_from_live_client(self):
        """
        Receive audio + transcripts from the Live Client.
        Audio goes to outgoing_audio_queue; transcripts go to buffers.
        """
        try:
            if not self.gemini_session:
                return

            while self.is_running:
                async for response in self.gemini_session.receive():
                    if not self.is_running:
                        break

                    # ── 1. Audio PCM from model ──────────────────────────────
                    audio_data = response.data
                    if audio_data:
                        if not getattr(self, "_first_audio_received", False):
                            self._first_audio_received = True
                            # Drain leftover ringback from queue
                            while not self.outgoing_audio_queue.empty():
                                try:
                                    self.outgoing_audio_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    break
                            # Tell Twilio/Tata to stop playing buffered ringback
                            if self.stream_sid:
                                try:
                                    await self.websocket.send_text(
                                        json.dumps({"event": "clear", "streamSid": self.stream_sid})
                                    )
                                except Exception:
                                    pass

                        mulaw_audio = self.audio_processor.pcm24_to_mulaw(audio_data)
                        if mulaw_audio:
                            self.outgoing_audio_queue.put_nowait(mulaw_audio)
                            # Track outbound audio for recording mix
                            try:
                                import audioop
                                self._outbound_recording_buffer.extend(
                                    audioop.ulaw2lin(mulaw_audio, 2)
                                )
                            except Exception:
                                pass

                    # ── 2. Transcription & Interruption ───────────────────────
                    if response.server_content:
                        sc = response.server_content

                        # ── 2a. Interruption signal ─────────────────────────
                        # When the user speaks while the model is generating,
                        # Gemini cancels generation and sends interrupted=True.
                        # We MUST flush our local audio buffers immediately.
                        if getattr(sc, 'interrupted', False):
                            logger.info(f"[INTERRUPT] Gemini signaled interruption for session {self.session_id}")
                            await self._handle_interruption()

                        output_transcript = getattr(sc, "output_transcription", None)
                        if output_transcript and getattr(output_transcript, "text", None):
                            text = output_transcript.text.strip()
                            if text:
                                self._agent_transcript_buffer += text + " "
                                self._last_transcript_time = time.time()

                        input_transcript = getattr(sc, "input_transcription", None)
                        if input_transcript and getattr(input_transcript, "text", None):
                            text = input_transcript.text.strip()
                            if text:
                                self._customer_transcript_buffer += text + " "
                                self._last_transcript_time = time.time()
                                # Phase 4: Track when user stops speaking for TTFB
                                self._user_speech_end_time = time.time()
                                self._ttfb_logged = False

                        if response.text:
                            logger.info(f"Gemini text response: {response.text}")

                    # ── 3. Tool / Function Calls ──────────────────────────────
                    if hasattr(response, 'tool_call') and response.tool_call:
                        asyncio.create_task(self._handle_tool_call(response.tool_call))

                if not self.is_running:
                    break

        except asyncio.CancelledError:
            logger.info(f"Live client receive task cancelled for session {self.session_id}")
        except Exception as e:
            logger.error(f"Error receiving from Live client: {e}", exc_info=True)
            self.is_running = False

    async def _handle_interruption(self):
        """
        React to Gemini's interruption signal.

        1. Drain the outgoing audio queue (discard stale audio)
        2. Send a Twilio/Tata 'clear' event to flush their playback buffer
        3. Clear the outbound recording buffer

        This eliminates the "ghost speaking" effect where the agent
        continues playing pre-buffered audio after being interrupted.
        """
        # 1. Drain outgoing audio queue
        drained = 0
        while not self.outgoing_audio_queue.empty():
            try:
                self.outgoing_audio_queue.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break

        # 2. Send 'clear' to telephony provider to flush their playback buffer
        if self.stream_sid:
            try:
                await self.websocket.send_text(
                    json.dumps({"event": "clear", "streamSid": self.stream_sid})
                )
            except Exception as e:
                logger.warning(f"Failed to send clear event: {e}")

        # 3. Clear outbound recording buffer
        self._outbound_recording_buffer.clear()

        # Phase 4: Log interrupt latency
        if self._last_transcript_time > 0:
            interrupt_latency_ms = int((time.time() - self._last_transcript_time) * 1000)
            logger.info(f"[PERF] Interrupt response time: {interrupt_latency_ms}ms, "
                        f"drained {drained} audio chunks")
        else:
            logger.info(f"[INTERRUPT] Drained {drained} audio chunks, sent clear to provider")

    async def _handle_tool_call(self, tool_call):
        """
        Execute a tool call from Gemini and return the result to the session.

        Gemini Live API supports function calling: the model can invoke tools
        registered in the session config, and this handler executes them
        via the existing ToolRegistry/ToolExecutor infrastructure.

        CRITICAL: Each FunctionResponse MUST include the `id` from the
        corresponding FunctionCall — otherwise the API rejects it and
        Gemini hangs waiting for the response (causing long silences).
        """
        from src.ai.tool_executor import ToolExecutor

        # Preserve original FunctionCall objects for their `id` field
        original_fcs = list(tool_call.function_calls)

        function_calls = []
        for fc in original_fcs:
            args = dict(fc.args) if fc.args else {}

            # Voice context: strip email_address from email tools.
            # The LLM often invents fake sender addresses (e.g. "customer.email@example.com")
            # which causes the connection lookup to fail. Removing it forces the
            # tool to use the company's default email connection.
            if fc.name in ("email_send", "email_draft") and "email_address" in args:
                logger.info(f"[TOOL] Stripping LLM-provided email_address='{args['email_address']}' "
                            f"from {fc.name} — will use company default")
                del args["email_address"]

            function_calls.append({
                "name": fc.name,
                "args": args,
            })

        logger.info(f"Executing {len(function_calls)} tool call(s): "
                    f"{[c['name'] for c in function_calls]}")

        extra_context = {
            "company_id": str(self.voice_session.company_id),
            "user_id": str(self.voice_session.customer_id),
        }

        results = await ToolExecutor.execute_from_function_calls(
            function_calls, extra_context=extra_context
        )

        # Log tool results for observability
        for fc_dict, result in zip(function_calls, results):
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"[TOOL] {fc_dict['name']} → {status} ({result.latency_ms}ms)")

        # Send results back to Gemini so it can continue the conversation
        try:
            from google.genai import types as genai_types

            function_responses = []
            for orig_fc, fc_dict, result in zip(original_fcs, function_calls, results):
                # The `id` from the original FunctionCall MUST be included
                # in the FunctionResponse — this is how Gemini correlates
                # the response with the request.
                fc_id = getattr(orig_fc, 'id', None)
                function_responses.append(
                    genai_types.FunctionResponse(
                        id=fc_id,
                        name=fc_dict["name"],
                        response={"output": result.output, "success": result.success},
                    )
                )

            # Use send_tool_response() — the dedicated SDK method for
            # returning function call results.
            await self.gemini_session.send_tool_response(
                function_responses=function_responses,
            )
            logger.info(f"Sent {len(function_responses)} tool response(s) back to Gemini "
                        f"(ids={[getattr(fc, 'id', None) for fc in original_fcs]})")
        except Exception as e:
            logger.error(f"Failed to send tool response to Gemini: {e}")

    async def _send_to_provider(self):
        """
        Send audio to telephony provider.

        Sends mulaw chunks directly as they arrive from the outgoing queue.
        The queue itself provides sufficient buffering; an additional jitter
        buffer was removed because it introduced audio gaps after interruption
        flushes and at the start of each new agent response.
        Phase 4: Added TTFB tracking.
        """
        try:
            while self.is_running:
                try:
                    # Block until audio is enqueued; wake on cancellation
                    mulaw_chunk = await self.outgoing_audio_queue.get()
                except asyncio.CancelledError:
                    break

                # Phase 4: TTFB tracking — time from user speech end to first audio out
                if self._user_speech_end_time and not self._ttfb_logged:
                    ttfb_ms = int((time.time() - self._user_speech_end_time) * 1000)
                    logger.info(f"[PERF] TTFB: {ttfb_ms}ms for session {self.session_id}")
                    self._ttfb_logged = True

                self.outbound_chunk_counter += 1
                payload = base64.b64encode(mulaw_chunk).decode("utf-8")
                await self.websocket.send_text(json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {
                        "payload": payload,
                        "chunk": self.outbound_chunk_counter,
                    },
                }))

        except Exception as e:
            logger.error(f"Error sending to provider: {e}")

    async def _flush_transcripts(self):
        """Flush transcript buffers every 0.5s after 1s of silence."""
        try:
            while self.is_running:
                await asyncio.sleep(0.5)
                if time.time() - self._last_transcript_time > 1.0:
                    if self._agent_transcript_buffer:
                        t = self._agent_transcript_buffer.strip()
                        self._agent_transcript_buffer = ""
                        asyncio.create_task(
                            self._log_conversation_turn("agent", t, "transcription")
                        )
                    if self._customer_transcript_buffer:
                        t = self._customer_transcript_buffer.strip()
                        self._customer_transcript_buffer = ""
                        asyncio.create_task(
                            self._log_conversation_turn("customer", t, "transcription")
                        )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error flushing transcripts: {e}")

    # ------------------------------------------------------------------
    # Logging — isolated sessions to avoid concurrent-commit errors
    # ------------------------------------------------------------------

    async def _log_conversation_turn(self, speaker: str, content: str, msg_type: str = "text"):
        """
        Log one conversation turn in an isolated DB session.
        (Shared self.db causes PendingRollbackError under concurrent async tasks.)
        """
        self.turn_number += 1
        turn = self.turn_number
        try:
            async with AsyncSessionLocal() as _session:
                _logger = ConversationLogger(_session)
                await _logger.log_turn(
                    company_id=self.voice_session.company_id,
                    customer_id=self.voice_session.customer_id,
                    agent_id=self.voice_session.agent_id,
                    session_id=self.session_id,
                    channel="voice",
                    turn_number=turn,
                    speaker=speaker,
                    content=content,
                    message_type=msg_type,
                )
        except Exception as _e:
            logger.warning(f"Failed to log turn {turn} for session {self.session_id}: {_e}")

    # ------------------------------------------------------------------
    # Cleanup — shared across both providers
    # ------------------------------------------------------------------

    async def _cleanup(self):
        """End session, persist recording, log usage, deduct credits."""
        logger.info(f"Cleaning up session {self.session_id}")

        if self.voice_session and self.started_at:
            end_time = self.call_ended_at or datetime.utcnow()
            duration = int((end_time - self.started_at).total_seconds())

            try:
                async with AsyncSessionLocal() as session:
                    # Export transcript
                    try:
                        convo_log = await ConversationLogger(session).export_transcript_json(
                            self.session_id
                        )
                    except Exception:
                        convo_log = []

                    # End session
                    await SessionManager(session).end_voice_session(
                        self.session_id,
                        duration_seconds=duration,
                        conversation_log=convo_log,
                    )

                    # Persist recording artifact (P0.4)
                    await self._save_recording_artifact(session)

                    # Usage + billing
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
                            "turn_count": self.turn_number,
                        },
                    )
                    logger.info(f"Session {self.session_id} total cost: ${total_cost}")

                    if total_cost and total_cost > 0:
                        cost_decimal = Decimal(str(total_cost))

                        # Fix #1: Apply TB formula before credit deduction
                        # (matches the pattern in worker.py execute_run)
                        try:
                            from src.billing.billing_service import calculate_tb
                            billing_svc = BillingService(session)
                            config = await billing_svc.get_billing_config(
                                self.voice_session.company_id
                            )
                            if not config:
                                mf, pf, spf, d = Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0")
                            else:
                                mf = Decimal(str(config.multiplier_factor))
                                pf = Decimal(str(config.platform_fee_pct))
                                spf = Decimal(str(config.sales_partner_fee_pct))
                                d = Decimal(str(config.discount_pct))

                            tb_result = calculate_tb(cost_decimal, mf, pf, spf, d)
                            billed_amount = tb_result["total_billing"]
                            logger.info(
                                f"Voice TB formula: raw=${cost_decimal} → billed=${billed_amount} "
                                f"(mf={mf}, pf={pf}, spf={spf}, d={d})"
                            )
                        except Exception as tb_err:
                            logger.warning(f"TB formula failed, falling back to raw cost: {tb_err}")
                            billed_amount = cost_decimal

                        try:
                            await CreditService(session).consume(
                                company_id=self.voice_session.company_id,
                                amount=billed_amount,
                            )
                            logger.info(
                                f"Voice credits deducted: ${billed_amount} "
                                f"(raw: ${cost_decimal})"
                            )
                        except Exception as ce:
                            logger.warning(f"Credit deduction failed: {ce}")

                        # Fix #7: Pass event_category="telephony" so charges
                        # appear in the correct report column
                        try:
                            duration_minutes = Decimal(str(duration)) / Decimal("60")
                            await BillingService(session).record_billing_event(
                                company_id=self.voice_session.company_id,
                                base_cost=cost_decimal,
                                grouping_type="agent",
                                grouping_value=str(self.voice_session.agent_id),
                                telephony_out_minutes=(
                                    duration_minutes
                                    if self.voice_session.direction == "outbound"
                                    else Decimal("0")
                                ),
                                telephony_in_minutes=(
                                    duration_minutes
                                    if self.voice_session.direction == "inbound"
                                    else Decimal("0")
                                ),
                                event_category="telephony",
                            )
                        except Exception as be:
                            logger.warning(f"Billing event recording failed: {be}")

                # --- Post-call: update lead queue if this was a CRM-driven call ---
                try:
                    if self.voice_session and self.session_id:
                        await self._update_lead_queue_post_call(session, duration)
                except Exception as lq_err:
                    logger.warning(f"Lead queue post-call update failed: {lq_err}")

            except Exception as e:
                logger.error(f"Error during cleanup DB update: {e}")

        # Close WebSocket
        try:
            await self.websocket.close()
        except Exception:
            pass

    async def _update_lead_queue_post_call(self, db_session, duration: int) -> None:
        """
        Update the lead_queue entry linked to this voice session.

        Called after call cleanup. Marks the lead as completed with
        call outcome data so the CRM can be updated.
        """
        try:
            from src.ai.lead_queue_service import LeadQueueService

            queue_svc = LeadQueueService(db_session)
            entry = await queue_svc.get_by_voice_session(self.session_id)

            if not entry:
                return  # Not a CRM-driven call, nothing to do

            # Build call outcome from session data
            call_outcome = {
                "status": "completed",
                "duration_seconds": duration,
                "turn_count": self.turn_number,
                "phone": self.voice_session.phone_number if self.voice_session else "",
            }

            # Extract transcript if available
            if hasattr(self, 'conversation_logger') and self.conversation_logger:
                try:
                    transcript = self.conversation_logger.get_transcript_text()
                    if transcript:
                        call_outcome["transcript_preview"] = transcript[:2000]
                except Exception:
                    pass

            await queue_svc.mark_completed(entry.id, call_outcome)
            logger.info(
                f"[LeadQueue] Post-call update: lead {entry.lead_id} "
                f"completed (duration={duration}s, turns={self.turn_number})"
            )

        except ImportError:
            pass  # lead_queue_model not available — skip silently
        except Exception as e:
            logger.warning(f"[LeadQueue] Post-call update error: {e}")


# ---------------------------------------------------------------------------
# TwilioStreamHandler — provider-specific session discovery
# ---------------------------------------------------------------------------

class TwilioStreamHandler(BaseStreamHandler):
    """
    Handles Twilio Media Stream WebSocket protocol.

    Resolves VoiceSession from session_id passed via URL parameter,
    then delegates the full audio pipeline to BaseStreamHandler.
    """

    def __init__(self, websocket: WebSocket, session_id: UUID, db: AsyncSession):
        super().__init__(websocket, db)
        self.session_id = session_id

    async def handle(self):
        """Main entry-point for Twilio WebSocket connections."""
        try:
            self.voice_session = await self.session_manager.get_voice_session(self.session_id)
            if not self.voice_session:
                logger.error(f"Voice session not found: {self.session_id}")
                await self.websocket.close()
                return

            self.is_running = True
            await self._setup_live_and_run()

        except Exception as e:
            logger.error(f"Error in Twilio stream handler: {e}", exc_info=True)
        finally:
            self.is_running = False
            await self._cleanup()


# ---------------------------------------------------------------------------
# TataStreamHandler — Tata Tele-specific session discovery
# ---------------------------------------------------------------------------

class TataStreamHandler(BaseStreamHandler):
    """
    Handles Tata Tele Media Stream WebSocket protocol.

    Tata Tele uses an identical wire protocol to Twilio's Media Streams,
    but the VoiceSession is resolved from the 'start' event payload rather
    than a URL parameter. Everything else is inherited from BaseStreamHandler.
    """

    def __init__(self, websocket: WebSocket, db: AsyncSession):
        super().__init__(websocket, db)
        self.number_router = NumberRouter(db)

    async def handle_direct(self):
        """Main entry-point for Tata Tele WebSocket connections."""
        try:
            self.is_running = True

            # Wait for 'start' event to discover/create VoiceSession
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

            await self._play_initial_ringback()
            await self._setup_live_and_run()

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

        For INBOUND calls: We look up the DID in customer_phone_numbers and create a session.
        """
        start_data = event.get("start", {})
        self.stream_sid = start_data.get("streamSid")
        self.call_sid = start_data.get("callSid")
        from_number = start_data.get("from")
        to_number = start_data.get("to")
        custom_identifier = (
            start_data.get("customParameters", {}).get("custom_identifier")
            if start_data.get("customParameters")
            else None
        )

        logger.info(
            f"Tata start event: call_sid={self.call_sid}, from={from_number}, "
            f"to={to_number}, custom_id={custom_identifier}"
        )

        # ── Strategy 1: Resume via custom_identifier (campaign flow) ─────────
        if custom_identifier:
            try:
                from uuid import UUID as _UUID
                session_id = _UUID(custom_identifier)
                existing_session = await self.session_manager.get_voice_session(session_id)
                if existing_session:
                    logger.info(f"Resuming outbound session via custom_identifier: {session_id}")
                    self.voice_session = existing_session
                    self.session_id = existing_session.id
                    await self.session_manager.update_voice_session(
                        self.session_id,
                        {"call_sid": self.call_sid, "stream_sid": self.stream_sid, "status": "active"},
                    )
                    return
            except Exception as e:
                logger.warning(f"Could not resume via custom_identifier: {e}")

        # ── Strategy 2: Resume pending outbound by DID ────────────────────────
        result = await self.db.execute(
            select(VoiceSession).where(
                and_(
                    VoiceSession.phone_number == from_number,
                    VoiceSession.provider == "tata_tele",
                    VoiceSession.direction == "outbound",
                    VoiceSession.status == "initiated",
                    VoiceSession.call_sid.like("pending_%"),
                )
            ).order_by(VoiceSession.started_at.desc()).limit(1)
        )
        existing_session = result.scalar_one_or_none()

        if existing_session:
            logger.info(f"Found pending outbound session: {existing_session.id}")
            self.voice_session = existing_session
            self.session_id = existing_session.id
            await self.session_manager.update_voice_session(
                self.session_id,
                {"call_sid": self.call_sid, "stream_sid": self.stream_sid, "status": "active"},
            )
            return

        # ── Strategy 3: Inbound call — resolve DID → customer assignment ─────
        customer_assignment = await self.number_router.find_customer_by_number(to_number)
        if not customer_assignment:
            customer_assignment = await self.number_router.find_customer_by_number(from_number)

        if not customer_assignment:
            logger.error(
                f"No session or customer for Tata call: from={from_number}, to={to_number}"
            )
            return

        # If the phone number is assigned to an agent but not a specific customer
        # (customer_id is NULL), generate a deterministic UUID from the caller's
        # phone number so the NOT NULL constraint on voice_sessions is satisfied.
        from uuid import uuid5, NAMESPACE_DNS as _NS
        resolved_customer_id = (
            customer_assignment.customer_id
            or uuid5(_NS, f"caller:{from_number}")
        )

        self.voice_session = await self.session_manager.create_voice_session(
            company_id=customer_assignment.company_id,
            customer_id=resolved_customer_id,
            agent_id=customer_assignment.agent_id,
            phone_number=(
                from_number
                if customer_assignment.phone_number == to_number
                else to_number
            ),
            provider="tata_tele",
            call_sid=self.call_sid,
            direction="inbound",
            metadata=start_data,
        )
        self.session_id = self.voice_session.id
        await self.session_manager.update_voice_session(
            self.session_id,
            {"stream_sid": self.stream_sid, "status": "active"},
        )
        logger.info(f"Created inbound Tata session: {self.session_id}")
