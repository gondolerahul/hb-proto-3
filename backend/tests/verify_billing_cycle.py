import asyncio
from datetime import datetime, timedelta
import sys
from unittest.mock import MagicMock
sys.modules["stripe"] = MagicMock()

from src.main import app
from src.common.database import engine, Base, AsyncSessionLocal
from src.billing.service import BillingService
from src.billing.schemas import SystemRateCreate, PartnerRateCreate
from src.ai.worker import generate_monthly_invoices
from sqlalchemy import text
from httpx import AsyncClient, ASGITransport
from uuid import UUID

async def run_test():
    print("Starting e2e billing verification...")
    # 1. Reset DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        # 2. Setup Identities
        print("Setting up identities...")
        # App Admin
        await client.post("/api/v1/auth/register", json={"email": "admin@hb.com", "password": "pass", "full_name": "Admin"})
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE users SET role = 'app_admin' WHERE email = 'admin@hb.com'"))
        
        # Login Admin
        resp = await client.post("/api/v1/auth/login", json={"email": "admin@hb.com", "password": "pass"})
        if resp.status_code != 200:
            print(f"Admin login failed: {resp.text}")
            return
        admin_token = resp.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create Partner
        resp = await client.post("/api/v1/partners", json={"name": "Partner", "admin_email": "partner@hb.com", "admin_name": "PAdmin", "admin_password": "pass"}, headers=admin_headers)
        if resp.status_code != 200:
            print(f"Create partner failed: {resp.text}")
            return
        partner_id = resp.json()["id"]
        
        # Login Partner
        resp = await client.post("/api/v1/auth/login", json={"email": "partner@hb.com", "password": "pass"})
        partner_token = resp.json()["access_token"]
        partner_headers = {"Authorization": f"Bearer {partner_token}"}
        
        # Create Tenant
        resp = await client.post(f"/api/v1/partners/{partner_id}/tenants", json={"name": "Tenant", "admin_email": "tenant@hb.com", "admin_name": "TAdmin", "admin_password": "pass"}, headers=partner_headers)
        tenant_id = resp.json()["id"]
        print(f"Identities created. Tenant ID: {tenant_id}")

        # 3. Setup Rates
        print("Setting up rates...")
        async with AsyncSessionLocal() as db:
            billing = BillingService(db)
            
            # System Rate
            sr_in = SystemRateCreate(resource_type="gpt-4-input", rate=0.03, unit="1k_tokens", is_active=True)
            sr = await billing.create_system_rate(sr_in)
            sr_id = sr.id
            
            # Partner Rate
            pr_in = PartnerRateCreate(partner_id=UUID(partner_id), system_rate_id=sr_id, rate=0.05, is_active=True)
            pr = await billing.create_partner_rate(pr_in)
            
            # 4. Simulate Usage
            print("Simulating usage...")
            # 100 units * 0.05 = 5.00 Tenant Cost
            await billing.calculate_and_create_ledger_entry(
                tenant_id=UUID(tenant_id),
                partner_id=UUID(partner_id),
                execution_id=None,
                resource_type="gpt-4-input",
                quantity=100,
                unit="1k_tokens",
                entry_metadata="Test usage"
            )
            print("Ledger entry created.")
    
    # 5. Generate Invoice
    print("Triggering invoice generation...")
    # Set fake_today to 40 days in future to be safe into next month
    fake_today = datetime.utcnow() + timedelta(days=40)
    
    await generate_monthly_invoices({}, target_date=fake_today)
    
    # 6. Verify Result
    async with AsyncSessionLocal() as db:
        billing = BillingService(db)
        
        # Verify Invoice
        result = await db.execute(text(f"SELECT * FROM invoices WHERE tenant_id = '{tenant_id}'"))
        invoice = result.fetchone()
        
        if invoice:
            print(f"\nSUCCESS: Invoice generated!")
            print(f"Invoice #: {invoice.invoice_number}")
            print(f"Amount:   ${invoice.total_amount}")
            print(f"Due Date: {invoice.due_date}")
            
            # Basic assertion
            # total_amount is likely Decimal.
            if abs(float(invoice.total_amount) - 5.00) < 0.001:
                print(">>> VERIFICATION PASSED: Amount is correct (5.00) <<<")
            else:
                print(f">>> VERIFICATION FAILED: Amount {invoice.total_amount} != 5.00 <<<")
        else:
            print("\n>>> VERIFICATION FAILED: No invoice found in DB <<<")

if __name__ == "__main__":
    asyncio.run(run_test())
