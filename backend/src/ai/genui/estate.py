"""genui/estate.py — the estate read model (VG-02, D5 §2).

One projection both renderers read: the World renderer draws it, the Sheet
renderer lists it, and L9's sheet equivalence is free *because* there is one
projection rather than twenty bespoke endpoints.

**This module computes no business truth of its own.** Districts are the
seeded PROCESS entities, colleagues their AGENT children, beacons the pending
approvals, treasuries the budget envelopes, weather a pure function over
states other subsystems already own. Where a fact does not exist yet, the
projection says so rather than inventing it — the D5 §4.1 rule (an absent
figure beats a fabricated one).

Honest v1 limits, named here so they are found and not discovered:

* **Fog is a named absence.** D5 §2.1 derives fog from "KPI below target for
  N consecutive snapshots", but ``KpiDefinition`` declares no target and no
  direction — there is nothing to be below. Plinths carry the values; the
  weather never claims fog until the KPI registry grows a target. (Recorded
  as a build-note delta; the fix belongs to the KPI registry, not here.)
* **Storm is estate-wide.** No per-process circuit-breaker state is stored
  anywhere (the credit breaker raises mid-run and persists nothing), so the
  projectable storm is the company's own stop states: dunning ``read_only``/
  ``suspended``. When it storms here, it storms over every district — which
  is truthful, because those states do stop everything.
* **District traffic mixes two sources.** ``in_1h`` counts signals routed to
  the district (``owner_process_id``), ``out_1h`` counts the district's runs
  completed, and ``parked`` counts its PARKED signals. PARKED consent/
  subscription holds also appear at the gatehouse of their channel — the
  same hold seen from both ends of the road, which is what the map draws.
* **Local time comes from ``VIHARA_ESTATE_TIMEZONE``** (deployment-wide,
  default UTC). A per-tenant timezone has no home yet; when it gets one
  (LEARN's ``surface.*`` namespace is the candidate), this reads it.

Scoping: every function takes ``company_id`` from the caller, and the router
takes it from the session — never from a parameter (D5 §2.2).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.connectors.models import ConnectorBinding
from src.ai.evolution.models import EntityVersion
from src.ai.governance.models import HITLCheckpointDef
from src.ai.kpi.definitions import KPI_DEFINITIONS
from src.ai.learning.models import KpiSnapshot
from src.ai.loop.models import BudgetEnvelope, LoopRuntime
from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.signals.models import Signal, SignalStatus, TriggerRegistration
from src.ai.tenant_schema.data_plane import tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord
from src.ai.twin.models import TwinRun, TwinScenario
from src.auth.models import Company
from src.common.config import settings

# ── projection constants ──────────────────────────────────────────────────────

#: Quarter membership for the Wave-0 processes — projection data, mirroring
#: the solo_pack template domains. A process this table does not know (a
#: tenant-custom one) lands in the "custom" quarter rather than nowhere.
QUARTER_FOR_PROCESS: dict[str, str] = {
    "P03": "acquisition",
    "P06": "care",
    "P08": "finance",
    "P10": "finance",
    "P14": "compliance",
    "P19": "intelligence",
}

QUARTER_NAMES: dict[str, str] = {
    "acquisition": "Acquisition",
    "care": "Care",
    "finance": "Finance",
    "compliance": "Compliance",
    "intelligence": "Intelligence",
    "custom": "Custom",
}

#: Which gatehouse a signal type belongs to, by prefix. The gateway roster is
#: seeded from solo_pack templates; this mapping is how PARKED/inbound counts
#: land on the right door.
_CHANNEL_PREFIXES: tuple[tuple[str, str], ...] = (
    ("email", "email"),
    ("message.", "whatsapp"),
    ("voice.", "voice"),
    ("broadcast.", "broadcast"),
)

_ACTIVE_RUN_STATUSES = ("PENDING", "RUNNING")


# ── pure helpers (no DB — unit-tested directly) ──────────────────────────────

def phase_for(local: datetime) -> str:
    """Day runs 06:00–18:00 local; everything else is night (art bible §4 —
    the shift is luminance, and the boundary only has to be *consistent*)."""
    return "day" if 6 <= local.hour < 18 else "night"


def channel_for_signal_type(signal_type: str) -> str | None:
    """Which gatehouse a signal belongs to, or None for internal traffic."""
    for prefix, channel in _CHANNEL_PREFIXES:
        if signal_type.startswith(prefix):
            return channel
    return None


def sla_seconds_left(
    requested_at: datetime | None, sla_seconds: int | None, now: datetime,
) -> int | None:
    """Seconds until the checkpoint's SLA fires; None when no SLA governs.
    Never negative — an overdue card reads 0, and the timeout sweep owns
    what happens next (trust002), not this projection."""
    if requested_at is None or sla_seconds is None:
        return None
    deadline = requested_at + timedelta(seconds=sla_seconds)
    return max(0, int((deadline - now).total_seconds()))


def weather_for(
    *,
    district_name: str,
    storming: bool,
    envelope_spent_fraction: float | None,
    envelope_days_left: int | None,
    all_triggers_disabled: bool,
    downshift_fraction: float = 0.8,
) -> dict[str, Any]:
    """The one weather state a district shows (D5 §2.1), computed on read.

    Precedence: storm > heat-shimmer > moonlit > clear. Fog is deliberately
    absent (module docstring). Every non-clear state carries the icon and the
    sentence, because those are what the sheet equivalent and the screen
    reader receive (art bible §8).
    """
    if storming:
        return {
            "state": "storm",
            "icon": "cloud-lightning",
            "sentence": f"{district_name} is stopped — the account is not in good standing.",
        }
    if (
        envelope_spent_fraction is not None
        and envelope_spent_fraction >= downshift_fraction
    ):
        days = f" with {envelope_days_left} days left" if envelope_days_left else ""
        pct = int(envelope_spent_fraction * 100)
        return {
            "state": "heat-shimmer",
            "icon": "flame",
            "sentence": f"{district_name} has used {pct}% of its envelope{days}.",
        }
    if all_triggers_disabled:
        return {
            "state": "moonlit",
            "icon": "moon",
            "sentence": f"{district_name} is hibernating; nothing is scheduled.",
        }
    return {"state": "clear", "icon": None, "sentence": None}


def envelope_days_left(refreshed_at: datetime, cycle: str, now: datetime) -> int:
    """Days remaining in the envelope's cycle, floored at 0."""
    length = 7 if cycle == "weekly" else 30
    end = refreshed_at + timedelta(days=length)
    return max(0, (end - now).days)


async def _tenant_plane_regions(company_id: uuid.UUID) -> dict[str, Any]:
    """Halls and monuments — the two regions that live in the tenant plane.

    A separate session on purpose: records are tenant-DB, everything else in
    the estate is control-plane, and one transaction never spans both (HANDOFF
    §5). ORM only — tenant routing is a ``schema_translate_map`` and raw SQL
    would name a schema that does not exist (the STRAT T6 lesson).
    """
    halls: dict[str, dict[str, Any]] = {}
    monuments: list[dict[str, Any]] = []
    async with tenant_data_plane.session(company_id) as ts:
        defs = (
            await ts.execute(
                select(TenantEntityDef).where(
                    TenantEntityDef.company_id == company_id))
        ).scalars().all()
        count_rows = (
            await ts.execute(
                select(TenantRecord.entity_def_id, func.count())
                .where(
                    TenantRecord.company_id == company_id,
                    TenantRecord.deleted_at.is_(None),
                ).group_by(TenantRecord.entity_def_id))
        ).all()
        counts: dict[uuid.UUID, int] = {
            row[0]: int(row[1]) for row in count_rows}
        for d in defs:
            module = d.module or "General"
            hall = halls.setdefault(module, {"module": module, "objects": [], "records": 0})
            hall["objects"].append(d.name)
            hall["records"] += int(counts.get(d.id, 0))

        resolution_defs = [d.id for d in defs if d.name == "Resolution"]
        if resolution_defs:
            rows = (
                await ts.execute(
                    select(TenantRecord).where(
                        TenantRecord.company_id == company_id,
                        TenantRecord.entity_def_id.in_(resolution_defs),
                        TenantRecord.deleted_at.is_(None),
                        TenantRecord.data["status"].astext == "active",
                    ))
            ).scalars().all()
            for r in rows:
                data = r.data if isinstance(r.data, dict) else {}
                monuments.append({
                    "resolution_id": str(r.id),
                    "title": data.get("title"),
                    "district": data.get("concerns_module"),
                    "adopted_at": r.updated_at.isoformat(),
                })
    return {
        "halls": sorted(halls.values(), key=lambda h: str(h["module"])),
        "monuments": monuments,
    }


# ── the composition ──────────────────────────────────────────────────────────

async def estate_view(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None,
) -> dict[str, Any]:
    """The whole estate, one read (D5 §2's payload)."""
    now = now or datetime.utcnow()

    company = (
        await db.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    storming = bool(
        company is not None
        and company.subscription_status in ("read_only", "suspended"))

    entities = (
        await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.company_id == company_id,
                HierarchicalEntity.deleted_at.is_(None),
                HierarchicalEntity.is_template.isnot(True),
            ))
    ).scalars().all()

    by_id: dict[uuid.UUID, HierarchicalEntity] = {e.id: e for e in entities}
    processes = [e for e in entities if e.type == "PROCESS"]
    process_code: dict[uuid.UUID, str] = {}
    for p in processes:
        meta = p.metadata_extensions if isinstance(p.metadata_extensions, dict) else {}
        process_code[p.id] = str(meta.get("process_code") or p.name)

    def district_of(entity_id: uuid.UUID) -> uuid.UUID | None:
        """Nearest PROCESS ancestor (bounded walk — the tree is shallow)."""
        seen: set[uuid.UUID] = set()
        cur = by_id.get(entity_id)
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            if cur.type == "PROCESS":
                return cur.id
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        return None

    def colleague_of(entity_id: uuid.UUID) -> uuid.UUID | None:
        """The AGENT directly under the PROCESS on the ancestor path."""
        chain: list[HierarchicalEntity] = []
        seen: set[uuid.UUID] = set()
        cur = by_id.get(entity_id)
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            chain.append(cur)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        for i, node in enumerate(chain):
            if node.type == "PROCESS" and i > 0:
                return chain[i - 1].id
        return None

    def is_gateway(e: HierarchicalEntity) -> bool:
        tags = e.tags if isinstance(e.tags, list) else []
        return any(isinstance(t, str) and t.startswith("channel:") for t in tags)

    def gateway_channel(e: HierarchicalEntity) -> str:
        tags = e.tags if isinstance(e.tags, list) else []
        for t in tags:
            if isinstance(t, str) and t.startswith("channel:"):
                return t.split(":", 1)[1]
        return "unknown"

    def gateway_code(e: HierarchicalEntity) -> str:
        tags = e.tags if isinstance(e.tags, list) else []
        for t in tags:
            if isinstance(t, str) and t.startswith("agent_code:"):
                return t.split(":", 1)[1]
        return e.name

    # Pending approvals, scoped through the run's company (the VG-05 rule:
    # copy the read's scoping — this is get_pending_approvals' join).
    approvals = (
        await db.execute(
            select(HumanApproval, ExecutionRun.entity_id)
            .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
            .where(
                ExecutionRun.company_id == company_id,
                HumanApproval.status == "PENDING",
            ))
    ).all()

    sla_by_key: dict[str, int | None] = {
        row.key: row.sla_seconds
        for row in (await db.execute(select(HITLCheckpointDef))).scalars()
    }

    hands_raised: set[uuid.UUID] = set()
    beacons: list[dict[str, Any]] = []
    for approval, run_entity_id in approvals:
        district_id = district_of(run_entity_id)
        agent_id = colleague_of(run_entity_id)
        if agent_id is not None:
            hands_raised.add(agent_id)
        beacons.append({
            "approval_id": str(approval.id),
            "district": process_code.get(district_id) if district_id else None,
            "checkpoint_key": approval.checkpoint_key,
            "sla_seconds_left": sla_seconds_left(
                approval.requested_at, sla_by_key.get(approval.checkpoint_key or ""), now),
        })

    # Active runs and the last hour's traffic, attributed per district.
    hour_ago = now - timedelta(hours=1)
    active_rows = (
        await db.execute(
            select(ExecutionRun.entity_id, func.count())
            .where(
                ExecutionRun.company_id == company_id,
                ExecutionRun.status.in_(_ACTIVE_RUN_STATUSES),
            ).group_by(ExecutionRun.entity_id))
    ).all()
    running_entities: set[uuid.UUID] = {row[0] for row in active_rows}

    inbound_rows = (
        await db.execute(
            select(Signal.owner_process_id, func.count())
            .where(
                Signal.company_id == company_id,
                Signal.created_at >= hour_ago,
                Signal.owner_process_id.isnot(None),
            ).group_by(Signal.owner_process_id))
    ).all()
    completed_rows = (
        await db.execute(
            select(ExecutionRun.entity_id, func.count())
            .where(
                ExecutionRun.company_id == company_id,
                ExecutionRun.completed_at >= hour_ago,
            ).group_by(ExecutionRun.entity_id))
    ).all()
    parked_rows = (
        await db.execute(
            select(Signal.owner_process_id, func.count())
            .where(
                Signal.company_id == company_id,
                Signal.status == SignalStatus.PARKED,
                Signal.owner_process_id.isnot(None),
            ).group_by(Signal.owner_process_id))
    ).all()

    in_1h: dict[uuid.UUID, int] = {
        row[0]: int(row[1]) for row in inbound_rows if row[0] is not None}
    parked_by_district: dict[uuid.UUID, int] = {
        row[0]: int(row[1]) for row in parked_rows if row[0] is not None}
    out_1h: dict[uuid.UUID, int] = {}
    for entity_id, count in completed_rows:
        d = district_of(entity_id)
        if d is not None:
            out_1h[d] = out_1h.get(d, 0) + int(count)

    # Envelopes (tenant class), keyed by their owning entity.
    envelopes = (
        await db.execute(
            select(BudgetEnvelope).where(
                BudgetEnvelope.company_id == company_id,
                BudgetEnvelope.budget_class == "tenant",
            ))
    ).scalars().all()
    envelope_by_entity: dict[uuid.UUID, BudgetEnvelope] = {
        env.entity_id: env for env in envelopes}

    # Trigger hibernation, per process.
    trigger_rows = (
        await db.execute(
            select(
                TriggerRegistration.process_entity_id,
                func.bool_or(TriggerRegistration.enabled),
            )
            .where(TriggerRegistration.company_id == company_id)
            .group_by(TriggerRegistration.process_entity_id))
    ).all()
    any_trigger_enabled: dict[uuid.UUID, bool] = {
        row[0]: bool(row[1]) for row in trigger_rows}

    # Latest KPI snapshot per key (a bounded fetch, reduced in Python).
    fortnight_ago = (now - timedelta(days=14)).date()
    snapshot_rows = (
        await db.execute(
            select(KpiSnapshot)
            .where(
                KpiSnapshot.company_id == company_id,
                KpiSnapshot.captured_on >= fortnight_ago,
            ).order_by(KpiSnapshot.captured_on.desc()))
    ).scalars().all()
    latest_snapshot: dict[str, KpiSnapshot] = {}
    for snap in snapshot_rows:
        latest_snapshot.setdefault(snap.kpi_key, snap)
    kpis_by_process: dict[str, list[dict[str, Any]]] = {}
    for definition in KPI_DEFINITIONS:
        snap_ = latest_snapshot.get(definition.key)
        kpis_by_process.setdefault(definition.owner_process, []).append({
            "kpi_key": definition.key,
            "display_name": definition.display_name,
            "value": float(snap_.value) if snap_ is not None and snap_.value is not None else None,
            "measurable": bool(snap_.measurable) if snap_ is not None else False,
            "unit": snap_.unit if snap_ is not None else definition.unit,
        })

    # Signals today, for the gatehouses.
    today_start = datetime(now.year, now.month, now.day)
    signal_rows = (
        await db.execute(
            select(Signal.type, Signal.status, func.count())
            .where(
                Signal.company_id == company_id,
                Signal.created_at >= today_start,
            ).group_by(Signal.type, Signal.status))
    ).all()
    inbound_today: dict[str, int] = {}
    parked_by_channel: dict[str, int] = {}
    for signal_type, status, count in signal_rows:
        channel = channel_for_signal_type(str(signal_type))
        if channel is None:
            continue
        inbound_today[channel] = inbound_today.get(channel, 0) + int(count)
        if status == SignalStatus.PARKED:
            parked_by_channel[channel] = parked_by_channel.get(channel, 0) + int(count)

    # ── assemble districts ────────────────────────────────────────────────
    districts: list[dict[str, Any]] = []
    quarters_seen: dict[str, list[str]] = {}
    for process in processes:
        code = process_code[process.id]
        quarter = QUARTER_FOR_PROCESS.get(code, "custom")
        quarters_seen.setdefault(quarter, []).append(code)

        colleagues = [
            e for e in entities
            if e.parent_id == process.id and e.type == "AGENT" and not is_gateway(e)
        ]
        env = envelope_by_entity.get(process.id)
        spent_fraction: float | None = None
        days_left: int | None = None
        if env is not None and Decimal(env.envelope_usd) > 0:
            spent_fraction = float(
                Decimal(env.spent_usd) / Decimal(env.envelope_usd))
            days_left = envelope_days_left(env.refreshed_at, env.cycle, now)

        has_triggers = process.id in any_trigger_enabled
        districts.append({
            "process_code": code,
            "name": process.display_name or process.name,
            "quarter": quarter,
            "colleagues": [
                {
                    "entity_id": str(c.id),
                    "name": c.display_name or c.name,
                    "autonomy": (
                        c.governance.get("autonomy_level")
                        if isinstance(c.governance, dict) else None
                    ) or "A1",
                    "hand_raised": c.id in hands_raised,
                    "state": "running" if c.id in running_entities else "idle",
                }
                for c in colleagues
            ],
            "kpi": {"plinth": kpis_by_process.get(code, [])},
            "treasury": (
                {
                    "envelope_id": str(env.id),
                    "spent": float(env.spent_usd),
                    "cap": float(env.envelope_usd),
                    "reserve_protected": float(env.reserved_usd) > 0,
                }
                if env is not None else None
            ),
            "weather": weather_for(
                district_name=process.display_name or process.name,
                storming=storming,
                envelope_spent_fraction=spent_fraction,
                envelope_days_left=days_left,
                all_triggers_disabled=(
                    has_triggers and not any_trigger_enabled[process.id]),
                downshift_fraction=(
                    env.downshift_at_pct / 100 if env is not None else 0.8),
            ),
            "traffic": {
                "in_1h": in_1h.get(process.id, 0),
                "out_1h": out_1h.get(process.id, 0),
                "parked": parked_by_district.get(process.id, 0),
            },
        })

    # ── the remaining regions ─────────────────────────────────────────────
    runtime = (
        await db.execute(
            select(LoopRuntime).where(LoopRuntime.company_id == company_id))
    ).scalars().first()

    bindings = (
        await db.execute(
            select(ConnectorBinding).where(
                ConnectorBinding.company_id == company_id))
    ).scalars().all()

    scenario_count = (
        await db.execute(
            select(func.count()).select_from(TwinScenario).where(
                TwinScenario.company_id == company_id,
                TwinScenario.status != "archived",
            ))
    ).scalar_one()
    last_twin_run = (
        await db.execute(
            select(func.max(TwinRun.started_at)).where(
                TwinRun.company_id == company_id))
    ).scalar_one()

    version_count = (
        await db.execute(
            select(func.count()).select_from(EntityVersion).where(
                EntityVersion.company_id == company_id))
    ).scalar_one()
    terminated_count = (
        await db.execute(
            select(func.count()).select_from(HierarchicalEntity).where(
                HierarchicalEntity.company_id == company_id,
                HierarchicalEntity.deleted_at.isnot(None),
            ))
    ).scalar_one()

    tz = ZoneInfo(settings.VIHARA_ESTATE_TIMEZONE)
    local = datetime.now(tz)

    tenant_regions = await _tenant_plane_regions(company_id)

    return {
        "estate": {
            "loop_id": str(runtime.loop_entity_id) if runtime is not None else None,
            "pulse": {
                "beat_at": (
                    runtime.last_beat_at.isoformat()
                    if runtime is not None and runtime.last_beat_at is not None
                    else None),
                "healthy": bool(
                    runtime is not None
                    and runtime.enabled
                    and runtime.consecutive_missed == 0),
            },
            "local_time": local.isoformat(),
            "phase": phase_for(local),
            "standing": company.subscription_status if company is not None else None,
        },
        "quarters": [
            {"code": q, "name": QUARTER_NAMES.get(q, q.title()),
             "districts": sorted(codes)}
            for q, codes in sorted(quarters_seen.items())
        ],
        "districts": districts,
        "gatehouses": [
            {
                "gateway_code": gateway_code(e),
                "channel": gateway_channel(e),
                "health": "ok",
                "inbound_today": inbound_today.get(gateway_channel(e), 0),
                "parked": parked_by_channel.get(gateway_channel(e), 0),
            }
            for e in entities if is_gateway(e)
        ],
        "bridges": [
            {
                "binding_id": str(b.id),
                "connector": b.connector_id,
                "state": b.status,
                "credentials_expire_at": (
                    b.credentials_expire_at.isoformat()
                    if b.credentials_expire_at is not None else None),
                "conflicts_open": 0,
            }
            for b in bindings
        ],
        "halls": tenant_regions["halls"],
        "monuments": tenant_regions["monuments"],
        "beacons": beacons,
        "glasshouse": {
            "open_scenarios": int(scenario_count),
            "last_run_at": (
                last_twin_run.isoformat() if last_twin_run is not None else None),
        },
        "gallery": {
            "versions": int(version_count),
            "terminated": int(terminated_count),
        },
        "as_of": now.isoformat(),
    }


async def district_view(
    db: AsyncSession, company_id: uuid.UUID, code: str,
    *, now: datetime | None = None,
) -> dict[str, Any] | None:
    """One district's block from the estate, or None when the company has no
    such process — the same 404-shaped answer a cross-tenant probe gets, so a
    probe learns nothing (the VG-05 rule)."""
    estate = await estate_view(db, company_id, now=now)
    districts: list[dict[str, Any]] = estate["districts"]
    for district in districts:
        if district["process_code"] == code:
            district["as_of"] = estate["as_of"]
            return district
    return None
