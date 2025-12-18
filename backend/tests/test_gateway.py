import asyncio
import httpx
import time

async def test_gateway():
    print("Testing API Gateway...")
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Test Health/Root (Proxy check)
        try:
            response = await client.get("/")
            print(f"Root endpoint status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Gateway proxying to backend successfully")
            else:
                print(f"❌ Gateway proxy failed: {response.text}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return

        # 2. Test Rate Limiting
        print("\nTesting Rate Limiting...")
        start_time = time.time()
        count = 0
        try:
            # Send 110 requests (limit is 100/min)
            for i in range(110):
                response = await client.get("/")
                if response.status_code == 429:
                    print(f"✅ Rate limit triggered after {count} requests")
                    break
                count += 1
            
            if count >= 110:
                print("❌ Rate limit NOT triggered")
        except Exception as e:
            print(f"❌ Rate limit test error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gateway())
