"""Inc 2 / TRUST — the platform-initiated cost classification (B13).

Platform-initiated work (Meta-Agent iterations, self-healing/dreaming, sandbox +
test builds) is a distinct class from tenant-requested work — that split is what
lets platform spend draw from its own capped envelope. The admission + envelope
separation are exercised against a live DB in test_platform_budget_db.py.
"""
from __future__ import annotations

from src.ai.services.cost_attribution import (
    CostAttribution,
    PLATFORM_INITIATED_ATTRIBUTIONS,
)


class TestClassification:
    def test_platform_kinds_are_platform(self):
        for kind in (CostAttribution.META_REVIEW, CostAttribution.DREAMING,
                     CostAttribution.SANDBOX, CostAttribution.TEST_DRIVER,
                     CostAttribution.META_SPEC_CRITIC):
            assert kind.value in PLATFORM_INITIATED_ATTRIBUTIONS

    def test_tenant_kinds_are_not_platform(self):
        for kind in (CostAttribution.PLANNER, CostAttribution.ACTOR_STEP,
                     CostAttribution.TOOL, CostAttribution.CRITIC_PRE,
                     CostAttribution.CHILD_RUN):
            assert kind.value not in PLATFORM_INITIATED_ATTRIBUTIONS

    def test_platform_set_is_a_strict_subset(self):
        all_kinds = {a.value for a in CostAttribution}
        assert PLATFORM_INITIATED_ATTRIBUTIONS < all_kinds
