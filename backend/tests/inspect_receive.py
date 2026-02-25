
import asyncio
import inspect
import sys
try:
    import google.genai as genai
    from google.genai import types
except ImportError:
    print("google.genai not found")
    sys.exit(1)

async def inspect_session():
    client = genai.Client(api_key="TEST")
    # We can inspect the return annotation of connect
    # It returns AsyncIterator[AsyncSession]
    
    # We need to find the definition of AsyncSession
    # It is likely in google.genai.live
    import google.genai.live
    
    AsyncSession = google.genai.live.AsyncSession
    print(f"AsyncSession: {AsyncSession}")
    
    if hasattr(AsyncSession, 'receive'):
        receive_method = AsyncSession.receive
        print(f"receive signature: {inspect.signature(receive_method)}")
        print(f"receive doc: {receive_method.__doc__}")
    else:
        print("No receive method found")

if __name__ == "__main__":
    asyncio.run(inspect_session())
