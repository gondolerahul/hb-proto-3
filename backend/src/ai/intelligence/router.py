"""intelligence/router.py — the model router (RTR).

The router the §3.3 target doc envisions, reached *through* the shipped
``LLMRouter.call_llm`` seam (which delegates when a company's task default is
``routing_mode='router'``). No agent call site changes.

* **v1** reproduced the configured task default (non-inferior).
* **v2** scores the company's *credentialed, catalog-eligible* models on
  capability-fit vs cost, biased by wallet headroom — downshifting to a cheaper
  tier before failing (§5). When a company has no catalog-bound candidate it
  falls back to v1's default binding, so router mode is always safe.

Candidates are the company's own active integrations **bound to an active
catalog row** — never a model the tenant lacks credentials for. The decision is
written on its own committed transaction (durable audit, the signal pattern).

Design: increment-5/02_router.md §3–§5.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from typing import Optional, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intelligence.complexity import score as complexity_score
from src.ai.intelligence.models import RoutingDecision
from src.ai.intelligence.scoring import (
    Candidate,
    capability_fit,
    cost_pressure,
    utility,
)
from src.ai.intelligence.types import ModelBinding, RoutingSignals

__all__ = ["IntelligenceRouter"]


class IntelligenceRouter:
    def __init__(self, db: AsyncSession, company_id: UUID) -> None:
        self.db = db
        self.company_id = company_id

    async def route(self, signals: RoutingSignals) -> ModelBinding:
        """Pick a model for a step, record the decision, return the binding."""
        signals = await self._enrich(signals)
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

    async def reroute(self, signals: RoutingSignals, exclude: set[str]) -> ModelBinding | None:
        """Pick the next-best eligible model, excluding already-tried ones — the
        provider-error fallback (T5). Returns None when no alternative remains
        (the caller then re-raises the original error). Records the decision with
        reason 'fallback' and fallback_used=True."""
        signals = await self._enrich(signals)
        candidates = [c for c in await self._candidates(signals) if c.model_name not in exclude]
        if not candidates:
            return None
        best = max(candidates, key=lambda c: utility(c, signals.complexity, signals))
        decision_id = await self._record(
            task_type=signals.task_type, model_registry_id=best.model_registry_id,
            reason="fallback", signals=signals, fallback_used=True)
        return ModelBinding(
            integration_id=best.integration_id, model_name=best.model_name,
            provider=best.provider, reason="fallback",
            model_registry_id=best.model_registry_id, decision_id=decision_id)

    async def _enrich(self, signals: RoutingSignals) -> RoutingSignals:
        """Fill in what the router sees itself: the step's heuristic complexity,
        the wallet's headroom, and the company's **effective allow-list** (D5).
        The enriched signals are scored *and* recorded (a legible audit trail)."""
        from src.ai.intelligence.allow_list import effective_allow

        headroom = await self._wallet_headroom()
        allow = signals.allow_list
        if allow is None:
            # Read live so a revoked opt-in bites on the very next call.
            allow = tuple(sorted(await effective_allow(self.db, self.company_id)))
        return replace(
            signals,
            wallet_headroom_usd=headroom if headroom is not None else signals.wallet_headroom_usd,
            complexity=complexity_score(signals),
            allow_list=allow,
        )

    async def _select(
        self, signals: RoutingSignals
    ) -> tuple[UUID, str, str, UUID | None, str]:
        """v2: score the company's eligible credentialed models; fall back to the
        configured default when there is no catalog-bound candidate.

        Returns (integration_id, model_name, provider, model_registry_id, reason).
        """
        candidates = await self._candidates(signals)
        if not candidates:
            return await self._default_binding(signals)  # v1 path — always safe

        # A pinned model wins if the tenant pinned one and it is a candidate.
        if signals.pinned_model:
            for c in candidates:
                if c.model_name == signals.pinned_model:
                    return (c.integration_id, c.model_name, c.provider, c.model_registry_id, "pinned")

        best = max(candidates, key=lambda c: utility(c, signals.complexity, signals))
        best_fit = max(
            candidates,
            key=lambda c: capability_fit(c.capability_profile, signals.complexity, signals.needs_tools),
        )
        # "downshift" when cost pressure moved the pick off the most-capable model.
        reason = "downshift" if (best is not best_fit and cost_pressure(signals) > 1.0) else "auto"
        return (best.integration_id, best.model_name, best.provider, best.model_registry_id, reason)

    async def _candidates(self, signals: RoutingSignals) -> list[Candidate]:
        """The company's active, catalog-bound integrations that are eligible for
        this step (active catalog row, modality, context, allow-list). Never a
        model the tenant lacks credentials for."""
        from src.ai.intelligence.models import ModelRegistry, ModelStatus
        from src.ai.intelligence.registry import RegistryService
        from src.config.models import IntegrationRegistry

        irs = (await self.db.execute(
            select(IntegrationRegistry).where(
                IntegrationRegistry.company_id == self.company_id,
                IntegrationRegistry.status == "active",
                IntegrationRegistry.model_registry_id.isnot(None),
            )
        )).scalars().all()
        if not irs:
            return []

        reg = RegistryService(self.db)
        now = datetime.utcnow()
        out: list[Candidate] = []
        for ir in irs:
            model = (await self.db.execute(
                select(ModelRegistry).where(ModelRegistry.id == ir.model_registry_id)
            )).scalar_one_or_none()
            if model is None or model.status != ModelStatus.ACTIVE:
                continue
            cap = model.capability_profile or {}
            if signals.modality not in (cap.get("modalities") or []):
                continue
            if int(cap.get("max_context", 0)) < signals.context_tokens:
                continue
            if signals.allow_list is not None and model.provider not in signals.allow_list:
                continue
            inp = await reg.resolve_price(model.id, "input_token", now)
            outp = await reg.resolve_price(model.id, "output_token", now)
            cost_proxy = (float(inp.unit_price) if inp else 0.0) + (float(outp.unit_price) if outp else 0.0)
            out.append(Candidate(
                integration_id=cast(UUID, ir.id),
                model_name=cast(Optional[str], ir.model_name) or model.model_name,
                provider=model.provider,
                model_registry_id=model.id,
                capability_profile=cap,
                cost_proxy=cost_proxy,
            ))
        return out

    async def _wallet_headroom(self) -> float | None:
        """Approximate available headroom across the company's budget envelopes
        (a *hint* for cost pressure — the authoritative wallet-hold admission is
        downstream, so this read is deliberately non-locking)."""
        from src.ai.loop.models import BudgetEnvelope

        rows = (await self.db.execute(
            select(BudgetEnvelope).where(BudgetEnvelope.company_id == self.company_id)
        )).scalars().all()
        if not rows:
            return None
        return sum(
            float(e.envelope_usd) - float(e.reserved_usd) - float(e.spent_usd) for e in rows
        )

    async def _default_binding(
        self, signals: RoutingSignals
    ) -> tuple[UUID, str, str, UUID | None, str]:
        """v1: reproduce the company's configured task default (non-inferior).
        The fallback when no catalog-bound candidate exists."""
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
