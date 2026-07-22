"""pragya/commands.py — executing an authorised command.

Reached only after ``runtime.run_turn`` classified the intent and
``require_tier`` allowed it. Every function here therefore re-checks the
decision it was given rather than trusting the caller: an executor that
assumes it was called correctly is one refactor away from being callable
incorrectly.

Scope is deliberately narrow. Pragya can pause and resume a tenant's own
processes, and she can demote an agent. She cannot approve anything — approvals
are console artifacts at the Judgment Desk, which is standing rule 2, and the
one thing that must never become reachable from a channel she talks on.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.governance.demotion import one_level_down
from src.ai.inward_auth.models import AccountManagerSession
from src.ai.inward_auth.sessions import require_tier
from src.ai.inward_auth.tiers import IntentKind
from src.ai.orm.entity import HierarchicalEntity
from src.ai.pragya.intents import ExtractedCommand
from src.ai.schemas.governance import AutonomyLevel
from src.ai.signals.models import SignalTypes, TriggerRegistration
from src.ai.signals.service import emit_signal

logger = logging.getLogger(__name__)

__all__ = ["CommandOutcome", "execute_command", "APPROVAL_REDIRECT", "ALL_TRIGGERS"]

#: Explicit whole-workforce scope. Only the kill switch and an owner who
#: literally said "everything" reach it — never an unresolved target.
ALL_TRIGGERS = "*"


#: Standing rule 2. An owner asking Pragya to approve something is redirected,
#: never accommodated — the whole point is that an approval cannot be collected
#: over a channel that might be the compromised one.
APPROVAL_REDIRECT = (
    "I can't approve that myself — approvals live in the Judgment Desk so "
    "there's always a record of a human making the call, and me taking your "
    "word for it over chat would defeat that. It's waiting for you at "
    "/ai/approvals; it takes one click."
)


@dataclass
class CommandOutcome:
    executed: bool
    message: str
    changed: dict[str, Any] | None = None


async def _pause_or_resume(
    db: AsyncSession, company_id: uuid.UUID, *, enable: bool, target: str | None,
) -> CommandOutcome:
    """Flip trigger registrations on or off.

    Pausing disarms the triggers rather than deleting anything: inbound work
    still arrives and is parked, so resuming picks up where it left off
    instead of starting from a gap. That mirrors C5's read-only dunning state,
    where inbound is parked-not-dropped for the same reason.
    """
    # An unscoped pause is ambiguous, and resolving ambiguity toward "all" is
    # the worst available guess: "pause invoice chasing" would silently stop
    # the whole workforce. Only the kill switch means everything, and it says
    # so explicitly by passing ALL_TRIGGERS.
    if target is None:
        verb = "resume" if enable else "pause"
        return CommandOutcome(
            False,
            f"Which one should I {verb}? I'd rather ask than {verb} everything "
            f"by mistake — or say \"{verb} everything\" if that's what you meant.")

    stmt = select(TriggerRegistration).where(
        TriggerRegistration.company_id == company_id)

    if target != ALL_TRIGGERS:
        # An owner says "invoice chasing", not "invoice.overdue" — so the
        # target is matched against the owning process's display name first,
        # and only then against the raw signal pattern.
        needle = f"%{target.strip().lower()}%"
        stmt = stmt.join(
            HierarchicalEntity,
            TriggerRegistration.process_entity_id == HierarchicalEntity.id,
        ).where(
            func.lower(HierarchicalEntity.display_name).like(needle)
            | func.lower(TriggerRegistration.type_pattern).like(needle)
        )

    rows = list((await db.execute(stmt)).scalars().all())

    if target and not rows:
        return CommandOutcome(
            False,
            f"I couldn't find anything matching \"{target}\". Want me to "
            "list what's currently running?")

    changed = 0
    for row in rows:
        if row.enabled != enable:
            row.enabled = enable
            changed += 1
    await db.flush()

    verb = "resumed" if enable else "paused"
    scope = "everything" if target == ALL_TRIGGERS else f'"{target}"'
    if not changed:
        return CommandOutcome(
            True, f"{scope.capitalize()} was already {verb}. Nothing to change.",
            {"triggers_changed": 0})

    return CommandOutcome(
        True,
        f"Done — {verb} {scope} ({changed} trigger"
        f"{'s' if changed != 1 else ''}). Anything that arrives meanwhile is "
        f"parked, not dropped, so nothing gets lost."
        if not enable else
        f"Done — {verb} {scope} ({changed} trigger"
        f"{'s' if changed != 1 else ''}). Anything parked while it was off "
        f"will be picked up.",
        {"triggers_changed": changed},
    )


async def _demote_agent(
    db: AsyncSession, company_id: uuid.UUID, target: str | None,
) -> CommandOutcome:
    """Owner-commanded demotion — the C4 trigger a human pulls."""
    if not target:
        return CommandOutcome(
            False, "Which agent should I pull back? Name it and I'll do it.")

    needle = target.strip().lower()
    entity = (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.type == "AGENT",
            func.lower(HierarchicalEntity.display_name).contains(needle),
        ).limit(1)
    )).scalars().first()

    if entity is None:
        return CommandOutcome(False, f"I couldn't find an agent called \"{target}\".")

    governance = dict(entity.governance or {})
    try:
        current = AutonomyLevel(governance.get("autonomy_level") or "A1")
    except ValueError:
        current = AutonomyLevel.A1

    target_level = one_level_down(current)
    if target_level == current:
        return CommandOutcome(
            True,
            f"{entity.display_name} is already at {current.value} — it asks "
            "you before every external action, so there's nothing further to "
            "take away.")

    governance["autonomy_level"] = target_level.value
    governance["autonomy_demoted_at"] = datetime.utcnow().isoformat()
    governance["autonomy_demotion_reason"] = ["owner command"]
    entity.governance = governance

    await emit_signal(
        db, company_id=company_id, source="pragya",
        type=SignalTypes.GOVERNANCE_AUTONOMY_DEMOTED,
        payload={
            "agent_id": str(entity.id),
            "display_name": entity.display_name,
            "from_level": current.value,
            "to_level": target_level.value,
            "triggers": ["owner_command"],
            "reasons": ["you asked me to"],
        },
    )
    return CommandOutcome(
        True,
        f"{entity.display_name} moved from {current.value} to "
        f"{target_level.value}. It'll keep working, it just checks with you "
        f"more often now.",
        {"agent_id": str(entity.id), "to_level": target_level.value},
    )


async def execute_command(
    db: AsyncSession,
    session: AccountManagerSession,
    command: ExtractedCommand,
    *,
    company_id: uuid.UUID,
) -> CommandOutcome:
    """Run an authorised command.

    Re-checks authorisation before acting. The check is not redundant with
    ``run_turn``'s: a step-up can lapse between classification and
    execution, and this is the moment that actually matters.
    """
    decision = require_tier(session, command.tier)
    if not decision.allowed:
        return CommandOutcome(
            False,
            "That verification has expired — one more tap and I'll run it.")

    if command.kind == IntentKind.PROCESS_PAUSE:
        return await _pause_or_resume(
            db, company_id, enable=False, target=command.target)

    if command.kind == IntentKind.PROCESS_RESUME:
        return await _pause_or_resume(
            db, company_id, enable=True, target=command.target)

    if command.kind == IntentKind.AUTONOMY_RAISE:
        # Only demotion is executable by command. Raising autonomy needs the
        # §9.7 evidence and its own checkpoint, and "promote X" over chat is
        # exactly the shortcut C4's anti-rubber-stamp rule exists to prevent.
        if "demote" in command.summary.lower() or "pull back" in command.summary.lower():
            return await _demote_agent(db, company_id, command.target)
        return CommandOutcome(
            False,
            "I can't raise an agent's autonomy from here — that needs evidence "
            "it's earned it, including a random re-audit of its recent work. "
            "I can show you where it stands if you'd like.")

    if command.kind == IntentKind.LOOP_KILL_SWITCH:
        # The one command that legitimately means everything.
        return await _pause_or_resume(
            db, company_id, enable=False, target=ALL_TRIGGERS)

    return CommandOutcome(
        False,
        "I understood that as a command but I don't have a safe way to run it "
        "yet. Can you tell me what you'd like to happen?")
