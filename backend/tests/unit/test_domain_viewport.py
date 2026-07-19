"""Inc 1 / SCH — need-to-know memory viewport (technical doc §24.3).

The enforcement primitive "share knowledge, not habits": a support agent
scoped to ["general","crm"] provably cannot see a payroll-tagged node. Pure
functions + the assemble_memory wiring; the §24.4 retrieval upgrade that
stamps per-node domains end-to-end is Increment 2.
"""
from __future__ import annotations

import pytest

from src.ai.memory.domain_viewport import (
    filter_by_domain,
    is_node_visible,
    resolve_allowed_domains,
)


class TestResolveAllowedDomains:
    def test_absent_is_unrestricted(self):
        assert resolve_allowed_domains({}) is None
        assert resolve_allowed_domains({"memory_domains": []}) is None

    def test_list_includes_general_implicitly(self):
        allowed = resolve_allowed_domains({"memory_domains": ["crm"]})
        assert allowed == frozenset({"crm", "general"})

    def test_reads_typed_governance(self):
        from src.ai.schemas.governance import Governance
        gov = Governance.model_validate({"memory_domains": ["financial"]})
        assert resolve_allowed_domains(gov) == frozenset({"financial", "general"})


class TestIsNodeVisible:
    def test_unrestricted_sees_everything(self):
        assert is_node_visible("payroll", None) is True

    def test_untagged_node_is_general(self):
        assert is_node_visible(None, frozenset({"general", "crm"})) is True

    def test_payroll_excluded_from_general_crm(self):
        allowed = frozenset({"general", "crm"})
        assert is_node_visible("payroll", allowed) is False
        assert is_node_visible("crm", allowed) is True
        assert is_node_visible("general", allowed) is True


class TestFilterByDomain:
    def _nodes(self):
        return [
            {"id": 1, "domain": "general", "text": "hours are 9-5"},
            {"id": 2, "domain": "crm", "text": "Acme is a customer"},
            {"id": 3, "domain": "payroll", "text": "salary is X"},
            {"id": 4, "domain": "legal", "text": "the NDA says Y"},
            {"id": 5, "text": "untagged note"},
        ]

    def test_support_agent_cannot_see_payroll_or_legal(self):
        allowed = resolve_allowed_domains({"memory_domains": ["crm"]})
        visible = filter_by_domain(self._nodes(), allowed,
                                   domain_getter=lambda n: n.get("domain"))
        ids = {n["id"] for n in visible}
        assert ids == {1, 2, 5}   # general, crm, untagged(=general) — NOT payroll/legal

    def test_unrestricted_keeps_all(self):
        visible = filter_by_domain(self._nodes(), None,
                                   domain_getter=lambda n: n.get("domain"))
        assert len(visible) == 5


class TestAssemblerWiring:
    @pytest.mark.asyncio
    async def test_assemble_memory_applies_viewport(self, monkeypatch):
        """assemble_memory drops out-of-domain nodes from the assembled context."""
        import src.ai.memory.assembler as asm

        async def _fake_v2(*_a, **_k):
            return {"__episodic_memory__": [
                {"domain": "crm", "text": "call log"},
                {"domain": "payroll", "text": "comp discussion"},
            ]}

        monkeypatch.setattr(asm, "_assemble_v2", _fake_v2)
        allowed = resolve_allowed_domains({"memory_domains": ["crm"]})
        result = await asm.assemble_memory(
            db=None, company_id=None, entity_id=None,  # type: ignore[arg-type]
            memory_scope="INTELLIGENCE_ONLY",  # skip the legacy episodic top-up
            allowed_domains=allowed,
        )
        episodes = result["__episodic_memory__"]
        assert len(episodes) == 1
        assert episodes[0]["domain"] == "crm"
