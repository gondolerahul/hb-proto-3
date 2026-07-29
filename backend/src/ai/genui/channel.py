"""genui/channel.py — Pragya's event channel (VG-07, D5 §5).

A WebSocket, because the contract is genuinely bidirectional; the shipped
chat endpoints stay (the legacy console uses them) and this is additive.

The four rules, from the contract, and where each lives:

1. **One session across devices.** The socket attaches to the existing
   ``account_manager_sessions`` row — the same row voice and the console
   share. A second device joins the same session's group; it does not open
   a second one, or "zero repeated context" becomes a per-device promise.
2. **``viewport`` is what makes conversation contextual.** The hub keeps
   the session's current viewport and depth; a steward who has to ask
   "which invoice?" while it is on screen has failed §10.2.
3. **The channel may never elevate.** ``step_up_result`` is *cached* here
   as a hint and nothing more — elevation happens only through
   ``/ai/authn/*`` (a failure must count against the lockout), and the gate
   re-checks the real tier on every act. Nothing in this module touches
   ``auth_level``; a test pins that.
4. **Only Pragya writes the client leg (L2).** The socket registry is
   module-private; the two writers are the handler's own replies and
   ``deliver_tray`` — and ``deliver_tray`` is also the **single permitted
   caller** of ``push.send_tray_push``, so the pocket and the socket share
   one delivery door. No socket open → the tray goes to push; a device
   asleep in a pocket is still reached (L8).

Echo fan-out: ``install_echo_fanout`` wires the echo bus here at boot; an
echo lands in the session's context buffer (what Pragya "saw the user do"),
consumed by STEWARD's turn context. It is never re-broadcast to the client
— the client did the act.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from typing import Any, Protocol

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.ai.genui.echo import record_echo, validate_echo
from src.ai.genui.models import UiEcho
from src.ai.genui.navigation import anchors_from_outcome, navigation_for
from src.ai.genui.push import send_tray_push
from src.ai.inward_auth.models import ChannelKind
from src.ai.inward_auth.sessions import get_or_create_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/pragya", tags=["Pragya Channel"])

ECHO_CONTEXT_LIMIT = 50


class SocketLike(Protocol):
    """What the hub needs from a socket — a real WebSocket satisfies it, and
    tests drive the protocol with a fake."""

    async def send_json(self, data: dict[str, Any]) -> None: ...


class _SessionState:
    def __init__(self) -> None:
        self.sockets: set[Any] = set()
        self.viewport: dict[str, Any] | None = None
        self.depth: int = 0
        self.step_up_hint: dict[str, Any] | None = None
        self.echoes: deque[dict[str, Any]] = deque(maxlen=ECHO_CONTEXT_LIMIT)
        #: The open voice leg, if any (S4 — ``voice_channel.VoiceLeg``).
        self.voice: Any | None = None


class ChannelHub:
    """In-memory socket registry, one entry per account-manager session."""

    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, _SessionState] = {}
        self._by_user: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}

    # ── membership ────────────────────────────────────────────────────────
    def join(
        self, session_id: uuid.UUID,
        company_id: uuid.UUID, user_id: uuid.UUID, socket: Any,
    ) -> _SessionState:
        state = self._sessions.setdefault(session_id, _SessionState())
        state.sockets.add(socket)
        self._by_user[(company_id, user_id)] = session_id
        return state

    def leave(self, session_id: uuid.UUID, socket: Any) -> None:
        state = self._sessions.get(session_id)
        if state is None:
            return
        state.sockets.discard(socket)
        if not state.sockets:
            # Context survives a disconnect on purpose: the session is the
            # unit of memory, not the socket.
            pass

    def state_for_user(
        self, company_id: uuid.UUID, user_id: uuid.UUID,
    ) -> _SessionState | None:
        session_id = self._by_user.get((company_id, user_id))
        return self._sessions.get(session_id) if session_id else None

    def users_with_open_sockets(self, company_id: uuid.UUID) -> set[uuid.UUID]:
        """Who in this company is listening right now (STEWARD's watcher asks
        before composing a tray). A user whose sockets have all left keeps
        their ``_by_user`` entry — session context survives a disconnect on
        purpose — so presence is decided by live sockets, not by the map."""
        listening: set[uuid.UUID] = set()
        for (cid, uid), session_id in self._by_user.items():
            if cid != company_id:
                continue
            state = self._sessions.get(session_id)
            if state is not None and state.sockets:
                listening.add(uid)
        return listening

    # ── the one client-leg writer (rule 4) ────────────────────────────────
    async def _emit(self, state: _SessionState, event: dict[str, Any]) -> int:
        delivered = 0
        for socket in list(state.sockets):
            try:
                await socket.send_json(event)
                delivered += 1
            except Exception:  # noqa: BLE001 — one dead socket must not stop the rest
                state.sockets.discard(socket)
        return delivered

    async def _emit_bytes(self, state: _SessionState, data: bytes) -> int:
        """The audio half of the client leg (S4) — same writer, same rule 4:
        only Pragya's own modules hold the registry, so only her synthesis
        can put sound on the wire."""
        delivered = 0
        for socket in list(state.sockets):
            try:
                await socket.send_bytes(data)
                delivered += 1
            except Exception:  # noqa: BLE001 — one dead socket must not stop the rest
                state.sockets.discard(socket)
        return delivered


_hub = ChannelHub()


def hub() -> ChannelHub:
    return _hub


# ── the single delivery door (L8) ────────────────────────────────────────────

async def deliver_tray(
    db: Any,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    tray: dict[str, Any],
    *,
    push_transport: Any = None,
) -> str:
    """Deliver one tray: sockets first, push when nobody is listening.
    Returns "socket" | "push" | "nowhere" — the caller may care, the user
    always gets at most one path (no double-notification)."""
    state = _hub.state_for_user(company_id, user_id)
    if state is not None and state.sockets:
        delivered = await _hub._emit(state, {"type": "deliver_tray", "tray": tray})
        if delivered:
            return "socket"
    sentence = (tray.get("what_happened") or {}).get(
        "sentence") or "A decision is waiting for you."
    reached = await send_tray_push(
        db, company_id, user_id,
        tray_id=str(tray.get("tray_id")), one_sentence=str(sentence),
        transport=push_transport)
    return "push" if reached else "nowhere"


# ── echo fan-out (installed at boot) ─────────────────────────────────────────

async def echo_fanout(echo: UiEcho) -> None:
    """What Pragya saw the user do — into the session's context buffer,
    never back to the client."""
    if echo.user_id is None:
        return
    state = _hub.state_for_user(echo.company_id, echo.user_id)
    if state is not None:
        state.echoes.append({
            "sentence": echo.sentence,
            "action_ref": echo.action_ref,
            "occurred_at": echo.occurred_at.isoformat(),
        })


# ── the protocol ─────────────────────────────────────────────────────────────

async def dispatch_message(
    db: Any,
    state: _SessionState,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    message: dict[str, Any],
) -> dict[str, Any] | None:
    """One client message in, at most one **caller-scoped** reply out.
    Unknown types fail visible (an error event), never silent (the repo's
    standing rule).

    The utterance branch is the exception and speaks **to the session**
    (STEWARD S3): presence → at most one navigation event → the narration —
    because one session spans devices (rule 1), and an answer only the
    asking device hears would make "zero repeated context" a per-device
    promise. Its caller-scoped return is an error, or nothing.
    """
    kind = message.get("type")

    if kind == "viewport":
        state.viewport = message.get("context_ref")
        return None
    if kind == "depth_change":
        state.depth = int(message.get("level", 0))
        return None
    if kind == "step_up_result":
        # Rule 3: a *hint* for presence only. The session row is untouched;
        # the tier gate re-checks on every act.
        state.step_up_hint = {
            "tier": message.get("tier"), "ok": bool(message.get("ok"))}
        return None
    if kind == "action_echo":
        payload = {
            "sentence": message.get("sentence"),
            "action_ref": message.get("action_ref"),
            "manifest_hash": message.get("manifest_hash"),
            "component_id": message.get("component_id"),
            "occurred_at": message.get("occurred_at"),
        }
        problem = validate_echo(payload)
        if problem is not None:
            return {"type": "error", "reason": problem}
        echo = await record_echo(db, company_id, user_id, payload)
        return {"type": "echo_ack", "echo_id": str(echo.id)}
    if kind == "utterance":
        text = str(message.get("text") or "").strip()
        if not text:
            return {"type": "error", "reason": "an utterance needs text"}
        error, _spoken = await handle_utterance(
            db, state, company_id, user_id, text)
        return error

    if kind == "mic":
        from src.ai.genui import voice_channel

        mic_state = message.get("state")
        if mic_state == "open":
            return await voice_channel.open_mic(db, state, company_id, user_id)
        if mic_state == "closed":
            await voice_channel.close_mic(state)
            return None
        return {"type": "error", "reason": f"unknown mic state {mic_state!r}"}

    return {"type": "error", "reason": f"unknown message type {kind!r}"}


async def handle_utterance(
    db: Any,
    state: _SessionState,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    text: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """One heard sentence through the one turn loop, told to the session.

    Returns ``(caller_error, spoken_reply)`` — the second is what the voice
    leg synthesises; the session has already received presence → at most
    one navigation event → the narration by the time this returns. Shared
    by the typed path and the voice leg so a spoken command and a typed one
    are the same turn in every respect but the audio.
    """
    from src.ai.pragya.runtime import TurnRequest, run_turn

    await _hub._emit(state, {"type": "presence", "state": "working"})
    try:
        result = await run_turn(db, TurnRequest(
            company_id=company_id, user_id=user_id, text=text,
            channel_kind=ChannelKind.CONSOLE))
        await db.commit()
    except Exception:  # noqa: BLE001 — she is away, not the channel dead
        # Presence must not pretend to listen when the runtime cannot run
        # (§7's honest mapping). The next successful turn's own working →
        # listening cycle clears it.
        logger.exception("pragya turn failed on the channel")
        await _hub._emit(state, {"type": "presence", "state": "away"})
        return ({
            "type": "error",
            "reason": "I can't act on that right now — something failed "
                      "on my side. Give me a moment and ask again.",
        }, None)

    navigation = navigation_for(result.command)
    if navigation is not None:
        # She walks the map before she speaks — the beam or the surface
        # arrives, then the words about it.
        await _hub._emit(state, navigation)
    event: dict[str, Any] = {
        "type": "narrate", "text": result.reply,
        "anchors": anchors_from_outcome(result)}
    if result.needs_step_up or result.needs_oob:
        # Reported so the client can open the ceremony — the ceremony
        # itself runs only through /ai/authn/* (rule 3).
        event["step_up"] = {
            "tier": result.tier,
            "command_ref": result.command_ref,
            "oob": result.needs_oob,
        }
    await _hub._emit(state, event)
    await _hub._emit(state, {"type": "presence", "state": "listening"})
    return (None, result.reply)


@router.websocket("/channel")
async def channel_socket(websocket: WebSocket) -> None:
    """VG-07. Token in the query (the browser cannot set WS headers); the
    same JWT the REST surface takes."""
    from src.auth.dependencies import _authenticate_user
    from src.common.database import AsyncSessionLocal

    token = websocket.query_params.get("token")
    async with AsyncSessionLocal() as db:
        try:
            user = await _authenticate_user(token, db)
        except Exception:  # noqa: BLE001 — an unauthenticated socket gets no detail
            await websocket.close(code=4401)
            return
        company_id = user.company_id
        user_id = user.id
        session = await get_or_create_session(
            db, company_id=company_id,
            channel_kind=ChannelKind.CONSOLE, user_id=user_id)
        session_id = session.id
        await db.commit()

    await websocket.accept()
    state = _hub.join(session_id, company_id, user_id, websocket)
    await _hub._emit(state, {"type": "presence", "state": "listening"})
    try:
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                break
            frame = raw.get("bytes")
            if frame is not None:
                # Binary frames are the mic (S4) — straight to the voice
                # leg's queue, no session, no dispatch.
                from src.ai.genui import voice_channel

                await voice_channel.feed_audio(state, frame)
                continue
            try:
                message = json.loads(raw.get("text") or "")
            except ValueError:
                await websocket.send_json(
                    {"type": "error", "reason": "not JSON"})
                continue
            async with AsyncSessionLocal() as db:
                # Presence transitions live inside dispatch_message (S3) —
                # the loop only carries caller-scoped replies.
                reply = await dispatch_message(
                    db, state, company_id, user_id, message)
            if reply is not None:
                await websocket.send_json(reply)
    except WebSocketDisconnect:
        pass
    finally:
        from src.ai.genui import voice_channel

        # A disconnect aborts synthesis too — nobody is left to talk to.
        await voice_channel.close_mic(state, abort=True)
        _hub.leave(session_id, websocket)
