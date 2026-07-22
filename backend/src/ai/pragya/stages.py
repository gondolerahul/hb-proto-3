"""pragya/stages.py — the nine-stage engagement machine (pure).

The flow (functional §4.3) is mostly linear, with one structural exception
that is the whole point of the design: **stage 9 loops back to stage 4**, not
to stage 1. A business that has been operating for three months has new
evidence, so the honest move is to re-test the assumptions against it — not to
re-introduce yourself and ask what the company does.

That makes stages 4–6 *re-enterable* and everything else forward-only. The
rules below encode exactly that, and nothing else: no stage may be skipped
forward, because each one produces the artifacts the next one reads.

Pure by construction — no database, no clock, no LLM. Persistence lives in
``pragya/engagement.py``, which uses this module to decide what is legal.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

__all__ = [
    "Stage",
    "StageInfo",
    "STAGE_INFO",
    "DISCOVERY_STAGES",
    "REENTERABLE_STAGES",
    "TransitionError",
    "can_advance",
    "can_reenter",
    "next_stage",
    "validate_transition",
    "is_discovery",
]


class Stage(IntEnum):
    """The nine stages. ``IntEnum`` so ordering comparisons are the rules."""

    BASELINE = 1
    ASSUMPTIONS = 2
    INGESTION = 3
    ANALYSIS = 4
    SOLUTION = 5
    BLUEPRINT = 6
    INTEGRATION = 7
    DEPLOY = 8
    OPERATE = 9


#: Stages 1–5 are the scripted discovery protocol; 6–9 are mechanical.
DISCOVERY_STAGES: frozenset[Stage] = frozenset(
    {Stage.BASELINE, Stage.ASSUMPTIONS, Stage.INGESTION, Stage.ANALYSIS,
     Stage.SOLUTION}
)

#: The continuous re-engagement window: from OPERATE the engagement may drop
#: back to any of these, because the business changed and the analysis should
#: be re-tested rather than assumed to still hold.
REENTERABLE_STAGES: frozenset[Stage] = frozenset(
    {Stage.ANALYSIS, Stage.SOLUTION, Stage.BLUEPRINT}
)


@dataclass(frozen=True)
class StageInfo:
    """What a stage is called and what it is for, for display and reporting."""

    stage: Stage
    name: str
    summary: str
    scripted: bool


STAGE_INFO: dict[Stage, StageInfo] = {
    Stage.BASELINE: StageInfo(
        Stage.BASELINE, "Baseline knowledge",
        "Research the company before asking anything the public record answers.",
        True),
    Stage.ASSUMPTIONS: StageInfo(
        Stage.ASSUMPTIONS, "Working assumptions",
        "A numbered, reviewable hypothesis of how the business runs.", True),
    Stage.INGESTION: StageInfo(
        Stage.INGESTION, "Deep knowledge ingestion",
        "Documents and connected sources indexed into the knowledge base.", True),
    Stage.ANALYSIS: StageInfo(
        Stage.ANALYSIS, "Revised analysis",
        "Assumptions tested against evidence; open questions surfaced.", True),
    Stage.SOLUTION: StageInfo(
        Stage.SOLUTION, "Solution engineering",
        "Priorities, sequence, KPIs and budget decided with the owner.", True),
    Stage.BLUEPRINT: StageInfo(
        Stage.BLUEPRINT, "Blueprint finalization",
        "Which bundle, processes and agents activate, and where they stop.",
        False),
    Stage.INTEGRATION: StageInfo(
        Stage.INTEGRATION, "Integration",
        "Connect the channels and systems the blueprint actually demands.",
        False),
    Stage.DEPLOY: StageInfo(
        Stage.DEPLOY, "Test & deploy",
        "Activate at A1 autonomy and verify the triggers are armed.", False),
    Stage.OPERATE: StageInfo(
        Stage.OPERATE, "Operate",
        "Monitor, report KPIs, surface approvals, take commands.", False),
}


class TransitionError(ValueError):
    """A stage move that the engagement flow does not permit."""


def is_discovery(stage: Stage) -> bool:
    """Whether the stage is one of the scripted discovery stages (1–5)."""
    return stage in DISCOVERY_STAGES


def next_stage(current: Stage) -> Stage | None:
    """The stage that follows ``current``, or ``None`` at OPERATE.

    OPERATE has no successor — it is where the engagement lives. Leaving it
    is a *re-entry* backwards, which is ``can_reenter``'s business.
    """
    if current is Stage.OPERATE:
        return None
    return Stage(current + 1)


def can_advance(current: Stage, target: Stage) -> bool:
    """Forward movement is strictly one stage at a time.

    No skipping: each stage produces artifacts the next one reads, so a
    skipped stage is a later stage operating on data that was never gathered.
    """
    return target == next_stage(current)


def can_reenter(current: Stage, target: Stage) -> bool:
    """Backward movement, permitted only as continuous re-engagement.

    Only from OPERATE, and only into stages 4–6. Dropping back to stage 1 or 2
    from live operation would mean re-introducing yourself to a customer of
    three months, and dropping to 3 would mean re-running ingestion rather
    than adding to it.
    """
    return current is Stage.OPERATE and target in REENTERABLE_STAGES


def validate_transition(current: Stage, target: Stage) -> None:
    """Raise ``TransitionError`` unless the move is legal.

    Staying put is always legal — a stage is a conversation, and most turns
    do not move it.
    """
    if target == current:
        return
    if can_advance(current, target) or can_reenter(current, target):
        return

    if target < current:
        raise TransitionError(
            f"cannot move back from {STAGE_INFO[current].name} to "
            f"{STAGE_INFO[target].name}: re-engagement runs from Operate into "
            f"stages 4–6 only"
        )
    raise TransitionError(
        f"cannot skip from {STAGE_INFO[current].name} to "
        f"{STAGE_INFO[target].name}: each stage reads what the previous one "
        f"produced"
    )
