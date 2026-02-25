
import asyncio
import inspect
import sys

try:
    import google.genai as genai
    print(f"Version: {genai.__version__}")
except ImportError:
    print("google.genai not found")
    sys.exit(1)

try:
    # Try to find the AsyncSession class
    # It might be in google.genai._internal.live or similar
    # But usually exposed or accessible via return type annotation
    
    # Let's look at client.aio.live.connect
    client = genai.Client(api_key="MUST_BE_PROVIDED_BUT_WE_ONLY_INSPECT")
    connect_method = client.aio.live.connect
    print(f"Connect method: {connect_method}")
    print(f"Connect signature: {inspect.signature(connect_method)}")
    
    # We can try to import AsyncSession directly if we guess the path
    # based on typical structure
    # Try google.genai.live
    import google.genai.live as live_module
    print("Imported google.genai.live")
    
    if hasattr(live_module, 'AsyncSession'):
        session_cls = live_module.AsyncSession
        print(f"Found AsyncSession class: {session_cls}")
        if hasattr(session_cls, 'send'):
            print(f"AsyncSession.send signature: {inspect.signature(session_cls.send)}")
        else:
            print("AsyncSession has no send method??")
            print(dir(session_cls))
            
    else:
        print("AsyncSession not found in google.genai.live")
        print(dir(live_module))

except Exception as e:
    print(f"Error inspecting: {e}")
