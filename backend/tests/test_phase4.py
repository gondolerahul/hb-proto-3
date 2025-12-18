import pytest
import asyncio
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.database import Base
from src.auth.models import User, Tenant, Partner
from src.config.service import ConfigService
from src.config.schemas import AIModelCreate
from src.ai.service import AIService
from src.ai.schemas import AgentCreate, ModelConfig, ExecutionCreate
from src.ai.worker import run_execution
from src.billing.service import BillingService
from src.billing.schemas import (
    SystemRateCreate,
    PartnerRateCreate,
)

@pytest.mark.asyncio
async def test_phase4_billing_flow():
    """
    Comprehensive Phase 4 test covering:
    1. System rate creation (App Admin)
    2. Partner rate creation (must be >= system rate)
    3. AI agent execution with automatic ledger entry creation
    4. Usage reporting
    5. Partner earnings calculation
    """
    # Setup DB
    from src.common.database import engine, AsyncSessionLocal
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # 1. Setup Partner, Tenant and User
        partner_id = uuid4()
        partner = Partner(id=partner_id, name="Test Partner")
        db.add(partner)
        
        tenant_id = uuid4()
        tenant = Tenant(id=tenant_id, name="Test Tenant", partner_id=partner_id)
        db.add(tenant)
        
        user = User(
            email=f"test_phase4_{uuid4()}@example.com",
            full_name="Test User",
            hashed_password="hashed_secret",
            tenant_id=tenant_id,
            role="tenant_admin"
        )
        db.add(user)
        await db.commit()

        # 2. Create Billing Service
        billing_service = BillingService(db)

        # 3. Create System Rates (what platform pays to providers)
        print("\n=== Creating System Rates ===")
        input_rate = await billing_service.create_system_rate(
            SystemRateCreate(
                resource_type="text_tokens_input",
                unit="1k_tokens",
                rate=Decimal("0.03"),
                description="GPT-4 input tokens"
            )
        )
        print(f"Created system rate for input: ${input_rate.rate} per {input_rate.unit}")
        
        output_rate = await billing_service.create_system_rate(
            SystemRateCreate(
                resource_type="text_tokens_output",
                unit="1k_tokens",
                rate=Decimal("0.06"),
                description="GPT-4 output tokens"
            )
        )
        print(f"Created system rate for output: ${output_rate.rate} per {output_rate.unit}")
        
        assert input_rate.id is not None
        assert input_rate.rate == Decimal("0.03")
        assert output_rate.rate == Decimal("0.06")

        # 4. Create Partner Rates (what partner charges tenants - must be >= system rate)
        print("\n=== Creating Partner Rates ===")
        partner_input_rate = await billing_service.create_partner_rate(
            PartnerRateCreate(
                partner_id=partner_id,
                system_rate_id=input_rate.id,
                rate=Decimal("0.05")  # Partner markup: $0.05 vs $0.03
            )
        )
        print(f"Created partner rate for input: ${partner_input_rate.rate} per 1k tokens")
        
        partner_output_rate = await billing_service.create_partner_rate(
            PartnerRateCreate(
                partner_id=partner_id,
                system_rate_id=output_rate.id,
                rate=Decimal("0.10")  # Partner markup: $0.10 vs $0.06
            )
        )
        print(f"Created partner rate for output: ${partner_output_rate.rate} per 1k tokens")
        
        assert partner_input_rate.rate == Decimal("0.05")
        assert partner_output_rate.rate == Decimal("0.10")

        # 5. Test validation: Partner rate must be >= system rate
        print("\n=== Testing Rate Validation ===")
        try:
            await billing_service.create_partner_rate(
                PartnerRateCreate(
                    partner_id=partner_id,
                    system_rate_id=input_rate.id,
                    rate=Decimal("0.01")  # Too low! Should fail
                )
            )
            assert False, "Should have raised ValueError for rate < system rate"
        except ValueError as e:
            print(f"✓ Validation passed: {e}")
            assert "must be >=" in str(e)

        # 6. Setup AI Models and Agent
        print("\n=== Setting up AI Agent ===")
        config_service = ConfigService(db)
        model_in = AIModelCreate(
            model_key="gpt-4-test",
            provider="openai",
            model_type="text"
        )
        await config_service.create_ai_model(model_in)

        ai_service = AIService(db)
        agent_in = AgentCreate(
            name="Test Billing Agent",
            role="You are a helpful assistant for testing billing.",
            llm_config=ModelConfig(provider="openai", model="gpt-4-test")
        )
        agent = await ai_service.create_agent(agent_in, tenant_id)
        print(f"Created agent: {agent.name}")
        assert agent.id is not None

        # 7. Trigger Execution (which should auto-create ledger entries)
        print("\n=== Triggering Execution with Billing ===")
        execution_in = ExecutionCreate(
            agent_id=agent.id,
            input_data={"prompt": "Test billing integration"}
        )
        
        # Mock redis for the test
        import unittest.mock
        with unittest.mock.patch('src.ai.service.create_pool') as mock_redis:
            mock_pool = unittest.mock.AsyncMock()
            mock_redis.return_value = mock_pool
            
            execution = await ai_service.trigger_execution(execution_in, tenant_id)
            assert execution.id is not None
            assert execution.status == "pending"
            print(f"Created execution: {execution.id}")

        # 8. Process Execution (simulating worker)
        print("\n=== Processing Execution ===")
        await run_execution(None, str(execution.id))

        # 9. Verify Execution Completed
        await db.refresh(execution)
        assert execution.status == "completed"
        assert execution.result_data is not None
        print(f"✓ Execution completed with tokens: {execution.result_data.get('usage')}")

        # 10. Verify Ledger Entries Were Created
        print("\n=== Verifying Ledger Entries ===")
        ledger_entries = await billing_service.get_ledger_entries(tenant_id=tenant_id)
        
        assert len(ledger_entries) == 2  # One for input tokens, one for output
        print(f"✓ Created {len(ledger_entries)} ledger entries")
        
        for entry in ledger_entries:
            print(f"\nLedger Entry: {entry.resource_type}")
            print(f"  Quantity: {entry.quantity} {entry.unit}")
            print(f"  Platform Cost: ${entry.platform_cost}")
            print(f"  Tenant Cost: ${entry.tenant_cost}")
            print(f"  Partner Commission: ${entry.partner_commission}")
            
            # Verify calculations
            assert entry.tenant_id == tenant_id
            assert entry.partner_id == partner_id
            assert entry.execution_id == execution.id
            assert entry.tenant_cost >= entry.platform_cost
            assert entry.partner_commission == entry.tenant_cost - entry.platform_cost
            
            # Verify cost calculations
            if entry.resource_type == "text_tokens_input":
                # 10 tokens = 0.01 of 1k tokens
                expected_quantity = Decimal("0.01")
                assert entry.quantity == expected_quantity
                assert entry.platform_cost == expected_quantity * Decimal("0.03")  # System rate
                assert entry.tenant_cost == expected_quantity * Decimal("0.05")  # Partner rate
            elif entry.resource_type == "text_tokens_output":
                # 20 tokens = 0.02 of 1k tokens
                expected_quantity = Decimal("0.02")
                assert entry.quantity == expected_quantity
                assert entry.platform_cost == expected_quantity * Decimal("0.06")
                assert entry.tenant_cost == expected_quantity * Decimal("0.10")

        # 11. Test Usage Report
        print("\n=== Testing Usage Report ===")
        now = datetime.utcnow()
        start_date = now - timedelta(hours=1)
        end_date = now + timedelta(hours=1)
        
        usage_report = await billing_service.get_usage_report(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date
        )
        
        print(f"Usage Report for Tenant {tenant_id}:")
        print(f"  Period: {usage_report.period_start} to {usage_report.period_end}")
        print(f"  Total Cost: ${usage_report.total_cost}")
        print(f"  Line Items: {len(usage_report.line_items)}")
        
        assert usage_report.tenant_id == tenant_id
        assert len(usage_report.line_items) == 2
        assert usage_report.total_cost > 0
        
        for line in usage_report.line_items:
            print(f"    - {line.resource_type}: {line.total_quantity} {line.unit} = ${line.total_cost}")

        # 12. Test Partner Earnings Report
        print("\n=== Testing Partner Earnings Report ===")
        earnings_report = await billing_service.get_partner_earnings(
            partner_id=partner_id,
            start_date=start_date,
            end_date=end_date
        )
        
        print(f"Partner Earnings Report for Partner {partner_id}:")
        print(f"  Period: {earnings_report.period_start} to {earnings_report.period_end}")
        print(f"  Total Earnings: ${earnings_report.total_earnings}")
        print(f"  Tenants: {len(earnings_report.tenants)}")
        
        assert earnings_report.partner_id == partner_id
        assert len(earnings_report.tenants) == 1
        assert earnings_report.total_earnings > 0
        
        for tenant_earning in earnings_report.tenants:
            print(f"    - Tenant {tenant_earning.tenant_name}: ${tenant_earning.total_commission}")
            assert tenant_earning.tenant_id == tenant_id

        # 13. Verify Commission Calculation
        print("\n=== Verifying Commission Calculation ===")
        total_commission = sum(entry.partner_commission for entry in ledger_entries)
        print(f"Total partner commission from ledger: ${total_commission}")
        print(f"Total partner earnings from report: ${earnings_report.total_earnings}")
        assert total_commission == earnings_report.total_earnings
        
        # Calculate expected commission
        # Input: 0.01 * (0.05 - 0.03) = 0.0002
        # Output: 0.02 * (0.10 - 0.06) = 0.0008
        # Total: 0.0010
        expected_commission = Decimal("0.001")
        assert abs(total_commission - expected_commission) < Decimal("0.000001")
        print(f"✓ Commission calculation verified: ${total_commission}")

    print("\n" + "="*60)
    print("Phase 4 Test Passed Successfully!")
    print("="*60)
