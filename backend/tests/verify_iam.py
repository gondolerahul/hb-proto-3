import asyncio
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.common.database import engine, Base

async def run_test():
    # Reset DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register
        print("Testing Registration...")
        reg_payload = {
            "email": "test@example.com",
            "password": "strongpassword123",
            "full_name": "Test User"
        }
        response = await client.post("/api/v1/auth/register", json=reg_payload)
        print(f"Register Response: {response.status_code}")
        if response.status_code != 200:
            print(response.text)
            return
        user_data = response.json()
        print(f"User Created: {user_data['email']} (Tenant: {user_data['tenant_id']})")

        # 2. Login
        print("\nTesting Login...")
        login_payload = {
            "email": "test@example.com",
            "password": "strongpassword123"
        }
        response = await client.post("/api/v1/auth/login", json=login_payload)
        print(f"Login Response: {response.status_code}")
        if response.status_code != 200:
            print(response.text)
            return
        token_data = response.json()
        access_token = token_data['access_token']
        print(f"Token Received: {access_token[:20]}...")

        # 3. Test Protected Route (Me)
        print("\nTesting Protected Route (/auth/me)...")
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get("/api/v1/auth/me", headers=headers)
        print(f"Me Response: {response.status_code}")
        if response.status_code != 200:
            print(response.text)
            return
        print(f"User: {response.json()['email']}")

        # 4. Test RBAC (Admin Only) - Should Fail
        print("\nTesting RBAC (/auth/admin-only) - Expecting 403...")
        response = await client.get("/api/v1/auth/admin-only", headers=headers)
        print(f"Admin Response: {response.status_code}")
        if response.status_code == 403:
            print("Success: Access Denied as expected.")
        else:
            print(f"Failed: Unexpected status code {response.status_code}")

if __name__ == "__main__":
    asyncio.run(run_test())
