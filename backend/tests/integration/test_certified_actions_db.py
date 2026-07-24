"""VG-05 — certified actions on the REST path are scoped and tier-gated.

Two defects this pins, both in shipped code before Increment 6:

1. **Cross-tenant approval response.** ``respond_to_approval`` selected the
   approval by id alone, while ``get_pending_approvals`` right above it had
   always joined ``ExecutionRun`` to filter by company. Any authenticated user
   holding an approval UUID could approve another tenant's HITL card.
2. **No step-up on the console path.** ``require_tier`` had no REST call sites,
   so a categorised act cost a ceremony when *asked for* through Pragya and
   nothing when *clicked*.

Route handlers are called directly with a company-scoped fake user, matching
``test_connectors_router.py`` — which is exactly why the gates are imperative
calls in the handler body rather than FastAPI dependencies (a declarative
dependency does not run on a direct call, so this suite could not observe it).
``needs_db``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text

from src.ai.inward_auth.models import AuthLevel, ChannelKind
from src.ai.inward_auth.sessions import elevate, get_or_create_session
from src.ai.loop.service import ensure_sheel
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


async def _make_tenant(label: str):
    """A committed company + user + run, ready to hang approvals off."""
    from src.common.database import AsyncSessionLocal

    cid, uid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"{label}-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, company_id, email, full_name, hashed_password, "
                 "role, is_active, created_at, updated_at) VALUES "
                 "(:u, :c, :e, :f, 'x', 'admin', true, now(), now())"),
            {"u": str(uid), "c": str(cid), "e": f"{label}-{uid.hex[:8]}@example.test",
             "f": f"{label} tester"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    async with AsyncSessionLocal() as db:
        sheel = await ensure_sheel(db, cid)
        run_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO execution_runs (id, entity_id, company_id, status, created_at) "
                 "VALUES (:r, :e, :c, 'PAUSED', now())"),
            {"r": str(run_id), "e": str(sheel.id), "c": str(cid)})
        await db.commit()
    return SimpleNamespace(company_id=cid, id=uid, role="admin", run_id=run_id)


async def _drop_tenant(cid: uuid.UUID) -> None:
    from src.common.database import AsyncSessionLocal, engine

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "DELETE FROM human_approvals WHERE run_id IN "
            "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
        for tbl in ("account_manager_sessions", "signals", "budget_envelopes",
                    "loop_runtime", "execution_runs"):
            await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                        {"c": str(cid)})
        await s.execute(text("DELETE FROM users WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


@pytest_asyncio.fixture
async def tenants():
    """Two unrelated tenants — the only way to prove the scoping bites."""
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    from src.common.database import engine

    await engine.dispose()
    alice = await _make_tenant("cert-a")
    bob = await _make_tenant("cert-b")
    try:
        yield alice, bob
    finally:
        await _drop_tenant(alice.company_id)
        await _drop_tenant(bob.company_id)
        tenant_data_plane.reset_cache()


async def _add_approval(run_id: uuid.UUID, snapshot: dict | None) -> uuid.UUID:
    import json

    from src.common.database import AsyncSessionLocal

    aid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO human_approvals (id, run_id, checkpoint_trigger, "
                 "checkpoint_key, status, context_snapshot, requested_at) VALUES "
                 "(:i, :r, 'policy_gate', :k, 'PENDING', CAST(:s AS json), now())"),
            {"i": str(aid), "r": str(run_id), "k": "before_outbound_payout_above_band",
             "s": json.dumps(snapshot) if snapshot is not None else None})
        await db.commit()
    return aid


async def _elevate_console(user) -> None:
    """Give the user a live T2 ceremony, as a passkey step-up would."""
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=user.company_id, user_id=user.id,
            channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey", level=AuthLevel.OOB_CONFIRMED)
        await db.commit()


# ── the cross-tenant hole ─────────────────────────────────────────────────────

async def test_one_tenant_cannot_respond_to_anothers_approval(tenants):
    """The IDOR. Bob holds Alice's approval id and is fully authenticated."""
    from src.ai.router import ApprovalRespondRequest, respond_to_approval
    from src.common.database import AsyncSessionLocal

    alice, bob = tenants
    approval_id = await _add_approval(alice.run_id, {"category": "email_dispatch"})
    await _elevate_console(bob)   # Bob is *maximally* authorised in his own tenant

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await respond_to_approval(
                approval_id, ApprovalRespondRequest(status="APPROVED"), db, bob)
    # 404, not 403: a probe must not learn that the id exists elsewhere.
    assert exc.value.status_code == 404

    # And Alice's card is untouched.
    async with AsyncSessionLocal() as db:
        status = (await db.execute(
            text("SELECT status FROM human_approvals WHERE id = :i"),
            {"i": str(approval_id)})).scalar_one()
    assert status == "PENDING"


# ── the step-up gate ──────────────────────────────────────────────────────────

async def test_a_categorised_approval_needs_a_ceremony(tenants):
    """Clicking 'approve' on a payout without stepping up is refused."""
    from src.ai.router import ApprovalRespondRequest, respond_to_approval
    from src.common.database import AsyncSessionLocal

    alice, _ = tenants
    approval_id = await _add_approval(
        alice.run_id, {"category": "payout", "amount": 100.0, "band": 500.0})

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await respond_to_approval(
                approval_id, ApprovalRespondRequest(status="APPROVED"), db, alice)

    assert exc.value.status_code == 403
    detail = exc.value.detail
    assert detail["error"] == "step_up_required"
    assert detail["tier"] == "T2"
    # The refusal is an instruction — the console knows which modal to open.
    assert detail["needs_step_up"] is True


async def test_the_same_approval_passes_once_elevated(tenants):
    """The gate refuses a state, not a person — the ceremony clears it."""
    from src.ai.router import ApprovalRespondRequest, respond_to_approval
    from src.common.database import AsyncSessionLocal

    alice, _ = tenants
    approval_id = await _add_approval(
        alice.run_id, {"category": "payout", "amount": 100.0, "band": 500.0})
    await _elevate_console(alice)

    async with AsyncSessionLocal() as db:
        await respond_to_approval(
            approval_id, ApprovalRespondRequest(status="APPROVED"), db, alice)

    async with AsyncSessionLocal() as db:
        status = (await db.execute(
            text("SELECT status FROM human_approvals WHERE id = :i"),
            {"i": str(approval_id)})).scalar_one()
    assert status == "APPROVED"


async def test_an_uncategorised_approval_still_clears_at_bound(tenants):
    """The regression guard for the shipped Solo Pack console.

    A non-policy checkpoint carries no external business effect, so it must not
    have acquired a ceremony — otherwise this hardening would put a passkey
    prompt in front of every routine confirmation a tenant sees.
    """
    from src.ai.router import ApprovalRespondRequest, respond_to_approval
    from src.common.database import AsyncSessionLocal

    alice, _ = tenants
    approval_id = await _add_approval(alice.run_id, {"reason": "plan confirmation"})

    async with AsyncSessionLocal() as db:
        await respond_to_approval(
            approval_id, ApprovalRespondRequest(status="APPROVED"), db, alice)

    async with AsyncSessionLocal() as db:
        status = (await db.execute(
            text("SELECT status FROM human_approvals WHERE id = :i"),
            {"i": str(approval_id)})).scalar_one()
    assert status == "APPROVED"


# ── the other certified surfaces ──────────────────────────────────────────────

async def test_binding_a_connector_needs_a_ceremony(tenants):
    """Submitting third-party credentials is T2 (Vihara §15.2)."""
    from src.ai.connectors.router import BindRequest, bind
    from src.common.database import AsyncSessionLocal

    alice, _ = tenants
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await bind("zoho_books",
                       BindRequest(credentials={"refresh_token": "secret"}),
                       alice, db)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "step_up_required"

    # Nothing was stored — the gate runs before the credential is touched.
    async with AsyncSessionLocal() as db:
        count = (await db.execute(
            text("SELECT count(*) FROM connector_bindings WHERE company_id = :c"),
            {"c": str(alice.company_id)})).scalar_one()
    assert count == 0


async def test_opting_into_a_foreign_provider_needs_a_ceremony(tenants):
    """D5 consent is the moment tenant data reaches a new jurisdiction."""
    from src.ai.intelligence.api import OptInRequest, opt_in_provider
    from src.common.database import AsyncSessionLocal

    alice, _ = tenants
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await opt_in_provider(
                "zhipu", OptInRequest(disclosure_version="1.0"), alice, db)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "step_up_required"


async def test_revoking_consent_is_never_gated(tenants):
    """The safe direction must not be blocked — including by a lockout."""
    from src.ai.intelligence.api import revoke_provider
    from src.common.database import AsyncSessionLocal

    alice, _ = tenants
    async with AsyncSessionLocal() as db:
        result = await revoke_provider("zhipu", alice, db)
    assert result["provider"] == "zhipu"
