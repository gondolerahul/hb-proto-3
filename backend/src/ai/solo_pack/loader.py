"""solo_pack/loader.py — validate curated templates before they become seed data.

A template is only fit to ship if it (1) parses through the shipped
``HierarchicalEntityCreate`` schema — which validates the GOV typed-governance
block (autonomy, authority bands, sod_class, checkpoint keys) — and (2) passes
the §20.5 deploy validators (Karuna gate, SoD, autonomy cap, parent-of-LOOP).
The loader runs both, so a malformed template fails in CI, never at a tenant.
"""
from __future__ import annotations

from typing import Any

__all__ = ["validate_template", "validate_all", "TemplateError"]


class TemplateError(ValueError):
    def __init__(self, name: str, errors: list[str]) -> None:
        self.template_name = name
        self.errors = errors
        super().__init__(f"template '{name}' invalid: " + "; ".join(errors))


def validate_template(template: dict[str, Any]) -> list[str]:
    """Return a list of problems with a template (empty = valid)."""
    errors: list[str] = []
    name = str(template.get("name", "<unnamed>"))

    # 1. Schema + typed governance (the GOV Pydantic block).
    try:
        from src.ai.schemas import HierarchicalEntityCreate

        HierarchicalEntityCreate.model_validate(template)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"schema/governance validation failed: {exc}")

    # 2. Deploy-time governance checks (fail closed).
    try:
        from src.ai.governance.deploy_validators import run_governance_deploy_checks

        for check, passed, reason in run_governance_deploy_checks(template):
            if not passed:
                errors.append(f"deploy check '{check}': {reason}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"deploy validation errored: {exc}")

    # 3. Solo Pack conventions: an agent_code/process_code tag or metadata id.
    tags = template.get("tags") or []
    meta = template.get("metadata_extensions") or {}
    has_code = (
        any(str(t).startswith(("agent_code:", "process_code:")) for t in tags)
        or meta.get("agent_code") or meta.get("process_code")
    )
    if not has_code:
        errors.append("missing a stable agent_code/process_code (tag or metadata)")

    return errors


def validate_all(templates: list[dict[str, Any]]) -> None:
    """Raise ``TemplateError`` on the first invalid template."""
    for template in templates:
        errors = validate_template(template)
        if errors:
            raise TemplateError(str(template.get("name", "<unnamed>")), errors)
