"""pragya/intents.py — turning what the owner said into a tiered command.

The bridge between conversation and AUTH. A turn becomes a `CommandIntent`,
the intent gets a tier from `inward_auth.tiers`, and nothing executes until
`require_tier` says the session has proved enough.

**The extraction is a hint; the classification is the rule.** Language models
are good at reading intent and bad at being adversarially reliable, so the
design never lets extraction *lower* a tier:

* Anything the extractor cannot confidently map becomes `UNKNOWN`, which the
  classifier floors at T3. An owner occasionally asked for a step-up they did
  not need is a small cost; a spoofer whose ambiguous phrasing slipped through
  as T1 is not.
* Keyword pre-screening runs **alongside** the model, never instead of it, and
  can only raise. If the text contains "pause", the intent is at least a
  process mutation regardless of how the model read the sentence.

This is why the module is mostly a deterministic table with a model-shaped
hole in the middle, rather than a prompt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.ai.inward_auth.tiers import (
    Classification,
    CommandIntent,
    IntentKind,
    Tier,
    classify,
)

__all__ = [
    "ExtractedCommand",
    "COMMAND_PATTERNS",
    "screen_text",
    "build_intent",
    "classify_turn",
    "INTENT_SCHEMA",
]


@dataclass(frozen=True)
class ExtractedCommand:
    """What the turn was understood to ask for, before authorisation."""

    kind: str
    classification: Classification
    #: The §20 action category, when the command maps to one.
    category: str | None = None
    amount: float | None = None
    #: What the command acts on — a process code, an agent id, a record.
    target: str | None = None
    #: A short restatement, used in refusal copy and the step-up prompt.
    summary: str = ""
    #: True when the tier came from a keyword screen overriding the model.
    screened_up: bool = False

    @property
    def tier(self) -> Tier:
        return self.classification.tier


#: The tool-call schema handed to the model. Kept here beside the screening
#: table so the two vocabularies cannot drift apart.
INTENT_SCHEMA: dict[str, Any] = {
    "name": "classify_owner_turn",
    "description": (
        "Classify what the owner's message is asking for. If the message is "
        "conversation rather than an instruction, use 'general_question' or "
        "'tenant_read'. If you are not confident, use 'unknown' — an honest "
        "'unknown' is always better than a confident wrong guess."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    IntentKind.GENERAL_QUESTION, IntentKind.TENANT_READ,
                    IntentKind.REPORT, IntentKind.WORK_ASSIGNMENT,
                    IntentKind.PROCESS_PAUSE, IntentKind.PROCESS_RESUME,
                    IntentKind.AUTONOMY_RAISE, IntentKind.BINDING_CHANGE,
                    IntentKind.BULK_DATA_OPERATION, IntentKind.CATEGORISED_ACTION,
                    IntentKind.LOOP_KILL_SWITCH, IntentKind.UNKNOWN,
                ],
            },
            "category": {
                "type": ["string", "null"],
                "description": "§20 action category, when the command maps to one.",
            },
            "amount": {"type": ["number", "null"]},
            "target": {
                "type": ["string", "null"],
                "description": "Process code, agent id, or record the command acts on.",
            },
            "summary": {
                "type": "string",
                "description": "One short line restating the command, for confirmation.",
            },
        },
        "required": ["kind", "summary"],
    },
}


#: Keyword screens. Each maps a pattern to the *floor* it imposes — never a
#: ceiling. Deliberately over-inclusive: a false positive costs one step-up,
#: a false negative costs a company.
COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(kill|shut(\s|-)?down|stop everything|emergency stop)\b", re.I),
     IntentKind.LOOP_KILL_SWITCH),
    (re.compile(r"\bpaus(e|ing)\b|\bhold off\b|\bstop\b", re.I),
     IntentKind.PROCESS_PAUSE),
    (re.compile(r"\bresum(e|ing)\b|\brestart\b|\bturn .* back on\b", re.I),
     IntentKind.PROCESS_RESUME),
    (re.compile(r"\bautonom|\bpromote\b|\bdemote\b|\bA[123]\b", re.I),
     IntentKind.AUTONOMY_RAISE),
    (re.compile(r"\bdelete\b|\bpurge\b|\bwipe\b|\bbulk\b", re.I),
     IntentKind.BULK_DATA_OPERATION),
    (re.compile(r"\bpay\b|\bpayout\b|\brefund\b|\btransfer\b|\bbank\b", re.I),
     IntentKind.CATEGORISED_ACTION),
    (re.compile(r"\bregister\b.*\b(number|phone|whatsapp|email)\b", re.I),
     IntentKind.BINDING_CHANGE),
)

#: Floors imposed by a screen hit, as tiers. Used to check the model did not
#: under-call; the classifier still assigns the final tier.
_SCREEN_FLOOR: dict[str, Tier] = {
    IntentKind.LOOP_KILL_SWITCH: Tier.T3,
    IntentKind.PROCESS_PAUSE: Tier.T2,
    IntentKind.PROCESS_RESUME: Tier.T2,
    IntentKind.AUTONOMY_RAISE: Tier.T2,
    IntentKind.BULK_DATA_OPERATION: Tier.T2,
    IntentKind.CATEGORISED_ACTION: Tier.T2,
    IntentKind.BINDING_CHANGE: Tier.T2,
}


#: An owner explicitly scoping a command to the whole workforce. Matched so
#: "pause everything" reaches the all-scope, while "pause invoice chasing"
#: with an unresolved target does not — see ``commands.ALL_TRIGGERS``.
_ALL_SCOPE = re.compile(
    r"\b(everything|all of (it|them)|the whole (lot|thing)|all agents|"
    r"all processes)\b", re.I)


def scopes_to_everything(text: str) -> bool:
    """Whether the owner explicitly said 'all of it'."""
    return bool(_ALL_SCOPE.search(text))


def screen_text(text: str) -> str | None:
    """The highest-impact intent kind the raw text suggests, or ``None``.

    Runs independently of the model. Patterns are ordered most-severe first
    and the first hit wins, so "stop everything" screens as a kill switch
    rather than a pause.
    """
    for pattern, kind in COMMAND_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def build_intent(
    *,
    kind: str,
    category: str | None = None,
    amount: float | None = None,
    band: float | None = None,
    touches_tenant_data: bool = True,
) -> CommandIntent:
    return CommandIntent(
        kind=kind, category=category, amount=amount, band=band,
        touches_tenant_data=touches_tenant_data,
    )


def classify_turn(
    text: str,
    extracted: dict[str, Any] | None,
    *,
    band: float | None = None,
) -> ExtractedCommand:
    """Classify one owner turn into a tiered command.

    ``extracted`` is the model's reading (``INTENT_SCHEMA`` shape) or ``None``
    when extraction failed or was not run. Failure is not a pass-through: with
    no extraction the intent is ``UNKNOWN``, which fails up to T3.
    """
    screened = screen_text(text)

    if not extracted or not isinstance(extracted.get("kind"), str):
        # No usable reading. If the text screened as something specific, use
        # that; otherwise it is genuinely unknown and fails up.
        kind = screened or IntentKind.UNKNOWN
        classification = classify(build_intent(kind=kind))
        return ExtractedCommand(
            kind=kind, classification=classification,
            target="*" if scopes_to_everything(text) else None,
            summary=text.strip()[:200],
            screened_up=screened is not None,
        )

    kind = extracted["kind"]
    category = extracted.get("category") or None
    amount = extracted.get("amount")
    summary = str(extracted.get("summary") or text.strip())[:200]
    target = extracted.get("target") or None

    classification = classify(build_intent(
        kind=kind, category=category,
        amount=float(amount) if isinstance(amount, (int, float)) else None,
        band=band,
    ))

    # The screen can only raise. If the raw text looks like a pause and the
    # model called it a read, the pause wins — a model that under-calls a
    # command is exactly the failure this guards against, whether the cause is
    # a bad reading or a deliberately crafted sentence.
    screened_up = False
    if screened is not None:
        floor = _SCREEN_FLOOR.get(screened, Tier.T2)
        if classification.tier < floor:
            classification = classify(build_intent(kind=screened, category=category))
            kind = screened
            screened_up = True

    resolved_target = str(target) if target else None
    if resolved_target is None and scopes_to_everything(text):
        resolved_target = "*"

    return ExtractedCommand(
        kind=kind, classification=classification, category=category,
        amount=float(amount) if isinstance(amount, (int, float)) else None,
        target=resolved_target,
        summary=summary, screened_up=screened_up,
    )
