"""
ai.loop — the LOOP runtime (Increment 1 / LOOP+ENV).

A Loop is a **scheduler and aggregator, never a run** (technical doc §17): a
per-tenant heartbeat cron dispatches due schedules, sweeps parked signals,
rolls up child-Process cost into budget envelopes + the Loop's CORTEX tree,
and stamps liveness. A watchdog flags stalled heartbeats. Budget envelopes
(§20.4) with a protected reserve and wallet holds (§23.3) make spending safe
under concurrency. No changes to the shipped AgentLoop, executors, or the TB
billing engine.

Design: docs/product-road-map/increment-1/04_loop_env_runtime_budget.md.
"""
from src.ai.loop.models import BudgetEnvelope, LoopRuntime, WalletHold

__all__ = ["LoopRuntime", "BudgetEnvelope", "WalletHold"]
