"""Increment 6 / GATE T5–T7 — KAR-05, the broadcast gateway.

The Karuna posture is enforced by the shared builder, so most of what matters
here is that KAR-05 actually went through it and that its specialisations
(no ad tools, no publish tools) hold. The injection golden follows
`test_kar_gateways.py`: prove a hijacked gateway has nothing to reach.
"""
from __future__ import annotations

import json
import uuid

import pytest

from src.ai.governance.authority import category_for_tool
from src.ai.governance.policy_gate import (
    ActIntent,
    BLOCK,
    PASS,
    RAISE_HITL,
    evaluate_policy,
)
from src.ai.schemas.governance import AutonomyLevel, Governance
from src.ai.signals.models import SignalTypes
from src.ai.solo_pack.consent import ConsentDecision, set_channel_posture_checker
from src.ai.solo_pack.templates import GATEWAYS, SOLO_PACK_TEMPLATES
from src.ai.solo_pack.templates.gateways import KAR_05_BROADCAST


# ── T5: the gateway is a real Karuna gateway ─────────────────────────


def test_kar05_is_in_the_roster() -> None:
    assert KAR_05_BROADCAST in GATEWAYS
    assert len(GATEWAYS) == 4
    assert len(SOLO_PACK_TEMPLATES) == 19


def test_kar05_carries_the_karuna_posture() -> None:
    """By construction, via the shared builder — not by remembering to."""
    gov = KAR_05_BROADCAST["governance"]
    assert gov["karuna_profile"] is True
    assert gov["autonomy_level"] == "A1"
    # No authority bands: a gateway has no monetary reach, so a hijack has
    # nothing to spend.
    assert "authority" not in gov


def test_kar05_holds_no_ad_tools() -> None:
    """Decision 3. Ad tools are money and belong to a marketing process agent
    under its own band, never to the inbound face."""
    tool_ids = {t["tool_id"] for t in KAR_05_BROADCAST["capabilities"]["tools"]}
    assert not any(category_for_tool(t) == "ad_spend" for t in tool_ids)


def test_kar05_cannot_publish_either() -> None:
    """Its job is inbound → business signal. Giving the outward face a publish
    tool would put the reply path and the injection surface in one agent."""
    tool_ids = {t["tool_id"] for t in KAR_05_BROADCAST["capabilities"]["tools"]}
    assert not any(category_for_tool(t) == "broadcast" for t in tool_ids)


def test_kar05_is_externally_bound_so_the_deploy_gate_bites() -> None:
    """`broadcast_provider` makes the deploy Karuna gate treat this as
    externally bound — so a KAR-05 that lost `karuna_profile` would fail to
    publish, exactly as KAR-01/03 do."""
    assert KAR_05_BROADCAST["metadata_extensions"]["broadcast_provider"] == "multi"


def test_kar05_consumes_the_right_signal() -> None:
    patterns = KAR_05_BROADCAST["metadata_extensions"]["trigger_patterns"]
    assert patterns == [SignalTypes.BROADCAST_INBOUND]


def test_slice_still_seeds_email_only() -> None:
    """Adding a gateway must not widen the thin vertical slice."""
    from src.ai.solo_pack.templates import SLICE_TEMPLATES

    codes = {
        tag.split(":", 1)[1]
        for t in SLICE_TEMPLATES for tag in t["tags"] if tag.startswith("agent_code:")
    }
    assert "KAR-05" not in codes


# ── T5: the injection golden ─────────────────────────────────────────


@pytest.mark.parametrize("category", ["payout", "refund", "contract", "vendor_creation",
                                      "ad_spend"])
def test_a_hijacked_broadcast_gateway_cannot_move_money(category: str) -> None:
    """The trust down-payment, now including ad spend.

    A public comment is the cheapest hostile input there is — anyone can write
    one. A run tainted by it must not reach money, and `ad_spend` is money.
    """
    intent = ActIntent(action_category=category, amount_usd=5000.0,
                       counterparty_trust="counterparty")
    decision = evaluate_policy(intent, Governance(autonomy_level=AutonomyLevel.A1))
    assert decision.decision == BLOCK


def test_a_hijacked_gateway_can_still_be_asked_to_reply() -> None:
    """The deliberate other half: `broadcast` is not high-impact, because
    replying in public to a counterparty is what a gateway is *for*. At A1 it
    is still a card — it is just not a refusal."""
    intent = ActIntent(action_category="broadcast", counterparty_trust="counterparty")
    decision = evaluate_policy(intent, Governance(autonomy_level=AutonomyLevel.A1))
    assert decision.decision == RAISE_HITL


# ── T7: end to end, through the real tool path ───────────────────────


class _Probe:
    """A real SocialMediaTool subclass that records what reached the API."""

    def __init__(self, name: str, platform: str, result: dict | None = None):
        self.executed = False
        self.result = result or {"success": True, "post_id": "urn:li:share:1"}
        self._name, self._platform = name, platform

    def build(self):
        from src.ai.tools.social.base import SocialMediaTool

        outer = self

        class T(SocialMediaTool):
            name = outer._name
            platform = outer._platform
            description = "probe"

            def get_function_schema(self):
                return {"name": self.name, "parameters": {}}

            async def _execute(self, params, credentials, context):
                outer.executed = True
                return outer.result

        return T()


@pytest.fixture
def _wired(monkeypatch):
    """Credentials resolve, and the audit emit is captured rather than run."""
    import src.ai.social_connection_service as svc

    async def resolve_connection(company_id, platform, account_name=None,
                                 platform_user_id=None):
        return {"access_token": "tok"}

    monkeypatch.setattr(svc, "resolve_connection", resolve_connection)

    emitted: list[dict] = []

    async def fake_audit(self, company_id, params, result, suppressed_count):
        from src.ai.governance.authority import category_for_tool as cat

        if cat(self.name) == "broadcast" and not result.get("error"):
            emitted.append({"platform": self.platform, "tool": self.name,
                            "suppressed": suppressed_count})

    from src.ai.tools.social.base import SocialMediaTool

    monkeypatch.setattr(SocialMediaTool, "_audit_publish", fake_audit)
    set_channel_posture_checker(None)
    yield emitted
    set_channel_posture_checker(None)


@pytest.mark.asyncio
async def test_an_a1_agent_publishing_is_a_governed_act(_wired) -> None:
    """The headline of the whole workstream, stated as the gate sees it.

    Before GATE this resolved to PASS — an A1 agent, the band where every
    categorised external effect raises a card, could publish to the public
    internet without one.
    """
    decision = evaluate_policy(
        ActIntent(action_category=category_for_tool("linkedin_create_post")),
        Governance(autonomy_level=AutonomyLevel.A1),
    )
    assert decision.decision == RAISE_HITL
    assert decision.checkpoint_key == "before_public_broadcast"


@pytest.mark.asyncio
async def test_an_a3_publish_needs_no_card_but_still_emits_the_audit(_wired) -> None:
    """The other half of T7: autonomy removes the card, never the audit trail."""
    decision = evaluate_policy(
        ActIntent(action_category="broadcast"),
        Governance(autonomy_level=AutonomyLevel.A3),
    )
    assert decision.decision == PASS

    probe = _Probe("linkedin_create_post", "linkedin")
    tool = probe.build()
    await tool.run_with_context(
        json.dumps({"text": "hi"}), {"company_id": str(uuid.uuid4())})

    assert probe.executed is True
    assert _wired == [{"platform": "linkedin", "tool": "linkedin_create_post",
                       "suppressed": 0}]


@pytest.mark.asyncio
async def test_a_read_emits_no_publish_audit(_wired) -> None:
    probe = _Probe("linkedin_get_analytics", "linkedin")
    tool = probe.build()
    await tool.run_with_context(
        json.dumps({"analytics_type": "page"}), {"company_id": str(uuid.uuid4())})
    assert _wired == []


@pytest.mark.asyncio
async def test_a_failed_publish_emits_no_audit(_wired) -> None:
    """An audit row for a post that never happened is worse than none."""
    probe = _Probe("linkedin_create_post", "linkedin", result={"error": "rate limited"})
    tool = probe.build()
    await tool.run_with_context(
        json.dumps({"text": "hi"}), {"company_id": str(uuid.uuid4())})
    assert _wired == []


@pytest.mark.asyncio
async def test_a_refused_publish_emits_no_audit(_wired, monkeypatch) -> None:
    async def refuse(company_id, channel, purpose):
        return ConsentDecision(allowed=False, reason="off")

    set_channel_posture_checker(refuse)
    probe = _Probe("linkedin_create_post", "linkedin")
    tool = probe.build()
    await tool.run_with_context(
        json.dumps({"text": "hi"}), {"company_id": str(uuid.uuid4())})
    assert probe.executed is False
    assert _wired == []


@pytest.mark.asyncio
async def test_the_audit_never_breaks_a_send(monkeypatch) -> None:
    """The post has already happened when the audit runs. Raising here would
    report failure for something that succeeded, and the caller would retry —
    publishing twice. A missing audit row is the lesser harm."""
    import src.ai.social_connection_service as svc

    async def resolve_connection(company_id, platform, account_name=None,
                                 platform_user_id=None):
        return {"access_token": "tok"}

    monkeypatch.setattr(svc, "resolve_connection", resolve_connection)

    async def boom(db, company_id, **kw):
        raise RuntimeError("bus down")

    import src.ai.signals.broadcast_inbound as producer

    monkeypatch.setattr(producer, "emit_broadcast_published", boom)
    set_channel_posture_checker(None)

    probe = _Probe("linkedin_create_post", "linkedin")
    tool = probe.build()
    raw = await tool.run_with_context(
        json.dumps({"text": "hi"}), {"company_id": str(uuid.uuid4())})

    assert json.loads(raw)["success"] is True
