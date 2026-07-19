"""memory/domain_viewport.py — need-to-know memory scoping (technical doc §24.3).

"Share knowledge, not habits" has a mechanical edge: Knowledge and Episodic
nodes carry a **domain tag** (stamped at ingestion from the HBS module of
origin — the same vocabulary as ``hbs_seed.DOMAIN_TAGS``). An entity's
governance block carries ``memory_domains`` (an allow-list); its viewport
*cannot contain* a node outside that list. A support agent scoped to
``["general", "crm"]`` never sees a ``payroll`` node — prevented by
construction, not by prompt instruction.

Pure functions here; wired into ``assemble_memory`` at viewport-assembly time.
The retrieval stack that carries per-node domain metadata end-to-end is the
§24.4 upgrade (Increment 2); this is the enforcement primitive it plugs into.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

__all__ = [
    "GENERAL_DOMAIN",
    "resolve_allowed_domains",
    "is_node_visible",
    "filter_by_domain",
]

GENERAL_DOMAIN = "general"


def resolve_allowed_domains(governance: Any) -> Optional[frozenset[str]]:
    """The entity's memory-domain allow-list, or ``None`` for "no restriction".

    Accepts a governance dict or a typed ``Governance`` model. An empty/absent
    ``memory_domains`` means unrestricted (None) — the default for entities
    that have not opted into need-to-know scoping. ``general`` is always
    implicitly included so common knowledge is never walled off.
    """
    raw: Any = None
    if isinstance(governance, dict):
        raw = governance.get("memory_domains")
    else:
        raw = getattr(governance, "memory_domains", None)
    if not raw:
        return None
    return frozenset({str(d) for d in raw} | {GENERAL_DOMAIN})


def is_node_visible(node_domain: Optional[str], allowed: Optional[frozenset[str]]) -> bool:
    """True when a node of ``node_domain`` may enter the viewport.

    No allow-list → everything visible. An untagged node (``None``) is treated
    as ``general`` (common knowledge), so legacy/un-tagged memory is never
    hidden — only explicitly-tagged sensitive domains are gated.
    """
    if allowed is None:
        return True
    domain = node_domain or GENERAL_DOMAIN
    return domain in allowed


def filter_by_domain(
    nodes: Iterable[Any],
    allowed: Optional[frozenset[str]],
    *,
    domain_getter: Callable[[Any], Optional[str]],
) -> list[Any]:
    """Drop nodes whose domain is outside the allow-list (§24.3)."""
    if allowed is None:
        return list(nodes)
    return [n for n in nodes if is_node_visible(domain_getter(n), allowed)]
