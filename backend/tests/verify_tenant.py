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
        # 0. Bootstrap App Admin (Need a way to create one, for now let's register and manually update role via SQL or just assume we have a backdoor/script)
        # Since we don't have a CLI, let's register a user and then update their role directly in DB for testing purposes.
        print("Bootstrapping App Admin...")
        reg_payload = {"email": "admin@hb.com", "password": "adminpass", "full_name": "App Admin"}
        await client.post("/api/v1/auth/register", json=reg_payload)
        
        # Login to get token
        login_payload = {"email": "admin@hb.com", "password": "adminpass"}
        resp = await client.post("/api/v1/auth/login", json=login_payload)
        admin_token = resp.json()["access_token"]
        
        # Hack: Update role to app_admin
        # In a real test we'd use a fixture, here we rely on the fact that we just created it.
        # But wait, we can't easily run SQL here without duplicating DB logic.
        # Let's use the `service` layer or just trust that we can add a temporary endpoint or use a backdoor.
        # Actually, let's just use the DB engine to update it.
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE users SET role = 'app_admin' WHERE email = 'admin@hb.com'"))

        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Create Partner
        print("\nCreating Partner...")
        partner_payload = {
            "name": "TechResellers Inc",
            "admin_email": "partner@tech.com",
            "admin_name": "Partner Admin",
            "admin_password": "partnerpass"
        }
        resp = await client.post("/api/v1/partners", json=partner_payload, headers=headers)
        print(f"Create Partner: {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text)
            return
        partner_id = resp.json()["id"]
        print(f"Partner ID: {partner_id}")

        # 2. Login as Partner Admin
        print("\nLogging in as Partner Admin...")
        login_payload = {"email": "partner@tech.com", "password": "partnerpass"}
        resp = await client.post("/api/v1/auth/login", json=login_payload)
        partner_token = resp.json()["access_token"]
        partner_headers = {"Authorization": f"Bearer {partner_token}"}

        # 3. Create Tenant under Partner
        print("\nCreating Tenant under Partner...")
        tenant_payload = {
            "name": "Client Corp",
            "admin_email": "client@corp.com",
            "admin_name": "Client Admin",
            "admin_password": "clientpass"
        }
        resp = await client.post(f"/api/v1/partners/{partner_id}/tenants", json=tenant_payload, headers=partner_headers)
        print(f"Create Tenant: {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text)
            return
        tenant_id = resp.json()["id"]
        print(f"Tenant ID: {tenant_id}")

        # 4. List Tenants (as Partner)
        print("\nListing Tenants...")
        resp = await client.get("/api/v1/tenants", headers=partner_headers)
        print(f"List Tenants: {resp.status_code}")
        tenants = resp.json()
        print(f"Found {len(tenants)} tenants")
        
        # 5. Suspend Tenant
        print("\nSuspending Tenant...")
        update_payload = {"status": "suspended"}
        resp = await client.put(f"/api/v1/tenants/{tenant_id}", json=update_payload, headers=partner_headers)
        print(f"Update Tenant: {resp.status_code}")
        print(f"New Status: {resp.json()['status']}")

if __name__ == "__main__":
    asyncio.run(run_test())
