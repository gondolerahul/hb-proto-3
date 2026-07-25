"""twin/counterparties.py — simulated people, disclosed as such (TWIN T11).

Owner decision (concepts §6.4): simulated counterparties are **permitted** in
the Glasshouse. A scenario asking "what if we chased overdue invoices harder"
needs someone on the other end to chase, and a rehearsal against an empty room
teaches nothing.

Two constraints, and they are the whole module:

1. **Disclosed, always.** Every simulated counterparty is marked, in the record
   it writes and in the result the tenant reads. A simulated customer that
   looks like a real one is a lie the product tells about its own evidence —
   and worse, one that could be mistaken for a real lead and followed up.
2. **Confined to the twin plane.** These are built only for a twin session.
   T1's isolation means a simulated person physically cannot reach the live
   business, which is why this module needs no guard of its own: the guarantee
   is structural, not procedural.

Reuses the shipped ``persona_service`` rather than inventing a second notion of
a person, per the decision.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "SIMULATED_MARKER",
    "SimulatedCounterparty",
    "build_counterparty",
    "is_simulated",
    "disclose",
]

#: The field that marks a record as not describing a real person. A reserved
#: key rather than a naming convention on the display name, because a name can
#: be edited and a scenario's output can be exported.
SIMULATED_MARKER = "_simulated"


@dataclass(frozen=True)
class SimulatedCounterparty:
    """A person who does not exist, and says so."""

    handle: str
    display_name: str
    persona: str
    seed: str

    def as_record(self) -> dict[str, Any]:
        """The record body a scenario writes into the twin plane."""
        return {
            "name": self.display_name,
            "handle": self.handle,
            SIMULATED_MARKER: True,
            "_simulated_note": (
                "This counterparty was generated for a Glasshouse rehearsal. "
                "They are not a real person and this is not a real lead."
            ),
        }


def build_counterparty(
    scenario_id: uuid.UUID, index: int, *, persona: str = "prospect",
) -> SimulatedCounterparty:
    """Deterministically derive a simulated counterparty for a scenario.

    Deterministic on (scenario, index) so re-running a scenario faces the same
    cast. Two runs that differ only because the imaginary customers were
    re-rolled are not comparable, and comparability is most of what the
    Glasshouse is for.
    """
    seed = hashlib.sha256(f"{scenario_id}:{index}:{persona}".encode()).hexdigest()[:12]
    return SimulatedCounterparty(
        handle=f"sim-{seed}",
        # The name carries the marker too. Belt and braces: the structured flag
        # is authoritative, but a human skimming a result should not have to
        # check a field to know what they are looking at.
        display_name=f"[simulated] {persona.title()} {seed[:4]}",
        persona=persona,
        seed=seed,
    )


def is_simulated(record: Optional[dict[str, Any]]) -> bool:
    """Whether a record describes a simulated person."""
    return bool((record or {}).get(SIMULATED_MARKER))


def disclose(result: dict[str, Any], counterparties: int) -> dict[str, Any]:
    """Stamp a scenario result with its use of simulated people.

    Returns a new dict — a result that has already been handed to a caller must
    not change under them.
    """
    if counterparties <= 0:
        return dict(result)
    disclosed = dict(result)
    disclosed["simulated_counterparties"] = counterparties
    disclosed["simulated_counterparties_note"] = (
        f"{counterparties} counterparty/counterparties in this rehearsal were "
        f"generated, not real. Any behaviour attributed to them is an "
        f"assumption this scenario made, not evidence about your customers."
    )
    return disclosed
