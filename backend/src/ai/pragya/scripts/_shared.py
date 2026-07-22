"""pragya/scripts/_shared.py — the shape of a stage script.

A stage script is a **reviewed asset**, not code that happens to contain
prose. It is checked in and reviewed the way the HBS spine and the curated
agent templates are, because what it encodes is judgment about how a
consulting engagement should be run — not an implementation detail.

The structure exists to make that judgment reviewable. Each stage declares
what it must achieve, what Pragya may and may not say, which questions she is
allowed to ask (and, critically, *why* each one earns its place), and what has
to be true before she moves on. A reviewer can therefore disagree with a
specific question without having to read the orchestration loop.

Two conventions carry the consulting quality bar:

* **Every question states its ``why``.** A question that cannot justify itself
  is a question that wastes the owner's attention, and the owner's attention
  is the scarcest input the engagement has.
* **Every question states ``skip_if``.** Pragya must never ask what she already
  knows. This is the machine-checkable half of "research before asking"
  (functional §4.3 stage 1), and it is why ``skip_if`` is required rather than
  optional.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Question", "StageScript", "GLOBAL_GUARDRAILS"]


#: Rules that hold in every stage. Repeated into each script's rendered prompt
#: rather than assumed, because a stage prompt is what the model actually sees.
GLOBAL_GUARDRAILS: tuple[str, ...] = (
    "Never state a number you have not computed from the tenant's own records. "
    "If a figure is not yet measurable, say exactly which data is missing "
    "instead of estimating. A plausible invented number is the single fastest "
    "way to lose an owner's trust, and it is unrecoverable.",
    "State assumptions as assumptions. If you inferred something rather than "
    "read it, say so in the same sentence you say it.",
    "You cannot approve your own work. When something needs a human decision, "
    "link the owner to the Judgment Desk — never collect an approval in chat, "
    "even if the owner offers one, and even if they insist.",
    "You do not execute a sensitive command because the conversation felt "
    "authentic. Every command is tiered and verified separately; a warm "
    "conversation is not authentication.",
    "The owner's time is the scarce resource, not yours. Never ask what you "
    "could look up, and never re-ask what you have already been told.",
    "Write for a busy owner: short paragraphs, concrete nouns, no consultant "
    "throat-clearing. Do not open with 'Great question!' or narrate your own "
    "process unless asked.",
)


@dataclass(frozen=True)
class Question:
    """One thing Pragya may ask the owner during a stage.

    ``why`` is shown to no one at runtime — it exists so a reviewer can strike
    a question that does not earn its place, and so a later author has to
    articulate a justification before adding one.
    """

    ask: str
    why: str
    skip_if: str
    follow_up: str | None = None


@dataclass(frozen=True)
class StageScript:
    """The reviewed script for one engagement stage."""

    stage: int
    name: str
    #: One sentence: what this stage exists to achieve.
    goal: str
    #: What must already be true for the stage to be entered.
    entry_condition: str
    #: Pragya's standing instructions while in this stage.
    system_prompt: str
    #: How she opens on entering. May reference artifacts from earlier stages.
    opening: str
    #: Discovery items the stage must resolve before it can close.
    must_cover: tuple[str, ...]
    #: The permitted asks, in priority order.
    questions: tuple[Question, ...] = ()
    #: Keys written into ``pragya_engagements.artifacts`` by this stage.
    artifacts: tuple[str, ...] = ()
    #: The stage's headline output — the one artifact that must carry content
    #: before the stage can be considered done.
    #:
    #: Needed because several artifacts are legitimately *empty*:
    #: ``assumptions.struck`` is empty when the owner struck nothing,
    #: ``ingestion.declined`` when they shared everything. Requiring every
    #: artifact to be non-empty would stall an engagement that was going
    #: perfectly well, so presence is the general bar and this one key is the
    #: substantive one.
    primary_artifact: str | None = None
    #: Conditions that must all hold before advancing.
    exit_criteria: tuple[str, ...] = ()
    #: Stage-specific prohibitions, on top of GLOBAL_GUARDRAILS.
    guardrails: tuple[str, ...] = field(default_factory=tuple)
    #: The line that carries the owner into the next stage.
    handoff: str = ""

    def render_prompt(self) -> str:
        """The full system prompt for this stage, guardrails included.

        Assembled rather than stored so a change to ``GLOBAL_GUARDRAILS``
        cannot be silently missed by four of the five stages.
        """
        rules = "\n".join(f"- {rule}" for rule in
                          (*GLOBAL_GUARDRAILS, *self.guardrails))
        cover = "\n".join(f"- {item}" for item in self.must_cover)
        return (
            f"{self.system_prompt}\n\n"
            f"## This stage must resolve\n{cover}\n\n"
            f"## Rules that always apply\n{rules}\n"
        )
