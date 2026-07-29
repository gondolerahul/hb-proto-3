"""GLASS X1 — the binding seam, mutation-tested in both directions.

This is invisible plumbing on a path every live run takes, so the tests
have to prove two opposite things: that ordinary life is untouched, and
that nothing escapes a rehearsal. Each was verified to fail when the
corresponding check is removed from ``twin/binding.py``.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from src.ai.tenant_schema.data_plane import Plane
from src.ai.twin.binding import (
    TwinBinding,
    active_binding,
    effective_plane,
    in_twin,
    resolve_tool,
    twin_bound,
)

COMPANY = uuid.uuid4()


class FakeTool:
    def __init__(self, name: str):
        self.name = name


REAL = FakeTool("send_email")
SUBSTITUTE = FakeTool("send_email (simulated)")


def _binding(**tools: object) -> TwinBinding:
    return TwinBinding(
        company_id=COMPANY,
        tools=dict(tools) or {"send_email": SUBSTITUTE},
        recorder=None,
    )


# ── direction 1: with no binding, nothing changes ────────────────────────────

def test_without_a_binding_the_real_tool_is_returned_untouched():
    assert active_binding() is None
    assert in_twin() is False
    assert resolve_tool("send_email", REAL) is REAL


def test_without_a_binding_an_unknown_tool_stays_unknown():
    assert resolve_tool("no_such_tool", None) is None


def test_without_a_binding_the_requested_plane_is_honoured():
    assert effective_plane(Plane.LIVE) is Plane.LIVE
    # Including the twin plane — materialisation asks for it explicitly.
    assert effective_plane(Plane.TWIN) is Plane.TWIN


# ── direction 2: inside a binding, nothing escapes ───────────────────────────

def test_inside_a_binding_the_substitute_is_returned():
    with twin_bound(_binding()):
        assert resolve_tool("send_email", REAL) is SUBSTITUTE


def test_inside_a_binding_an_unlisted_tool_resolves_to_nothing_not_to_reality():
    """The substituted registry is built from the company's full tool set,
    so an unknown name inside a rehearsal means something reached for a
    tool that was never part of this run. Answering with a live tool is
    the one mistake this module exists to prevent."""
    with twin_bound(_binding()):
        assert resolve_tool("some_other_tool", REAL) is None


def test_inside_a_binding_asking_for_the_live_plane_still_gets_the_twin():
    """A rehearsal that could write to reality by asking politely would
    not be a rehearsal."""
    with twin_bound(_binding()):
        assert effective_plane(Plane.LIVE) is Plane.TWIN
        assert effective_plane(Plane.TWIN) is Plane.TWIN


# ── the binding must not leak ────────────────────────────────────────────────

def test_the_binding_is_gone_after_the_block():
    with twin_bound(_binding()):
        assert in_twin() is True
    assert in_twin() is False
    assert resolve_tool("send_email", REAL) is REAL


def test_the_binding_is_gone_after_the_block_raises():
    with pytest.raises(RuntimeError):
        with twin_bound(_binding()):
            raise RuntimeError("the run fell over")
    assert in_twin() is False
    assert effective_plane(Plane.LIVE) is Plane.LIVE


def test_nesting_restores_the_outer_binding():
    outer = _binding(send_email=FakeTool("outer"))
    inner = _binding(send_email=FakeTool("inner"))
    with twin_bound(outer):
        with twin_bound(inner):
            assert active_binding() is inner
        assert active_binding() is outer
    assert active_binding() is None


@pytest.mark.asyncio
async def test_a_binding_does_not_leak_across_concurrent_tasks():
    """Contextvars are per-task; two scenarios and a live run in one
    worker process must not see each other's bindings. That isolation is
    the property the contextvar was chosen for."""
    seen: dict[str, object] = {}

    async def bound_task() -> None:
        with twin_bound(_binding()):
            await asyncio.sleep(0)
            seen["bound"] = resolve_tool("send_email", REAL)

    async def live_task() -> None:
        await asyncio.sleep(0)
        seen["live"] = resolve_tool("send_email", REAL)

    await asyncio.gather(bound_task(), live_task())
    assert seen["bound"] is SUBSTITUTE
    assert seen["live"] is REAL


# ── the seam is actually installed at its three call sites ───────────────────

def test_the_executor_resolves_through_the_seam_at_both_sites():
    """A gate nothing routes through is not a gate (the B11 lesson). Both
    ``ToolRegistry.get_tool`` results in the executor must pass through
    ``_twin_resolve`` — pinned on the source, so deleting either call is
    a failing test rather than a silent live tool inside a rehearsal."""
    import inspect

    from src.ai import tool_executor

    source = inspect.getsource(tool_executor)
    assert source.count("_twin_resolve(") >= 3  # the def + both call sites
    for line in source.splitlines():
        stripped = line.strip()
        if "ToolRegistry.get_tool(" in stripped and "_twin_resolve" not in stripped:
            raise AssertionError(
                f"unguarded tool resolution in the executor: {stripped!r}")


def test_the_plane_resolver_consults_the_seam():
    import inspect

    from src.ai.tenant_schema import data_plane

    source = inspect.getsource(data_plane.TenantDataPlane.session)
    assert "effective_plane(plane)" in source
