"""Inc-7 D8 E1 — ``GET /ai/consent``'s read model against real rows.

The registry's enforcement is tested next door (``test_consent_registry_db``);
what this file pins is the *read*: company scoping, the counts a panel puts
in front of an owner, and the one thing that would make those counts a lie —
the tenant's own channel switch is stored under a reserved identity in the
same table as the people who asked to be left alone, and must never be
counted or listed as one of them. ``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.trust.consent_read import channel_consent, consent_view
from src.ai.trust.consent_registry import (
    add_dnc,
    record_unsubscribe,
    set_channel_posture,
    set_consent,
)
from src.ai.trust.models import ConsentPurpose, ConsentStatus

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


async def _make_company(name: str) -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"{name}-{cid.hex[:8]}"})
        await s.commit()
    return cid


async def _drop_company(cid: uuid.UUID) -> None:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        for tbl in ("consent_records", "dnc_entries", "unsubscribe_log"):
            await s.execute(
                text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


@pytest_asyncio.fixture
async def companies():
    """Two tenants, because the interesting failure of a read model is
    reading someone else's rows, not reading none."""
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import engine

    await engine.dispose()
    mine = await _make_company("consent-read")
    theirs = await _make_company("consent-read-other")
    try:
        yield mine, theirs
    finally:
        await _drop_company(mine)
        await _drop_company(theirs)


async def _seed(company: uuid.UUID) -> None:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await add_dnc(db, company, "email", "Stop@Example.com", reason="asked to stop")
        await add_dnc(db, company, "whatsapp", "+91 98765 43210")
        await record_unsubscribe(db, company, "email", "bye@example.com",
                                 ConsentPurpose.MARKETING)
        await record_unsubscribe(db, company, "email", "bye@example.com",
                                 ConsentPurpose.TRANSACTIONAL)
        await set_consent(db, company, "email", "yes@example.com",
                          ConsentPurpose.MARKETING, ConsentStatus.GRANTED)
        await set_consent(db, company, "email", "no@example.com",
                          ConsentPurpose.MARKETING, ConsentStatus.DENIED)
        await db.commit()


async def test_the_view_reports_this_company_and_no_other(companies):
    from src.common.database import AsyncSessionLocal

    mine, theirs = companies
    await _seed(mine)
    async with AsyncSessionLocal() as db:
        view = await consent_view(db, mine)
        empty = await consent_view(db, theirs)

    assert view["totals"] == {
        "dnc": 2, "unsubscribed": 1, "granted": 1, "denied": 1}
    assert {c["channel"] for c in view["channels"]} == {"email", "whatsapp"}
    # The other tenant's read is empty, not the first tenant's rows.
    assert empty["totals"] == {"dnc": 0, "unsubscribed": 0, "granted": 0, "denied": 0}
    assert empty["channels"] == [] and empty["entries"] == []


async def test_one_person_unsubscribing_twice_is_one_person(companies):
    """The log is append-only and purpose-scoped: two rows for the same
    address are two events and one counterparty. A bay headed 'who asked us
    to stop' that counted events would overstate the number an owner acts on."""
    from src.common.database import AsyncSessionLocal

    mine, _ = companies
    await _seed(mine)
    async with AsyncSessionLocal() as db:
        view = await consent_view(db, mine)

    assert view["totals"]["unsubscribed"] == 1
    unsubs = [e for e in view["entries"] if e["kind"] == "unsubscribe"]
    assert len(unsubs) == 2  # both events are listed; the count is people


async def test_the_tenants_own_switch_is_a_posture_never_a_person(companies):
    """``CHANNEL_POSTURE_IDENTITY`` lives in the same tables as real
    counterparties. It must show up as the channel's posture and nowhere
    else — a tenant's marketing switch listed among the people who asked to
    be left alone is a lie about a number they are meant to act on."""
    from src.common.database import AsyncSessionLocal

    mine, _ = companies
    async with AsyncSessionLocal() as db:
        await set_channel_posture(db, mine, "linkedin", ConsentPurpose.MARKETING,
                                  ConsentStatus.DENIED)
        await db.commit()
    async with AsyncSessionLocal() as db:
        view = await consent_view(db, mine)

    assert view["totals"] == {"dnc": 0, "unsubscribed": 0, "granted": 0, "denied": 0}
    assert view["entries"] == []
    linkedin = next(c for c in view["channels"] if c["channel"] == "linkedin")
    assert linkedin["posture"] == "restricted"
    assert linkedin["purposes"] == {"marketing": False, "transactional": True}
    assert "marketing" in linkedin["reason"]


async def test_a_channel_wide_dnc_closes_the_gate(companies):
    """The whole-channel off switch, set the way GATE T3 sets it (a DNC row
    on the posture identity — see test_gate_broadcast_db)."""
    from src.ai.trust.consent_registry import CHANNEL_POSTURE_IDENTITY
    from src.common.database import AsyncSessionLocal

    mine, _ = companies
    async with AsyncSessionLocal() as db:
        await add_dnc(db, mine, "linkedin", CHANNEL_POSTURE_IDENTITY,
                      reason="we do not post promotions")
        await db.commit()
    async with AsyncSessionLocal() as db:
        blocks = await channel_consent(db, mine, ["linkedin"])

    assert blocks["linkedin"]["posture"] == "closed"
    assert blocks["linkedin"]["dnc"] == 0  # the switch is not a counterparty


async def test_entries_carry_what_the_bay_lists(companies):
    from src.common.database import AsyncSessionLocal

    mine, _ = companies
    await _seed(mine)
    async with AsyncSessionLocal() as db:
        view = await consent_view(db, mine, limit=3)

    assert len(view["entries"]) == 3  # the cap is honoured
    dnc = next(
        e for e in (await _all_entries(mine)) if e["identity"] == "stop@example.com")
    assert dnc["kind"] == "dnc"
    assert dnc["channel"] == "email"
    assert dnc["reason"] == "asked to stop"
    assert dnc["at"] is not None


async def _all_entries(company: uuid.UUID) -> list[dict]:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        view = await consent_view(db, company, limit=100)
    return list(view["entries"])
