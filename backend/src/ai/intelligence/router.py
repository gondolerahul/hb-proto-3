"""intelligence/router.py — the model router (RTR).

The router the §3.3 target doc envisions, reached *through* the shipped
``LLMRouter.call_llm`` seam (which delegates when a company's task default is
``routing_mode='router'``). No agent call site changes.

**v1** reproduces the company's configured task default — non-inferior by
construction (a routing change is a §22.4 event) — and records a
``routing_decisions`` row so every routed call is auditable. **v2** (complexity
scoring + wallet-aware downshift) replaces the selection in ``_select`` without
touching the seam.

The decision is written on its **own** committed transaction (the signal-emit
pattern, HANDOFF §5) so the audit record is durable regardless of the run's
transaction, and its id is available to link the usage row.

Design: increment-5/02_router.md §3.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intelligence.models import RoutingDecision
from src.ai.intelligence.types import ModelBinding, RoutingSignals

__all__ = ["IntelligenceRouter"]


class IntelligenceRouter:
    def __init__(self, db: AsyncSession, company_id: UUID) -> None:
        self.db = db
        self.company_id = company_id

    async def route(self, signals: RoutingSignals) -> ModelBinding:
        """Pick a model for a step, record the decision, return the binding."""
        integration_id, model_name, provider, model_registry_id, reason = await self._select(signals)

        decision_id = await self._record(
            task_type=signals.task_type,
            model_registry_id=model_registry_id,
            reason=reason,
            signals=signals,
        )
        return ModelBinding(
            integration_id=integration_id,
            model_name=model_name,
            provider=provider,
            reason=reason,
            model_registry_id=model_registry_id,
            decision_id=decision_id,
        )

    async def _select(
        self, signals: RoutingSignals
    ) -> tuple[UUID, str, str, UUID | None, str]:
        """v1: reproduce the company's configured task default (non-inferior).

        Returns (integration_id, model_name, provider, model_registry_id, reason).
        v2 overrides this with eligible()+utility() scoring; the seam and the
        recording below do not change.
        """
        from src.config.models import IntegrationRegistry
        from src.config.service import ConfigService

        task_default = await ConfigService(self.db).get_task_default(
            self.company_id, signals.task_type)
        if task_default is None:
            raise RuntimeError(
                f"IntelligenceRouter: no task default for '{signals.task_type}' "
                f"(company {self.company_id}) — routing requires a configured default.")

        integration = (await self.db.execute(
            select(IntegrationRegistry).where(IntegrationRegistry.id == task_default.integration_id)
        )).scalar_one_or_none()
        if integration is None:
            raise RuntimeError(
                f"IntelligenceRouter: task default points to a missing integration "
                f"({task_default.integration_id}).")

        # config.IntegrationRegistry is legacy Column-style, so its reads are
        # Column-typed under mypy --strict; cast to the runtime types.
        return (
            cast(UUID, integration.id),
            cast(Optional[str], integration.model_name) or "",
            cast(str, integration.provider_name),
            cast(Optional[UUID], integration.model_registry_id),
            "rule",
        )

    async def _record(
        self, *, task_type: str, model_registry_id: UUID | None,
        reason: str, signals: RoutingSignals, fallback_used: bool = False,
    ) -> UUID:
        """Persist the decision on its own committed transaction (durable audit)."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            decision = RoutingDecision(
                run_id=None,                       # v1 leaves NULL; run correlates via usage_log
                step_id=None,
                company_id=self.company_id,
                task_type=task_type,
                model_registry_id=model_registry_id,
                reason=reason,
                signals=asdict(signals),
                fallback_used=fallback_used,
            )
            s.add(decision)
            await s.commit()
            await s.refresh(decision)
            return decision.id
