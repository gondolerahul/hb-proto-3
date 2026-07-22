"""pragya/scripts — the reviewed stage scripts for the discovery half.

Stages 1–5 are the as-is discovery protocol (functional §4.3, closing register
C8's script half). Each is a checked-in, reviewed asset — the same standing as
the HBS spine and the curated agent templates — because what they encode is
judgment about how an engagement should be run, not implementation detail.

Stages 6–9 have no scripts by design: they are mechanical (finalize the
blueprint, connect systems, activate, operate) and are driven by the Inc-2
wizard APIs rather than by discovery conversation.
"""
from __future__ import annotations

from src.ai.pragya.scripts._shared import GLOBAL_GUARDRAILS, Question, StageScript
from src.ai.pragya.scripts.stage_1 import STAGE_1
from src.ai.pragya.scripts.stage_2 import STAGE_2
from src.ai.pragya.scripts.stage_3 import STAGE_3
from src.ai.pragya.scripts.stage_4 import STAGE_4
from src.ai.pragya.scripts.stage_5 import STAGE_5

__all__ = [
    "GLOBAL_GUARDRAILS",
    "Question",
    "StageScript",
    "STAGE_1", "STAGE_2", "STAGE_3", "STAGE_4", "STAGE_5",
    "DISCOVERY_SCRIPTS",
    "script_for_stage",
]

#: The discovery scripts, indexed by stage number.
DISCOVERY_SCRIPTS: dict[int, StageScript] = {
    1: STAGE_1,
    2: STAGE_2,
    3: STAGE_3,
    4: STAGE_4,
    5: STAGE_5,
}


def script_for_stage(stage: int) -> StageScript | None:
    """The script for ``stage``, or ``None`` for the unscripted stages 6–9."""
    return DISCOVERY_SCRIPTS.get(stage)
