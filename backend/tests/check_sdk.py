
import asyncio
import os
try:
    import google.genai as genai
    print("google.genai available")
except ImportError:
    print("google.genai NOT available")
    exit(1)

async def check_session_methods():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set")
        return

    client = genai.Client(api_key=api_key)
    # We can't easily inspect the Live session object without connecting,
    # and connecting requires a real connection.
    # However, we can inspect client.aio.live ... 
    
    print(f"genai version: {genai.__version__}")
    
    # Let's try to see if we can inspect the AsyncSession definition
    # by import
    try:
        from google.genai.live import AsyncSession
        print("Imported AsyncSession")
        print(dir(AsyncSession))
    except ImportError:
        print("Could not import AsyncSession directly")

if __name__ == "__main__":
    asyncio.run(check_session_methods())
