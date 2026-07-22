"""pragya/advancement.py — when the engagement moves on (pure).

Increment 3 left the exit criteria as prose the model reads, so nothing
advanced on its own. The split here is deliberate and it is the design:

* **The prose ``exit_criteria`` stay prose.** They instruct Pragya how to
  behave. A predicate over them would be an LLM grading its own conversation.
* **The declared ``artifacts`` are the machine-checkable half.** A stage that
  produced its outputs is *eligible*; one that did not, is not.

Eligibility is not advancement. Two stages require the owner to say so:

* **Stage 2 (working assumptions)** — the deliverable is which assumptions the
  owner *struck*. Advancing on artifacts alone would mean Pragya deciding the
  owner had reviewed her hypothesis.
* **Stage 5 (solution engineering)** — the deliverable is the owner's chosen
  priority. "Pragya proposes, the owner decides" (functional §4.3) is not
  satisfied by Pragya noticing that a decision-shaped artifact exists.

Confirmation is an explicit owner action, never inferred from prose. Reading
agreement out of "yeah, that sounds about right" is exactly the failure these
two stages exist to prevent.

Stages 6–9 are mechanical and driven by the wizard APIs (``deployment.py``);
they do not consult this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.ai.pragya.scripts import script_for_stage
from src.ai.pragya.stages import DISCOVERY_STAGES, Stage

__all__ = [
    "AUTO_ADVANCE_STAGES",
    "CONFIRM_STAGES",
    "Eligibility",
    "evaluate_eligibility",
    "needs_owner_confirmation",
    "advancement_prompt",
]


#: Gathering stages — nothing is being agreed, only collected. Advance as soon
#: as the stage has produced what it declared.
AUTO_ADVANCE_STAGES: frozenset[Stage] = frozenset(
    {Stage.BASELINE, Stage.INGESTION, Stage.ANALYSIS}
)

#: Agreement stages — the owner's decision *is* the artifact.
CONFIRM_STAGES: frozenset[Stage] = frozenset(
    {Stage.ASSUMPTIONS, Stage.SOLUTION}
)


@dataclass(frozen=True)
class Eligibility:
    """Whether a stage has produced what it declared, and what is missing."""

    stage: Stage
    eligible: bool
    missing: tuple[str, ...] = ()
    #: Set when the primary artifact exists but carries no content.
    primary_empty: bool = False
    reason: str = ""

    @property
    def needs_confirmation(self) -> bool:
        return self.eligible and self.stage in CONFIRM_STAGES


def _has_content(value: Any) -> bool:
    """Whether an artifact was *answered* — the bar for a secondary artifact.

    ``None`` and blank strings are absence. An empty *list* is content: it is
    the legitimate answer to "what did the owner strike?" when they struck
    nothing, and treating it as absence would stall a healthy engagement.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _has_substance(value: Any) -> bool:
    """Whether an artifact carries something — the bar for the *primary*.

    Stricter than ``_has_content`` on purpose, and the difference is the whole
    reason both exist. "Which assumptions did the owner strike? None" is a
    complete answer. "What are my assumptions about this business? None" is
    not a completed stage — it is a stage that produced nothing.

    So an empty collection satisfies a secondary artifact and fails a primary
    one.
    """
    if not _has_content(value):
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def evaluate_eligibility(
    stage: Stage, artifacts: dict[str, Any] | None,
) -> Eligibility:
    """Whether ``stage`` has produced its declared outputs. Pure."""
    bag = artifacts or {}

    if stage not in DISCOVERY_STAGES:
        return Eligibility(
            stage=stage, eligible=False,
            reason="stages 6-9 are mechanical; advancement is driven by the "
                   "wizard APIs, not by artifacts")

    script = script_for_stage(int(stage))
    if script is None or not script.artifacts:
        return Eligibility(stage=stage, eligible=False,
                           reason="stage declares no artifacts")

    # Presence is the general bar: an extractor that emitted a key considered
    # the question, whatever the answer turned out to be.
    missing = tuple(k for k in script.artifacts if k not in bag)
    if missing:
        return Eligibility(
            stage=stage, eligible=False, missing=missing,
            reason=f"{len(missing)} of {len(script.artifacts)} artifacts not "
                   f"yet established")

    # The headline output is the one that must actually carry content.
    primary = script.primary_artifact
    if primary is not None and not _has_substance(bag.get(primary)):
        return Eligibility(
            stage=stage, eligible=False, primary_empty=True,
            reason=f"{primary!r} is the stage's substantive output and is empty")

    if stage in CONFIRM_STAGES:
        return Eligibility(
            stage=stage, eligible=True,
            reason="artifacts complete; waiting on the owner to confirm")

    return Eligibility(stage=stage, eligible=True,
                       reason="artifacts complete")


def needs_owner_confirmation(stage: Stage) -> bool:
    """Whether this stage may only advance on an explicit owner action."""
    return stage in CONFIRM_STAGES


def advancement_prompt(stage: Stage) -> str:
    """What Pragya says when a confirm-stage is ready to move on.

    She asks; she does not announce. The question is the point — an owner who
    was not asked has not agreed.
    """
    if stage is Stage.ASSUMPTIONS:
        return ("That's my read of how things work. If I've got it right, say "
                "so and I'll start pulling in your documents to test it — or "
                "keep striking the ones that are wrong.")
    if stage is Stage.SOLUTION:
        return ("That's the plan as I understand it. Happy for me to put the "
                "exact configuration together, or is there something you'd "
                "change first?")
    return "Ready to move on when you are."
