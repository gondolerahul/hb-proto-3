import asyncio
import httpx
import json
from uuid import uuid4

# Configuration
BASE_URL = "http://localhost:8001" # Target Backend API directly
TEST_PHONE_FROM = "14155551234"
TEST_PHONE_TO = "14155556789"  # Business number

async def test_twilio_webhook():
    print("\n--- Testing Twilio Webhook (Text) ---")
    # Prefix is /webhooks/voice defined in router
    url = f"{BASE_URL}/webhooks/voice/whatsapp/incoming"
    
    # Twilio form data
    data = {
        "From": f"whatsapp:+{TEST_PHONE_FROM}",
        "To": f"whatsapp:+{TEST_PHONE_TO}",
        "Body": "Hello, how are you?",
        "MessageSid": f"SM{uuid4().hex}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200 and "<Response>" in response.text:
                print("✅ Twilio Webhook Success")
            else:
                print("❌ Twilio Webhook Failed")
    except Exception as e:
        print(f"❌ Error in Twilio Webhook: {repr(e)}")
        import traceback
        traceback.print_exc()

async def test_tata_webhook():
    print("\n--- Testing Tata Tele Webhook ---")
    url = f"{BASE_URL}/webhooks/voice/tata/whatsapp/incoming"
    
    # Tata JSON payload
    data = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": TEST_PHONE_FROM,
                        "id": f"wamid.{uuid4().hex}",
                        "text": { "body": "Hello from Tata" },
                        "type": "text"
                    }],
                    "metadata": { "display_phone_number": TEST_PHONE_TO }
                }
            }]
        }]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
            
            if response.status_code == 200 and response.json().get("status") == "ok":
                print("✅ Tata Webhook Success")
            else:
                print("❌ Tata Webhook Failed")
    except Exception as e:
        print(f"❌ Error: {e}")

async def test_outbound_message():
    print("\n--- Testing Outbound Message ---")
    url = f"{BASE_URL}/api/v1/messaging/send"
    print(f"Endpoint: {url}")
    
    # Try sending without auth - expect 401
    try:
        data = {
            "to": TEST_PHONE_TO,
            "message": "Hello"
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 401:
                print("✅ Outbound Endpoint Exists (Got 401 Unauthorized as expected)")
            elif response.status_code == 200:
                print("✅ Outbound Message Sent (Unexpectedly open?)")
            else:
                print(f"❌ Outbound Failed: {response.status_code} {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    await test_twilio_webhook()
    await test_tata_webhook()
    await test_outbound_message()

if __name__ == "__main__":
    asyncio.run(main())
