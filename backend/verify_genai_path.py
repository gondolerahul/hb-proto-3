import asyncio
from uuid import uuid4
from decimal import Decimal
from src.ai.worker import call_llm_unified
from src.common.database import AsyncSessionLocal

async def verify_genai():
    print("Testing call_llm_unified with google-genai...")
    
    # Placeholder config/api_key for testing
    # Note: This will likely fail without a real API key, but we want to see the library call being initialized.
    config = {
        "model_name": "gemini-1.5-flash",
        "temperature": 0.7,
        "max_tokens": 100
    }
    
    try:
        # Using a dummy key to verify the code path
        # In a real scenario, this would be a valid key
        result = await call_llm_unified(config, "System prompt", "User prompt", "DUMMY_KEY")
        print("Result:", result)
    except Exception as e:
        print("Expected Error (since key is dummy):", e)
        if "google-genai" in str(e):
            print("SUCCESS: Code path is using google-genai library.")
        else:
            print("FAILED: Unexpected error or library not used correctly.")

if __name__ == "__main__":
    asyncio.run(verify_genai())
