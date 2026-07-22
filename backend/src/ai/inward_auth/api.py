"""inward_auth/api.py — the ``/ai/authn/*`` surface (Inc-3 AUTH).

Company-scoped and console-only by construction: every route hangs off the
shipped JWT session, which *is* the console channel's bound identity. Other
channels do not step up here — they receive a link that opens this console and
runs the ceremony in the browser, because the browser is where the
authenticator lives (decision 2, console-first).

The failure path is the load-bearing part of this file. Every ceremony that can
fail routes through ``_fail_step_up``, which counts the attempt against the
session and — on crossing the threshold — locks T2+ and alerts every channel
the user registered. A route that verified a factor without going through it
would silently disable the brute-force protection, so there is exactly one way
to fail.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth import bindings as binding_service
from src.ai.inward_auth import oob as oob_service
from src.ai.inward_auth import step_up as totp_service
from src.ai.inward_auth import webauthn_ceremony
from src.ai.inward_auth.models import AccountManagerSession, AuthLevel, ChannelKind
from src.ai.inward_auth.sessions import (
    effective_level,
    elevate,
    get_or_create_session,
    is_locked,
    record_failed_stepup,
    require_tier,
)
from src.ai.inward_auth.tiers import CommandIntent, Tier, classify
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/authn", tags=["Inward Channel Auth"])


# ── request bodies ────────────────────────────────────────────────────────────

class BindingCreate(BaseModel):
    channel_kind: str
    address: str
    label: str | None = None


class BindingConfirm(BaseModel):
    binding_id: uuid.UUID
    code: str


class TotpConfirm(BaseModel):
    code: str


class StepUpRequest(BaseModel):
    method: str = Field("totp", description="totp | passkey")
    code: str | None = None
    credential: dict[str, Any] | None = None


class CeremonyFinish(BaseModel):
    credential: dict[str, Any]
    label: str | None = None


class OobIssue(BaseModel):
    command_ref: str


class OobConfirmBody(BaseModel):
    challenge_id: uuid.UUID
    command_ref: str
    nonce: str


class ClassifyRequest(BaseModel):
    kind: str
    category: str | None = None
    amount: float | None = None
    band: float | None = None
    touches_tenant_data: bool = True


# ── helpers ───────────────────────────────────────────────────────────────────

async def _console_session(
    db: AsyncSession, user: User
) -> AccountManagerSession:
    return await get_or_create_session(
        db,
        company_id=cast(uuid.UUID, user.company_id),
        user_id=cast(uuid.UUID, user.id),
        channel_kind=ChannelKind.CONSOLE,
    )


async def _fail_step_up(
    db: AsyncSession, session: AccountManagerSession, user: User, reason: str,
) -> dict[str, Any]:
    """The single failure path: count it, and alert every channel on lockout."""
    locked = await record_failed_stepup(db, session)
    alerted = 0
    if locked:
        alerted = await binding_service.alert_all_channels(
            db,
            company_id=cast(uuid.UUID, user.company_id),
            user_id=cast(uuid.UUID, user.id),
            event="step_up_lockout",
            detail=(f"{session.failed_stepups} failed step-up attempts; "
                    "sensitive commands are locked temporarily"),
        )
    await db.commit()
    return {
        "ok": False,
        "reason": reason,
        "locked": locked,
        "failed_attempts": session.failed_stepups,
        "channels_alerted": alerted,
    }


async def _require_t2_console(
    db: AsyncSession, user: User
) -> AccountManagerSession:
    """Guard for the routes that are themselves T2 (binding changes)."""
    session = await _console_session(db, user)
    decision = require_tier(session, Tier.T2)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail={
            "reason": decision.reason,
            "needs_step_up": decision.needs_step_up,
            "locked": decision.locked,
        })
    return session


# ── status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What this console session holds, and what factors are available to it."""
    user_id = cast(uuid.UUID, current_user.id)
    session = await _console_session(db, current_user)
    await db.commit()

    return {
        "auth_level": effective_level(session),
        "elevated_until": (session.elevated_until.isoformat()
                           if session.elevated_until else None),
        "elevated_by": session.elevated_by,
        "locked": is_locked(session),
        "locked_until": (session.locked_until.isoformat()
                         if session.locked_until else None),
        "failed_stepups": session.failed_stepups,
        "has_passkey": await webauthn_ceremony.has_passkey(db, user_id=user_id),
        "has_totp": await totp_service.has_totp(db, user_id),
        "bindings": [
            {
                "id": str(b.id),
                "channel_kind": b.channel_kind,
                "address": b.address,
                "label": b.label,
                "verified": b.verified_at is not None,
            }
            for b in await binding_service.list_bindings(db, user_id=user_id)
        ],
    }


@router.post("/classify")
async def post_classify(
    body: ClassifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Classify a command and say whether this session could run it.

    Exposed so the console can show the owner *why* a command needs a
    ceremony before they attempt it, using the same classifier the executor
    will apply — not a second copy of the rules in the frontend.
    """
    session = await _console_session(db, current_user)
    await db.commit()

    result = classify(CommandIntent(
        kind=body.kind, category=body.category, amount=body.amount,
        band=body.band, touches_tenant_data=body.touches_tenant_data))
    decision = require_tier(session, result.tier)

    return {
        "tier": result.tier.name,
        "why": result.reason,
        "allowed": decision.allowed,
        "current_level": decision.current_level,
        "required_level": decision.required_level,
        "needs_step_up": decision.needs_step_up,
        "needs_oob": decision.needs_oob,
        "locked": decision.locked,
        "reason": decision.reason,
    }


# ── channel bindings (T5) ─────────────────────────────────────────────────────

@router.get("/bindings")
async def get_bindings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = await binding_service.list_bindings(
        db, user_id=cast(uuid.UUID, current_user.id))
    return [
        {
            "id": str(b.id),
            "channel_kind": b.channel_kind,
            "address": b.address,
            "label": b.label,
            "verified": b.verified_at is not None,
            "last_seen_at": b.last_seen_at.isoformat() if b.last_seen_at else None,
        }
        for b in rows
    ]


@router.post("/bindings")
async def post_binding(
    body: BindingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start enrolling a channel. Enrolling is itself a T2 command."""
    await _require_t2_console(db, current_user)
    result = await binding_service.begin_enrollment(
        db,
        company_id=cast(uuid.UUID, current_user.company_id),
        user_id=cast(uuid.UUID, current_user.id),
        channel_kind=body.channel_kind,
        address=body.address,
        label=body.label,
    )
    if not result.ok:
        await db.rollback()
        raise HTTPException(status_code=400, detail=result.reason)
    await db.commit()
    # The OTP itself is never returned — it goes to the channel being claimed,
    # which is the entire proof. Returning it here would defeat the handshake.
    return {"ok": True, "binding_id": str(result.binding_id), "reason": result.reason}


@router.post("/bindings/confirm")
async def post_binding_confirm(
    body: BindingConfirm,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await binding_service.confirm_enrollment(
        db,
        company_id=cast(uuid.UUID, current_user.company_id),
        user_id=cast(uuid.UUID, current_user.id),
        binding_id=body.binding_id,
        code=body.code,
    )
    await db.commit()
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.reason)
    return {"ok": True, "binding_id": str(result.binding_id)}


@router.delete("/bindings/{binding_id}")
async def delete_binding(
    binding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_t2_console(db, current_user)
    revoked = await binding_service.revoke_binding(
        db, user_id=cast(uuid.UUID, current_user.id), binding_id=binding_id)
    await db.commit()
    if not revoked:
        raise HTTPException(status_code=404, detail="no such binding")
    return {"ok": True}


# ── TOTP (the §11.3 fallback) ─────────────────────────────────────────────────

@router.post("/totp/enroll")
async def post_totp_enroll(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    enrollment = await totp_service.begin_totp_enrollment(
        db,
        user_id=cast(uuid.UUID, current_user.id),
        account_label=cast(str, current_user.email),
    )
    await db.commit()
    return {
        "secret": enrollment.secret,
        "provisioning_uri": enrollment.provisioning_uri,
    }


@router.post("/totp/confirm")
async def post_totp_confirm(
    body: TotpConfirm,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await totp_service.confirm_totp_enrollment(
        db, user_id=cast(uuid.UUID, current_user.id), code=body.code)
    await db.commit()
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.reason)
    return {"ok": True, "reason": result.reason}


# ── WebAuthn ceremonies ───────────────────────────────────────────────────────

@router.post("/webauthn/register/begin")
async def post_webauthn_register_begin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    options = await webauthn_ceremony.begin_registration(
        db,
        user_id=cast(uuid.UUID, current_user.id),
        user_name=cast(str, current_user.email),
        display_name=cast(str, current_user.full_name),
    )
    await db.commit()
    return options


@router.post("/webauthn/register/finish")
async def post_webauthn_register_finish(
    body: CeremonyFinish,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await webauthn_ceremony.finish_registration(
        db, user_id=cast(uuid.UUID, current_user.id),
        credential=body.credential, label=body.label)
    await db.commit()
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.reason)
    return {"ok": True, "reason": result.reason}


@router.get("/webauthn/credentials")
async def get_webauthn_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = await webauthn_ceremony.list_credentials(
        db, user_id=cast(uuid.UUID, current_user.id))
    return [
        {
            "id": str(c.id),
            "label": c.label,
            "created_at": c.created_at.isoformat(),
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        }
        for c in rows
    ]


@router.delete("/webauthn/credentials/{credential_row_id}")
async def delete_webauthn_credential(
    credential_row_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_t2_console(db, current_user)
    deleted = await webauthn_ceremony.delete_credential(
        db, user_id=cast(uuid.UUID, current_user.id),
        credential_row_id=credential_row_id)
    await db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="no such credential")
    return {"ok": True}


@router.post("/webauthn/authenticate/begin")
async def post_webauthn_authenticate_begin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _console_session(db, current_user)
    if is_locked(session):
        await db.commit()
        raise HTTPException(
            status_code=403, detail="step-up is locked after repeated failures")

    options = await webauthn_ceremony.begin_authentication(
        db, user_id=cast(uuid.UUID, current_user.id))
    await db.commit()
    if options is None:
        raise HTTPException(status_code=400, detail="no passkey registered")
    return options


# ── step-up: the one elevation path ───────────────────────────────────────────

@router.post("/step-up")
async def post_step_up(
    body: StepUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Complete a ceremony and elevate the console session.

    Both factors land here so that success and failure are handled once:
    ``passkey`` finishes an assertion begun at ``/webauthn/authenticate/begin``,
    ``totp`` verifies a code.
    """
    session = await _console_session(db, current_user)
    user_id = cast(uuid.UUID, current_user.id)

    if is_locked(session):
        await db.commit()
        raise HTTPException(
            status_code=403, detail="step-up is locked after repeated failures")

    if body.method == "passkey":
        if body.credential is None:
            raise HTTPException(status_code=400, detail="credential is required")
        result = await webauthn_ceremony.finish_authentication(
            db, user_id=user_id, credential=body.credential)
    elif body.method == "totp":
        if not body.code:
            raise HTTPException(status_code=400, detail="code is required")
        result = await totp_service.verify_totp(db, user_id=user_id, code=body.code)
    else:
        raise HTTPException(status_code=400, detail=f"unknown method {body.method!r}")

    if not result.ok:
        return await _fail_step_up(db, session, current_user, result.reason)

    await elevate(db, session, method=result.method)
    await db.commit()
    return {
        "ok": True,
        "auth_level": session.auth_level,
        "elevated_by": session.elevated_by,
        "elevated_until": (session.elevated_until.isoformat()
                           if session.elevated_until else None),
    }


# ── T3 out-of-band leg ────────────────────────────────────────────────────────

@router.post("/oob/issue")
async def post_oob_issue(
    body: OobIssue,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Send a confirmation nonce to a *second* registered channel."""
    session = await _console_session(db, current_user)
    challenge = await oob_service.issue_challenge(
        db, session, command_ref=body.command_ref)
    if not challenge.ok:
        await db.rollback()
        raise HTTPException(status_code=400, detail=challenge.reason)
    await db.commit()
    # The nonce goes to the second channel, never back over this one — that
    # separation is the only thing the second leg is buying.
    return {
        "ok": True,
        "challenge_id": str(challenge.challenge_id),
        "sent_to_channel": challenge.channel_kind,
    }


@router.post("/oob/confirm")
async def post_oob_confirm(
    body: OobConfirmBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _console_session(db, current_user)
    result = await oob_service.confirm(
        db,
        company_id=cast(uuid.UUID, current_user.company_id),
        user_id=cast(uuid.UUID, current_user.id),
        challenge_id=body.challenge_id,
        command_ref=body.command_ref,
        nonce=body.nonce,
    )
    if not result.ok:
        # A wrong nonce is a failed verification like any other.
        return await _fail_step_up(db, session, current_user, result.reason)

    await db.commit()
    return {"ok": True, "auth_level": AuthLevel.OOB_CONFIRMED, "reason": result.reason}
