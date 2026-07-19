"""Inc 1 / GOV — the typed governance block validates at the boundary (§20.1).

Malformed governance fails Pydantic validation (→ 422 at the API); valid
blocks round-trip; unknown keys are preserved (extra="allow") so kernel
fields aren't silently dropped on save.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ai.schemas.governance import (
    AutonomyLevel,
    Governance,
    SoDClass,
)


class TestTypedValidation:
    def test_default_is_a1(self):
        assert Governance().autonomy_level == AutonomyLevel.A1
        assert Governance().sod_class == SoDClass.NONE

    def test_bad_autonomy_level_rejected(self):
        with pytest.raises(ValidationError):
            Governance.model_validate({"autonomy_level": "A9"})

    def test_bad_sod_class_rejected(self):
        with pytest.raises(ValidationError):
            Governance.model_validate({"sod_class": "overlord"})

    def test_authority_bands_typed(self):
        gov = Governance.model_validate({
            "autonomy_level": "A2",
            "authority": {"payout_usd": 500, "discount_pct": 10},
        })
        assert gov.authority.payout_usd == 500.0
        assert gov.authority.discount_pct == 10.0

    def test_bad_authority_amount_rejected(self):
        with pytest.raises(ValidationError):
            Governance.model_validate({"authority": {"payout_usd": "lots"}})


class TestFieldPreservation:
    def test_unknown_kernel_keys_preserved(self):
        # extra="allow": a kernel field we haven't modelled must survive a
        # round-trip rather than being dropped on save.
        gov = Governance.model_validate({
            "autonomy_level": "A1",
            "some_future_breaker_setting": {"threshold": 3},
        })
        dumped = gov.model_dump(mode="json")
        assert dumped["some_future_breaker_setting"] == {"threshold": 3}

    def test_max_concurrent_children_modelled(self):
        gov = Governance.model_validate({"max_concurrent_children": 4})
        assert gov.max_concurrent_children == 4

    def test_memory_domains_carried(self):
        gov = Governance.model_validate({"memory_domains": ["general", "financial"]})
        assert gov.memory_domains == ["general", "financial"]
