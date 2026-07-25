"""solo_pack/templates — the curated Solo Pack entity definitions (reviewed).

Hand-authored ``hierarchical_entities`` definitions, each with A1 governance +
explicit authority bands + ``sod_class`` + ``memory_domains``, reviewed like
the HBS spine (Inc-2 decision 3). A malformed template fails fast through the
loader (schema + GOV typed governance + deploy validators), so every
channel-facing entity carries a complete governance block.

Per domain module:

* ``acquisition`` — P03 Cold-to-Closed (KAR-02, AGT-013, AGT-015) — the SLICE.
* ``care``        — P06 Resolve-to-Retain (AGT-030, AGT-035, AGT-092).
* ``finance``     — P08 Order-to-Cash (AGT-038, maker) + P10 Record-to-Report
                    (AGT-046, checker) — segregation of duties across owners.
* ``compliance``  — P14 Continuous Guardrails (AGT-068, auditor; protected).
* ``intelligence``— P19 Sense-Decide-Optimize (AGT-051; read-all planner).

``SOLO_PACK_STRUCTURE`` (the manifest) encodes the parentage the activation
service seeds: gateways + processes under Sheel, workforce agents under their
process. ``SLICE_TEMPLATES`` stays the four acquisition entities for
back-compat; ``SOLO_PACK_TEMPLATES`` is the full Wave-0 set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.ai.solo_pack.templates.acquisition import (
    ACQUISITION_TEMPLATES,
    AGT_013,
    AGT_015,
    KAR_02_EMAIL,
    P03_ACQUISITION,
)
from src.ai.solo_pack.templates.care import (
    AGT_030,
    AGT_035,
    AGT_092,
    CARE_TEMPLATES,
    P06_RESOLVE,
)
from src.ai.solo_pack.templates.compliance import (
    AGT_068,
    COMPLIANCE_TEMPLATES,
    P14_GUARDRAILS,
)
from src.ai.solo_pack.templates.finance import (
    AGT_038,
    AGT_046,
    FINANCE_TEMPLATES,
    P08_ORDER_TO_CASH,
    P10_RECORD_TO_REPORT,
)
from src.ai.solo_pack.templates.gateways import (
    GATEWAY_TEMPLATES,
    KAR_01_VOICE,
    KAR_01_VOICE_STUB,
    KAR_03_WHATSAPP,
    KAR_05_BROADCAST,
)
from src.ai.solo_pack.templates.intelligence import (
    AGT_051,
    INTELLIGENCE_TEMPLATES,
    P19_OPTIMIZE,
)

__all__ = [
    # SLICE (back-compat) ------------------------------------------------------
    "KAR_02_EMAIL", "P03_ACQUISITION", "AGT_013", "AGT_015", "SLICE_TEMPLATES",
    # Gateways (KAR) -----------------------------------------------------------
    "KAR_03_WHATSAPP", "KAR_01_VOICE", "KAR_01_VOICE_STUB", "KAR_05_BROADCAST",
    # PACK entities ------------------------------------------------------------
    "P06_RESOLVE", "AGT_030", "AGT_035", "AGT_092",
    "P08_ORDER_TO_CASH", "AGT_038", "P10_RECORD_TO_REPORT", "AGT_046",
    "P14_GUARDRAILS", "AGT_068",
    "P19_OPTIMIZE", "AGT_051",
    # Structure ----------------------------------------------------------------
    "ProcessGroup", "GATEWAYS", "PROCESS_GROUPS", "SOLO_PACK_STRUCTURE",
    "SOLO_PACK_TEMPLATES", "process_group", "process_codes",
]


@dataclass(frozen=True)
class ProcessGroup:
    """A Wave-0 process and the workforce agents seeded under it."""

    process: dict[str, Any]
    agents: tuple[dict[str, Any], ...]

    @property
    def process_code(self) -> str:
        return str(self.process["metadata_extensions"]["process_code"])

    @property
    def templates(self) -> tuple[dict[str, Any], ...]:
        return (self.process, *self.agents)


# The shared outward gateways (feed every process). KAR-01 replaced its Inc-2
# stub in Inc-3 VOICE; Inc-6 GATE added KAR-05, taking the roster to 19.
GATEWAYS: list[dict[str, Any]] = [
    KAR_02_EMAIL, KAR_03_WHATSAPP, KAR_01_VOICE, KAR_05_BROADCAST]

# The six Wave-0 processes with their workforce agents (the seeding tree).
PROCESS_GROUPS: list[ProcessGroup] = [
    ProcessGroup(P03_ACQUISITION, (AGT_013, AGT_015)),
    ProcessGroup(P06_RESOLVE, (AGT_030, AGT_035, AGT_092)),
    ProcessGroup(P08_ORDER_TO_CASH, (AGT_038,)),
    ProcessGroup(P10_RECORD_TO_REPORT, (AGT_046,)),
    ProcessGroup(P14_GUARDRAILS, (AGT_068,)),
    ProcessGroup(P19_OPTIMIZE, (AGT_051,)),
]

# The manifest the activation service reads (gateways + the process tree).
SOLO_PACK_STRUCTURE: dict[str, Any] = {
    "gateways": GATEWAYS,
    "process_groups": PROCESS_GROUPS,
}

# Back-compat: the four email→quote entities the SLICE authored and tests pin.
SLICE_TEMPLATES: list[dict[str, Any]] = ACQUISITION_TEMPLATES

# The full Wave-0 set (gateways + every process + every workforce agent).
SOLO_PACK_TEMPLATES: list[dict[str, Any]] = [
    *GATEWAYS,
    *(t for g in PROCESS_GROUPS for t in g.templates),
]


def process_group(process_code: str) -> Optional[ProcessGroup]:
    """Return the ProcessGroup for a process code (e.g. ``"P08"``), or None."""
    for group in PROCESS_GROUPS:
        if group.process_code == process_code:
            return group
    return None


def process_codes() -> list[str]:
    """The Wave-0 process codes, in seeding order."""
    return [group.process_code for group in PROCESS_GROUPS]
