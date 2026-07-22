"""pragya/artifacts.py — turning a conversation into engagement state.

The missing half of Increment 3. The stage scripts declare what each stage
must *produce* (``StageScript.artifacts``), `record_artifacts` persists it, and
nothing in between ever extracted anything — so the bag stayed empty and
advancement had nothing to check.

The extraction schema is **built from the scripts**, not hand-written beside
them. A reviewed script that gains an artifact key gains an extraction slot on
the same edit, which is the only way the two stay in agreement.

Two deliberate properties:

* **Extraction never invents.** The prompt is explicit that an artifact absent
  from the conversation stays absent. An engagement's artifacts are evidence
  the platform will act on in stage 6; a hallucinated assumption list is worse
  than an empty one, because an empty one is visibly not ready.
* **Extraction is additive.** `record_artifacts` merges by key, so a re-entered
  stage (4–6 are re-enterable) refines rather than erases. Only keys the
  extractor actually returns are written.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.pragya.scripts import StageScript, script_for_stage
from src.ai.pragya.stages import Stage

logger = logging.getLogger(__name__)

__all__ = [
    "ARTIFACT_TOOL_NAME",
    "schema_key",
    "artifact_schema_for",
    "parse_extraction",
    "extraction_prompt",
]

ARTIFACT_TOOL_NAME = "record_stage_artifacts"


def schema_key(artifact_key: str) -> str:
    """``assumptions.list`` → ``assumptions__list``.

    Dots are legal in JSON Schema property names but several function-calling
    APIs are stricter than the spec. Sanitising and mapping back is cheaper
    than discovering which providers object.
    """
    return artifact_key.replace(".", "__")


def artifact_schema_for(stage: Stage) -> dict[str, Any] | None:
    """The extraction tool schema for a stage, or ``None`` if it has no script.

    Every artifact is a free-form value, not a typed shape: the scripts
    describe artifacts in prose (`"numbered; each with evidence + confidence"`)
    and pinning a schema here would freeze reviewed assets to a structure
    nobody reviewed.
    """
    script = script_for_stage(int(stage))
    if script is None or not script.artifacts:
        return None

    properties: dict[str, Any] = {}
    for key in script.artifacts:
        properties[schema_key(key)] = {
            "type": ["string", "array", "object", "null"],
            "description": f"Content for '{key}'. Omit entirely if the "
                           f"conversation has not established it yet.",
        }

    return {
        "name": ARTIFACT_TOOL_NAME,
        "description": (
            "Record what this stage of the engagement has established so far. "
            "Only include a field the conversation actually supports — omit "
            "anything not yet established rather than guessing at it."
        ),
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": [],
        },
    }


def extraction_prompt(script: StageScript) -> str:
    """The instruction that accompanies the schema.

    Separate from the stage's own system prompt because this is a different
    job: the stage prompt tells Pragya how to *converse*, this tells an
    extractor how to *read* the conversation she just had.
    """
    covers = "\n".join(f"- {item}" for item in script.must_cover)
    return (
        f"You are reading a conversation that is at stage {script.stage} of a "
        f"business engagement — {script.name}.\n\n"
        f"This stage exists to resolve:\n{covers}\n\n"
        f"Call {ARTIFACT_TOOL_NAME} with whatever the conversation has "
        f"actually established. Rules:\n"
        f"- Omit any field the conversation does not support. Do NOT guess, "
        f"infer beyond what was said, or fill a field to look complete.\n"
        f"- An empty list is a real answer when the conversation genuinely "
        f"established that there is nothing (e.g. the owner struck no "
        f"assumptions). Absence of discussion is not an empty list — omit it.\n"
        f"- Quote the owner's own words where the artifact is about what they "
        f"said."
    )


def parse_extraction(
    stage: Stage, args: dict[str, Any] | None,
) -> dict[str, Any]:
    """Map a tool-call payload back to artifact keys.

    Unknown properties are dropped: an extractor inventing a key would put
    state into the engagement that no script declared and nothing reads.
    """
    script = script_for_stage(int(stage))
    if script is None or not args:
        return {}

    by_schema_key = {schema_key(k): k for k in script.artifacts}
    extracted: dict[str, Any] = {}

    for raw_key, value in args.items():
        artifact_key = by_schema_key.get(raw_key)
        if artifact_key is None:
            logger.debug("dropping undeclared artifact %r at stage %s",
                         raw_key, int(stage))
            continue
        if value is None:
            continue
        extracted[artifact_key] = value

    return extracted
