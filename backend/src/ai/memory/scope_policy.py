"""
ai.memory.scope_policy — Declarative ScopePolicy for CortexService
(Phase 11 Track 6).

When a :class:`CortexService` is constructed with
``scoped_subtree_root_id``, every operation must stay inside the
descendant set of that root. The legacy implementation enforced this
ad-hoc in a few places; Track 6 centralises it through a typed
:class:`ScopePolicy` object that the service consults uniformly.

Defaults are **strict** — the service raises :class:`ScopeViolation`
on the first attempt to read or write outside the scoped subtree. The
child-recursion code path that needs to read shared parent context
explicitly passes ``ScopePolicy(can_read_outside=True)``.

The policy is intentionally a tiny dataclass — feature flags
(``memory.scope_policy_enforced``) gate whether violations raise or
just warn, but the policy itself stays declarative.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScopePolicy:
    can_read_outside: bool = False
    can_write_outside: bool = False
    can_navigate_to_siblings: bool = False
    error_on_violation: bool = True

    @classmethod
    def child_recursion_default(cls) -> "ScopePolicy":
        """Default for child recursive runs: read parent, never write up."""
        return cls(
            can_read_outside=True,
            can_write_outside=False,
            can_navigate_to_siblings=False,
            error_on_violation=True,
        )


class ScopeViolation(RuntimeError):
    """Raised when a CortexService operation breaks its ScopePolicy."""

    def __init__(self, operation: str, target_id: str, scope_root_id: str):
        super().__init__(
            f"ScopeViolation: {operation} on {target_id} is outside scoped "
            f"subtree rooted at {scope_root_id}"
        )
        self.operation = operation
        self.target_id = target_id
        self.scope_root_id = scope_root_id


__all__ = ["ScopePolicy", "ScopeViolation"]
