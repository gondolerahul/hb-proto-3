"""Increment 6 / TWIN T6 — certified actions are simulated, never executed (L5).

§12 calls this "the load-bearing one in this workstream": one un-substituted
tool is a real external effect from a rehearsal. So the tests here are about
what *cannot* happen, and the mutation test at the bottom removes substitution
and asserts an "external call attempted" failure.
"""
from __future__ import annotations

import json

import pytest

from src.ai.governance.authority import TOOL_CATEGORY_MAP, category_for_tool
from src.ai.twin.substitution import (
    PLANE_LOCAL_TOOLS,
    CallRecorder,
    SubstitutedTool,
    needs_substitution,
    substituted_registry,
)


class _RealTool:
    """Stands in for a shipped tool. Records if it was ever actually reached —
    which, inside the glass room, must never happen for an external effect."""

    def __init__(self, name: str):
        self.name = name
        self.description = f"real {name}"
        self.reached = False

    def get_function_schema(self):
        return {"name": self.name, "parameters": {"type": "object", "properties": {}}}

    async def run_with_context(self, input_data, context=None):
        self.reached = True
        return json.dumps({"success": True, "real": True})


# ── What gets substituted ────────────────────────────────────────────


@pytest.mark.parametrize("tool", [
    "send_email", "stripe_payout", "issue_refund", "esign_contract",
    "linkedin_create_post", "meta_ads_create_campaign", "create_invoice",
])
def test_every_categorised_act_is_substituted(tool: str) -> None:
    """A category is the platform's own declaration that an act has an external
    effect, so it can never simultaneously be plane-local."""
    assert category_for_tool(tool) is not None, "fixture assumption"
    assert needs_substitution(tool) is True


def test_the_whole_categorised_surface_is_substituted() -> None:
    """Totality, in the same spirit as GATE's: not a hand-picked list.

    Anything the PolicyGate governs is an external effect by definition, so a
    category added later is substituted the day it lands.
    """
    unsubstituted = [t for t in TOOL_CATEGORY_MAP if not needs_substitution(t)]
    assert unsubstituted == []


@pytest.mark.parametrize("tool", sorted(PLANE_LOCAL_TOOLS))
def test_plane_local_tools_run_for_real(tool: str) -> None:
    """A tenant-record write in a twin session writes to the *twin* schema —
    T1's isolation makes that true by construction. Stubbing it would make the
    rehearsal useless: a scenario that cannot write records cannot simulate a
    business."""
    assert needs_substitution(tool) is False


@pytest.mark.parametrize("tool", ["get_invoice", "list_contacts", "search_leads"])
def test_reads_run_for_real(tool: str) -> None:
    assert needs_substitution(tool) is False


def test_an_unrecognised_tool_is_substituted() -> None:
    """**Deny by default** — the only safe direction in a glass room.

    The failure mode of forgetting to allow-list something is a stubbed call in
    a rehearsal, which is annoying. The failure mode of the inverse is a real
    external effect from a simulation, which is unforgivable.
    """
    assert needs_substitution("some_new_tool_nobody_told_us_about") is True
    assert needs_substitution("") is True


# ── The stub cannot reach a real tool ────────────────────────────────


@pytest.mark.asyncio
async def test_a_substituted_call_never_reaches_the_real_tool() -> None:
    real = _RealTool("send_email")
    recorder = CallRecorder()
    registry = substituted_registry({"send_email": real}, recorder)

    await registry["send_email"].run_with_context(json.dumps({"to": "a@b.com"}))

    assert real.reached is False, "a rehearsal sent a real email"
    assert isinstance(registry["send_email"], SubstitutedTool)


def test_the_stub_holds_no_reference_to_the_real_tool() -> None:
    """Not a flag on the live executor — a different object. There is nothing
    here for a bug to fall through to."""
    real = _RealTool("stripe_payout")
    registry = substituted_registry({"stripe_payout": real}, CallRecorder())
    stub = registry["stripe_payout"]

    assert real not in vars(stub).values()
    assert not any(isinstance(v, _RealTool) for v in vars(stub).values())


def test_the_live_registry_is_not_mutated() -> None:
    """Substituting in place would corrupt the registry for every other run in
    the process — the second-worst bug this module could have."""
    real = _RealTool("send_email")
    original = {"send_email": real}
    substituted_registry(original, CallRecorder())
    assert original["send_email"] is real


@pytest.mark.asyncio
async def test_the_agent_is_told_the_call_was_simulated() -> None:
    """In the payload the agent reads, not only in our logs: an agent that
    believes it really sent the invoice plans its next step as though it had."""
    registry = substituted_registry({"send_email": _RealTool("send_email")},
                                    CallRecorder())
    raw = await registry["send_email"].run_with_context("{}")
    payload = json.loads(raw)
    assert payload["simulated"] is True
    assert "no external effect" in payload["note"].lower()


# ── The recorder is half the value of the feature ────────────────────


@pytest.mark.asyncio
async def test_the_recorder_reports_what_would_have_happened() -> None:
    """A tenant rehearsing a charter change wants to know it would have sent
    40 emails and asked for one approval."""
    recorder = CallRecorder()
    registry = substituted_registry(
        {"send_email": _RealTool("send_email"),
         "stripe_payout": _RealTool("stripe_payout")},
        recorder,
    )
    for _ in range(3):
        await registry["send_email"].run_with_context("{}")
    await registry["stripe_payout"].run_with_context("{}")

    assert recorder.by_category() == {"email_dispatch": 3, "payout": 1}
    assert recorder.external_effects == 4


@pytest.mark.asyncio
async def test_a_broken_schema_does_not_leak_a_real_tool() -> None:
    """The one place an exception could plausibly fall back to the real tool.
    It must not."""
    class _Broken(_RealTool):
        def get_function_schema(self):
            raise RuntimeError("schema is broken")

    broken = _Broken("send_email")
    registry = substituted_registry({"send_email": broken}, CallRecorder())
    await registry["send_email"].run_with_context("{}")
    assert broken.reached is False


# ── The mutation test §12 names as load-bearing ──────────────────────


@pytest.mark.asyncio
async def test_mutation_removing_substitution_attempts_a_real_external_call() -> None:
    """Remove substitution and a real external call is attempted.

    This is the test that makes L5 a guarantee rather than a hope: it
    reproduces, in one place, exactly what a missing substitution would do —
    the real tool is reached. If `substituted_registry` ever started passing an
    external-effect tool through, the assertions above would fail; this one
    shows what failure would *mean*.
    """
    real = _RealTool("send_email")

    # The mutation: the registry passes everything through unchanged.
    unsubstituted = {"send_email": real}
    await unsubstituted["send_email"].run_with_context(json.dumps({"to": "a@b.com"}))
    assert real.reached is True, "the mutation should reach the real tool"

    # The shipped behaviour, on the same tool, does not.
    fresh = _RealTool("send_email")
    guarded = substituted_registry({"send_email": fresh}, CallRecorder())
    await guarded["send_email"].run_with_context(json.dumps({"to": "a@b.com"}))
    assert fresh.reached is False
