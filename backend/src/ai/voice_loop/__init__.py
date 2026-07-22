"""ai/voice_loop — realtime voice inside the governed loop (Inc-3 VOICE, B7).

The shipped ``src/voice/`` stack handles media: carriers, streams, realtime
model clients, transcripts. This package handles what B7 asked and that stack
does not — how a half-second conversational turn coexists with an eight-stage
loop, and what happens to governance when it cannot.

* ``profile``   — which stages run live and which defer. The answer's core:
  the PolicyGate is pure, so governance stays inline; LLM judgment defers.
* ``live_gate`` — the voice-shaped consequence of a gate decision. A governed
  act is *promised*, never completed on the turn.
* ``identity``  — caller ID resolves a binding but can never elevate.
* ``handoff``   — agent-to-agent transfer that keeps the media session and the
  context, rather than bridging the call.
* ``deferred``  — the post-call run that executes the stages the turn skipped.

**This init deliberately re-exports only ``profile``.** The Solo Pack's KAR-01
template reads the profile, and ``inward_auth`` is reached *from* ``identity``
— so importing ``identity`` here would close the cycle
``bindings → consent → templates → profile → identity → bindings``. Import the
submodules directly (``from src.ai.voice_loop.identity import …``). Same
reasoning as the Solo Pack tools registering at the entry points rather than
from a package init: keep an init free of anything that imports back toward
its own consumers.
"""
from __future__ import annotations

__all__ = [
    "REALTIME_PROFILE",
    "LIVE_STAGES",
    "DEFERRED_STAGES",
    "LIVE_COMPLETION_RULE",
    "TURN_BUDGET_MS",
    "Stage",
    "Disposition",
]

from src.ai.voice_loop.profile import (
    DEFERRED_STAGES,
    LIVE_COMPLETION_RULE,
    LIVE_STAGES,
    REALTIME_PROFILE,
    TURN_BUDGET_MS,
    Disposition,
    Stage,
)
