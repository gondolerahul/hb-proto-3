"""tenant_schema/write_policy.py — a pluggable per-object write rule.

The record service already answers *who* may write (owner-writes / others-
propose) and *whether the shape is valid* (`validate_record_data`). Neither
answers *whether this particular change is a legal move* — that a Proposition
may only be adopted from `tabled`, that a Mandate may not issue from a revoked
Resolution, that an honesty grade must have a run behind it.

Those rules are domain knowledge belonging to the workstream that owns the
objects, not to the record service. So this is a seam, in exactly the shape KAR
used for consent and Inc-4 used for SoR write-back: the policy lives in
``ai/strategy/``, installs itself at boot, and the enforcement call sits at the
existing write path. The record service stays ignorant of Planning.

**Refuse, do not raise.** A policy refusal is a normal answer a surface renders,
not an exception — the same choice `PROPOSED` and `CONFLICT` make.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

__all__ = ["WritePolicy", "set_write_policy", "check_write_policy"]

#: ``(def_name, data, current_data, actor_process_code) -> refusal reason or None``.
#: ``current_data`` is None on a create. ``actor_process_code`` is None for the
#: human/admin/API path and set for an agent-originated write.
WritePolicy = Callable[
    [str, dict[str, Any], Optional[dict[str, Any]], Optional[str]], Optional[str]]

_policy: Optional[WritePolicy] = None


def set_write_policy(policy: Optional[WritePolicy]) -> None:
    """Install (or clear, with None) the object write policy."""
    global _policy
    _policy = policy


def check_write_policy(
    def_name: str, data: dict[str, Any],
    current_data: Optional[dict[str, Any]] = None,
    actor_process_code: Optional[str] = None,
) -> Optional[str]:
    """The refusal reason, or None to allow.

    **Fails open on an unexpected error**, and the asymmetry is deliberate: an
    object rule is a correctness guard over a tenant's own records, not a
    security control, and a policy bug that made every write in the product
    fail would be a far worse outcome than one illegal state transition. The
    security controls in this codebase (the PolicyGate, `require_tier`, the
    ownership gate) all fail *closed*, and none of them route through here.
    """
    if _policy is None:
        return None
    try:
        return _policy(def_name, data, current_data, actor_process_code)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        logger.warning("write policy raised on %s; allowing the write: %s",
                       def_name, exc)
        return None
