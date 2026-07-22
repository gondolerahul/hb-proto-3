"""kpi/compute.py — computing the C6 KPIs, or honestly declining to.

Every computation follows the same two-step shape, and the order matters:

1. **Check prerequisites.** Which of the KPI's required objects actually exist
   as entity definitions in this tenant, and do any records populate the
   required fields?
2. **Only then compute.**

A KPI that fails step 1 returns ``value=None`` with ``missing`` naming exactly
what is absent. It never returns ``0``. This is the distinction the whole of
C6 rests on: zero is a measurement ("you are owed nothing"), absence is the
lack of one ("I cannot tell what you are owed"), and reporting the second as
the first is how an owner ends up making a decision on a number that was never
real.

Records live in the tenant data plane and approvals in the control plane, so
the two are queried through different sessions — never assume one transaction
spans both.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.kpi.definitions import KPI_DEFINITIONS, Cadence, KpiDefinition
from src.ai.tenant_schema.data_plane import get_tenant_session
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord

__all__ = ["KpiResult", "compute_all", "compute_one", "WINDOW_DAYS"]


WINDOW_DAYS: dict[Cadence, int] = {
    Cadence.WEEKLY: 7,
    Cadence.MONTHLY: 30,
    Cadence.ROLLING_30D: 30,
}


@dataclass
class KpiResult:
    """A KPI reading, or a stated inability to take one."""

    key: str
    display_name: str
    unit: str
    formula: str
    #: ``None`` means not measurable. It never means zero.
    value: float | None = None
    baseline_value: float | None = None
    #: What is absent, when ``value`` is None.
    missing: list[str] = field(default_factory=list)
    caveat: str | None = None
    window_days: int = 30
    sample_size: int = 0

    @property
    def measurable(self) -> bool:
        return self.value is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "unit": self.unit,
            "formula": self.formula,
            "value": self.value,
            "baseline_value": self.baseline_value,
            "measurable": self.measurable,
            "missing": self.missing,
            "caveat": self.caveat,
            "window_days": self.window_days,
            "sample_size": self.sample_size,
        }

    def as_sentence(self) -> str:
        """How Pragya says it. Unmeasurable KPIs say what is missing."""
        if not self.measurable:
            missing = ", ".join(self.missing) or "the underlying data"
            return (f"{self.display_name}: not yet measurable — I'd need "
                    f"{missing}.")
        return f"{self.display_name}: {self.value:g} ({self.unit})"


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


async def _defined_objects(db: AsyncSession, company_id: uuid.UUID) -> set[str]:
    rows = (await db.execute(
        select(TenantEntityDef.name).where(TenantEntityDef.company_id == company_id)
    )).scalars().all()
    return set(rows)


async def _records(
    db: AsyncSession, company_id: uuid.UUID, object_name: str,
) -> list[dict[str, Any]]:
    """Live records for an object as plain dicts (soft-deleted excluded)."""
    rows = (await db.execute(
        select(TenantRecord.data)
        .join(TenantEntityDef, TenantRecord.entity_def_id == TenantEntityDef.id)
        .where(
            TenantRecord.company_id == company_id,
            TenantEntityDef.name == object_name,
            TenantRecord.deleted_at.is_(None),
        )
    )).scalars().all()
    return [r for r in rows if isinstance(r, dict)]


def _field_missing(
    definition: KpiDefinition, records: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Required fields that no record populates.

    A field defined in the schema but populated nowhere cannot support a
    formula, so it counts as missing — this is the case that would otherwise
    silently produce a confident zero.
    """
    missing: list[str] = []
    for qualified in definition.required_fields:
        object_name, _, field_name = qualified.partition(".")
        rows = records.get(object_name, [])
        if not any(row.get(field_name) is not None for row in rows):
            missing.append(qualified)
    return missing


async def _pending_approvals(db: AsyncSession, company_id: uuid.UUID) -> int:
    """Control-plane count of approvals waiting on a human."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.orm.execution import ExecutionRun, HumanApproval

    return int((await db.execute(
        select(func.count(HumanApproval.id))
        .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
        .join(HierarchicalEntity, ExecutionRun.entity_id == HierarchicalEntity.id)
        .where(
            HierarchicalEntity.company_id == company_id,
            HumanApproval.status == "PENDING",
        )
    )).scalar() or 0)


def _sum_outstanding(invoices: Sequence[dict[str, Any]], overdue_only: bool,
                     now: datetime) -> tuple[float, int]:
    total = Decimal("0")
    counted = 0
    for inv in invoices:
        status = str(inv.get("status") or "").lower()
        if status in ("paid", "void"):
            continue
        gross = _to_decimal(inv.get("total"))
        if gross is None:
            continue
        paid = _to_decimal(inv.get("amount_paid")) or Decimal("0")
        if overdue_only and status != "overdue":
            due = inv.get("due_date")
            if not due:
                continue
            try:
                due_at = datetime.fromisoformat(str(due)[:19])
            except ValueError:
                continue
            if due_at > now:
                continue
        total += gross - paid
        counted += 1
    return float(total), counted


async def compute_one(
    definition: KpiDefinition,
    *,
    records: dict[str, list[dict[str, Any]]],
    pending_approvals: int,
    defined: set[str],
    now: datetime,
) -> KpiResult:
    """Compute a single KPI from already-fetched data, or decline to."""
    window = WINDOW_DAYS[definition.cadence]
    result = KpiResult(
        key=definition.key, display_name=definition.display_name,
        unit=definition.unit, formula=definition.formula,
        caveat=definition.caveat, window_days=window,
    )

    # Declared-but-uncaptured KPIs never guess. gross_margin is the live
    # example: the Blueprint names it, the Solo Pack cannot source it.
    if not definition.captured_today:
        result.missing = [
            f"{definition.caveat or 'a data source the Solo Pack does not capture'}"
        ]
        return result

    absent_objects = [o for o in definition.required_objects if o not in defined]
    if absent_objects:
        result.missing = [f"{o} records" for o in absent_objects]
        return result

    missing_fields = _field_missing(definition, records)
    if missing_fields:
        result.missing = missing_fields
        return result

    cutoff = now - timedelta(days=window)

    if definition.key == "agent_hitl_load":
        result.value = float(pending_approvals)
        result.sample_size = pending_approvals
        return result

    if definition.key == "open_pipeline_value":
        total, count = Decimal("0"), 0
        for opp in records.get("Opportunity", []):
            if str(opp.get("stage") or "").lower() in ("won", "lost"):
                continue
            amount = _to_decimal(opp.get("amount"))
            if amount is not None:
                total += amount
                count += 1
        result.value, result.sample_size = float(total), count
        return result

    if definition.key in ("receivables_outstanding", "overdue_receivables"):
        overdue_only = definition.key == "overdue_receivables"
        value, count = _sum_outstanding(
            records.get("Invoice", []), overdue_only, now)
        result.value, result.sample_size = value, count
        return result

    if definition.key == "quote_acceptance_rate":
        decided = [q for q in records.get("Quote", [])
                   if str(q.get("status") or "").lower()
                   in ("accepted", "rejected", "expired")]
        if not decided:
            # No decided quote is not a 0% acceptance rate — it is no data.
            result.missing = ["decided quotes (all quotes are still open)"]
            return result
        accepted = sum(1 for q in decided
                       if str(q.get("status")).lower() == "accepted")
        result.value = round(100.0 * accepted / len(decided), 1)
        result.sample_size = len(decided)
        return result

    if definition.key == "collections_recovered":
        total, count = Decimal("0"), 0
        for pay in records.get("Payment", []):
            if str(pay.get("direction") or "").lower() != "inbound":
                continue
            if str(pay.get("status") or "").lower() != "cleared":
                continue
            when = pay.get("payment_date")
            if when:
                try:
                    if datetime.fromisoformat(str(when)[:19]) < cutoff:
                        continue
                except ValueError:
                    continue
            amount = _to_decimal(pay.get("amount"))
            if amount is not None:
                total += amount
                count += 1
        result.value, result.sample_size = float(total), count
        return result

    if definition.key == "days_sales_outstanding":
        outstanding, _ = _sum_outstanding(records.get("Invoice", []), False, now)
        revenue = Decimal("0")
        for pay in records.get("Payment", []):
            if str(pay.get("direction") or "").lower() != "inbound":
                continue
            amount = _to_decimal(pay.get("amount"))
            if amount is not None:
                revenue += amount
        if revenue <= 0:
            # Dividing by no revenue produces an infinity, not a metric.
            result.missing = ["recognised revenue in the window"]
            return result
        result.value = round(outstanding / float(revenue) * window, 1)
        result.sample_size = len(records.get("Invoice", []))
        return result

    if definition.key in ("lead_response_time", "ticket_resolution_time"):
        # Both need an event timeline the Solo Pack does not yet write per
        # record (first-touch / resolved-at). Say so rather than approximate
        # from created_at, which would silently measure something else.
        result.missing = [
            "a first-response timestamp on each record (not captured yet)"
        ]
        return result

    result.missing = ["a computation for this KPI"]
    return result


async def compute_all(
    db: AsyncSession, company_id: uuid.UUID, now: datetime | None = None,
) -> list[KpiResult]:
    """Every KPI for a company, measured or honestly declined.

    Never raises for a tenant with no data: a brand-new company gets a full
    list of "not yet measurable" readings, which is the correct answer and the
    one stage 9 should show on day one.
    """
    at = now or datetime.utcnow()
    needed = {o for d in KPI_DEFINITIONS for o in d.required_objects}

    defined: set[str] = set()
    records: dict[str, list[dict[str, Any]]] = {}
    try:
        async with get_tenant_session(company_id) as tdb:
            defined = await _defined_objects(tdb, company_id)
            for object_name in sorted(needed & defined):
                records[object_name] = await _records(tdb, company_id, object_name)
    except Exception:
        # No tenant schema yet (pre-activation). Everything is unmeasurable,
        # which is exactly what a new tenant should be told.
        defined, records = set(), {}

    pending = await _pending_approvals(db, company_id)

    return [
        await compute_one(
            definition, records=records, pending_approvals=pending,
            defined=defined, now=at,
        )
        for definition in KPI_DEFINITIONS
    ]
