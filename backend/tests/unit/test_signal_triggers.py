"""Inc 1 / SIG — trigger-registry resolution is pure and deterministic.

The Blueprint's "exactly one owning Process per signal" rule made
mechanical: priority DESC, then process_entity_id ASC (§18.3). These are
the decision-table tests; DB-backed behavior lives in
tests/integration/test_signal_bus_db.py.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from src.ai.signals.triggers import pattern_matches, select_owner


def _reg(pattern: str, priority: int = 100, enabled: bool = True,
         entity_id: uuid.UUID | None = None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        process_entity_id=entity_id or uuid.uuid4(),
        type_pattern=pattern,
        priority=priority,
        enabled=enabled,
    )


class TestPatternMatches:
    def test_exact(self):
        assert pattern_matches("lead.inbound", "lead.inbound")
        assert not pattern_matches("lead.inbound", "lead.outbound")

    def test_prefix_glob(self):
        assert pattern_matches("lead.*", "lead.inbound")
        assert pattern_matches("lead.*", "lead.inbound.web")
        assert not pattern_matches("lead.*", "leader.elected")
        assert not pattern_matches("lead.*", "lead")

    def test_wildcard_all(self):
        assert pattern_matches("*", "anything.at.all")

    def test_exact_is_not_prefix(self):
        assert not pattern_matches("lead", "lead.inbound")


class TestSelectOwner:
    def test_no_match_returns_none(self):
        assert select_owner([_reg("payment.*")], "lead.inbound") is None

    def test_disabled_never_matches(self):
        assert select_owner([_reg("lead.*", enabled=False)], "lead.inbound") is None

    def test_highest_priority_wins(self):
        low = _reg("lead.*", priority=50)
        high = _reg("lead.inbound", priority=200)
        assert select_owner([low, high], "lead.inbound") is high

    def test_priority_beats_specificity_by_design(self):
        # Exact-vs-glob specificity is expressed through priority, not
        # special-cased (01_sig doc §1.3).
        glob = _reg("lead.*", priority=300)
        exact = _reg("lead.inbound", priority=100)
        assert select_owner([glob, exact], "lead.inbound") is glob

    def test_tie_breaks_on_entity_id_ascending(self):
        a_id = uuid.UUID("00000000-0000-0000-0000-00000000000a")
        b_id = uuid.UUID("00000000-0000-0000-0000-00000000000b")
        a = _reg("lead.*", priority=100, entity_id=a_id)
        b = _reg("lead.*", priority=100, entity_id=b_id)
        # Same result regardless of input order — deterministic.
        assert select_owner([b, a], "lead.inbound") is a
        assert select_owner([a, b], "lead.inbound") is a

    def test_wildcard_is_catchall_at_low_priority(self):
        catchall = _reg("*", priority=1)
        specific = _reg("payment.failed", priority=100)
        assert select_owner([catchall, specific], "payment.failed") is specific
        assert select_owner([catchall, specific], "unmapped.event") is catchall
