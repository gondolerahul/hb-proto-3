"""strategy/governance.py — who may decide, and what a decision may say (STRAT T5).

Two gates, and they are different gates — the same distinction AUTH's docstring
draws between the PolicyGate and `require_tier`:

* **`STRATEGY_RESOLUTION` (T2)** asks *did this human prove enough to adopt?*
  Enforced at the REST handler through `inward_auth/guard.enforce_kind`, in the
  handler body — never a `Depends`, because this repo's router tests call
  handlers directly and a declarative gate would be invisible to every test
  claiming to cover the route.
* **The write policy** asks *is this change a legal move, whoever asked?* It
  fills the `tenant_schema/write_policy` seam and applies to humans and agents
  alike.

**Revoking is not gated.** The asymmetry VG-05 established: the safe direction
must never be harder than the unsafe one. Adopting a resolution needs T2;
revoking one needs an ordinary session.

**Agents may draft, never adopt.** Today that is doubly true and it is worth
knowing why, because the second half is what will still hold when the first
stops: `_owner_gate` already makes *every* agent write to a Planning object a
proposal, since the Planning owner process has no seeded agent to own them
(04a §7.1). If a planning agent is ever seeded, that protection disappears
and only this policy remains.
So the rule is written against `actor_process_code` rather than relying on the
ownership gate, and it is tested by simulating exactly that future.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.ai.strategy.pipeline import PLANNING_OBJECTS, validate_write

logger = logging.getLogger(__name__)

__all__ = [
    "AGENT_FORBIDDEN_WRITES",
    "agent_may_write",
    "strategy_write_policy",
    "install_strategy_write_policy",
]

#: `object -> field -> values an agent may not set`. A table rather than an
#: `if`, so adding a decision-shaped field is an edit to data that a totality
#: test can read, not a branch somebody has to notice.
AGENT_FORBIDDEN_WRITES: dict[str, dict[str, frozenset[str]]] = {
    # Adopting is the act that turns a suggestion into the business's decision.
    # An agent may write the Proposition all day; it may not carry the motion.
    "Resolution": {"status": frozenset({"active"})},
}


def agent_may_write(
    object_name: str, data: dict[str, Any], actor_process_code: Optional[str],
) -> Optional[str]:
    """Refusal reason for an agent-originated write, or None.

    `actor_process_code is None` is the human / admin / API path and is never
    refused here — that path is gated by `STRATEGY_RESOLUTION` at the router
    instead, which is where a *human* is asked to prove themselves.
    """
    if actor_process_code is None:
        return None
    forbidden = AGENT_FORBIDDEN_WRITES.get(object_name)
    if not forbidden:
        return None
    for field, values in forbidden.items():
        if field in data and data[field] in values:
            return (f"{actor_process_code} may not set {object_name}.{field} to "
                    f"{data[field]!r} — an agent may draft a proposition, only a "
                    "human adopts a resolution")
    return None


def strategy_write_policy(
    def_name: str, data: dict[str, Any],
    current_data: Optional[dict[str, Any]] = None,
    actor_process_code: Optional[str] = None,
) -> Optional[str]:
    """The `WritePolicy` STRAT installs. Refusal reason, or None to allow."""
    if def_name not in PLANNING_OBJECTS:
        return None

    refusal = agent_may_write(def_name, data, actor_process_code)
    if refusal is not None:
        return refusal

    verdict = validate_write(def_name, data, current=current_data)
    return None if verdict else verdict.reason


def install_strategy_write_policy() -> None:
    """Fill the record service's write-policy seam. Called at boot.

    Registered at the entry points (`main.py` and `worker.py`) beside
    `install_consent_registry` and `register_solo_pack_tools`, not from a
    package `__init__` — importing a policy from an init is how the Solo Pack
    tools cycled.
    """
    from src.ai.tenant_schema.write_policy import set_write_policy

    set_write_policy(strategy_write_policy)
    logger.info("STRAT: object write policy installed")
