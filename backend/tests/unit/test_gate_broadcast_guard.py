"""Increment 6 / GATE T3+T4 — channel posture and audience DNC filtering.

The categories (T1/T2) decide whether the *agent* may act at its band. These
decide whether the *tenant* broadcasts on this channel at all — a different
question with a different answer source, which is why §5 splits them.

Everything here runs against the seam (``solo_pack.consent``) with an injected
checker, so the policy is exercised without a database. The registry half
(`evaluate_channel_posture` reading real rows) is covered in
`tests/integration/test_gate_broadcast_db.py`.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.solo_pack.consent import (
    ConsentDecision,
    filter_audience,
    set_channel_posture_checker,
    set_consent_checker,
)
from src.ai.trust.broadcast_guard import (
    AUDIENCE_KEYS,
    guard_social_call,
    purpose_for_tool,
)

COMPANY = uuid.uuid4()


@pytest.fixture(autouse=True)
def _clear_seams():
    """Every test installs its own checkers; none leaks into the next."""
    set_channel_posture_checker(None)
    set_consent_checker(None)
    yield
    set_channel_posture_checker(None)
    set_consent_checker(None)


def _posture(allowed: bool, reason: str = ""):
    async def checker(company_id, channel, purpose):
        return ConsentDecision(allowed=allowed, reason=reason)

    return checker


def _dnc(*blocked: str):
    async def checker(company_id, channel, to_address, purpose):
        if to_address in blocked:
            return ConsentDecision(allowed=False, reason="on the do-not-contact list")
        return ConsentDecision(allowed=True, reason="clear")

    return checker


# ── T3: channel posture ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_posture_permissive_until_the_tenant_sets_one() -> None:
    """Decision 6 / Inc-2 decision 8: no imposed global default.

    Defaulting closed would have every tenant's first post fail silently, with
    nothing in the product yet explaining why.
    """
    result = await guard_social_call(
        "linkedin_create_post", "linkedin", COMPANY, {"text": "hello"})
    assert result.allowed is True


@pytest.mark.asyncio
async def test_a_tenant_can_refuse_a_channel() -> None:
    set_channel_posture_checker(
        _posture(False, "this tenant does not broadcast on linkedin"))
    result = await guard_social_call(
        "linkedin_create_post", "linkedin", COMPANY, {"text": "hello"})
    assert result.allowed is False
    assert "does not broadcast" in result.reason


@pytest.mark.asyncio
async def test_a_read_is_never_gated_by_posture() -> None:
    """Even with the channel switched off, reading analytics stays allowed —
    posture governs publishing, not looking."""
    set_channel_posture_checker(_posture(False, "off"))
    result = await guard_social_call(
        "linkedin_get_analytics", "linkedin", COMPANY, {"analytics_type": "page"})
    assert result.allowed is True


@pytest.mark.parametrize(
    "tool,expected",
    [
        ("linkedin_create_post", "marketing"),
        ("tiktok_publish_video", "marketing"),
        ("youtube_upload_video", "marketing"),
        ("linkedin_manage_comments", "transactional"),
        ("facebook_manage_comments", "transactional"),
    ],
)
def test_publishing_is_marketing_but_a_public_reply_is_support(
    tool: str, expected: str
) -> None:
    """Split so a tenant can refuse marketing on a channel and still let its
    agents answer a customer's public comment."""
    assert purpose_for_tool(tool) == expected


@pytest.mark.asyncio
async def test_posture_is_asked_per_purpose() -> None:
    """A tenant refusing marketing on a channel keeps its support replies."""
    seen: list[str] = []

    async def checker(company_id, channel, purpose):
        seen.append(purpose)
        return ConsentDecision(allowed=(purpose == "transactional"), reason=purpose)

    set_channel_posture_checker(checker)

    post = await guard_social_call(
        "linkedin_create_post", "linkedin", COMPANY, {"text": "buy"})
    reply = await guard_social_call(
        "linkedin_manage_comments", "linkedin", COMPANY, {"action": "create"})

    assert post.allowed is False
    assert reply.allowed is True
    assert seen == ["marketing", "transactional"]


@pytest.mark.asyncio
async def test_posture_is_asked_about_the_right_platform() -> None:
    seen: list[str] = []

    async def checker(company_id, channel, purpose):
        seen.append(channel)
        return ConsentDecision(allowed=True)

    set_channel_posture_checker(checker)
    await guard_social_call("tiktok_publish_video", "tiktok", COMPANY, {})
    assert seen == ["tiktok"]


# ── T4: audience DNC filtering ───────────────────────────────────────


@pytest.mark.asyncio
async def test_an_audience_is_filtered_not_refused() -> None:
    """Decision 5. Refusing a 10,000-row upload over one unsubscribe would push
    tenants to build the list by hand outside the platform — where it would be
    filtered by nothing at all."""
    set_consent_checker(_dnc("blocked@example.com"))
    result = await guard_social_call(
        "meta_ads_manage_audiences", "meta_ads", COMPANY,
        {"emails": ["ok@example.com", "blocked@example.com", "fine@example.com"]},
    )
    assert result.allowed is True
    assert result.params["emails"] == ["ok@example.com", "fine@example.com"]
    assert result.suppressed_count == 1


@pytest.mark.asyncio
async def test_the_suppressed_identifier_never_reaches_the_platform() -> None:
    """The load-bearing property: the returned params, which are what execute,
    must not contain a suppressed person."""
    set_consent_checker(_dnc("blocked@example.com"))
    result = await guard_social_call(
        "linkedin_ads_manage_audiences", "linkedin_ads", COMPANY,
        {"emails": ["blocked@example.com"]},
    )
    assert "blocked@example.com" not in result.params["emails"]
    assert result.params["emails"] == []


@pytest.mark.asyncio
async def test_a_clean_audience_is_untouched() -> None:
    set_consent_checker(_dnc())
    payload = {"emails": ["a@example.com", "b@example.com"], "name": "Q3 list"}
    result = await guard_social_call(
        "meta_ads_manage_audiences", "meta_ads", COMPANY, payload)
    assert result.params["emails"] == ["a@example.com", "b@example.com"]
    assert result.params["name"] == "Q3 list"
    assert result.suppressed_count == 0


@pytest.mark.asyncio
async def test_non_audience_params_are_never_rewritten() -> None:
    """`special_ad_categories` is a list on a campaign tool and has nothing to
    do with people. Only the named audience keys are filtered."""
    set_consent_checker(_dnc("CREDIT"))
    result = await guard_social_call(
        "meta_ads_create_campaign", "meta_ads", COMPANY,
        {"special_ad_categories": ["CREDIT"], "name": "c"},
    )
    assert result.params["special_ad_categories"] == ["CREDIT"]
    assert result.suppressed_count == 0


@pytest.mark.asyncio
async def test_filter_audience_preserves_order() -> None:
    """A tenant reading the result back should see its own list, minus the
    suppressed rows — not a reordered one."""
    set_consent_checker(_dnc("b@x.com"))
    result = await filter_audience(
        COMPANY, "meta_ads", ["a@x.com", "b@x.com", "c@x.com"])
    assert result.allowed == ("a@x.com", "c@x.com")
    assert result.suppressed == ("b@x.com",)
    assert result.suppressed_count == 1


def test_no_shipped_tool_declares_an_audience_parameter() -> None:
    """The honest limit, pinned so it is noticed when it changes.

    The shipped audience tools build from rules and lookalike sources; none
    accepts a raw list of person identifiers, so T4's filter has no live feed
    today. It is wired anyway, at the one place such a list would arrive. When
    a tool grows one of these parameters this test fails, which is the prompt
    to confirm the filtering is what that platform actually needs.
    """
    import ast
    import pathlib

    social = pathlib.Path(__file__).resolve().parents[2] / "src" / "ai" / "tools" / "social"
    declared: set[str] = set()
    for path in social.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in AUDIENCE_KEYS:
                    declared.add(f"{path.name}:{node.value}")
    assert not declared, (
        "a social tool now declares an audience-identifier parameter: "
        f"{sorted(declared)} — confirm T4's filtering fits that platform"
    )


# ── The guard is reachable through the real call site ────────────────
#
# HANDOFF §5, the VG-05 lesson: "a gate must be reachable by the test harness
# that claims to cover it". Everything above calls `guard_social_call`
# directly, so deleting the wiring from `SocialMediaTool.run_with_context`
# would break none of it. These drive a real tool through `run_with_context`
# instead, which is what actually executes in production.


class _FakeTool:
    """A minimal SocialMediaTool that records whether it reached the API."""

    def __init__(self, name: str, platform: str):
        self._name = name
        self._platform = platform
        self.executed_with: dict | None = None

    def build(self):
        from src.ai.tools.social.base import SocialMediaTool

        outer = self

        class Probe(SocialMediaTool):
            name = outer._name
            platform = outer._platform
            description = "probe"

            def get_function_schema(self):
                return {"name": self.name, "parameters": {}}

            async def _execute(self, params, credentials, context):
                outer.executed_with = dict(params)
                return {"success": True}

        return Probe()


@pytest.fixture
def _fake_credentials(monkeypatch):
    async def resolve_connection(company_id, platform, account_name=None,
                                 platform_user_id=None):
        return {"access_token": "tok"}

    import src.ai.social_connection_service as svc

    monkeypatch.setattr(svc, "resolve_connection", resolve_connection)
    return resolve_connection


@pytest.mark.asyncio
async def test_a_refused_channel_stops_the_tool_reaching_the_platform(
    _fake_credentials,
) -> None:
    """The load-bearing wiring test: refusal must happen before `_execute`.

    Delete the `guard_social_call` block from `SocialMediaTool.run_with_context`
    and this fails — nothing else does.
    """
    import json

    set_channel_posture_checker(_posture(False, "this tenant does not broadcast on linkedin"))
    probe = _FakeTool("linkedin_create_post", "linkedin")
    tool = probe.build()

    raw = await tool.run_with_context(
        json.dumps({"text": "hello"}), {"company_id": str(COMPANY)})
    result = json.loads(raw)

    assert probe.executed_with is None, "the platform API was reached despite a refusal"
    assert result["refused_by"] == "channel_posture"


@pytest.mark.asyncio
async def test_an_allowed_channel_still_publishes(_fake_credentials) -> None:
    """The refusal path must not be the only path — a permissive posture
    (the default) has to leave the tool working."""
    import json

    probe = _FakeTool("linkedin_create_post", "linkedin")
    tool = probe.build()

    raw = await tool.run_with_context(
        json.dumps({"text": "hello"}), {"company_id": str(COMPANY)})

    assert probe.executed_with == {"text": "hello"}
    assert json.loads(raw)["success"] is True


@pytest.mark.asyncio
async def test_the_tool_executes_with_the_filtered_audience(_fake_credentials) -> None:
    """T4 through the call site: `_execute` must see the cleaned list, so a
    suppressed person cannot reach the ad platform even though the call itself
    was allowed to proceed."""
    import json

    set_consent_checker(_dnc("blocked@example.com"))
    probe = _FakeTool("meta_ads_manage_audiences", "meta_ads")
    tool = probe.build()

    await tool.run_with_context(
        json.dumps({"emails": ["ok@example.com", "blocked@example.com"]}),
        {"company_id": str(COMPANY)},
    )

    assert probe.executed_with is not None
    assert probe.executed_with["emails"] == ["ok@example.com"]
