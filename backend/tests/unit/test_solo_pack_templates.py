"""Inc 2 / SLICE — the curated Solo Pack templates are valid + well-formed.

The templates are the product's quality bar (reviewed like the HBS spine), so
CI proves each parses through the shipped entity schema + the GOV typed
governance + the deploy validators, and that the governance is complete (no
unset-band window on the sellable path).
"""
from __future__ import annotations

import pytest

from src.ai.solo_pack.loader import TemplateError, validate_all, validate_template
from src.ai.solo_pack.templates import (
    AGT_013,
    AGT_015,
    AGT_038,
    AGT_046,
    AGT_068,
    KAR_02_EMAIL,
    P03_ACQUISITION,
    PROCESS_GROUPS,
    SLICE_TEMPLATES,
    SOLO_PACK_TEMPLATES,
    process_codes,
    process_group,
)
from src.ai.tenant_schema.hbs_seed import HBS_SPINE


class TestValidity:
    def test_all_templates_validate(self):
        validate_all(SLICE_TEMPLATES)  # raises on any invalid

    def test_four_templates(self):
        assert len(SLICE_TEMPLATES) == 4

    @pytest.mark.parametrize("tpl", SLICE_TEMPLATES, ids=lambda t: t["name"])
    def test_each_is_clean(self, tpl):
        assert validate_template(tpl) == []


class TestGovernanceCompleteness:
    def test_all_a1(self):
        for t in SLICE_TEMPLATES:
            assert t["governance"]["autonomy_level"] == "A1"

    def test_gateway_has_karuna_and_no_money_authority(self):
        gov = KAR_02_EMAIL["governance"]
        assert gov["karuna_profile"] is True
        assert "authority" not in gov  # a gateway has no monetary authority

    def test_money_touching_agents_have_bands(self):
        # P03 + AGT-013 + AGT-015 carry explicit authority bands (closes the
        # Inc-1 unset-band pass-through window on the sellable path).
        for t in (P03_ACQUISITION, AGT_013, AGT_015):
            assert t["governance"].get("authority"), t["name"]

    def test_sod_maker_on_deal_closer(self):
        assert AGT_013["governance"]["sod_class"] == "maker"

    def test_memory_domains_scoped_to_crm(self):
        for t in SLICE_TEMPLATES:
            assert set(t["governance"]["memory_domains"]) <= {"general", "crm"}


class TestStructure:
    def test_p03_owns_the_acquisition_objects(self):
        meta = P03_ACQUISITION["metadata_extensions"]
        assert meta["process_code"] == "P03"
        assert set(meta["owns_objects"]) == {"Lead", "Opportunity", "Quote"}

    def test_p03_dispatches_both_agents(self):
        steps = P03_ACQUISITION["planning"]["static_plan"]["steps"]
        hints = {s["target"]["entity_name_hint"] for s in steps}
        assert hints == {"agt-013-inbound-deal-closer", "agt-015-proposal-quote"}

    def test_quote_send_is_checkpoint_gated(self):
        assert "before_high_value_email_dispatch" in AGT_015["governance"]["checkpoint_keys"]

    def test_a_malformed_template_is_rejected(self):
        bad = dict(KAR_02_EMAIL)
        bad = {**bad, "governance": {**bad["governance"], "autonomy_level": "A9"}}
        with pytest.raises(TemplateError):
            validate_all([bad])


# ── PACK: the full Wave-0 roster ─────────────────────────────────────────────
# HBS spine ownership rendered as its process code (`owner` → "P{nn}").
_SPINE_OWNER: dict[str, str] = {o["name"]: f"P{int(o['owner']):02d}" for o in HBS_SPINE}


class TestPackRoster:
    def test_all_pack_templates_validate(self):
        validate_all(SOLO_PACK_TEMPLATES)  # raises on any invalid

    @pytest.mark.parametrize("tpl", SOLO_PACK_TEMPLATES, ids=lambda t: t["name"])
    def test_each_is_clean(self, tpl):
        assert validate_template(tpl) == []

    def test_roster_is_sixteen(self):
        # 1 gateway + 6 processes + 9 workforce agents.
        assert len(SOLO_PACK_TEMPLATES) == 16

    def test_names_unique(self):
        names = [t["name"] for t in SOLO_PACK_TEMPLATES]
        assert len(names) == len(set(names))

    def test_six_wave0_processes(self):
        assert process_codes() == ["P03", "P06", "P08", "P10", "P14", "P19"]

    def test_nine_workforce_agents(self):
        codes = {
            tag.split(":", 1)[1]
            for g in PROCESS_GROUPS for a in g.agents
            for tag in a["tags"] if tag.startswith("agent_code:")
        }
        assert codes == {
            "AGT-013", "AGT-015", "AGT-030", "AGT-035", "AGT-092",
            "AGT-038", "AGT-046", "AGT-051", "AGT-068",
        }

    def test_every_agent_belongs_to_exactly_one_process(self):
        seen: dict[str, str] = {}
        for g in PROCESS_GROUPS:
            for a in g.agents:
                assert a["name"] not in seen, a["name"]
                seen[a["name"]] = g.process_code
        # every workforce template in the flat set is claimed by a group
        agent_names = {a["name"] for g in PROCESS_GROUPS for a in g.agents}
        flat_agents = {
            t["name"] for t in SOLO_PACK_TEMPLATES if t["type"] == "AGENT"
            and "gateway" not in t["tags"]
        }
        assert agent_names == flat_agents


class TestPackOwnershipMatchesSpine:
    """Each process's declared owns_objects must match the HBS spine owner code."""

    @pytest.mark.parametrize("group", PROCESS_GROUPS, ids=lambda g: g.process_code)
    def test_owns_objects_agree_with_spine(self, group):
        code = group.process_code
        for obj_name in group.process["metadata_extensions"]["owns_objects"]:
            assert _SPINE_OWNER.get(obj_name) == code, (obj_name, code)

    def test_p19_owns_nothing(self):
        p19 = process_group("P19")
        assert p19 is not None
        assert p19.process["metadata_extensions"]["owns_objects"] == []


class TestPackGovernance:
    def test_all_pack_a1(self):
        for t in SOLO_PACK_TEMPLATES:
            assert t["governance"]["autonomy_level"] == "A1", t["name"]

    def test_finance_segregation_of_duties(self):
        # maker ≠ checker across two owners; the deploy validator keeps a single
        # entity from being both — here they are structurally separate.
        assert AGT_038["governance"]["sod_class"] == "maker"
        assert AGT_046["governance"]["sod_class"] == "checker"
        assert AGT_038["capabilities"]["sod_tags"] == ["financial_maker"]
        assert AGT_046["capabilities"]["sod_tags"] == ["financial_checker"]

    def test_watchdog_is_read_only_auditor(self):
        assert AGT_068["governance"]["sod_class"] == "auditor"
        assert AGT_068["capabilities"]["sod_tags"] == ["audit"]
        # auditor independence: no 'operate' tag alongside 'audit'
        assert "operate" not in AGT_068["capabilities"]["sod_tags"]

    def test_finance_memory_domains_have_no_crm_leak(self):
        for name in ("agt-038-accounts-receivable", "agt-046-bookkeeping-reconciliation"):
            tpl = next(t for t in SOLO_PACK_TEMPLATES if t["name"] == name)
            domains = set(tpl["governance"]["memory_domains"])
            assert domains <= {"general", "financial"}
            assert "crm" not in domains

    def test_watchdog_memory_domains_are_legal_trust(self):
        assert set(AGT_068["governance"]["memory_domains"]) == {"general", "legal", "trust"}

    def test_p14_is_protected(self):
        p14 = process_group("P14")
        assert p14 is not None
        assert p14.process["metadata_extensions"].get("protected") is True

    def test_no_channel_facing_entity_has_unset_bands(self):
        # Any agent that can send_email carries explicit checkpoint governance
        # (closes the Inc-1 unset-band pass-through on the sellable path).
        for t in SOLO_PACK_TEMPLATES:
            tool_ids = {tc.get("tool_id") for tc in t.get("capabilities", {}).get("tools", [])}
            if "send_email" in tool_ids:
                assert t["governance"].get("checkpoint_keys"), t["name"]

    def test_deploy_validator_rejects_maker_and_checker_on_one_entity(self):
        # The §9.4 SoD rule: no single entity may be both maker and checker.
        bad = {**AGT_038, "name": "sod-violation",
               "capabilities": {**AGT_038["capabilities"],
                                "sod_tags": ["financial_maker", "financial_checker"]}}
        errs = validate_template(bad)
        assert any("segregation-of-duties" in e for e in errs), errs
