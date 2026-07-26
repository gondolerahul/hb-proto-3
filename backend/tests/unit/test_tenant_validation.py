"""Inc 1 / SCH — record validation is pure (technical doc §19.2).

Required/type/enum checks, alias resolution (§19.4), and ref extraction —
no DB. DB-backed record behaviour is in tests/integration/test_tenant_records_db.py.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.tenant_schema.validation import (
    ValidationError,
    resolve_alias,
    validate_record_data,
)

_FIELDS = [
    {"name": "name", "type": "string", "required": True},
    {"name": "amount", "type": "money", "aliases": ["value"]},
    {"name": "status", "type": "enum", "values": ["open", "closed"], "default": "open"},
    {"name": "count", "type": "integer"},
    {"name": "account", "type": "ref", "target": "Account", "rel": "belongs_to", "direction": "out"},
    {"name": "old_field", "type": "string", "lifecycle": "deprecated"},
    {"name": "hidden_field", "type": "string", "lifecycle": "hidden"},
]


class TestScalarValidation:
    def test_valid_record(self):
        r = validate_record_data(_FIELDS, {"name": "Acme", "status": "open", "count": 3})
        assert r.clean_data["name"] == "Acme"
        assert r.clean_data["count"] == 3

    def test_missing_required_fails(self):
        with pytest.raises(ValidationError) as ei:
            validate_record_data(_FIELDS, {"status": "open"})
        assert any("required" in e for e in ei.value.errors)

    def test_unknown_field_fails(self):
        with pytest.raises(ValidationError) as ei:
            validate_record_data(_FIELDS, {"name": "x", "bogus": 1})
        assert any("unknown field" in e for e in ei.value.errors)

    def test_bad_enum_fails(self):
        with pytest.raises(ValidationError):
            validate_record_data(_FIELDS, {"name": "x", "status": "invalid"})

    def test_bad_integer_type_fails(self):
        with pytest.raises(ValidationError):
            validate_record_data(_FIELDS, {"name": "x", "count": "three"})

    def test_bool_is_not_integer(self):
        with pytest.raises(ValidationError):
            validate_record_data(_FIELDS, {"name": "x", "count": True})

    def test_money_shape(self):
        r = validate_record_data(_FIELDS, {"name": "x", "amount": {"amount": 10, "currency": "INR"}})
        assert r.clean_data["amount"]["currency"] == "INR"

    def test_money_bad_shape_fails(self):
        with pytest.raises(ValidationError):
            validate_record_data(_FIELDS, {"name": "x", "amount": 10})

    def test_partial_skips_required(self):
        r = validate_record_data(_FIELDS, {"status": "closed"}, partial=True)
        assert r.clean_data["status"] == "closed"


class TestAliases:
    def test_resolve_alias(self):
        assert resolve_alias(_FIELDS, "value") == "amount"
        assert resolve_alias(_FIELDS, "amount") == "amount"
        assert resolve_alias(_FIELDS, "nope") is None

    def test_alias_normalises_on_write(self):
        r = validate_record_data(_FIELDS, {"name": "x", "value": {"amount": 5, "currency": "INR"}})
        assert "amount" in r.clean_data and "value" not in r.clean_data


class TestLifecycle:
    def test_deprecated_still_validates(self):
        r = validate_record_data(_FIELDS, {"name": "x", "old_field": "still ok"})
        assert r.clean_data["old_field"] == "still ok"

    def test_hidden_dropped_from_write(self):
        r = validate_record_data(_FIELDS, {"name": "x", "hidden_field": "gone"})
        assert "hidden_field" not in r.clean_data


class TestRefs:
    def test_ref_extracted_not_in_data(self):
        acc = uuid.uuid4()
        r = validate_record_data(_FIELDS, {"name": "x", "account": str(acc)})
        assert "account" not in r.clean_data
        assert len(r.refs) == 1
        assert r.refs[0].target == "Account"
        assert r.refs[0].rel_type == "belongs_to"
        assert r.refs[0].dst_record_id == acc

    def test_bad_ref_id_fails(self):
        with pytest.raises(ValidationError):
            validate_record_data(_FIELDS, {"name": "x", "account": "not-a-uuid"})


class TestHBSSpine:
    def test_spine_is_35_objects(self):
        # 27 through Inc 1; 35 from Inc 6 / STRAT's eight Planning objects.
        from src.ai.tenant_schema.hbs_seed import HBS_SPINE, hbs_object_names
        assert len(HBS_SPINE) == 35
        names = hbs_object_names()
        assert "Invoice" in names and "Vendor" in names and "Product/SKU" in names
        for planning in ("Objective", "Target", "Forecast", "Minutes",
                         "Proposition", "Resolution", "Mandate", "Review"):
            assert planning in names, planning

    def test_every_ref_targets_a_real_object(self):
        from src.ai.tenant_schema.hbs_seed import HBS_SPINE, hbs_object_names
        names = set(hbs_object_names())
        for obj in HBS_SPINE:
            for f in obj["fields"]:
                if f["type"] == "ref" and f["target"] != "*":
                    assert f["target"] in names, f"{obj['name']}.{f['name']} → {f['target']}"

    def test_every_object_has_owner_and_domain(self):
        from src.ai.tenant_schema.hbs_seed import HBS_SPINE, DOMAIN_TAGS
        for obj in HBS_SPINE:
            assert obj["owner"], obj["name"]
            assert obj["domain"] in DOMAIN_TAGS, obj["name"]
