"""pragya/reflection.py — what a stage taught us (Inc-4 PRAGYA-RT T6).

Increment 3 tried to reflect on a *call*, using the task loop's ``Reflector``.
Two things were wrong with that and they are the same thing: the ``Reflector``
takes an ``AgentState`` and an ``Observation`` — shapes that describe a task
step — and a conversation is not a task step.

So this is a different operation, at a different granularity:

* **Not per call.** A call is an arbitrary slice of a relationship. Two calls
  might complete one stage; one call might complete three.
* **Per stage.** A stage has a beginning, an end, declared artifacts and a
  purpose, which is exactly what makes a reflection worth writing.

The output is durable engagement state, not a log line. It is written back
into the artifacts bag under a reserved key so that a re-entered stage (4–6
are re-enterable) can read what the previous pass concluded rather than
rediscovering it — which is the whole reason §4.3's re-entry arrow points at
stage 4 and not stage 1.

Reflection runs **after** the stage has closed, off the reply path. It costs a
model call and buys nothing the owner is waiting for.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.llm.router import LLMRouter
from src.ai.pragya.engagement import record_artifacts
from src.ai.pragya.models import PragyaEngagement
from src.ai.pragya.scripts import script_for_stage
from src.ai.pragya.stages import STAGE_INFO, Stage

logger = logging.getLogger(__name__)

__all__ = [
    "REFLECTION_KEY_PREFIX",
    "REFLECTION_TOOL",
    "StageReflection",
    "reflection_key",
    "reflection_prompt",
    "parse_reflection",
    "reflect_on_stage",
]

#: Reserved artifact namespace. Prefixed so a reflection can never collide
#: with a key a stage script declares.
REFLECTION_KEY_PREFIX = "reflection.stage_"

REFLECTION_TOOL = "record_stage_reflection"


def reflection_key(stage: Stage) -> str:
    return f"{REFLECTION_KEY_PREFIX}{int(stage)}"


@dataclass(frozen=True)
class StageReflection:
    """What the stage established, and what it left open."""

    stage: int
    learned: str
    surprised: str = ""
    still_open: tuple[str, ...] = ()
    confidence: str = "moderate"
    at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "learned": self.learned,
            "surprised": self.surprised,
            "still_open": list(self.still_open),
            "confidence": self.confidence,
            "at": self.at or datetime.utcnow().isoformat(),
        }


REFLECTION_SCHEMA: dict[str, Any] = {
    "name": REFLECTION_TOOL,
    "description": (
        "Record what this stage of the engagement established, for the next "
        "stage and for any later pass that re-enters this one."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "learned": {
                "type": "string",
                "description": "What is now known that was not known before. "
                               "Concrete and specific to this business.",
            },
            "surprised": {
                "type": "string",
                "description": "What contradicted an earlier assumption. Empty "
                               "if nothing did — do not invent a surprise.",
            },
            "still_open": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Questions this stage could not settle.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "moderate", "high"],
                "description": "How well-supported the above is by what was "
                               "actually said, not how confident it sounds.",
            },
        },
        "required": ["learned"],
    },
}


def reflection_prompt(stage: Stage) -> str:
    """The instruction for the reflection pass."""
    info = STAGE_INFO[stage]
    script = script_for_stage(int(stage))
    covers = ""
    if script is not None:
        covers = "\n".join(f"- {item}" for item in script.must_cover)
        covers = f"\n\nThis stage was meant to resolve:\n{covers}"

    return (
        f"Stage {int(stage)} of a business engagement has just closed — "
        f"{info.name}. {info.summary}{covers}\n\n"
        f"Write down what this stage actually established, for whoever picks "
        f"the engagement up next — including you, months from now, when the "
        f"business has changed and this stage is re-entered.\n\n"
        f"Rules:\n"
        f"- Be specific to this business. 'The owner clarified their process' "
        f"is worthless; 'quotes are approved by the founder personally above "
        f"₹2L' is not.\n"
        f"- Record what **contradicted** an earlier assumption. That is the "
        f"most valuable thing a stage produces, and the easiest to lose.\n"
        f"- Leave 'surprised' empty if nothing did. Do not manufacture a "
        f"surprise to look insightful.\n"
        f"- 'confidence' describes how well the conversation supports this, "
        f"not how assured you want to sound."
    )


def parse_reflection(stage: Stage, args: dict[str, Any] | None) -> StageReflection | None:
    """Turn a tool payload into a reflection, or ``None`` if it said nothing."""
    if not args:
        return None
    learned = str(args.get("learned") or "").strip()
    if not learned:
        # A reflection with no content is not a reflection. Writing an empty
        # one would make the stage look reflected-upon when it was not.
        return None

    raw_open = args.get("still_open") or []
    still_open = tuple(str(x).strip() for x in raw_open if str(x).strip()) \
        if isinstance(raw_open, list) else ()

    confidence = str(args.get("confidence") or "moderate").lower()
    if confidence not in ("low", "moderate", "high"):
        confidence = "moderate"

    return StageReflection(
        stage=int(stage),
        learned=learned,
        surprised=str(args.get("surprised") or "").strip(),
        still_open=still_open,
        confidence=confidence,
        at=datetime.utcnow().isoformat(),
    )


async def reflect_on_stage(
    db: AsyncSession,
    engagement: PragyaEngagement,
    stage: Stage,
    transcript: list[dict[str, Any]],
    *,
    company_id: uuid.UUID,
) -> StageReflection | None:
    """Reflect on a closed stage and store it in the engagement.

    Returns ``None`` when there was nothing to reflect on or the model
    declined — both are fine, and neither is an error worth raising. A failed
    reflection costs future context, not correctness: the stage happened, its
    artifacts are recorded, and the engagement continues.
    """
    if not transcript:
        return None

    lines = "\n".join(
        f"{t.get('role', 'user')}: {t.get('content', '')}" for t in transcript)
    artifacts = {
        k: v for k, v in (engagement.artifacts or {}).items()
        if not k.startswith(REFLECTION_KEY_PREFIX)
    }

    router = LLMRouter(db=db, company_id=company_id)
    try:
        response = await router.call_llm(
            task_type="text_generation",
            system_prompt=reflection_prompt(stage),
            user_prompt=(f"=== CONVERSATION ===\n{lines}\n=== END ===\n\n"
                         f"=== RECORDED ARTIFACTS ===\n{artifacts}\n=== END ==="),
            tools=[REFLECTION_SCHEMA],
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pragya stage-%s reflection failed: %s", int(stage), exc)
        return None

    for call in response.function_calls:
        if call.get("name") != REFLECTION_TOOL:
            continue
        reflection = parse_reflection(stage, dict(call.get("args") or {}))
        if reflection is None:
            return None
        await record_artifacts(
            db, engagement, {reflection_key(stage): reflection.as_dict()})
        logger.info("pragya reflected on stage %s (confidence=%s)",
                    int(stage), reflection.confidence)
        return reflection

    return None
