"""LINE L3 — the WhatsApp read-mirror, driven against fakes.

The rules: a verified binding or nothing; the preference can silence it;
the message never carries an approval path; the two senders each have
exactly one permitted import site (the L8 pattern applied twice); and the
door's order is socket → push → WhatsApp → nowhere.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from src.ai.genui import channel as ch
from src.ai.genui import whatsapp_mirror as wm

BACKEND_ROOT = Path(__file__).resolve().parents[2]
COMPANY = uuid.uuid4()
USER = uuid.uuid4()


class FakeTransportRecorder:
    def __init__(self, sent_ok: bool = True):
        self.sent: list[tuple[str, str]] = []
        self.sent_ok = sent_ok

    async def __call__(self, to: str, message: str) -> bool:
        self.sent.append((to, message))
        return self.sent_ok


def _mirror_with(monkeypatch, *, address: str | None, pref: object = None):
    async def fake_address(db, company_id, user_id):
        return address

    async def fake_prefs(db, user_id, *, prefix=None):
        return (
            {"notify.whatsapp_mirror": {"value": pref, "learned": False}}
            if pref is not None else {})

    monkeypatch.setattr(wm, "_verified_address", fake_address)
    import src.ai.learning.preferences as preferences

    monkeypatch.setattr(preferences, "get_preferences", fake_prefs)


@pytest.mark.asyncio
async def test_a_tray_notice_reaches_a_verified_binding(monkeypatch):
    _mirror_with(monkeypatch, address="919876543210")
    transport = FakeTransportRecorder()
    sent = await wm.send_tray_notice(
        None, COMPANY, USER, "A payout needs you.", transport=transport)
    assert sent is True
    to, message = transport.sent[0]
    assert to == "+919876543210"
    assert message.startswith("A payout needs you.")
    assert wm.TRAY_SUFFIX in message


@pytest.mark.asyncio
async def test_no_verified_binding_means_no_send(monkeypatch):
    _mirror_with(monkeypatch, address=None)
    transport = FakeTransportRecorder()
    assert await wm.send_tray_notice(
        None, COMPANY, USER, "s", transport=transport) is False
    assert transport.sent == []


@pytest.mark.asyncio
async def test_the_preference_silences_the_mirror(monkeypatch):
    _mirror_with(monkeypatch, address="919876543210", pref="off")
    transport = FakeTransportRecorder()
    assert await wm.send_tray_notice(
        None, COMPANY, USER, "s", transport=transport) is False
    assert transport.sent == []


@pytest.mark.asyncio
async def test_a_raising_transport_loses_a_notice_never_raises(monkeypatch):
    _mirror_with(monkeypatch, address="919876543210")

    async def broken(to, message):
        raise RuntimeError("provider down")

    assert await wm.send_tray_notice(
        None, COMPANY, USER, "s", transport=broken) is False


@pytest.mark.asyncio
async def test_the_morning_summary_reads_like_a_morning(monkeypatch):
    _mirror_with(monkeypatch, address="919876543210")
    transport = FakeTransportRecorder()
    sent = await wm.send_morning_summary(
        None, COMPANY, USER,
        ["Ravi finished two pieces of work.", "Meera is waiting on you."],
        transport=transport)
    assert sent is True
    _, message = transport.sent[0]
    assert message.startswith("Good morning. ")
    assert "Meera is waiting on you." in message


@pytest.mark.asyncio
async def test_an_empty_morning_sends_nothing(monkeypatch):
    _mirror_with(monkeypatch, address="919876543210")
    transport = FakeTransportRecorder()
    assert await wm.send_morning_summary(
        None, COMPANY, USER, [], transport=transport) is False
    assert transport.sent == []


# ── the door's order (decision 1) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_door_tries_whatsapp_last_and_exactly_once(monkeypatch):
    fresh = ch.ChannelHub()
    monkeypatch.setattr(ch, "_hub", fresh)

    async def push_reaches_nobody(*a, **k):
        return 0

    monkeypatch.setattr(ch, "send_tray_push", push_reaches_nobody)
    _mirror_with(monkeypatch, address="919876543210")
    transport = FakeTransportRecorder()
    outcome = await ch.deliver_tray(
        None, COMPANY, USER,
        {"tray_id": "t1", "what_happened": {"sentence": "A payout needs you."}},
        mirror_transport=transport)
    assert outcome == "whatsapp"
    assert len(transport.sent) == 1


@pytest.mark.asyncio
async def test_push_reached_means_the_mirror_stays_silent(monkeypatch):
    fresh = ch.ChannelHub()
    monkeypatch.setattr(ch, "_hub", fresh)

    async def push_reaches_one(*a, **k):
        return 1

    monkeypatch.setattr(ch, "send_tray_push", push_reaches_one)
    transport = FakeTransportRecorder()
    outcome = await ch.deliver_tray(
        None, COMPANY, USER, {"tray_id": "t1"}, mirror_transport=transport)
    assert outcome == "push"
    assert transport.sent == []


# ── the import boundaries (the L8 pattern, applied twice) ────────────────────

def _sites_referencing(needle: str) -> set[str]:
    referencing = set()
    for path in (BACKEND_ROOT / "src").rglob("*.py"):
        rel = str(path.relative_to(BACKEND_ROOT))
        if needle in path.read_text(encoding="utf-8"):
            referencing.add(rel)
    return referencing


def test_the_tray_notice_has_exactly_one_permitted_import_site():
    allowed = {
        "src/ai/genui/whatsapp_mirror.py",
        "src/ai/genui/channel.py",
    }
    referencing = _sites_referencing("send_tray_notice")
    assert referencing <= allowed, (
        f"send_tray_notice referenced outside the single-writer set: "
        f"{sorted(referencing - allowed)} — only the one delivery door may "
        "reach a phone")


def test_the_morning_summary_has_exactly_one_permitted_import_site():
    allowed = {
        "src/ai/genui/whatsapp_mirror.py",
        "src/ai/genui/morning_job.py",
    }
    referencing = _sites_referencing("send_morning_summary")
    assert referencing <= allowed, (
        f"send_morning_summary referenced outside its single-writer set: "
        f"{sorted(referencing - allowed)}")
