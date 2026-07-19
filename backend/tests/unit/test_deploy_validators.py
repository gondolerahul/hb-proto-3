"""Inc 1 / GOV — deploy-time governance validators (technical doc §20.5).

Pure checks that fail closed: Karuna gate, SoD conflicts, autonomy caps.
"""
from __future__ import annotations

from src.ai.governance.deploy_validators import (
    check_autonomy_cap,
    check_karuna_gate,
    check_sod_conflicts,
    run_governance_deploy_checks,
)


class TestKarunaGate:
    def test_no_binding_passes(self):
        name, passed, _ = check_karuna_gate({"governance": {}})
        assert name == "karuna_gate" and passed

    def test_bound_without_profile_fails(self):
        spec = {"metadata_extensions": {"telephony_provider": "tata"}, "governance": {}}
        _, passed, reason = check_karuna_gate(spec)
        assert not passed and "karuna_profile" in reason

    def test_bound_with_profile_passes(self):
        spec = {
            "metadata_extensions": {"telephony_provider": "tata"},
            "governance": {"karuna_profile": True},
        }
        _, passed, _ = check_karuna_gate(spec)
        assert passed

    def test_channels_capability_counts_as_binding(self):
        spec = {"capabilities": {"channels": ["whatsapp"]}, "governance": {}}
        _, passed, _ = check_karuna_gate(spec)
        assert not passed


class TestSoDConflicts:
    def test_clean_entity_passes(self):
        _, passed, _ = check_sod_conflicts({"capabilities": {"sod_tags": ["operate"]}})
        assert passed

    def test_maker_checker_conflict_fails(self):
        spec = {"capabilities": {"sod_tags": ["financial_maker", "financial_checker"]}}
        _, passed, reason = check_sod_conflicts(spec)
        assert not passed and "segregation" in reason

    def test_vendor_create_and_pay_conflict(self):
        spec = {"capabilities": {"sod_tags": ["vendor_create", "vendor_pay"]}}
        _, passed, _ = check_sod_conflicts(spec)
        assert not passed

    def test_self_promote_quarantined(self):
        spec = {"capabilities": {"sod_tags": ["self_promote"]}}
        _, passed, reason = check_sod_conflicts(spec)
        assert not passed and "quarantine" in reason

    def test_auditor_operate_conflict(self):
        spec = {"capabilities": {"sod_tags": ["audit", "operate"]}}
        _, passed, _ = check_sod_conflicts(spec)
        assert not passed


class TestAutonomyCap:
    def test_a1_default_passes(self):
        _, passed, _ = check_autonomy_cap({"governance": {}})
        assert passed

    def test_a1_explicit_passes(self):
        _, passed, _ = check_autonomy_cap({"governance": {"autonomy_level": "A1"}})
        assert passed

    def test_a2_at_birth_fails(self):
        _, passed, reason = check_autonomy_cap({"governance": {"autonomy_level": "A2"}})
        assert not passed and "promotion" in reason

    def test_a0_allowed(self):
        _, passed, _ = check_autonomy_cap({"governance": {"autonomy_level": "A0"}})
        assert passed

    def test_unknown_level_fails(self):
        _, passed, _ = check_autonomy_cap({"governance": {"autonomy_level": "A9"}})
        assert not passed


class TestRunAll:
    def test_all_pass_for_clean_entity(self):
        results = run_governance_deploy_checks({"governance": {"autonomy_level": "A1"}})
        assert all(passed for _, passed, _ in results)
        assert len(results) == 4  # karuna, sod, autonomy, parent_of_loop

    def test_parent_of_loop_rejected(self):
        results = run_governance_deploy_checks({
            "type": "LOOP", "parent_id": "x", "parent_type": "PROCESS",
            "governance": {"autonomy_level": "A1"},
        })
        assert any(name == "parent_of_loop" and not passed for name, passed, _ in results)
