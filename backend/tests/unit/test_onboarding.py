"""Inc 2 / ONBOARD — the wizard step services (pure steps).

The bundle picker (step 4) and the governance preview (step 3) are pure over
the curated templates — the contract Pragya drives in Inc 3. Activation +
status are exercised against a live tenant in test_onboarding_db.py.
"""
from __future__ import annotations

import pytest

from src.ai.solo_pack.onboarding import governance_preview, list_bundles


class TestListBundles:
    def test_solo_pack_plus_seven(self):
        bundles = list_bundles()
        assert len(bundles) == 8  # Solo Pack default + 7 starter bundles
        assert bundles[0]["key"] == "solo_pack"
        assert bundles[0]["is_default"] is True

    def test_solo_pack_activates_all_six_processes(self):
        solo = list_bundles()[0]
        assert solo["process_codes"] == ["P03", "P06", "P08", "P10", "P14", "P19"]
        assert solo["agent_count"] == 12  # the "12 agents": 3 gateways + 9 workforce

    def test_unpopulated_bundles_flagged_unavailable(self):
        by_key = {b["key"]: b for b in list_bundles()}
        # Fulfillment (P05/P15) + Talent (P12) have no Wave-0 process yet.
        assert by_key["fulfillment"]["available_now"] is False
        assert by_key["talent"]["available_now"] is False
        assert by_key["fiscal"]["available_now"] is True

    def test_full_membership_exposed_for_future(self):
        fiscal = {b["key"]: b for b in list_bundles()}["fiscal"]
        # The picker shows the full §2.1 membership even though only P08/P10 seed now.
        assert set(fiscal["all_processes"]) == {"P08", "P09", "P10", "P11", "P18"}
        assert fiscal["process_codes"] == ["P08", "P10"]


class TestGovernancePreview:
    def test_every_entity_is_a1(self):
        preview = governance_preview("solo_pack")
        summaries = list(preview["gateways"])
        for proc in preview["processes"]:
            summaries.append(proc["process"])
            summaries.extend(proc["agents"])
        for s in summaries:
            assert s["autonomy_level"] == "A1", s["name"]

    def test_shows_finance_sod_roles(self):
        preview = governance_preview("fiscal")
        agents = {a["code"]: a for proc in preview["processes"] for a in proc["agents"]}
        assert agents["AGT-038"]["sod_class"] == "maker"
        assert agents["AGT-046"]["sod_class"] == "checker"

    def test_gateways_have_no_authority(self):
        preview = governance_preview("solo_pack")
        for gw in preview["gateways"]:
            assert gw["authority"] is None  # gateways carry no monetary reach

    def test_agent_codes_resolved_from_tags(self):
        preview = governance_preview("growth")
        codes = {a["code"] for proc in preview["processes"] for a in proc["agents"]}
        assert codes == {"AGT-013", "AGT-015"}

    def test_unknown_bundle_raises(self):
        with pytest.raises(ValueError):
            governance_preview("no-such-bundle")
