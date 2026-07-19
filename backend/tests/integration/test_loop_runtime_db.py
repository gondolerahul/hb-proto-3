"""Inc 1 / LOOP+ENV — DB-backed runtime (§17, §20.4, §23.3).

The exit-demo scene: two concurrent runs racing a wallet that can fund only
one → exactly one is admitted (the E3 race, closed by FOR UPDATE holds). Plus
settlement, graceful bounded debt, the heartbeat's rollup/stamp, and the
watchdog flagging a stalled Loop. Self-managed committed fixtures. ``needs_db``.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.models import HoldStatus, LoopRuntime, WalletHold
from src.ai.loop.wallet_holds import (
    place_hold,
    record_graceful_debt,
    settle_hold,
)
from src.billing.credit_service import InsufficientCreditsError

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


async def _mk_company(s: AsyncSession, cid: uuid.UUID, wallet_balance: str) -> None:
    await s.execute(
        text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
             "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
        {"id": str(cid), "n": f"loop-test-{cid.hex[:8]}"},
    )
    # daily_expires_at in the future + daily_credits=0 so get_or_create_wallet
    # does NOT auto-inject the daily free credits (which would inflate balance
    # past our controlled amount and defeat the race test).
    await s.execute(
        text("INSERT INTO credit_wallets (id, company_id, account_model, daily_credits, "
             "daily_expires_at, wallet_balance, wallet_expires_at, subscription_credits, "
             "subscription_bonus_credits, wallet_debt, updated_at) "
             "VALUES (gen_random_uuid(), :c, 'pay_as_you_go', 0, now() + interval '365 days', "
             ":bal, now() + interval '365 days', 0, 0, 0, now())"),
        {"c": str(cid), "bal": wallet_balance},
    )


async def _mk_run(s: AsyncSession, cid: uuid.UUID) -> uuid.UUID:
    ent_id = uuid.uuid4()
    await s.execute(
        text("INSERT INTO hierarchical_entities (id, company_id, version, type, status, name) "
             "VALUES (:e, :c, '1.0.0', 'AGENT', 'ACTIVE', 'runner')"),
        {"e": str(ent_id), "c": str(cid)},
    )
    run_id = uuid.uuid4()
    await s.execute(
        text("INSERT INTO execution_runs (id, company_id, entity_id, status, created_at) "
             "VALUES (:r, :c, :e, 'PENDING', now())"),
        {"r": str(run_id), "c": str(cid), "e": str(ent_id)},
    )
    return run_id


@pytest_asyncio.fixture
async def loop_company():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await _mk_company(s, cid, wallet_balance="0.60")  # funds ~one AGENT hold ($0.05 floor)
        await s.commit()
    try:
        yield cid
    finally:
        async with AsyncSessionLocal() as s:
            for tbl in ("wallet_holds", "budget_envelopes", "loop_runtime",
                        "execution_runs", "signals"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM credit_wallets WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestWalletHolds:
    async def test_admission_and_settlement(self, loop_company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            run_id = await _mk_run(s, loop_company)
            await s.commit()
            hold = await place_hold(s, loop_company, run_id, "AGENT")
            await s.commit()
            assert hold.status == HoldStatus.ACTIVE
            assert hold.amount_held == Decimal("0.0500")

            settled = await settle_hold(s, run_id, Decimal("0.03"))
            await s.commit()
            assert settled.status == HoldStatus.SETTLED
            assert settled.amount_spent == Decimal("0.0300")

    async def test_idempotent_readmission(self, loop_company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            run_id = await _mk_run(s, loop_company)
            await s.commit()
            h1 = await place_hold(s, loop_company, run_id, "AGENT")
            await s.commit()
            h2 = await place_hold(s, loop_company, run_id, "AGENT")  # arq retry
            assert h1.id == h2.id

    async def test_graceful_debt_is_bounded(self, loop_company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            run_id = await _mk_run(s, loop_company)
            await s.commit()
            await place_hold(s, loop_company, run_id, "AGENT")  # hold $0.05
            await s.commit()
            # Overage of $5 is capped at max($1, 5% of $0.05) = $1.
            debt = await record_graceful_debt(s, loop_company, run_id, Decimal("5.00"))
            await s.commit()
            assert debt == Decimal("1.00")
            wd = (await s.execute(
                text("SELECT wallet_debt FROM credit_wallets WHERE company_id = :c"),
                {"c": str(loop_company)})).scalar_one()
            assert Decimal(str(wd)) == Decimal("1.0000")


@pytest.mark.slow
class TestAdmissionRace:
    async def test_two_racers_one_admitted(self, loop_company):
        """The E3 exit-demo: a wallet funding one AGENT hold, two concurrent
        admissions on separate connections → exactly one succeeds."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            # Fund exactly one $0.05 hold: set balance to $0.05.
            await s.execute(
                text("UPDATE credit_wallets SET wallet_balance = 0.05, "
                     "wallet_expires_at = now() + interval '365 days' WHERE company_id = :c"),
                {"c": str(loop_company)})
            run_a = await _mk_run(s, loop_company)
            run_b = await _mk_run(s, loop_company)
            await s.commit()

        async def _try(run_id):
            async with AsyncSessionLocal() as s:
                try:
                    await place_hold(s, loop_company, run_id, "AGENT")
                    await s.commit()
                    return True
                except InsufficientCreditsError:
                    await s.rollback()
                    return False

        results = await asyncio.gather(_try(run_a), _try(run_b))
        assert sum(results) == 1, f"exactly one admission expected, got {results}"

        async with AsyncSessionLocal() as s:
            n = (await s.execute(
                text("SELECT COUNT(*) FROM wallet_holds WHERE company_id = :c AND status = 'ACTIVE'"),
                {"c": str(loop_company)})).scalar_one()
            assert n == 1


class TestHeartbeatWatchdog:
    async def test_heartbeat_seeds_and_stamps(self, loop_company):
        from src.common.database import AsyncSessionLocal
        from src.ai.loop.service import ensure_sheel
        from src.ai.loop.heartbeat import beat_one

        async with AsyncSessionLocal() as s:
            loop = await ensure_sheel(s, loop_company)
            await s.commit()
            loop_id = loop.id

        async with AsyncSessionLocal() as s:
            out = await beat_one(s, None, loop_id, now=datetime.utcnow())
            assert "utilization_pct" in out

        async with AsyncSessionLocal() as s:
            rt = await s.get(LoopRuntime, loop_id)
            assert rt.last_beat_at is not None
            assert rt.consecutive_missed == 0
            assert rt.stats and "spent_usd" in rt.stats

    async def test_watchdog_flags_stalled(self, loop_company):
        from src.common.database import AsyncSessionLocal
        from src.ai.loop.service import ensure_sheel
        from src.ai.loop.watchdog import find_stalled

        async with AsyncSessionLocal() as s:
            loop = await ensure_sheel(s, loop_company)
            rt = await s.get(LoopRuntime, loop.id)
            rt.heartbeat_interval_s = 120
            rt.last_beat_at = datetime.utcnow() - timedelta(seconds=1000)  # > 3×120
            await s.commit()

        async with AsyncSessionLocal() as s:
            stalled = await find_stalled(s, now=datetime.utcnow())
            assert any(r.loop_entity_id == loop.id for r in stalled)
