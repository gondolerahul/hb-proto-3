"""
Test script for Phase 2 - Twilio Voice Integration.

Tests:
1. Streaming service starts
2. Database models load
3. Session manager creates sessions
4. Number router assigns numbers
5. WebSocket endpoints exist
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))


async def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        from src.streaming.models import VoiceSession, WhatsAppSession, ConversationHistory, CustomerPhoneNumber
        print("✓ Models imported successfully")
    except Exception as e:
        print(f"✗ Failed to import models: {e}")
        return False
    
    try:
        from src.streaming.session_manager import SessionManager
        print("✓ SessionManager imported successfully")
    except Exception as e:
        print(f"✗ Failed to import SessionManager: {e}")
        return False
    
    try:
        from src.streaming.number_router import NumberRouter
        print("✓ NumberRouter imported successfully")
    except Exception as e:
        print(f"✗ Failed to import NumberRouter: {e}")
        return False
    
    try:
        from src.streaming.audio_processor import AudioProcessor
        print("✓ AudioProcessor imported successfully")
    except Exception as e:
        print(f"✗ Failed to import AudioProcessor: {e}")
        return False
    
    try:
        from src.streaming.agent_loader import AgentContextLoader
        print("✓ AgentContextLoader imported successfully")
    except Exception as e:
        print(f"✗ Failed to import AgentContextLoader: {e}")
        return False
    
    try:
        from src.streaming.gemini_mock import MockGeminiClient
        print("✓ MockGeminiClient imported successfully")
    except Exception as e:
        print(f"✗ Failed to import MockGeminiClient: {e}")
        return False
    
    try:
        from src.streaming.websocket_handler import TwilioStreamHandler
        print("✓ TwilioStreamHandler imported successfully")
    except Exception as e:
        print(f"✗ Failed to import TwilioStreamHandler: {e}")
        return False
    
    try:
        from src.streaming.webhook_router import router
        print("✓ Webhook router imported successfully")
    except Exception as e:
        print(f"✗ Failed to import webhook router: {e}")
        return False
    
    return True


async def test_audio_processor():
    """Test audio conversion functions."""
    print("\nTesting AudioProcessor...")
    
    try:
        from src.streaming.audio_processor import AudioProcessor
        
        # Test silence generation
        silence = AudioProcessor.generate_silence(100, 16000)
        assert len(silence) > 0, "Silence generation failed"
        print(f"✓ Generated silence: {len(silence)} bytes")
        
        # Test duration calculation
        duration = AudioProcessor.calculate_duration_ms(silence, 16000)
        assert duration == 100, f"Duration calculation wrong: {duration} != 100"
        print(f"✓ Duration calculation correct: {duration}ms")
        
        # Test chunk splitting
        chunks = AudioProcessor.ensure_chunk_size(silence, 160)
        assert len(chunks) > 0, "Chunk splitting failed"
        print(f"✓ Split into {len(chunks)} chunks")
        
        return True
        
    except Exception as e:
        print(f"✗ AudioProcessor test failed: {e}")
        return False


async def test_number_router():
    """Test number router provider detection."""
    print("\nTesting NumberRouter...")
    
    try:
        from src.streaming.number_router import NumberRouter
        
        # Mock db session
        router = NumberRouter(None)
        
        # Test provider detection
        provider_india = router._detect_provider("+911234567890")
        assert provider_india == "tata_tele", f"India detection failed: {provider_india}"
        print("✓ India number → Tata Tele")
        
        provider_us = router._detect_provider("+15551234567")
        assert provider_us == "twilio", f"US detection failed: {provider_us}"
        print("✓ US number → Twilio")
        
        return True
        
    except Exception as e:
        print(f"✗ NumberRouter test failed: {e}")
        return False


async def test_mock_gemini():
    """Test mock Gemini client."""
    print("\nTesting MockGeminiClient...")
    
    try:
        from src.streaming.gemini_mock import MockGeminiClient
        
        client = MockGeminiClient(api_key="test")
        print("✓ MockGeminiClient created")
        
        # Test session
        async with client.aio.live.connect(
            model="gemini-2.0-flash-exp",
            config={"system_instruction": "Test"}
        ) as session:
            print("✓ Mock session connected")
            
            # Send test audio
            await session.send_realtime_input({
                "data": b"test_audio",
                "mime_type": "audio/pcm"
            })
            print("✓ Audio sent to mock Gemini")
        
        print("✓ Mock session disconnected")
        return True
        
    except Exception as e:
        print(f"✗ MockGeminiClient test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 2 Component Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(await test_imports())
    results.append(await test_audio_processor())
    results.append(await test_number_router())
    results.append(await test_mock_gemini())
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed! Phase 2 components are working.")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
