import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from src.auth.service import create_refresh_token, rotate_refresh_token, verify_refresh_token
from src.auth.models import User, RefreshToken
from src.common.email import EmailService
from src.ai.worker import call_llm

@pytest.mark.asyncio
async def test_refresh_token_flow():
    # Mock DB Session
    db = AsyncMock()
    
    # Mock User
    user_id = uuid.uuid4()
    user = User(id=user_id, email="test@example.com", is_verified=True)
    
    # Mock DB Execute Results
    # For verify_refresh_token, we need to return a RefreshToken and then a User
    mock_token = RefreshToken(
        user_id=user_id,
        token="old_token",
        expires_at=datetime.utcnow() + timedelta(days=7),
        revoked=False
    )
    
    # Setup mock for select(RefreshToken)
    # This is complex with SQLAlchemy async mocks, so we'll mock the service logic parts if possible
    # or just mock the db.execute return values carefully.
    
    # Let's test the service functions directly with mocked DB
    
    # 1. Create Token
    token = await create_refresh_token(db, user_id)
    assert len(token) > 10
    assert db.add.called
    assert db.commit.called
    
    # 2. Rotate Token
    # We need to mock the db.execute to return the old token
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_token
    db.execute.return_value = mock_result
    
    new_token = await rotate_refresh_token(db, "old_token")
    
    assert new_token != "old_token"
    assert mock_token.revoked is True
    assert db.commit.called

@pytest.mark.asyncio
async def test_email_service():
    with patch("smtplib.SMTP") as mock_smtp:
        service = EmailService()
        result = service.send_verification_email("test@example.com", "token123")
        
        assert result is True
        assert mock_smtp.return_value.send_message.called
        assert mock_smtp.return_value.quit.called

@pytest.mark.asyncio
async def test_llm_call_openai():
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from OpenAI"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
        mock_post.return_value = mock_response
        
        result = await call_llm("openai", "gpt-3.5-turbo", "fake-key", "sys", "user")
        
        assert result["output"] == "Hello from OpenAI"
        assert result["usage"]["prompt_tokens"] == 10

@pytest.mark.asyncio
async def test_llm_call_gemini():
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello from Gemini"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}
        }
        mock_post.return_value = mock_response
        
        result = await call_llm("gemini", "gemini-pro", "fake-key", "sys", "user")
        
        assert result["output"] == "Hello from Gemini"
        assert result["usage"]["prompt_tokens"] == 10
