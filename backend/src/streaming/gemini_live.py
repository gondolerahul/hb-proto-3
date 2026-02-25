"""
Real Gemini Live API Client for production use.

Integrates with google.genai SDK for real-time bidirectional audio streaming.
Replaces gemini_mock.py for production deployment.
"""
import logging
import os
from typing import Dict, Any, Optional, List
import asyncio

logger = logging.getLogger(__name__)

# Try to import google-genai SDK
try:
    import google.genai as genai
    GENAI_AVAILABLE = True
    logger.info("google.genai SDK available")
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google.genai SDK not installed - will fall back to mock")


class GeminiLiveClient:
    """
    Real Gemini Live API client for production streaming.
    
    Uses the google.genai SDK to connect to Gemini 2.0 Flash Exp
    with real-time bidirectional audio streaming.
    """
    
    def __init__(
        self,
        api_key: str,
        system_instruction: str,
        generation_config: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize Gemini Live client.
        
        Args:
            api_key: Gemini API key
            system_instruction: System instruction for the model
            generation_config: Generation parameters (temperature, etc.)
            conversation_history: Previous conversation turns for context
        """
        self.api_key = api_key
        self.system_instruction = system_instruction
        self.generation_config = generation_config or {
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "response_modalities": ["AUDIO"]
        }
        self.conversation_history = conversation_history or []
        
        # Initialize client
        if GENAI_AVAILABLE:
            self.client = genai.Client(api_key=api_key)
            logger.info("Gemini Live client initialized")
        else:
            raise RuntimeError("google.genai SDK not available. Install with: pip install google-genai")
    
    def create_session_config(self) -> Dict[str, Any]:
        """
        Create session configuration for Gemini Live API.
        
        Returns:
            Configuration dict for live.connect()
        """
        # Match the flat structure from user sample and SDK expectations
        config = {
            "response_modalities": ["AUDIO"],
        }
        
        # Add system instruction
        if self.system_instruction:
            config["system_instruction"] = self.system_instruction
            
        # Add speech config if not present in custom generation_config
        if not self.generation_config or "speech_config" not in self.generation_config:
            config["speech_config"] = {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": "Aoede"  # Natural female voice
                    }
                }
            }
        
        # Disable thinking for real-time voice (adds significant latency)
        # thinking_budget=0 prevents the model from generating reasoning text
        # before producing audio, reducing turn latency by 5-10+ seconds
        config["thinking_config"] = {
            "thinking_budget": 0
        }
        
        # Merge custom generation config (taking care not to nest incorrectly if passing flat args)
        if self.generation_config:
            # If generation_config contains known top-level keys, merge them directly
            for key, value in self.generation_config.items():
                config[key] = value
        
        return config
    
    async def connect(self, model: str = "gemini-2.0-flash-exp"):
        """
        Create a live session context manager.
        
        Args:
            model: Model name (default: gemini-2.0-flash-exp)
            
        Returns:
            Async context manager for live session
        """
        config = self.create_session_config()
        
        return self.client.aio.live.connect(
            model=model,
            config=config
        )


class GeminiLiveSession:
    """
    Wrapper for Gemini Live session with helper methods.
    
    Provides a cleaner interface for sending/receiving audio.
    """
    
    def __init__(self, session):
        """
        Initialize session wrapper.
        
        Args:
            session: Underlying Gemini Live session from client.aio.live.connect()
        """
        self.session = session
        self.is_active = True
    
    async def send_audio(self, audio_data: bytes, mime_type: str = "audio/pcm"):
        """
        Send audio chunk to Gemini.
        
        Args:
            audio_data: PCM16 audio bytes (16kHz, 16-bit, mono)
            mime_type: MIME type (default: audio/pcm)
        """
        if not self.is_active:
            logger.warning("Attempted to send audio to inactive session")
            return
        
        try:
            await self.session.send({
                "data": audio_data,
                "mime_type": mime_type
            })
        except Exception as e:
            logger.error(f"Error sending audio to Gemini: {e}")
            raise
    
    async def send_text(self, text: str):
        """
        Send text message to Gemini.
        
        Args:
            text: Text message
        """
        if not self.is_active:
            logger.warning("Attempted to send text to inactive session")
            return
        
        try:
            await self.session.send(text)
        except Exception as e:
            logger.error(f"Error sending text to Gemini: {e}")
            raise
    
    async def receive(self):
        """
        Receive responses from Gemini.
        
        Yields:
            Response objects with audio and/or text
        """
        try:
            async for response in self.session.receive():
                yield response
        except Exception as e:
            logger.error(f"Error receiving from Gemini: {e}")
            self.is_active = False
            raise
    
    async def close(self):
        """Close the session."""
        self.is_active = False
        # Session cleanup handled by context manager


def get_gemini_client(
    api_key: Optional[str] = None,
    system_instruction: str = "",
    generation_config: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> GeminiLiveClient:
    """
    Factory function to create Gemini Live client.
    
    Args:
        api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        system_instruction: System instruction
        generation_config: Generation parameters
        conversation_history: Conversation history for context
        
    Returns:
        GeminiLiveClient instance
        
    Raises:
        ValueError: If API key not provided or in environment
        RuntimeError: If google.genai SDK not available
    """
    # Get API key from env if not provided
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError(
            "Gemini API key required. Set GEMINI_API_KEY environment variable "
            "or pass api_key parameter."
        )
    
    return GeminiLiveClient(
        api_key=api_key,
        system_instruction=system_instruction,
        generation_config=generation_config,
        conversation_history=conversation_history
    )


# Fallback import for backward compatibility
def get_client_with_fallback(
    api_key: Optional[str] = None,
    system_instruction: str = "",
    generation_config: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
):
    """
    Get Gemini client with automatic fallback to mock.
    
    Tries to create real Gemini client, falls back to mock if:
    - google.genai not installed
    - No API key available
    - Any other initialization error
    
    Args:
        api_key: Gemini API key
        system_instruction: System instruction
        generation_config: Generation parameters
        conversation_history: Conversation history
        
    Returns:
        GeminiLiveClient or MockGeminiClient
    """
    try:
        return get_gemini_client(
            api_key=api_key,
            system_instruction=system_instruction,
            generation_config=generation_config,
            conversation_history=conversation_history
        )
    except (ValueError, RuntimeError) as e:
        logger.warning(f"Falling back to mock client: {e}")
        from src.streaming.gemini_mock import MockGeminiClient
        return MockGeminiClient(api_key=api_key or "mock")
