"""tenant_schema/validation.py — validate a record's data against its def (§19.2).

Pure functions (no IO): given a def's `fields` and an incoming `data` dict,
check required/type/enum constraints, resolve field aliases (§19.4), and pull
out ref assignments so the record service can materialise link rows. Ref
*targets* are verified against the DB by the record service, not here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Any, Callable

__all__ = ["RefAssignment", "ValidationError", "validate_record_data", "resolve_alias"]

_SCALAR_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "text": lambda v: isinstance(v, str),
    "email": lambda v: isinstance(v, str),
    "phone": lambda v: isinstance(v, str),
    "url": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "decimal": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "json": lambda v: True,
    "artifact": lambda v: isinstance(v, str),
}


class ValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class RefAssignment:
    field_name: str
    target: str            # def name, or "*" (polymorphic)
    rel_type: str
    direction: str         # "out" (this→dst) | "in" (dst→this)
    dst_record_id: uuid.UUID


@dataclass
class _ValidationResult:
    clean_data: dict[str, Any] = dc_field(default_factory=dict)
    refs: list[RefAssignment] = dc_field(default_factory=list)


def resolve_alias(fields: list[dict[str, Any]], key: str) -> str | None:
    """Map an incoming key to a canonical field name via name or aliases (§19.4)."""
    for f in fields:
        if f.get("name") == key:
            return str(f["name"])
        aliases = f.get("aliases") or []
        if key in aliases:
            return str(f["name"])
    return None


def _is_money(v: Any) -> bool:
    return isinstance(v, dict) and "amount" in v


def _is_datelike(v: Any) -> bool:
    if isinstance(v, (date, datetime)):
        return True
    if isinstance(v, str):
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return False


def validate_record_data(
    fields: list[dict[str, Any]],
    data: dict[str, Any],
    *,
    partial: bool = False,
) -> _ValidationResult:
    """Validate ``data`` against a def's ``fields``.

    ``partial`` (update path) skips required-field checks for absent fields.
    Raises :class:`ValidationError` with all problems collected. Returns the
    normalised data (canonical field names) plus the ref assignments to
    materialise. Hidden fields (§19.4) are dropped from writes; deprecated
    fields validate but warn.
    """
    by_name = {f["name"]: f for f in fields}
    result = _ValidationResult()
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for raw_key, value in data.items():
        canonical = resolve_alias(fields, raw_key)
        if canonical is None:
            errors.append(f"unknown field '{raw_key}'")
            continue
        spec = by_name[canonical]
        seen.add(canonical)
        lifecycle = spec.get("lifecycle", "active")
        if lifecycle == "hidden":
            continue  # dropped from writes, retained in stored data elsewhere
        if lifecycle == "deprecated":
            warnings.append(f"field '{canonical}' is deprecated")

        if value is None:
            result.clean_data[canonical] = None
            continue

        ftype = spec.get("type", "string")
        if ftype == "ref":
            ref = _validate_ref(canonical, spec, value, errors)
            if ref is not None:
                result.refs.append(ref)
            continue
        if not _check_scalar(ftype, spec, value, canonical, errors):
            continue
        result.clean_data[canonical] = value

    if not partial:
        for name, spec in by_name.items():
            if spec.get("required") and name not in seen:
                errors.append(f"missing required field '{name}'")
            rw = spec.get("required_when")
            if rw and name not in seen:
                for dep_key, dep_val in rw.items():
                    if data.get(dep_key) == dep_val:
                        errors.append(f"field '{name}' is required when {dep_key}={dep_val}")

    if errors:
        raise ValidationError(errors)
    return result


def _validate_ref(
    name: str, spec: dict[str, Any], value: Any, errors: list[str],
) -> RefAssignment | None:
    try:
        dst_id = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        errors.append(f"ref field '{name}' must be a record id, got {value!r}")
        return None
    return RefAssignment(
        field_name=name,
        target=str(spec.get("target", "*")),
        rel_type=str(spec.get("rel", "attached_to")),
        direction=str(spec.get("direction", "out")),
        dst_record_id=dst_id,
    )


def _check_scalar(
    ftype: str, spec: dict[str, Any], value: Any, name: str, errors: list[str],
) -> bool:
    if ftype == "enum":
        values = spec.get("values") or []
        if value not in values:
            errors.append(f"field '{name}'={value!r} not in enum {values}")
            return False
        return True
    if ftype == "money":
        if not _is_money(value):
            errors.append(f"field '{name}' must be a money object {{amount,currency}}")
            return False
        return True
    if ftype in ("date", "datetime"):
        if not _is_datelike(value):
            errors.append(f"field '{name}' must be an ISO {ftype}")
            return False
        return True
    check = _SCALAR_CHECKS.get(ftype)
    if check is None:
        errors.append(f"field '{name}' has unknown type '{ftype}'")
        return False
    if not check(value):
        errors.append(f"field '{name}' failed type check for '{ftype}'")
        return False
    return True
