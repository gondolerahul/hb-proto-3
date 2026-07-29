"""genui/navigation.py — she walks the map (STEWARD S3, 12_steward.md §7).

Derives at most one navigation event and the narration anchors from a
finished turn — **heuristic-first, from the turn outcome only** (the SEAM
manifest posture applied to navigation): an anchor is a pointer to
something that exists, resolved from what the turn actually did, never
model-invented. A target with no mapping gets her text answer and no event
— staying still is not a failure.

The one delta against D5 §5's ``materialize(manifest)`` sketch, recorded
in the build notes: **materialize names the surface; the manifest rides
the client's one manifest path.** A second manifest-delivery channel would
be a second thing to keep certified-safe — the cache, the refusal ladder
and VG-23's taint rule already live on the fetch path, so the event
carries ``surface_id`` and the client fetches as it would for any surface.

Duck-typed over the turn outcome on purpose: ``genui`` reaches ``pragya``
only lazily (the channel's own convention), and everything here must be
testable with a ``SimpleNamespace``.
"""
from __future__ import annotations

import re
from typing import Any

from src.ai.inward_auth.tiers import IntentKind

__all__ = ["navigation_for", "anchors_from_outcome"]

#: A district/process code as the estate renders it ("P03"). The pattern is
#: the runtime shape; source never spells any specific code the lint bans.
_PROCESS_CODE = re.compile(r"^p\d{2}$", re.IGNORECASE)

#: Words that mean "the whole place" rather than one district.
_ESTATE_WORDS = frozenset({"estate", "terrace", "home", "map", "overview"})

#: Read-shaped intents — the ones where "show me" wants a surface opened.
_READ_KINDS = frozenset({IntentKind.TENANT_READ, IntentKind.REPORT})


def navigation_for(command: Any) -> dict[str, Any] | None:
    """At most one navigation event per turn — focus *or* materialize,
    never both; a conversation that teleports the user twice per answer is
    worse than one that stays still.

    * A read of a known place **materializes** it (the surface opens).
    * A non-read act on a district **focuses** it (the beam walks there;
      the act's own consequences arrive through their own events).
    """
    if command is None:
        return None
    target = str(getattr(command, "target", "") or "").strip()
    if not target:
        return None
    kind = getattr(command, "kind", None)
    summary = str(getattr(command, "summary", "") or "")

    if kind in _READ_KINDS and target.lower() in _ESTATE_WORDS:
        return {
            "type": "materialize", "surface_id": "terrace", "reason": summary}
    if _PROCESS_CODE.match(target):
        code = target.upper()
        if kind in _READ_KINDS:
            return {
                "type": "materialize", "surface_id": f"district.{code}",
                "reason": summary}
        return {
            "type": "focus",
            "target_ref": {"kind": "district", "id": code},
            "narration": summary or None,
        }
    return None


def anchors_from_outcome(outcome: Any) -> list[dict[str, Any]]:
    """Chips on the narration — each a pointer to something the turn made
    real. Kept deliberately small in v1: the raised tray (the one artifact
    a turn most often leaves behind) and the district the command touched.
    Delegations and record refs are named an honest limit until their refs
    are stable enough to anchor."""
    anchors: list[dict[str, Any]] = []
    if getattr(outcome, "raised_approval", False):
        anchors.append({
            "kind": "tray", "label": "the waiting decision", "ref": "tray"})
    command = getattr(outcome, "command", None)
    target = str(getattr(command, "target", "") or "").strip()
    if command is not None and _PROCESS_CODE.match(target):
        code = target.upper()
        anchors.append({"kind": "district", "label": code, "ref": code})
    return anchors
