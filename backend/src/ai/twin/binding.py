"""twin/binding.py — what makes a run happen *inside* the Glasshouse (GLASS X1).

TWIN built a substituted tool registry and nothing could consume it. The
shipped executor resolves tools from a **class-level global**
(``ToolRegistry.get_tool``) and the record-writing tool opens its tenant
session with ``Plane.LIVE`` by default — so a twin run assembled from
TWIN's pieces alone would have executed real tools against the real plane
while a beautifully tested substitution object sat unused beside it.

**The binding is the missing seam**: one frozen object, set for the
duration of one run, read in exactly three places.

1. ``resolve_tool`` — called at the two ``ToolRegistry.get_tool`` sites in
   ``ai/tool_executor.py``. One helper rather than two inline checks,
   because two would be two things to keep in step.
2. ``effective_plane`` — called inside ``TenantDataPlane.session``. When a
   binding is active the plane is **forced to TWIN regardless of the
   argument**: a tool inside a rehearsal cannot opt back into reality by
   asking for ``Plane.LIVE``. That is the plane-level counterpart of
   substitution's deny-by-default, and it is deliberately stronger than
   the design's "bound to a twin session" wording.
3. ``twin_bound`` — the runner, and nothing else, sets it.

**Why a contextvar rather than a parameter** (owner decision 1,
14_glass.md §2): the alternative threads a flag through ``AgentLoop.run``
→ the executors → every tool, and ``agent_loop.py`` is pinned at its
1500-line cap. A contextvar follows the async task by itself, resets on
exit even when the body raises, and — the property that actually matters
— **cannot be forgotten by a call site that does not know it exists**,
which is precisely how a threaded flag would fail.

**Concurrency**: contextvars are per-task, so two scenarios and a live run
in one worker process cannot see each other's bindings. That isolation is
the thing being bought.

This module is invisible plumbing on a path every live run takes, so it
is mutation-tested in **both** directions — no binding changes nothing;
inside a binding nothing escapes — each verified to fail on the injected
change.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator

__all__ = [
    "TwinBinding",
    "active_binding",
    "twin_bound",
    "resolve_tool",
    "effective_plane",
    "in_twin",
]


@dataclass(frozen=True)
class TwinBinding:
    """One run's simulation context.

    Frozen on purpose: a binding a run could edit half-way through is a
    binding whose guarantees hold only for the first half of the run.
    """

    company_id: uuid.UUID
    #: The substituted registry from ``twin.substitution.substituted_registry``.
    tools: dict[str, Any] = field(default_factory=dict)
    #: The ``CallRecorder`` those substituted tools write to.
    recorder: Any = None


_binding: ContextVar[TwinBinding | None] = ContextVar("twin_binding", default=None)


def active_binding() -> TwinBinding | None:
    """The binding for the current task, or ``None`` in ordinary life."""
    return _binding.get()


def in_twin() -> bool:
    return _binding.get() is not None


@contextmanager
def twin_bound(binding: TwinBinding) -> Iterator[TwinBinding]:
    """Run a block inside the Glasshouse.

    Synchronous context manager over an async body by design: the token is
    reset in ``finally``, so a raising run leaves no binding behind — the
    leak this whole module would otherwise be.
    """
    token: Token[TwinBinding | None] = _binding.set(binding)
    try:
        yield binding
    finally:
        _binding.reset(token)


def resolve_tool(name: str, real: Any) -> Any:
    """The tool a call should actually reach.

    ``real`` is what the registry returned, passed in rather than looked up
    so this module never imports the tool registry — the executor already
    did the lookup, and a second lookup here would be a second thing that
    could disagree.

    Inside a binding, a name the substituted registry knows resolves to the
    substitute. A name it does *not* know resolves to ``None`` rather than
    to the real tool: the substituted registry is built from the company's
    full tool set, so an unknown name inside a rehearsal means something
    reached for a tool that was never part of this run — and answering that
    with a live tool is the one mistake this module exists to prevent.
    """
    binding = _binding.get()
    if binding is None:
        return real
    return binding.tools.get(name)


def effective_plane(requested: Any) -> Any:
    """The plane a tenant session must actually address.

    Inside a binding this is always the twin plane, *including* when the
    caller explicitly asked for ``Plane.LIVE`` — a rehearsal that could
    write to reality by asking politely would not be a rehearsal.
    """
    from src.ai.tenant_schema.data_plane import Plane

    if _binding.get() is None:
        return requested
    return Plane.TWIN
