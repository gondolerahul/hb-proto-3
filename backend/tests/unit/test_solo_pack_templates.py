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
    KAR_02_EMAIL,
    P03_ACQUISITION,
    SLICE_TEMPLATES,
)


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
