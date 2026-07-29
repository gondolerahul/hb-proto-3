"""talent/termination.py — VG-18: termination as workflow (DRIVER D7).

Spec §5's sentence: *"Termination = exit interview + handover memo;
portrait moves to the Gallery."* The design (11_driver.md §5), built:

1. The exit interview is a **tenure summary composed from what already
   exists** — runs, outcomes, dates. Deterministic; no generative prose.
2. The handover memo is an **artifact** (the file-backed store the
   Library lists): what was in flight, where it goes. Pending approvals
   survive the colleague — they belong to the human.
3. **Termination refuses while runs are live.** A termination that
   silently strands a half-done payment chase is the "nothing happened"
   bug this codebase keeps finding; the owner is told what is still
   running and may wait or pause it first.
4. The Gallery keeps the record: ``metadata_extensions["termination"]``
   stamps the entity before the shipped soft-delete marks it DELETED, so
   "colleagues past" is a query, not a new table. **No migration.**
5. Governance untouched: no ``enforce_*`` call (owner decision 3), and
   nothing here deletes audit — usage rows, echoes and influence records
   all survive.

One delta from the §5 design, recorded in the build notes: triggers
belong to PROCESS entities (the registry has no per-agent rows), so a
colleague has no triggers to park — the roster removal *is* the
stop-new-work step, because dispatch fans work to agents through their
process's roster.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval

__all__ = [
    "TenureSummary",
    "TerminationOutcome",
    "compose_memo_text",
    "terminate_colleague",
]

DEFAULT_ARTIFACTS_ROOT = Path("artificate/system-generated")


@dataclass(frozen=True)
class TenureSummary:
    name: str
    entity_id: str
    process_name: str | None
    first_run_at: str | None
    last_run_at: str | None
    runs_total: int
    runs_completed: int
    runs_failed: int
    pending_approvals: int


@dataclass(frozen=True)
class TerminationOutcome:
    status: str  # "terminated" | "refused" | "not_found"
    reason: str | None = None
    running_run_ids: list[str] = field(default_factory=list)
    memo_artifact_id: str | None = None
    summary: TenureSummary | None = None


def compose_memo_text(summary: TenureSummary, now: datetime) -> str:
    """The handover memo — deterministic, from shipped data only."""
    lines = [
        f"# Handover memo — {summary.name}",
        "",
        f"Prepared {now.date().isoformat()} on termination.",
        "",
        "## Tenure",
        f"- Worked from {summary.first_run_at or 'never started'} "
        f"to {summary.last_run_at or '—'}.",
        f"- {summary.runs_total} runs: {summary.runs_completed} completed, "
        f"{summary.runs_failed} failed.",
        "",
        "## In flight at termination",
    ]
    if summary.pending_approvals > 0:
        lines.append(
            f"- {summary.pending_approvals} approval(s) still waiting — they "
            "belong to you, not to the colleague, and remain in the tray.")
    else:
        lines.append("- Nothing was waiting on an approval.")
    lines += [
        "- New inbound work routes to "
        + (f"the {summary.process_name} front door."
           if summary.process_name else "the process front door."),
        "",
        "## The record",
        "- Every run trace, usage row and echo survives this termination.",
        f"- The portrait moves to the Gallery (colleagues past), keyed "
        f"{summary.entity_id}.",
    ]
    return "\n".join(lines)


async def _tenure(
    db: AsyncSession, entity: HierarchicalEntity, process_name: str | None,
) -> TenureSummary:
    runs = (
        await db.execute(
            select(ExecutionRun.status, ExecutionRun.created_at)
            .where(ExecutionRun.entity_id == entity.id))
    ).all()
    pending = (
        await db.execute(
            select(HumanApproval.id)
            .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
            .where(ExecutionRun.entity_id == entity.id,
                   HumanApproval.status == "PENDING"))
    ).all()
    created = sorted(r[1] for r in runs if r[1] is not None)
    return TenureSummary(
        name=entity.display_name or entity.name,
        entity_id=str(entity.id),
        process_name=process_name,
        first_run_at=created[0].date().isoformat() if created else None,
        last_run_at=created[-1].date().isoformat() if created else None,
        runs_total=len(runs),
        runs_completed=sum(1 for r in runs if r[0] == "COMPLETED"),
        runs_failed=sum(1 for r in runs if r[0] == "FAILED"),
        pending_approvals=len(pending),
    )


async def terminate_colleague(
    db: AsyncSession,
    company_id: uuid.UUID,
    entity_id: uuid.UUID,
    *,
    artifacts_root: Path | None = None,
    now: datetime | None = None,
) -> TerminationOutcome:
    now = now or datetime.utcnow()

    entity = (
        await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == entity_id,
                HierarchicalEntity.company_id == company_id,
                HierarchicalEntity.status != "DELETED",
            ))
    ).scalar_one_or_none()
    # An unknown id and a foreign id answer alike (the probe rule).
    if entity is None:
        return TerminationOutcome(status="not_found")
    if entity.type != "AGENT":
        return TerminationOutcome(
            status="refused",
            reason="Only colleagues (AGENT entities) are terminated; "
                   "processes are decommissioned, not exited.")

    running = (
        await db.execute(
            select(ExecutionRun.id).where(
                ExecutionRun.entity_id == entity_id,
                ExecutionRun.status == "RUNNING",
            ))
    ).scalars().all()
    if running:
        return TerminationOutcome(
            status="refused",
            reason=f"{entity.display_name or entity.name} is mid-work on "
                   f"{len(running)} run(s). Wait for them or pause them — a "
                   "termination must never strand half-done work silently.",
            running_run_ids=[str(r) for r in running],
        )

    process_name: str | None = None
    if entity.parent_id is not None:
        parent = (
            await db.execute(
                select(HierarchicalEntity).where(
                    HierarchicalEntity.id == entity.parent_id))
        ).scalar_one_or_none()
        if parent is not None:
            process_name = parent.display_name or parent.name

    summary = await _tenure(db, entity, process_name)
    memo = compose_memo_text(summary, now)

    # File the memo where every platform-saved file goes; the Library's
    # artifact collection lists it from the row.
    root = artifacts_root or DEFAULT_ARTIFACTS_ROOT
    directory = root / str(company_id) / now.date().isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    file_name = f"handover-{entity.name}-{now.strftime('%H%M%S')}.md"
    file_path = directory / file_name
    file_path.write_text(memo, encoding="utf-8")

    from src.ai.artifact_models import Artifact

    artifact = Artifact(
        company_id=company_id,
        agent_id=entity.id,
        origin="system-generated",
        file_category="documents",
        file_name=file_name,
        file_path=str(file_path),
        file_size=len(memo.encode("utf-8")),
        mime_type="text/markdown",
        purpose=f"Handover memo — {summary.name} terminated {now.date().isoformat()}",
        generated_by="talent.termination",
    )
    db.add(artifact)
    await db.flush()

    # The Gallery stamp precedes the delete so "colleagues past" can be a
    # query over metadata, never a new table.
    extensions = dict(entity.metadata_extensions or {})
    extensions["termination"] = {
        "terminated_at": now.isoformat(),
        "memo_artifact_id": str(artifact.id),
        "runs_total": summary.runs_total,
        "runs_completed": summary.runs_completed,
        "pending_approvals_at_exit": summary.pending_approvals,
    }
    entity.metadata_extensions = extensions
    entity.status = "DELETED"
    entity.deleted_at = now
    await db.commit()

    return TerminationOutcome(
        status="terminated",
        memo_artifact_id=str(artifact.id),
        summary=summary,
    )
