"""dossier/read.py — a colleague's terms of engagement, read (D8 E3).

The Dossier surface rendered a fixture because nothing served the thing it is
about: *what this colleague is for, what she may do, and who has to agree*.
This is that read. It is composed only from what the platform actually
stores, and where the surface's fixture asked for something the platform does
not have, the field is **absent and named** in ``absent`` rather than derived
from something adjacent. An endpoint that answers confidently from nothing is
worse than no endpoint, because the surface can no longer tell that the
platform lacks the answer.

**Three things are real and are projected.**

* **The charter** — ``goal``, ``description``, ``identity.system_prompt`` and
  ``identity.personality.tone`` are the entity's own authored fields, and the
  governance block goes out verbatim beside them. Clauses carry ``source`` so
  a reader can see which column a sentence came from; nothing here is
  paraphrased into a voice the record does not have.
* **The competencies** — an entity's tool list ships
  (``capabilities.tools[].tool_id``). Each entry carries the registry's own
  description as its note, and ``registered`` says whether the platform can
  resolve the name at all. That flag is not decoration: eight shipped Solo
  Pack templates name ``send_email``, and the registered tool is
  ``email_send`` — a dossier that quietly rendered a note for it would hide a
  live defect.
* **The authority** — for every §9.3 category this colleague's tools can
  reach, what the gate says. The answer is **asked of the gate**
  (:func:`evaluate_policy`), never recomputed here, for the reason
  ``consent_read`` gives: a panel that derives its own answer eventually
  disagrees with the control that actually refuses the act, and the tenant
  believes the panel. The gate is asked *without an amount*, because a
  dossier describes terms rather than an act — so where a category carries a
  value band, ``conditional_on_amount`` says the real answer depends on the
  number, and the band is printed beside it.

**And two are not.**

* **SLOs cannot be computed, because no target exists anywhere.**
  ``KpiDefinition`` declares a ``baseline`` (the same measure 30 days ago) and
  no target — the same hole that keeps fog off the estate's weather.
  ``HITLCheckpointDef.sla_seconds`` is a deadline for the *human reviewer*,
  not for the colleague. The demotion thresholds are a floor at which autonomy
  is taken away, not a level anyone promised. So this module ships
  ``reliability``: the readings the demotion sweep already measures, over the
  sweep's own window, with **no target and no dial fill**, and the demotion
  bar named as what it is. A reading with an honest "nothing to compare this
  to" is a measurement; the same reading with an invented 90% beside it is a
  claim.
* **Probation does not ship.** ``governance/demotion.py`` has automatic
  demotion and evidence-gated promotion (approvals plus a random deep-audit
  sample, so a rubber-stamped record cannot buy a level). Neither is a
  probationary period: nothing stores a start date, a length, or an
  "every act to the tray" rule, and no code reads such a thing. What *is*
  stored is the demotion stamp the sweep writes, and that is projected.

Company-scoped by the caller, which takes it from the session and never from a
parameter (D5 §2.2, the VG-05 rule). An entity in another tenant reads exactly
like an entity that does not exist.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.estate import ACTIVE_RUN_STATUSES, QUARTER_FOR_PROCESS
from src.ai.governance.authority import CATEGORY_RULES, category_for_tool
from src.ai.governance.demotion import DEFAULT_THRESHOLDS
from src.ai.governance.demotion_sweep import FAILED_STATUSES, WINDOW_DAYS
from src.ai.governance.models import HITLCheckpointDef
from src.ai.governance.policy_gate import PASS, ActIntent, evaluate_policy
from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.schemas.governance import Governance
from src.ai.tools.base import ToolRegistry

__all__ = [
    "ABSENT",
    "CONNECTOR_TOOL_PREFIX",
    "authority_view",
    "charter_clauses",
    "competencies",
    "dossier_view",
    "reliability_block",
]

#: A connector's tools are qualified ``mcp__<server>__<verb>`` (the Inc-4
#: CONN/SOR convention that ``authority.py`` and the taint firewall both key
#: off). It is the only thing that distinguishes a connector competency from a
#: platform one, and it is a real distinction rather than a label we assign.
CONNECTOR_TOOL_PREFIX = "mcp__"

#: How far up the tree the district walk will go. The hierarchy is shallow
#: (quarter → process → agent); the cap is a cycle guard, not a policy.
_MAX_ANCESTOR_HOPS = 12

#: What this read model cannot answer, and why. Served with every dossier so
#: the surface renders an absence deliberately instead of discovering an empty
#: field and guessing. Keys are stable; the frontend keys regions off them.
ABSENT: tuple[dict[str, str], ...] = (
    {
        "field": "slos",
        "why": "No SLO target is defined anywhere on the platform. KpiDefinition "
               "carries a baseline and no target; HITLCheckpointDef.sla_seconds is "
               "the human reviewer's deadline, not the colleague's; the demotion "
               "thresholds are the floor at which autonomy is removed. `reliability` "
               "carries the readings, with nothing to compare them to.",
    },
    {
        "field": "probation",
        "why": "No probationary period ships. Demotion is automatic and promotion is "
               "evidence-gated, but nothing stores a probation start, length, or an "
               "every-act-to-the-tray rule, and no code reads one.",
    },
    {
        "field": "standing",
        "why": "Associate / probationer / senior is not modelled. The only rank the "
               "platform keeps is the autonomy band, which is projected.",
    },
    {
        "field": "own_words",
        "why": "No first-person charter statement is stored. identity.system_prompt is "
               "second-person instruction and description is third-person; both are "
               "projected verbatim as clauses rather than rewritten into her voice.",
    },
    {
        "field": "doing",
        "why": "No run records a human-readable statement of what it is doing. "
               "`running_runs` counts them instead.",
    },
    {
        "field": "charter_proposals",
        "why": "Nothing stores a pending charter-change proposal. entity_versions "
               "records changes already applied; tenant record-change signals are a "
               "different thing entirely.",
    },
    {
        "field": "decisions",
        "why": "The decision column — what she was told, what it cost, and the trace "
               "under each one — is not a read this endpoint can serve. The runs "
               "exist and GET /ai/executions/{id}/trace serves one, but there is no "
               "per-entity execution read: GET /ai/executions takes no parameters at "
               "all and returns every root execution the company ever ran, so a "
               "dossier cannot ask for its own colleague's. `running_runs` counts "
               "them; naming them needs a filterable execution read first.",
    },
)


# ── pure helpers (no DB — unit-tested directly) ──────────────────────────────

def _text(value: Any) -> str | None:
    """A non-empty trimmed string, or nothing. An empty column is an absent
    clause, not a clause whose value is the empty string."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _governance_of(entity: HierarchicalEntity) -> Governance:
    """The entity's governance block as the gate sees it.

    A malformed block falls back to the schema defaults (A1) — the same
    tolerance ``demotion_sweep`` applies, and for the same reason: one bad row
    must not make the dossier unreadable, and A1 is the cautious answer.
    """
    raw = entity.governance if isinstance(entity.governance, dict) else {}
    try:
        return Governance.model_validate(raw)
    except Exception:  # noqa: BLE001 — a bad block is data, not an outage
        return Governance()


def charter_clauses(entity: HierarchicalEntity) -> list[dict[str, str]]:
    """The colleague's terms, one clause per field that actually carries text.

    Every clause names its ``source`` column. A field the entity leaves empty
    produces no clause at all — an owner reading "Tone: —" would reasonably
    conclude the platform has a tone setting it failed to render, when the
    truth is that this colleague was authored without one.
    """
    identity = entity.identity if isinstance(entity.identity, dict) else {}
    personality = identity.get("personality")
    personality = personality if isinstance(personality, dict) else {}
    governance = entity.governance if isinstance(entity.governance, dict) else {}

    candidates: list[tuple[str, str | None, str]] = [
        ("Goal", _text(entity.goal), "entity.goal"),
        ("Brief", _text(entity.description), "entity.description"),
        ("Role", _text(identity.get("role")), "identity.role"),
        ("Instructions", _text(identity.get("system_prompt")), "identity.system_prompt"),
        ("Tone", _text(personality.get("tone")), "identity.personality.tone"),
    ]
    clauses = [
        {"label": label, "value": value, "source": source}
        for label, value, source in candidates
        if value is not None
    ]

    # Segregation of duties is a clause only when it is one. "none" is the
    # default for every entity that was never given a maker/checker role, and
    # printing it would turn a default into a term of engagement.
    sod = _text(governance.get("sod_class"))
    if sod is not None and sod != "none":
        clauses.append({
            "label": "Segregation of duties",
            "value": sod,
            "source": "governance.sod_class",
        })

    cost = governance.get("max_cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        clauses.append({
            "label": "Cost ceiling per run",
            "value": f"USD {float(cost):.2f}",
            "source": "governance.max_cost_usd",
        })

    return clauses


def competencies(
    entity: HierarchicalEntity, company_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """What this colleague can do, from her own tool list.

    ``note`` is the registry's own description and is **omitted** when the
    platform cannot resolve the name — with ``registered: false`` beside it, so
    a tool the charter grants but the platform does not have reads as the
    defect it is rather than as a tool with no description.

    Tenant tools shadow global ones, so the lookup is company-scoped exactly
    the way execution resolves it.
    """
    capabilities = entity.capabilities if isinstance(entity.capabilities, dict) else {}
    declared = capabilities.get("tools")
    declared = declared if isinstance(declared, list) else []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in declared:
        # ``{"tool_id": ...}`` and nothing else, because that is the only shape
        # ``step_executor`` resolves. Reading a looser one here would list a
        # competency the colleague could never actually call.
        tool_id = _text(item.get("tool_id")) if isinstance(item, dict) else None
        if tool_id is None or tool_id in seen:
            continue
        seen.add(tool_id)

        is_connector = tool_id.startswith(CONNECTOR_TOOL_PREFIX)
        tool = ToolRegistry.get_tool(tool_id, company_id)
        category = category_for_tool(tool_id)
        rule = CATEGORY_RULES.get(category) if category else None

        entry: dict[str, Any] = {
            "name": tool_id,
            "kind": "connector" if is_connector else "tool",
            "registered": tool is not None,
            "category": category,
            "checkpoint_key": rule.checkpoint_key if rule is not None else None,
        }
        if tool is not None:
            note = _text(getattr(tool, "description", None))
            if note is not None:
                entry["note"] = note
        if is_connector:
            # ``mcp__<server>__<verb>`` — the server segment is the connector.
            parts = tool_id.split("__")
            if len(parts) >= 3 and parts[1]:
                entry["connector_id"] = parts[1]
        out.append(entry)
    return out


def authority_view(
    entity: HierarchicalEntity,
    granted: list[dict[str, Any]],
    checkpoint_defs: dict[str, HITLCheckpointDef],
) -> list[dict[str, Any]]:
    """Every §9.3 category this colleague's tools can reach, as the gate reads it.

    The decision and its reason come from :func:`evaluate_policy` verbatim —
    this module owns no copy of the matrix. The gate is asked with **no
    amount**, because a dossier describes terms and not a particular act; for
    a category that carries a value band that makes the answer conditional, so
    ``conditional_on_amount`` says so and the band is printed beside it. A
    dossier that flatly said "autonomous" for refunds would be true only until
    the first large one.
    """
    gov = _governance_of(entity)

    tools_by_category: dict[str, list[str]] = {}
    for competency in granted:
        category = competency.get("category")
        if isinstance(category, str) and category in CATEGORY_RULES:
            tools_by_category.setdefault(category, []).append(
                str(competency["name"]))

    out: list[dict[str, Any]] = []
    for category in sorted(tools_by_category):
        rule = CATEGORY_RULES[category]
        decision = evaluate_policy(
            ActIntent(action_category=category), gov)
        entry: dict[str, Any] = {
            "category": category,
            "tools": tools_by_category[category],
            "checkpoint_key": decision.checkpoint_key or rule.checkpoint_key,
            "decision": decision.decision,
            "reason": decision.reason,
            "band": decision.band,
            "unit": rule.unit,
            "hard_block": rule.hard_block,
            "always_hitl": rule.always_hitl,
            # A banded category that the gate lets through unamounted is only
            # autonomous *up to* the band — the number decides, and the dossier
            # has no number to decide with.
            "conditional_on_amount": bool(
                rule.band_field is not None
                and decision.decision == PASS
            ),
        }
        cdef = checkpoint_defs.get(rule.checkpoint_key)
        if cdef is not None:
            # Only from the registry row. A checkpoint the platform has not
            # seeded gets no invented description or SLA.
            entry["checkpoint_description"] = cdef.description
            entry["sla_seconds"] = cdef.sla_seconds
            entry["on_timeout"] = cdef.on_timeout
            entry["platform_mandatory"] = cdef.platform_mandatory
        out.append(entry)
    return out


def reliability_block(
    entity: HierarchicalEntity,
    *,
    runs_total: int,
    runs_failed: int,
    p95_latency_ms: float | None,
) -> dict[str, Any]:
    """Readings with no target, and the bar that does exist named as itself.

    ``demotion_bar`` is the C4 threshold set — the point at which the sweep
    takes a level away. It is deliberately not called a target and carries no
    dial fill: nobody promised these numbers, and a bar you fall through is
    not a level you aim for.
    """
    governance = entity.governance if isinstance(entity.governance, dict) else {}
    floor = governance.get("timeout_ms")
    return {
        "window_days": WINDOW_DAYS,
        "runs_total": runs_total,
        "runs_failed": runs_failed,
        # No runs is no rate. Zero would read as "never fails".
        "failure_rate": (runs_failed / runs_total) if runs_total else None,
        "p95_latency_ms": p95_latency_ms,
        "demotion_bar": {
            "min_runs": DEFAULT_THRESHOLDS.min_runs,
            "failure_rate": DEFAULT_THRESHOLDS.failure_rate,
            "latency_multiple": DEFAULT_THRESHOLDS.latency_multiple,
            "latency_floor_ms": (
                float(floor)
                if isinstance(floor, (int, float)) and not isinstance(floor, bool)
                else None
            ),
        },
    }


def _autonomy_block(entity: HierarchicalEntity) -> dict[str, Any]:
    """The band, plus the demotion stamp when the sweep has written one.

    The stamp is the closest thing the platform has to standing, and it is
    only ever present because something happened — so an absent stamp means
    "never demoted", which is a fact, and not "no data".
    """
    governance = entity.governance if isinstance(entity.governance, dict) else {}
    block: dict[str, Any] = {"band": _governance_of(entity).autonomy_level.value}
    demoted_at = _text(governance.get("autonomy_demoted_at"))
    if demoted_at is not None:
        block["demoted_at"] = demoted_at
        reasons = governance.get("autonomy_demotion_reason")
        if isinstance(reasons, list):
            block["demotion_reasons"] = [str(r) for r in reasons]
    return block


# ── the read ─────────────────────────────────────────────────────────────────

async def _district_of(
    db: AsyncSession, company_id: uuid.UUID, entity: HierarchicalEntity,
) -> dict[str, Any] | None:
    """The nearest PROCESS ancestor, as the estate names districts.

    Every hop re-checks ``company_id``: the parent pointer is a column and a
    cross-tenant one would otherwise walk the dossier straight out of its
    tenant.
    """
    current: HierarchicalEntity | None = entity
    for _ in range(_MAX_ANCESTOR_HOPS):
        if current is None:
            return None
        if current.type == "PROCESS":
            meta = (
                current.metadata_extensions
                if isinstance(current.metadata_extensions, dict) else {}
            )
            code = str(meta.get("process_code") or current.name)
            return {
                "process_code": code,
                "name": current.display_name or current.name,
                "quarter": QUARTER_FOR_PROCESS.get(code, "custom"),
            }
        if current.parent_id is None:
            return None
        current = (
            await db.execute(
                select(HierarchicalEntity).where(
                    HierarchicalEntity.id == current.parent_id,
                    HierarchicalEntity.company_id == company_id,
                ))
        ).scalar_one_or_none()
    return None


async def dossier_view(
    db: AsyncSession,
    company_id: uuid.UUID,
    entity_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """One colleague's dossier, or ``None`` when this company has no such entity.

    ``None`` covers unknown and cross-tenant alike, so a probe learns nothing
    from the difference (the tray/district precedent).
    """
    at = now or datetime.utcnow()

    entity = (
        await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == entity_id,
                HierarchicalEntity.company_id == company_id,
            ))
    ).scalar_one_or_none()
    if entity is None:
        return None

    checkpoint_defs = {
        row.key: row
        for row in (await db.execute(select(HITLCheckpointDef))).scalars()
    }

    cutoff = at - timedelta(days=WINDOW_DAYS)
    totals = (
        await db.execute(
            select(
                func.count(ExecutionRun.id),
                func.sum(
                    case((ExecutionRun.status.in_(FAILED_STATUSES), 1), else_=0)),
                func.percentile_cont(0.95).within_group(
                    ExecutionRun.execution_time_ms.asc()),
            ).where(
                ExecutionRun.company_id == company_id,
                ExecutionRun.entity_id == entity.id,
                ExecutionRun.created_at >= cutoff,
            ))
    ).one()

    running_runs = int((
        await db.execute(
            select(func.count()).select_from(ExecutionRun).where(
                ExecutionRun.company_id == company_id,
                ExecutionRun.entity_id == entity.id,
                ExecutionRun.status.in_(ACTIVE_RUN_STATUSES),
            ))
    ).scalar_one() or 0)

    open_approvals = int((
        await db.execute(
            select(func.count())
            .select_from(HumanApproval)
            .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
            .where(
                ExecutionRun.company_id == company_id,
                ExecutionRun.entity_id == entity.id,
                HumanApproval.status == "PENDING",
            ))
    ).scalar_one() or 0)

    identity = entity.identity if isinstance(entity.identity, dict) else {}
    granted = competencies(entity, company_id)
    return {
        "as_of": at.isoformat(),
        "entity_id": str(entity.id),
        # ``name`` is the slug the portrait key is derived from; the display
        # name is what a person calls her. Both, because the surface needs both
        # and deriving one from the other is guesswork.
        "name": entity.name,
        "display_name": entity.display_name,
        "role": _text(identity.get("role")),
        "type": entity.type,
        "status": entity.status,
        "version": entity.version,
        "charter_updated_at": (
            entity.updated_at.isoformat() if entity.updated_at else None),
        "retired_at": entity.deleted_at.isoformat() if entity.deleted_at else None,
        "district": await _district_of(db, company_id, entity),
        "autonomy": _autonomy_block(entity),
        "charter": {
            "clauses": charter_clauses(entity),
            # Verbatim, because the surface offers "in words / governance
            # record" as one flip of the same charter — two renderings of one
            # thing, not two sources that can disagree.
            "governance": (
                entity.governance if isinstance(entity.governance, dict) else {}),
            "authority": authority_view(entity, granted, checkpoint_defs),
        },
        "competencies": granted,
        "reliability": reliability_block(
            entity,
            runs_total=int(totals[0] or 0),
            runs_failed=int(totals[1] or 0),
            p95_latency_ms=float(totals[2]) if totals[2] is not None else None,
        ),
        "running_runs": running_runs,
        "open_approvals": open_approvals,
        "absent": [dict(item) for item in ABSENT],
    }
