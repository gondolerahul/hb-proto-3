"""Increment 6 / GATE T1+T2 — the broadcast and ad-spend categories.

The finding this closes: `src/ai/tools/social/` ships 64 tools across 16
platforms and not one appeared in ``TOOL_CATEGORY_MAP``. The PolicyGate only
gates *categorised* acts, so every one of them resolved to ``PASS`` — an agent
at A1, the band where every categorised external effect raises a HITL card,
could publish to the public internet and commit ad budget without one.

The load-bearing test here is ``test_every_social_tool_is_classified``: the
mapping is exact-keyed (see the comment in ``authority.py``), so a social tool
added later would silently be ungoverned again. That test makes it a CI
failure instead.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from src.ai.governance.authority import (
    CATEGORY_RULES,
    HIGH_IMPACT_CATEGORIES,
    TOOL_CATEGORY_MAP,
    category_for_tool,
)
from src.ai.governance.checkpoints import CHECKPOINT_KEYS, CHECKPOINT_SEED
from src.ai.governance.policy_gate import BLOCK, PASS, RAISE_HITL, evaluate_policy
from src.ai.schemas.governance import AutonomyLevel, AuthorityBands, Governance

SOCIAL_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "ai" / "tools" / "social"

# A read verb is not an external effect and must stay uncategorised (PASS), or
# every dashboard refresh becomes an approval. These are the only shapes that
# earn that exemption.
READ_PATTERNS = ("_get_", "_report", "_search", "_discover_")


def _shipped_social_tool_names() -> list[str]:
    """Every ``name = "..."`` declared on a class under ai/tools/social/.

    Parsed rather than imported: a tool that is declared but not exported from
    the package ``__init__`` is still reachable through the registry, so the
    source is the honest inventory.
    """
    names: list[str] = []
    for path in sorted(SOCIAL_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                for target in stmt.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "name"
                        and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)
                    ):
                        names.append(stmt.value.value)
    return names


def _is_read(tool_name: str) -> bool:
    return any(p in tool_name for p in READ_PATTERNS)


def _gov(level: AutonomyLevel, **bands: float) -> Governance:
    return Governance(
        autonomy_level=level,
        authority=AuthorityBands(**bands) if bands else None,
    )


def _intent(**kw: object):
    from src.ai.governance.policy_gate import ActIntent

    return ActIntent(**kw)  # type: ignore[arg-type]


# ── The inventory is real ────────────────────────────────────────────


def test_the_shipped_social_surface_is_what_the_finding_said() -> None:
    """64 tools across 16 platforms — the number the design doc asserted."""
    names = _shipped_social_tool_names()
    assert len(names) == 64, f"expected 64 social tools, found {len(names)}"
    assert len(set(names)) == 64, "social tool names must be unique"


# ── T2: the totality test (the load-bearing one) ─────────────────────


def test_every_social_tool_is_classified() -> None:
    """Every social tool either maps to a category or is a read. No middle.

    This is the durable guard. The mapping is exact-keyed, so a new social tool
    is ungoverned by default — exactly the bug GATE exists to fix. It must fail
    here, in CI, rather than in production.
    """
    unclassified = [
        name
        for name in _shipped_social_tool_names()
        if category_for_tool(name) is None and not _is_read(name)
    ]
    assert not unclassified, (
        "these social tools are neither categorised in TOOL_CATEGORY_MAP nor "
        f"recognisable as reads, so the PolicyGate passes them: {unclassified}"
    )


def test_read_tools_stay_uncategorised() -> None:
    """The two sets are disjoint — a read must not resolve to a category.

    Without this, the totality test above could be satisfied by categorising
    everything, which would turn every analytics refresh into an approval.
    """
    miscategorised = [
        (name, category_for_tool(name))
        for name in _shipped_social_tool_names()
        if _is_read(name) and category_for_tool(name) is not None
    ]
    assert not miscategorised, (
        f"read-only social tools resolved to a category: {miscategorised}"
    )


def test_the_named_publish_and_spend_tools_resolve() -> None:
    """Spot-check the tools the finding named by hand."""
    for tool in (
        "linkedin_create_post",
        "instagram_publish_media",
        "tiktok_publish_video",
        "quora_post_answer",
    ):
        assert category_for_tool(tool) == "broadcast", tool
    for tool in (
        "meta_ads_create_campaign",
        "google_ads_create_campaign",
        "linkedin_ads_manage_audiences",
    ):
        assert category_for_tool(tool) == "ad_spend", tool
    # ...and the reads the finding said must stay out.
    for tool in ("linkedin_get_analytics", "meta_ads_report", "twitter_search"):
        assert category_for_tool(tool) is None, tool


def test_social_mappings_are_exact_not_substring() -> None:
    """No social key may be a substring of another social tool's name.

    ``category_for_tool`` falls back to substring matching, and a key that is a
    prefix of a sibling would categorise it silently and wrongly.
    """
    names = set(_shipped_social_tool_names())
    social_keys = [k for k in TOOL_CATEGORY_MAP if k in names]
    for key in social_keys:
        collisions = [n for n in names if n != key and key in n]
        assert not collisions, f"key {key!r} is a substring of {collisions}"


# ── T1: the categories and their checkpoints ─────────────────────────


def test_broadcast_and_ad_spend_are_two_categories() -> None:
    """Decision 1: publishing and committing money are different acts."""
    assert "broadcast" in CATEGORY_RULES
    assert "ad_spend" in CATEGORY_RULES
    broadcast = CATEGORY_RULES["broadcast"]
    ad_spend = CATEGORY_RULES["ad_spend"]
    # broadcast is shaped like email_dispatch: no amount band.
    assert broadcast.band_field is None
    assert broadcast.unit == "none"
    assert broadcast.always_hitl is False
    # ad_spend carries an amount band, like payout.
    assert ad_spend.band_field == "ad_spend_usd"
    assert ad_spend.unit == "usd"
    assert ad_spend.default_band is not None and ad_spend.hard_block is not None
    assert ad_spend.hard_block > ad_spend.default_band


def test_ad_spend_is_high_impact_but_broadcast_is_not() -> None:
    """Decision 2: a hostile DM must not be able to drive money into an ad
    platform. A public reply to that same DM is ordinary support work."""
    assert "ad_spend" in HIGH_IMPACT_CATEGORIES
    assert "broadcast" not in HIGH_IMPACT_CATEGORIES


def test_the_two_new_checkpoints_exist_and_are_the_20th_and_21st() -> None:
    assert len(CHECKPOINT_SEED) == 21
    assert "before_public_broadcast" in CHECKPOINT_KEYS
    assert "before_ad_spend_above_band" in CHECKPOINT_KEYS


def test_every_category_rule_names_a_real_checkpoint() -> None:
    """A rule pointing at a checkpoint that does not exist raises a card
    nobody can find."""
    missing = [
        (name, rule.checkpoint_key)
        for name, rule in CATEGORY_RULES.items()
        if rule.checkpoint_key not in CHECKPOINT_KEYS
    ]
    assert not missing, f"category rules name unknown checkpoints: {missing}"


def test_ad_spend_checkpoint_is_not_the_payout_one() -> None:
    """The build-time correction, pinned.

    Borrowing ``before_outbound_payout_above_band`` would make an ad campaign
    un-opt-out-able (it is platform_mandatory), AUTO_DENY in 4h rather than 8h,
    and describe itself to the approver as an outbound payout.
    """
    assert (
        CATEGORY_RULES["ad_spend"].checkpoint_key != CATEGORY_RULES["payout"].checkpoint_key
    )
    row = next(r for r in CHECKPOINT_SEED if r["key"] == "before_ad_spend_above_band")
    assert row["platform_mandatory"] is False
    assert row["on_timeout"] == "auto_deny"   # money out fails safe on silence
    assert row["sla_seconds"] == 28800


def test_broadcast_checkpoint_parks_rather_than_denies() -> None:
    """An unposted post can wait; it should re-raise, not be denied."""
    row = next(r for r in CHECKPOINT_SEED if r["key"] == "before_public_broadcast")
    assert row["on_timeout"] == "auto_park"
    assert row["platform_mandatory"] is False


# ── The gate actually bites ──────────────────────────────────────────


def test_a1_publish_raises_a_card() -> None:
    """The headline: at A1 a public post now needs a human.

    This is the test the T7 mutation targets — delete the
    ``linkedin_create_post`` mapping and this must fail, alone.
    """
    decision = evaluate_policy(
        _intent(action_category=category_for_tool("linkedin_create_post")),
        _gov(AutonomyLevel.A1),
    )
    assert decision.decision == RAISE_HITL
    assert decision.checkpoint_key == "before_public_broadcast"


def test_a2_publish_is_autonomous() -> None:
    """At A2+ comms are autonomous — the same shape email_dispatch has.

    Stated because it is the deliberate half of decision 1: making every post
    an approval at every band would push tenants to post outside the platform.
    """
    decision = evaluate_policy(
        _intent(action_category="broadcast"), _gov(AutonomyLevel.A2)
    )
    assert decision.decision == PASS


def test_a0_publishes_nothing() -> None:
    decision = evaluate_policy(
        _intent(action_category="broadcast"), _gov(AutonomyLevel.A0)
    )
    assert decision.decision == BLOCK


@pytest.mark.parametrize(
    "amount,expected",
    [
        (50.0, PASS),          # inside the default 200 band
        (500.0, RAISE_HITL),   # above the band, below the ceiling
        (9000.0, BLOCK),       # above the 5000 hard block — no band may allow it
    ],
)
def test_ad_spend_respects_its_band(amount: float, expected: str) -> None:
    decision = evaluate_policy(
        _intent(action_category="ad_spend", amount_usd=amount),
        _gov(AutonomyLevel.A2),
    )
    assert decision.decision == expected


def test_ad_spend_band_is_tenant_tunable() -> None:
    """A tenant that raises its own band gets its own answer — the same
    mechanism every other monetary category uses."""
    decision = evaluate_policy(
        _intent(action_category="ad_spend", amount_usd=500.0),
        _gov(AutonomyLevel.A2, ad_spend_usd=1000.0),
    )
    assert decision.decision == PASS
    assert decision.band == 1000.0


def test_untrusted_context_cannot_drive_ad_spend() -> None:
    """Decision 2 end-to-end: a counterparty-trust run cannot commit budget."""
    decision = evaluate_policy(
        _intent(
            action_category="ad_spend",
            amount_usd=10.0,
            counterparty_trust="counterparty",
        ),
        _gov(AutonomyLevel.A3),
    )
    assert decision.decision in (RAISE_HITL, BLOCK)
    assert decision.decision != PASS
