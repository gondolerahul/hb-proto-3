"""tenant_schema/record_service.py — the one write path for tenant records.

Every record write goes through here (§19.2): validation, ref materialisation
into ``tenant_record_links``, compare-and-set versioning (§23.2), soft delete
(§19.5), and write ownership (§23.1 — owner writes, others propose). Agents
never touch the tables directly.

Cross-DB note: records/links live in the **tenant** DB (the injected session);
signals live in the **control plane** (§10.5), so ``object.change_proposed`` /
``object.write_conflict`` are emitted through a short separate control-plane
transaction — a notification, never part of the record transaction.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.tenant_schema.models import (
    TenantEntityDef,
    TenantRecord,
    TenantRecordLink,
)
from src.ai.tenant_schema.validation import (
    RefAssignment,
    ValidationError,
    validate_record_data,
)

logger = logging.getLogger(__name__)

__all__ = ["RecordService", "RecordResult", "OwnershipError", "ConflictError"]

WRITTEN = "written"
PROPOSED = "proposed"
CONFLICT = "conflict"
HITL_REQUIRED = "hitl_required"


class OwnershipError(PermissionError):
    pass


class ConflictError(RuntimeError):
    pass


@dataclass
class RecordResult:
    status: str                       # written | proposed | conflict | hitl_required
    record: Optional[TenantRecord] = None
    signal_id: Optional[uuid.UUID] = None
    reason: str = ""


class RecordService:
    """Owner-mediated CRUD over one tenant's business records."""

    def __init__(self, session: AsyncSession, company_id: uuid.UUID, redis: Any = None) -> None:
        self.db = session
        self.company_id = company_id
        self.redis = redis

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get(self, record_id: uuid.UUID, *, include_deleted: bool = False) -> Optional[TenantRecord]:
        rec = await self.db.get(TenantRecord, record_id)
        if rec is None or rec.company_id != self.company_id:
            return None
        if rec.deleted_at is not None and not include_deleted:
            return None
        return rec

    async def list_records(self, def_name: str, *, limit: int = 100) -> list[TenantRecord]:
        d = await self._def_by_name(def_name)
        if d is None:
            return []
        rows = (await self.db.execute(
            select(TenantRecord).where(
                TenantRecord.company_id == self.company_id,
                TenantRecord.entity_def_id == d.id,
                TenantRecord.deleted_at.is_(None),
            ).order_by(TenantRecord.created_at.desc()).limit(limit)
        )).scalars().all()
        return list(rows)

    async def traverse(
        self, record_id: uuid.UUID, *, rel_type: str | None = None, depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Walk outgoing links from a record (breadth-first, bounded depth)."""
        out: list[dict[str, Any]] = []
        frontier = [record_id]
        seen = {record_id}
        for _ in range(max(1, depth)):
            if not frontier:
                break
            stmt = select(TenantRecordLink).where(
                TenantRecordLink.company_id == self.company_id,
                TenantRecordLink.src_record_id.in_(frontier),
            )
            if rel_type:
                stmt = stmt.where(TenantRecordLink.rel_type == rel_type)
            links = (await self.db.execute(stmt)).scalars().all()
            next_frontier: list[uuid.UUID] = []
            for lk in links:
                out.append({"src": str(lk.src_record_id), "dst": str(lk.dst_record_id),
                            "rel_type": lk.rel_type})
                if lk.dst_record_id not in seen:
                    seen.add(lk.dst_record_id)
                    next_frontier.append(lk.dst_record_id)
            frontier = next_frontier
        return out

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create(
        self, def_name: str, data: dict[str, Any], *,
        actor_process_code: str | None = None, run_id: uuid.UUID | None = None,
        force_cross_owner: bool = False,
    ) -> RecordResult:
        d = await self._require_def(def_name)
        gate = await self._ownership_gate(d, data, actor_process_code, run_id,
                                          op="create", force=force_cross_owner)
        if gate is not None:
            return gate

        validated = validate_record_data(d.fields or [], data, partial=False)
        await self._verify_ref_targets(validated.refs)

        record = TenantRecord(
            company_id=self.company_id, entity_def_id=d.id,
            data=validated.clean_data, version=1, def_version=d.version,
            updated_by_run_id=run_id,
        )
        self.db.add(record)
        await self.db.flush()
        await self._materialise_links(record.id, validated.refs)
        return RecordResult(WRITTEN, record=record)

    async def update(
        self, record_id: uuid.UUID, data: dict[str, Any], *, expected_version: int,
        actor_process_code: str | None = None, run_id: uuid.UUID | None = None,
        force_cross_owner: bool = False, _retried: bool = False,
    ) -> RecordResult:
        record = await self.get(record_id)
        if record is None:
            raise ValueError(f"record {record_id} not found")
        d = await self._def_by_id(record.entity_def_id)
        if d is None:
            raise ValueError("record has no def")

        gate = await self._ownership_gate(d, data, actor_process_code, run_id,
                                          op="update", force=force_cross_owner,
                                          record_id=record_id)
        if gate is not None:
            return gate

        # Compare-and-set (§23.2): a stale version gets one bounded re-read-and-
        # retry, then an object.write_conflict signal instead of a blind overwrite.
        if record.version != expected_version:
            if not _retried:
                await self.db.refresh(record)
                if record.version == expected_version:
                    pass  # transient; fall through and write
                else:
                    return await self._raise_write_conflict(d, record, expected_version, run_id)
            else:
                return await self._raise_write_conflict(d, record, expected_version, run_id)

        validated = validate_record_data(d.fields or [], data, partial=True)
        await self._verify_ref_targets(validated.refs)

        merged = dict(record.data or {})
        merged.update(validated.clean_data)
        record.data = merged
        record.version += 1
        record.def_version = d.version   # lazy def-version upgrade on write (§19.4)
        record.updated_by_run_id = run_id
        await self.db.flush()
        await self._materialise_links(record.id, validated.refs)
        return RecordResult(WRITTEN, record=record)

    async def soft_delete(
        self, record_id: uuid.UUID, *, actor_process_code: str | None = None,
        run_id: uuid.UUID | None = None, force_cross_owner: bool = False,
    ) -> RecordResult:
        record = await self.get(record_id)
        if record is None:
            raise ValueError(f"record {record_id} not found")
        d = await self._def_by_id(record.entity_def_id)
        if d is None:
            raise ValueError("record has no def")
        gate = await self._ownership_gate(d, {}, actor_process_code, run_id,
                                          op="delete", force=force_cross_owner,
                                          record_id=record_id)
        if gate is not None:
            return gate
        record.deleted_at = datetime.utcnow()
        record.updated_by_run_id = run_id
        await self.db.flush()
        return RecordResult(WRITTEN, record=record)

    # ------------------------------------------------------------------
    # Ownership (§23.1 — owner writes, others propose)
    # ------------------------------------------------------------------

    async def _ownership_gate(
        self, d: TenantEntityDef, data: dict[str, Any], actor_process_code: str | None,
        run_id: uuid.UUID | None, *, op: str, force: bool,
        record_id: uuid.UUID | None = None,
    ) -> Optional[RecordResult]:
        """None → the caller may write directly; a RecordResult → stop here.

        Admin/API/seeding writes carry no actor process code and write directly.
        An agent (actor code set) acting on an object it does not own must
        propose, unless it forces a cross-owner write (HITL-gated).
        """
        if actor_process_code is None:
            return None  # platform/admin path
        owner = d.owner_process_code
        if owner is None or owner == actor_process_code:
            return None  # unresolved owner (platform-owned) or the owner itself
        # Cross-owner: propose, or force via HITL.
        if force:
            sig = await self._emit_signal(
                "object.change_proposed", d, record_id,
                {"op": op, "delta": data, "actor": actor_process_code,
                 "cross_owner": True, "requires_hitl": "before_cross_owner_write"},
                run_id,
            )
            await self._raise_cross_owner_hitl(d, record_id, actor_process_code, run_id)
            return RecordResult(HITL_REQUIRED, signal_id=sig,
                                reason=f"{actor_process_code} cross-owner {op} on "
                                       f"{d.name} (owned by {owner}) needs approval")
        sig = await self._emit_signal(
            "object.change_proposed", d, record_id,
            {"op": op, "delta": data, "actor": actor_process_code, "owner": owner},
            run_id,
        )
        return RecordResult(PROPOSED, signal_id=sig,
                            reason=f"{actor_process_code} proposed {op} on {d.name} "
                                   f"(owned by {owner})")

    async def _raise_write_conflict(
        self, d: TenantEntityDef, record: TenantRecord, expected: int,
        run_id: uuid.UUID | None,
    ) -> RecordResult:
        sig = await self._emit_signal(
            "object.write_conflict", d, record.id,
            {"expected_version": expected, "actual_version": record.version},
            run_id,
        )
        return RecordResult(CONFLICT, record=record, signal_id=sig,
                            reason=f"version conflict: expected {expected}, "
                                   f"found {record.version}")

    async def _raise_cross_owner_hitl(
        self, d: TenantEntityDef, record_id: uuid.UUID | None,
        actor: str, run_id: uuid.UUID | None,
    ) -> None:
        if run_id is None:
            return
        try:
            from src.common.database import AsyncSessionLocal
            from src.ai.orm.execution import HumanApproval

            async with AsyncSessionLocal() as cp:
                cp.add(HumanApproval(
                    run_id=run_id,
                    checkpoint_trigger=f"cross_owner:{d.name}",
                    checkpoint_key="before_cross_owner_write",
                    status="PENDING", requested_by="record_service",
                    context_snapshot={"def": d.name, "record_id": str(record_id) if record_id else None,
                                      "actor": actor, "owner": d.owner_process_code},
                ))
                await cp.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("cross-owner HITL raise failed: %s", exc)

    # ------------------------------------------------------------------
    # Links + refs
    # ------------------------------------------------------------------

    async def _materialise_links(self, record_id: uuid.UUID, refs: list[RefAssignment]) -> None:
        """Create a link row per ref, keeping document and graph in sync (§19.2)."""
        for ref in refs:
            src, dst = (record_id, ref.dst_record_id) if ref.direction == "out" \
                else (ref.dst_record_id, record_id)
            exists = (await self.db.execute(
                select(TenantRecordLink.id).where(
                    TenantRecordLink.src_record_id == src,
                    TenantRecordLink.dst_record_id == dst,
                    TenantRecordLink.rel_type == ref.rel_type,
                )
            )).scalar_one_or_none()
            if exists is not None:
                continue
            self.db.add(TenantRecordLink(
                company_id=self.company_id, src_record_id=src,
                dst_record_id=dst, rel_type=ref.rel_type,
            ))
        await self.db.flush()

    async def _verify_ref_targets(self, refs: list[RefAssignment]) -> None:
        for ref in refs:
            target = await self.get(ref.dst_record_id)
            if target is None:
                raise ValidationError([f"ref '{ref.field_name}' target "
                                       f"{ref.dst_record_id} not found"])
            if ref.target != "*":
                tdef = await self._def_by_id(target.entity_def_id)
                if tdef is None or tdef.name != ref.target:
                    raise ValidationError([f"ref '{ref.field_name}' must point at "
                                           f"{ref.target}, got "
                                           f"{tdef.name if tdef else '?'}"])

    # ------------------------------------------------------------------
    # Defs + signal emission
    # ------------------------------------------------------------------

    async def _def_by_name(self, name: str) -> Optional[TenantEntityDef]:
        return (await self.db.execute(
            select(TenantEntityDef).where(
                TenantEntityDef.company_id == self.company_id,
                TenantEntityDef.name == name,
            )
        )).scalar_one_or_none()

    async def _def_by_id(self, def_id: uuid.UUID) -> Optional[TenantEntityDef]:
        return await self.db.get(TenantEntityDef, def_id)

    async def _require_def(self, name: str) -> TenantEntityDef:
        d = await self._def_by_name(name)
        if d is None:
            raise ValueError(f"no tenant def named '{name}' for company {self.company_id}")
        return d

    async def _emit_signal(
        self, signal_type: str, d: TenantEntityDef, record_id: uuid.UUID | None,
        payload: dict[str, Any], run_id: uuid.UUID | None,
    ) -> Optional[uuid.UUID]:
        """Emit a control-plane signal (records are tenant-DB, signals are not)."""
        try:
            from src.common.database import AsyncSessionLocal
            from src.ai.signals.service import emit_signal, enqueue_dispatch
            from src.ai.signals.models import SignalSource, SignalTrust

            body = {"def": d.name, "record_id": str(record_id) if record_id else None,
                    "owner": d.owner_process_code, **payload}
            async with AsyncSessionLocal() as cp:
                sig_id = await emit_signal(
                    cp, company_id=self.company_id, source=SignalSource.AGENT,
                    type=signal_type, trust=SignalTrust.INTERNAL, payload=body,
                    object_refs=[str(record_id)] if record_id else None,
                )
                await cp.commit()
            if sig_id is not None:
                await enqueue_dispatch(self.redis, sig_id)
            return sig_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("record-service signal emit failed (%s): %s", signal_type, exc)
            return None
