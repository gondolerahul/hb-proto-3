"""Inc-7 D8 E1/E2 — the consent read model's pure parts.

The rows themselves are integration-tested (``test_consent_read_db.py``);
what must hold without a database is everything that could quietly lie to a
panel: the posture is *derived from the registry's own answers* and never
recomputed from the rows, the reason shown is the one that restricts, and
the door's block is a trim of the same read rather than a second opinion.

The router test is here too, for the reason the repo learned the hard way:
handlers are called directly, so a scoping rule that lives in a dependency
is a scoping rule nothing tests. What is pinned is that the company comes
from the session and that no company parameter exists to pass instead.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from src.ai.genui.estate import gate_consent_block
from src.ai.solo_pack.consent import ConsentDecision
from src.ai.trust import consent_read as cr

COMPANY = uuid.uuid4()


def _answers(monkeypatch: Any, per_purpose: dict[str, ConsentDecision]) -> None:
    """Stand in for the registry, so the derivation is tested against known
    answers rather than against rows that would re-test the registry."""
    async def fake(db: Any, company_id: Any, channel: str, purpose: str) -> ConsentDecision:
        return per_purpose[purpose]

    monkeypatch.setattr(cr, "evaluate_channel_posture", fake)


ALLOWED = ConsentDecision(allowed=True, reason="no email posture set — governed by band alone")
REFUSED_ALL = ConsentDecision(allowed=False, reason="this tenant does not broadcast on email")
REFUSED_MARKETING = ConsentDecision(
    allowed=False, reason="this tenant does not broadcast on email for marketing")


# ── posture is the registry's answer, not a second copy of the rules ─────────

@pytest.mark.asyncio
async def test_every_purpose_allowed_reads_open(monkeypatch):
    _answers(monkeypatch, {"marketing": ALLOWED, "transactional": ALLOWED})
    block = await cr.channel_posture(None, COMPANY, "email")
    assert block["posture"] == "open"
    assert block["purposes"] == {"marketing": True, "transactional": True}


@pytest.mark.asyncio
async def test_the_channel_wide_switch_reads_closed(monkeypatch):
    _answers(monkeypatch, {"marketing": REFUSED_ALL, "transactional": REFUSED_ALL})
    block = await cr.channel_posture(None, COMPANY, "email")
    assert block["posture"] == "closed"
    assert block["reason"] == REFUSED_ALL.reason  # verbatim, in the registry's words


@pytest.mark.asyncio
async def test_one_purpose_off_reads_restricted_and_says_which(monkeypatch):
    """The tenant who keeps transactional replies and refuses marketing is
    neither open nor closed, and a panel that rounded it to either would
    misdescribe a gate the owner deliberately configured."""
    _answers(monkeypatch, {"marketing": REFUSED_MARKETING, "transactional": ALLOWED})
    block = await cr.channel_posture(None, COMPANY, "email")
    assert block["posture"] == "restricted"
    assert block["purposes"] == {"marketing": False, "transactional": True}
    # The restricting reason wins — "no posture set" beside a refused purpose
    # reads as a bug in the gate rather than as the tenant's own choice.
    assert block["reason"] == REFUSED_MARKETING.reason


def test_recording_is_not_asked_about():
    """Nothing sets the recording purpose (it is a stub until voice ships),
    so reporting it would publish an answer no tenant has ever given."""
    assert "recording" not in cr.POSTURE_PURPOSES


# ── the door's block is a trim, never a second opinion (E2) ──────────────────

def test_the_gatehouse_shows_four_fields_of_the_same_read():
    block = gate_consent_block({
        "posture": "restricted", "reason": "because the registry said so",
        "purposes": {"marketing": False, "transactional": True},
        "dnc": 46, "unsubscribed": 12, "granted": 3, "denied": 1,
    })
    assert block == {
        "posture": "restricted", "reason": "because the registry said so",
        "dnc": 46, "unsubscribed": 12}


def test_a_channel_the_registry_was_not_asked_about_is_null_not_open():
    assert gate_consent_block(None) is None


# ── the router: company from the session, never a parameter ─────────────────

@pytest.mark.asyncio
async def test_the_endpoint_scopes_to_the_session_company(monkeypatch):
    from src.ai.trust import router as consent_router

    seen: dict[str, Any] = {}

    async def fake_view(db: Any, company_id: uuid.UUID, *, limit: int) -> dict[str, Any]:
        seen["company_id"] = company_id
        seen["limit"] = limit
        return {"channels": [], "entries": []}

    monkeypatch.setattr(consent_router, "consent_view", fake_view)
    await consent_router.get_consent(
        limit=50,
        current_user=SimpleNamespace(company_id=COMPANY),
        db=SimpleNamespace())
    assert seen == {"company_id": COMPANY, "limit": 50}


def test_the_endpoint_takes_no_company_parameter():
    """A cross-tenant read must not be expressible on this surface (D5 §2.2
    — the VG-05 lesson). The absence is the control, so it is pinned."""
    import inspect

    from src.ai.trust.router import get_consent

    params = set(inspect.signature(get_consent).parameters)
    assert params == {"limit", "current_user", "db"}
