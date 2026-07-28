"""Inc-7 prereq / voice go-live — Pragya's entity template, pure.

The seeder closes a gap that sat open from Increment 3: every resolver said
"the tenant's Pragya entity, *if one is seeded*" and nothing ever seeded one.
The tests that matter here are the ones that would let it reopen — a name the
resolvers cannot find, or a governance block that quietly widens.
"""
from __future__ import annotations

from src.ai.pragya.children import PRAGYA_ENTITY_NAMES
from src.ai.pragya.seed import PRAGYA_NAME, pragya_template


class TestTheResolversCanFindHer:
    def test_the_seeded_name_matches_what_the_resolvers_search_for(self):
        """The load-bearing test. `pragya_entity_for` and `available_children`
        both match on PRAGYA_ENTITY_NAMES; a rename here that missed that tuple
        would seed an entity nothing could ever find, and the failure would look
        like "voice is not configured" rather than like a rename."""
        assert any(n in PRAGYA_NAME.lower() for n in PRAGYA_ENTITY_NAMES), (
            f"{PRAGYA_NAME!r} matches none of {PRAGYA_ENTITY_NAMES}")

    def test_the_template_name_is_the_constant(self):
        assert pragya_template()["name"] == PRAGYA_NAME

    def test_she_is_an_active_agent(self):
        """`available_children` only treats AGENT and PROCESS as callable, and
        a DRAFT entity is not a colleague anyone can reach."""
        template = pragya_template()
        assert template["type"] == "AGENT"
        assert template["status"] == "ACTIVE"


class TestGovernance:
    def test_she_starts_at_a1(self):
        """Every categorised external effect raises a card — the right default
        for the thing that answers the phone."""
        assert pragya_template()["governance"]["autonomy_level"] == "A1"

    def test_she_is_not_a_karuna_gateway(self):
        """Karuna is the *outward* posture, for counterparty-facing gateways.
        Pragya is the inward face; marking her a gateway would apply the wrong
        threat model to the owner's own steward."""
        assert pragya_template()["governance"]["karuna_profile"] is False

    def test_her_memory_domains_start_narrow(self):
        assert pragya_template()["governance"]["memory_domains"] == ["general"]

    def test_strategy_is_not_granted(self):
        """04a §8.9 — no entity is granted the `strategy` domain by default,
        Pragya included. Board minutes stay invisible until someone grants it
        deliberately, and this test is where that decision is pinned."""
        assert "strategy" not in pragya_template()["governance"]["memory_domains"]

    def test_every_declared_domain_is_a_real_one(self):
        from src.ai.tenant_schema.hbs_seed import DOMAIN_TAGS

        for domain in pragya_template()["governance"]["memory_domains"]:
            assert domain in DOMAIN_TAGS, domain

    def test_she_has_a_cost_ceiling_and_a_timeout(self):
        """An account manager on an open phone line with no ceiling is an
        unbounded bill waiting for a bad turn."""
        governance = pragya_template()["governance"]
        assert governance["max_cost_usd"] > 0
        assert governance["timeout_ms"] > 0


class TestCapabilities:
    def test_she_proposes_no_raw_tools(self):
        """Inc-4 decision 6: her surface is her *child entities*, not a tool
        allow-list — a child is governed where governance already lives, and an
        allow-list would need a second, weaker story beside it."""
        assert pragya_template()["capabilities"]["tools"] == []

    def test_memory_is_enabled(self):
        memory = pragya_template()["capabilities"]["memory"]
        assert memory["enabled"] is True
