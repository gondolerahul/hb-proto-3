"""
ai.services.cost_attribution — Phase 11 Track 8 cost-ledger plumbing.

Every Decimal that lands on ``ExecutionRun.total_cost_usd`` MUST also
land on a ``usage_logs`` row with a structured ``attribution`` tag.
The Track 9 dashboard breaks cost down by these tags so we can
finally answer:

  * "How much of this run's cost was the critic pipeline?"
  * "How much is meta_spec_critic costing us per company per week?"
  * "Did the reformat-retry path blow up after the latest tool change?"

The full whitelist (see :data:`VALID_ATTRIBUTIONS`) is intentionally
small and codified here. Any add() call with an unknown attribution
logs a warning and falls back to ``"tool"`` so the ledger stays
self-healing rather than dropping a charge.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class CostAttribution(str, Enum):
    PLANNER          = "planner"
    ACTOR_STEP       = "actor_step"
    CRITIC_PRE       = "critic_pre"
    CRITIC_POST      = "critic_post"
    CRITIC_ALIGN     = "critic_align"
    CRITIC_SUPER     = "critic_super"
    REFORMAT_RETRY   = "reformat_retry"
    META_REVIEW      = "meta_review"
    DREAMING         = "dreaming"
    TOOL             = "tool"
    CHILD_RUN        = "child_run"
    EMBEDDING        = "embedding"
    META_SPEC_CRITIC = "meta_spec_critic"
    TEST_DRIVER      = "test_driver"
    SANDBOX          = "sandbox"
    MCP              = "mcp"
    # RETR T4 — the Growth+ retrieval rerank. TENANT-initiated (the tenant
    # asked the question), so it is deliberately NOT in
    # PLATFORM_INITIATED_ATTRIBUTIONS below and draws from tenant budget.
    RERANK           = "rerank"
    # PRAGYA-RT (Inc 4) — a conversational turn with the account manager.
    # TENANT-initiated (the owner spoke), so deliberately NOT in
    # PLATFORM_INITIATED_ATTRIBUTIONS: it draws from the tenant's envelope.
    # Classifying it as platform work would let ordinary conversation exhaust
    # the cap that exists to protect tenants *from* platform work (B13).
    PRAGYA_TURN      = "pragya_turn"
    # CONN+SOR (Inc 4) — the SoR sweep polling a connector for external changes
    # on a schedule. PLATFORM-initiated: the tenant did not ask for this poll,
    # so it draws from the platform envelope (below), never the tenant wallet —
    # a perpetual mirror refresh must not silently burn tenant credits (B13).
    CONNECTOR_SYNC   = "connector_sync"
    # EVX (Inc 5) — the eval-harness runs that validate a model-fleet change
    # (§22.4 admission). PLATFORM-initiated: the platform, not the tenant, is
    # testing a candidate model, so the spend draws from the platform envelope,
    # never a tenant wallet (B13).
    MODEL_ADMISSION  = "model_admission"
    # TWIN (Inc 6) — a Glasshouse scenario run. TENANT-initiated (the tenant
    # asked the what-if), so deliberately NOT in
    # PLATFORM_INITIATED_ATTRIBUTIONS. This **overrides ratified spec §12.1**,
    # which put twin spend under the platform class: doing that would let
    # tenant experimentation exhaust the cap that exists to protect tenants
    # *from* platform work (B13) — the same rule RERANK and PRAGYA_TURN follow.
    # Charter decision 7. The product consequence (a Glasshouse that visibly
    # costs money is one people use less) is answered by TWIN §6's bounded
    # windows, cached baselines and estimate-before-spend, not by reclassifying.
    TWIN_RUN         = "twin_run"
    # SEAM (Inc 7) — generating a Vihara manifest for a novel intent shape
    # (a cached shape costs nothing — D4 §5 makes the cache the cost control).
    # TENANT-initiated (a user asked for a surface), so deliberately NOT in
    # PLATFORM_INITIATED_ATTRIBUTIONS — the RERANK/PRAGYA_TURN/TWIN_RUN rule:
    # ordinary browsing must not exhaust the cap that protects tenants *from*
    # platform work (B13).
    MANIFEST_GENERATION = "manifest_generation"
    # STEWARD (Inc 7) — Pragya's one advisory sentence on a delivered tray
    # (owner decision 2026-07-29: LLM-written). TENANT-initiated: the card
    # exists because the tenant's own agent raised it, and the sentence is
    # part of serving that tenant's approval flow — the RERANK/PRAGYA_TURN
    # side of B13, so deliberately NOT in PLATFORM_INITIATED_ATTRIBUTIONS.
    # Written once per tray at first delivery (the watcher's rule), so the
    # spend is bounded by the number of cards, not by reads.
    TRAY_RECOMMENDATION = "tray_recommendation"
    # LINE (Inc 7) — the Morning Story's daily audio (owner decision
    # 2026-07-29: pre-generated). TENANT-initiated despite the schedule: a
    # standing instruction the tenant can turn off, like a scheduled
    # campaign — a per-tenant daily benefit must not live on the cap that
    # protects tenants FROM platform work (B13). The wallet gates
    # synthesis; speech metering itself is still VG-08's open debt, so
    # this is registered and waiting, as MANIFEST_GENERATION was.
    MORNING_STORY = "morning_story"


VALID_ATTRIBUTIONS: set[str] = {a.value for a in CostAttribution}

# B13 — the platform-INITIATED cost classes: work the platform starts without a
# tenant asking (Meta-Agent iterations, self-healing/dreaming, sandbox + test
# builds). These draw from a separate capped envelope (loop/platform_budget.py)
# so platform work parks at its cap and can never starve tenant work.
PLATFORM_INITIATED_ATTRIBUTIONS: frozenset[str] = frozenset({
    CostAttribution.META_REVIEW.value,
    CostAttribution.META_SPEC_CRITIC.value,
    CostAttribution.DREAMING.value,
    CostAttribution.SANDBOX.value,
    CostAttribution.TEST_DRIVER.value,
    CostAttribution.CONNECTOR_SYNC.value,
    CostAttribution.MODEL_ADMISSION.value,
})


__all__ = [
    "CostAttribution", "CostLedger", "VALID_ATTRIBUTIONS",
    "PLATFORM_INITIATED_ATTRIBUTIONS",
]


class CostLedger:
    """Writes attributed usage rows.

    Construction is cheap; the ledger is stateless beyond the db
    session it was handed.
    """

    def __init__(self, db: Any):
        self.db = db

    async def add(
        self,
        *,
        run_id: Optional[UUID],
        company_id: UUID,
        amount: Decimal,
        attribution: str,
        sku_id: Optional[UUID] = None,
        raw_quantity: float = 1.0,
        latency_ms: int = 0,
        log_metadata: Optional[dict] = None,
        commit: bool = False,
    ) -> Any:
        """Insert a ``UsageLog`` row tagged with ``attribution``.

        Notes:
          * When ``attribution`` is unknown, we log a warning and fall
            back to ``"tool"`` so a typo never silently drops a charge.
          * ``sku_id`` is required by the existing schema; when the
            caller doesn't know it (e.g. supervisor LLM with no
            IntegrationRegistry row), the ledger short-circuits to a
            structured event without inserting — the run.total_cost_usd
            update is the caller's responsibility either way.
          * ``commit=False`` by default — the caller's transaction
            handles persistence; tests pass ``commit=True`` for clarity.
        """
        if attribution not in VALID_ATTRIBUTIONS:
            logger.warning(
                "CostLedger: unknown attribution %r; recording as 'tool'.",
                attribution,
            )
            attribution = CostAttribution.TOOL.value

        amount = Decimal(str(amount or 0))
        if amount <= 0:
            return None

        if sku_id is None:
            # No registry row to bind to — emit a telemetry event so the
            # dashboard still sees the cost, but skip the SQL insert
            # (UsageLog.sku_id is NOT NULL).
            logger.info(
                "CostLedger.add: skipping SQL insert (no sku_id) for "
                "attribution=%s amount=%s", attribution, amount,
            )
            try:
                from src.ai.core.events import event
                event(
                    "agent.cost.charged",
                    run_id=str(run_id) if run_id else None,
                    company_id=str(company_id) if company_id else None,
                    attribution=attribution, sku=None,
                    amount_usd=float(amount), latency_ms=int(latency_ms),
                    persisted=False,
                )
            except Exception:                                               # pragma: no cover
                pass
            return None

        from src.ai.orm.usage import UsageLog
        meta = dict(log_metadata or {})
        meta.setdefault("latency_ms", int(latency_ms))
        row = UsageLog(
            company_id=company_id,
            run_id=run_id,
            sku_id=sku_id,
            raw_quantity=Decimal(str(raw_quantity)),
            calculated_cost=amount,
            log_metadata=meta,
            attribution=attribution,
        )
        self.db.add(row)
        if commit:
            await self.db.commit()
            await self.db.refresh(row)
        try:
            from src.ai.core.events import event
            event(
                "agent.cost.charged",
                run_id=str(run_id) if run_id else None,
                company_id=str(company_id) if company_id else None,
                attribution=attribution,
                sku=str(sku_id),
                amount_usd=float(amount),
                latency_ms=int(latency_ms),
                persisted=True,
            )
        except Exception:                                                   # pragma: no cover
            pass
        return row
