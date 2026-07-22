"""voice_loop/profile.py — the realtime execution profile (register B7, pure).

A conversational voice turn has roughly half a second. The shipped loop
(technical §12.1) has eight stages, three of which are model calls and one of
which writes to CORTEX. They cannot all run live, and B7 is the question of
which ones do.

**The answer is not "fewer guardrails".** The eight stages are not equally
expensive, and exactly one governance control — the §20.3 PolicyGate — is a
*pure function*: a table lookup and a numeric comparison. It costs microseconds
on a budget measured in hundreds of milliseconds, so it stays inline and a
voice agent is governed exactly as strictly as a text one.

What defers is **LLM judgment**: Strategize, Pre-Critic, Post-Critic, Reflect.
Those run after the call, over the transcript, in the deferred run — so
learning and criticism are not lost, only moved off the latency path.

The consequence is stated honestly in ``LIVE_COMPLETION_RULE`` and enforced in
``live_gate.py``: a voice turn may *promise* a governed action, never complete
one. An agent that could push a payout through mid-call because waiting was
inconvenient is precisely what §20.3 exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "Stage",
    "Disposition",
    "StageProfile",
    "REALTIME_PROFILE",
    "LIVE_STAGES",
    "DEFERRED_STAGES",
    "LIVE_COMPLETION_RULE",
    "TURN_BUDGET_MS",
    "profile_for",
    "runs_live",
    "is_model_call",
]


#: The conversational budget a turn must fit inside. Not a timeout — a design
#: constraint that decides which stages can be on the path at all.
TURN_BUDGET_MS = 500


#: The normative limit this profile implies. Quoted into the KAR-01 gateway's
#: prompt so the agent's own instructions and the enforcement agree.
LIVE_COMPLETION_RULE = (
    "A voice turn may not complete a governed external action synchronously. "
    "It may promise one: the approval card is raised during the call, the "
    "caller is told plainly that it needs a sign-off, and the action settles "
    "after the call."
)


class Stage(str, Enum):
    """The §12.1 stages, plus the PolicyGate that runs inside the pipeline."""

    PERCEIVE = "perceive"
    STRATEGIZE = "strategize"
    POLICY_GATE = "policy_gate"     # §20.3, before the LLM Pre-Critic
    PRE_CRITIC = "pre_critic"
    ACT = "act"
    OBSERVE = "observe"
    POST_CRITIC = "post_critic"
    REFLECT = "reflect"
    DECIDE = "decide"


class Disposition(str, Enum):
    LIVE = "live"           # runs on the turn, inside the budget
    DEFERRED = "deferred"   # runs post-call, over the transcript


@dataclass(frozen=True)
class StageProfile:
    """One stage's realtime disposition, and why."""

    stage: Stage
    disposition: Disposition
    #: Whether the stage costs a model round-trip. The deciding property.
    model_call: bool
    rationale: str


#: The §2.1 table as data. The invariant that matters: no stage with
#: ``model_call=True`` may be ``LIVE`` — that is what the budget forbids, and
#: it is asserted in the goldens rather than left as a comment.
REALTIME_PROFILE: tuple[StageProfile, ...] = (
    StageProfile(
        Stage.PERCEIVE, Disposition.LIVE, False,
        "The session context is already warm — the call has been running. "
        "Gathering it is a read, not a round-trip.",
    ),
    StageProfile(
        Stage.STRATEGIZE, Disposition.DEFERRED, True,
        "The planner is a model call. In a live turn the realtime model is "
        "already choosing what to say; a second planner would be both slow "
        "and redundant.",
    ),
    StageProfile(
        Stage.POLICY_GATE, Disposition.LIVE, False,
        "Pure function — a category lookup and a numeric band comparison. It "
        "costs microseconds, so realtime buys no excuse to skip governance. "
        "This is the load-bearing line of the whole profile.",
    ),
    StageProfile(
        Stage.PRE_CRITIC, Disposition.DEFERRED, True,
        "A model call, and the one that cannot fit. Its deterministic half "
        "(the PolicyGate) already ran inline; its LLM judgment runs after.",
    ),
    StageProfile(
        Stage.ACT, Disposition.LIVE, False,
        "The realtime model *is* the act. Tool calls it makes are the "
        "action, and uncategorised ones complete live.",
    ),
    StageProfile(
        Stage.OBSERVE, Disposition.LIVE, False,
        "Parsing a tool result is cheap, and the model needs it to speak the "
        "next sentence.",
    ),
    StageProfile(
        Stage.POST_CRITIC, Disposition.DEFERRED, True,
        "A model call. Alignment supervision over a transcript is better "
        "done on the whole conversation than sentence by sentence anyway.",
    ),
    StageProfile(
        Stage.REFLECT, Disposition.DEFERRED, True,
        "A model call plus a CORTEX write. Reflection over a completed call "
        "is more useful than over a half-finished one.",
    ),
    StageProfile(
        Stage.DECIDE, Disposition.DEFERRED, False,
        "Cheap in itself, but it reads what Strategize, Post-Critic and "
        "Reflect produced. Running it live would decide on absent inputs.",
    ),
)

_BY_STAGE: dict[Stage, StageProfile] = {p.stage: p for p in REALTIME_PROFILE}

LIVE_STAGES: tuple[Stage, ...] = tuple(
    p.stage for p in REALTIME_PROFILE if p.disposition is Disposition.LIVE)

DEFERRED_STAGES: tuple[Stage, ...] = tuple(
    p.stage for p in REALTIME_PROFILE if p.disposition is Disposition.DEFERRED)


def profile_for(stage: Stage) -> StageProfile:
    return _BY_STAGE[stage]


def runs_live(stage: Stage) -> bool:
    return _BY_STAGE[stage].disposition is Disposition.LIVE


def is_model_call(stage: Stage) -> bool:
    return _BY_STAGE[stage].model_call
