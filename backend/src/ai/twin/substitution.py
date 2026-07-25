"""twin/substitution.py — certified actions are simulated, never executed (TWIN T6, L5).

A twin run executes with a **substituted tool set**: every gateway send,
connector write-back and money tool is replaced by a recording stub that
returns a plausible result and logs the call.

**Not a flag on the live executor — a different registry.** A boolean like
``dry_run=True`` is one missing ``if`` away from sending a real invoice, and
this is exactly the class of bug that must be impossible rather than
tested-for. There is no code path here that can reach a real tool: the stub
does not hold a reference to one.

**Deny by default.** The design lists what to substitute; this implements the
inverse, which is the only safe direction in a glass room. A tool the twin does
not recognise is substituted, not executed. Recognising a tool as safe is a
deliberate act (:data:`PLANE_LOCAL_TOOLS`), so the failure mode of forgetting
is a stubbed call in a rehearsal — annoying — rather than a real external
effect from a simulation, which is unforgivable.

**The PolicyGate still runs.** A simulated payout still raises the HITL card it
would raise in reality, and the scenario result shows it. Half the value of
rehearsing a change is learning what it would have asked permission for.
Consent and DNC checks run too: a broadcast scenario the consent registry would
have refused must be refused in the glass room, or the rehearsal teaches the
wrong lesson.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.ai.governance.authority import category_for_tool

logger = logging.getLogger(__name__)

__all__ = [
    "PLANE_LOCAL_TOOLS",
    "PLANE_LOCAL_PREFIXES",
    "SimulatedCall",
    "CallRecorder",
    "needs_substitution",
    "SubstitutedTool",
    "substituted_registry",
]

#: Tools that touch nothing outside the plane the session is already bound to.
#:
#: A tenant-record write in a twin session writes to the *twin* schema — T1's
#: isolation guarantee makes that true by construction, so it needs no stub and
#: stubbing it would make the rehearsal useless (a scenario that cannot write
#: records cannot simulate a business).
PLANE_LOCAL_TOOLS: frozenset[str] = frozenset({
    "tenant_record_write",
    "tenant_record_read",
    "emit_business_signal",
})

#: Read-verb prefixes. A read has no external effect; letting them through is
#: what makes a replay a replay rather than a hallucination with real structure.
#: Note this is about *effect*, not cost — a read that costs money is still
#: charged to the tenant, which decision 7 already made visible.
PLANE_LOCAL_PREFIXES: tuple[str, ...] = (
    "get_", "list_", "search_", "read_", "fetch_", "calculate", "web_search",
)


@dataclass
class SimulatedCall:
    """One tool call the glass room intercepted."""

    tool: str
    args: Dict[str, Any]
    category: Optional[str]


@dataclass
class CallRecorder:
    """What a scenario would have done outside, had it been real.

    This is half the value of the feature: a tenant rehearsing a charter change
    wants to know it would have sent 40 emails and asked for one approval.
    """

    calls: list[SimulatedCall] = field(default_factory=list)

    def record(self, tool: str, args: Dict[str, Any]) -> None:
        self.calls.append(SimulatedCall(tool, dict(args), category_for_tool(tool)))

    def by_category(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for call in self.calls:
            key = call.category or "uncategorised"
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def external_effects(self) -> int:
        """Calls that would have left the tenant — the number that matters."""
        return sum(1 for c in self.calls if c.category is not None)


def needs_substitution(tool_name: str) -> bool:
    """Whether this tool must be stubbed inside the glass room.

    Deny by default: only an explicitly plane-local tool or a read verb passes
    through. A categorised act is always substituted regardless — a category is
    the platform's own declaration that the act has an external effect, so it
    can never simultaneously be plane-local.
    """
    if not tool_name:
        return True
    if category_for_tool(tool_name) is not None:
        return True
    if tool_name in PLANE_LOCAL_TOOLS:
        return False
    lowered = tool_name.lower()
    return not any(lowered.startswith(p) or p in lowered
                   for p in PLANE_LOCAL_PREFIXES)


class SubstitutedTool:
    """A recording stub standing in for a tool with an external effect.

    Deliberately holds **no reference** to the tool it replaces — only its name
    and schema. There is nothing here for a bug to fall through to.
    """

    def __init__(self, name: str, description: str, schema: Dict[str, Any],
                 recorder: CallRecorder) -> None:
        self.name = name
        self.description = f"[SIMULATED] {description}"
        self._schema = schema
        self._recorder = recorder

    def get_function_schema(self) -> Dict[str, Any]:
        return self._schema

    async def run(self, input_data: str) -> str:
        return await self.run_with_context(input_data, None)

    async def run_with_context(
        self, input_data: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        try:
            args = json.loads(input_data) if isinstance(input_data, str) else input_data
        except json.JSONDecodeError:
            args = {"_raw": input_data}
        if not isinstance(args, dict):
            args = {"_raw": args}

        self._recorder.record(self.name, args)
        logger.info("[twin] simulated %s (no external effect)", self.name)
        return json.dumps({
            "success": True,
            "simulated": True,
            "tool": self.name,
            # Said in the payload the agent reads, not only in our logs: an
            # agent that believes it really sent the invoice will plan its next
            # step as though it had.
            "note": (
                "This ran in the Glasshouse. No external effect occurred and "
                "nothing was sent, charged or published."
            ),
        })


def substituted_registry(
    real_tools: Dict[str, Any], recorder: CallRecorder,
) -> Dict[str, Any]:
    """Build the tool set a twin run executes with.

    Takes the tools a company would really have and returns a new mapping with
    every non-plane-local one replaced. The input mapping is not mutated —
    substituting in place would corrupt the live registry for every other run
    in the process, which is the second-worst bug this module could have.
    """
    substituted: Dict[str, Any] = {}
    for name, tool in real_tools.items():
        if not needs_substitution(name):
            substituted[name] = tool
            continue
        schema: Dict[str, Any] = {}
        try:
            raw = tool.get_function_schema()
            if isinstance(raw, dict):
                schema = raw
        except Exception:  # noqa: BLE001 — a broken schema must not leak a real tool
            schema = {"name": name, "parameters": {"type": "object", "properties": {}}}
        substituted[name] = SubstitutedTool(
            name, getattr(tool, "description", "") or "", schema, recorder)
    return substituted
