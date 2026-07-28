"""Voice go-live — the seeder, the shared line, and the one-tenant rule. ``needs_db``.

Three claims, all needing a database:

1. **`seed_pragya` is idempotent by the predicate the resolvers use** — a second
   call must find the first call's entity, not seed a rival that
   `pragya_entity_for`'s `.limit(1)` would then choose between arbitrarily.
2. **The shared line routes to Pragya with no company** — the number says which
   *face*, the caller says which *tenant* (owner decision, 2026-07-26,
   inverting Inc-4 decision 5).
3. **An address belongs to at most one tenant**, enforced by the database, not
   by discipline. That is what makes `company_for_caller`'s `.limit(1)` exact
   rather than a coin flip — and a coin flip there is a cross-tenant
   disclosure read aloud over the phone.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.pragya.channels.routing import (
    PRAGYA_SHARED_LABEL,
    VoiceFace,
    assign_pragya_number,
    assign_shared_pragya_number,
    company_for_caller,
    pragya_entity_for,
    route_for_number,
)
from src.ai.pragya.seed import seed_pragya

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def two_tenants():
    """Two tenants, a user each, and a spare pool number."""
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    a, b = uuid.uuid4(), uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    number = f"9199{uuid.uuid4().int % 10**8:08d}"

    async with AsyncSessionLocal() as s:
        for cid, name in ((a, "voice-a"), (b, "voice-b")):
            await s.execute(text(
                "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
                {"id": str(cid), "n": f"{name}-{cid.hex[:8]}"})
        for uid, cid in ((user_a, a), (user_b, b)):
            await s.execute(text(
                "INSERT INTO users (id, company_id, email, full_name, hashed_password, "
                " role, is_active, created_at, updated_at) "
                "VALUES (:id, :c, :e, :n, 'x', 'company_admin', true, now(), now())"),
                {"id": str(uid), "c": str(cid), "e": f"{uid.hex[:8]}@example.test",
                 "n": f"voice test {uid.hex[:6]}"})
        await s.execute(text(
            "INSERT INTO phone_numbers (id, phone_number, provider, status, "
            " is_active, created_at) "
            "VALUES (:id, :p, 'tata_tele', 'available', true, now())"),
            {"id": str(uuid.uuid4()), "p": number})
        await s.commit()
    try:
        yield {"a": a, "b": b, "user_a": user_a, "user_b": user_b, "number": number}
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM phone_numbers WHERE phone_number = :p"),
                            {"p": number})
            for cid in (a, b):
                await s.execute(text("DELETE FROM channel_bindings WHERE company_id = :c"),
                                {"c": str(cid)})
                await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                                {"c": str(cid)})
                await s.execute(text("DELETE FROM users WHERE company_id = :c"),
                                {"c": str(cid)})
                await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def _bind(s, *, company_id, user_id, address, verified=True):
    # Stored normalised, because that is what `begin_enrollment` does: voice
    # addresses keep digits only, so `+91…` and `91…` are the same binding.
    # A fixture that stored the raw form would be testing a row shape the
    # product never writes.
    from src.ai.inward_auth.models import ChannelKind, normalise_address
    address = normalise_address(ChannelKind.VOICE, address)
    await s.execute(text("""
        INSERT INTO channel_bindings
            (id, company_id, user_id, channel_kind, address, verified_at,
             otp_attempts, created_at)
        VALUES (:id, :c, :u, 'voice', :a, :v, 0, now())
    """), {"id": str(uuid.uuid4()), "c": str(company_id), "u": str(user_id),
           "a": address, "v": datetime.utcnow() if verified else None})


class TestSeeder:
    async def test_it_creates_her_and_the_resolvers_find_her(self, two_tenants):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            entity, created = await seed_pragya(s, two_tenants["a"])
            await s.commit()
            found = await pragya_entity_for(s, two_tenants["a"])

        assert created is True
        assert found is not None and found.id == entity.id

    async def test_it_is_idempotent(self, two_tenants):
        """A rival Pragya would make `pragya_entity_for`'s `.limit(1)` an
        arbitrary choice between two governance blocks."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            first, created_1 = await seed_pragya(s, two_tenants["a"])
            await s.commit()
            second, created_2 = await seed_pragya(s, two_tenants["a"])
            await s.commit()
            count = (await s.execute(text(
                "SELECT COUNT(*) FROM hierarchical_entities WHERE company_id = :c "
                "AND type = 'AGENT' AND deleted_at IS NULL"),
                {"c": str(two_tenants["a"])})).scalar()

        assert created_1 is True and created_2 is False
        assert first.id == second.id
        assert count == 1

    async def test_each_tenant_gets_her_own(self, two_tenants):
        """One per tenant even with a shared number: her governance band and
        memory viewport are per-tenant, and one entity cannot carry a
        governance block for every business at once."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            a, _ = await seed_pragya(s, two_tenants["a"])
            b, _ = await seed_pragya(s, two_tenants["b"])
            await s.commit()
        assert a.id != b.id


class TestSharedLine:
    async def test_it_routes_to_pragya_with_no_company(self, two_tenants):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            await assign_shared_pragya_number(
                s, phone_number=two_tenants["number"],
                owner_company_id=two_tenants["a"])
            await s.commit()
            route = await route_for_number(s, two_tenants["number"])

        assert route.face is VoiceFace.PRAGYA
        assert route.company_id is None, "the caller decides the tenant, not the line"
        assert "resolves from the caller" in route.reason

    async def test_it_needs_no_pragya_entity_up_front(self, two_tenants):
        """Unlike a dedicated number: the shared line serves every tenant, so
        there is no single Pragya it could point at."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            row = await assign_shared_pragya_number(
                s, phone_number=two_tenants["number"],
                owner_company_id=two_tenants["a"])
            await s.commit()
        assert row.label == PRAGYA_SHARED_LABEL
        assert row.agent_id is None

    async def test_a_dedicated_number_still_carries_its_company(self, two_tenants):
        """The per-tenant path is unchanged — both shapes work."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            await seed_pragya(s, two_tenants["a"])
            await s.commit()
            await assign_pragya_number(
                s, company_id=two_tenants["a"], phone_number=two_tenants["number"])
            await s.commit()
            route = await route_for_number(s, two_tenants["number"])

        assert route.face is VoiceFace.PRAGYA
        assert route.company_id == two_tenants["a"]


class TestCallerResolvesTheTenant:
    async def test_a_verified_binding_names_the_company(self, two_tenants):
        from src.common.database import AsyncSessionLocal

        caller = "+919812345678"
        async with AsyncSessionLocal() as s:
            await _bind(s, company_id=two_tenants["a"],
                        user_id=two_tenants["user_a"], address=caller)
            await s.commit()
            resolved = await company_for_caller(s, caller)
        assert resolved == two_tenants["a"]

    async def test_an_unverified_binding_names_nobody(self, two_tenants):
        """An unverified row is a *claim*, not a binding. Letting a claim pick
        a tenant would let anyone nominate whose business they reach."""
        from src.common.database import AsyncSessionLocal

        caller = "+919812345679"
        async with AsyncSessionLocal() as s:
            await _bind(s, company_id=two_tenants["a"],
                        user_id=two_tenants["user_a"], address=caller, verified=False)
            await s.commit()
            assert await company_for_caller(s, caller) is None

    async def test_an_unknown_caller_returns_none(self, two_tenants):
        """A first-class answer, not an error: the voice ceiling already caps
        an unbound caller at T0, so she greets them and reads nothing."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            assert await company_for_caller(s, "+919899999999") is None

    async def test_carrier_format_differences_still_resolve(self, two_tenants):
        """Twilio sends +91…, Tata may send 91… — a routing miss must not look
        like an unknown caller."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            await _bind(s, company_id=two_tenants["b"],
                        user_id=two_tenants["user_b"], address="+919812345680")
            await s.commit()
            assert await company_for_caller(s, "919812345680") == two_tenants["b"]


class TestOneAddressOneTenant:
    """The owner's rule, enforced by the database rather than by discipline."""

    async def test_the_same_address_cannot_be_active_in_two_tenants(self, two_tenants):
        from sqlalchemy.exc import IntegrityError

        from src.common.database import AsyncSessionLocal

        caller = "+919812345681"
        async with AsyncSessionLocal() as s:
            await _bind(s, company_id=two_tenants["a"],
                        user_id=two_tenants["user_a"], address=caller)
            await s.commit()

        with pytest.raises(IntegrityError):
            async with AsyncSessionLocal() as s:
                await _bind(s, company_id=two_tenants["b"],
                            user_id=two_tenants["user_b"], address=caller)
                await s.commit()

    async def test_a_revoked_binding_frees_the_address(self, two_tenants):
        """Somebody who genuinely leaves one business for another must be able
        to register the same phone at the new one."""
        from src.common.database import AsyncSessionLocal

        caller = "+919812345682"
        async with AsyncSessionLocal() as s:
            await _bind(s, company_id=two_tenants["a"],
                        user_id=two_tenants["user_a"], address=caller)
            await s.commit()
            from src.ai.inward_auth.models import ChannelKind, normalise_address
            await s.execute(text(
                "UPDATE channel_bindings SET revoked_at = now() WHERE address = :a"),
                {"a": normalise_address(ChannelKind.VOICE, caller)})
            await s.commit()
            await _bind(s, company_id=two_tenants["b"],
                        user_id=two_tenants["user_b"], address=caller)
            await s.commit()
            assert await company_for_caller(s, caller) == two_tenants["b"]

    async def test_enrollment_refuses_with_a_sentence_not_a_stack_trace(
            self, two_tenants):
        """The index is the guarantee; this check exists so the person
        enrolling gets something they can act on."""
        from src.ai.inward_auth.bindings import begin_enrollment
        from src.common.database import AsyncSessionLocal

        caller = "+919812345683"
        async with AsyncSessionLocal() as s:
            await _bind(s, company_id=two_tenants["a"],
                        user_id=two_tenants["user_a"], address=caller)
            await s.commit()

            result = await begin_enrollment(
                s, company_id=two_tenants["b"], user_id=two_tenants["user_b"],
                channel_kind="voice", address=caller)

        assert result.ok is False
        assert "different company" in result.reason
