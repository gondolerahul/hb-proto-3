"""
worker.py — Arq worker entrypoint.

This file is intentionally minimal. All execution logic lives in:
  - ai.core.execution_engine   (ExecutionEngine)
  - ai.core.arq_jobs           (job functions)
  - ai.core.prompt_utils        (parse_variables, build_sandwich_prompt, etc.)
  - ai.core.context_utils       (store_step_output, sanitize_context)
  - ai.core.exceptions          (UncertaintySignal, AgentError, etc.)
  - ai.step_executor            (StepExecutorService)

Only WorkerSettings and cron registration remain here because arq
requires them at module level for worker discovery.

Phase 10A restructuring: decomposed from 1,992 lines → ~80 lines.
"""
from arq.connections import RedisSettings
import logging
import warnings

# Suppress third-party DeprecationWarnings we can't fix (dependency-internal)
warnings.filterwarnings("ignore", message=".*Inheritance class AiohttpClientSession.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*", module="sqlalchemy")
warnings.filterwarnings("ignore", message=".*has been renamed to.*ddgs.*", category=RuntimeWarning)

logger = logging.getLogger(__name__)

# --- Arq job imports (used by WorkerSettings.functions) ---
from src.ai.core.arq_jobs import (
    run_execution_recursive,
    process_gateway_event,
    process_document,
    dreaming_worker,
    dreaming_cron_trigger,
    dreaming_outcome_trigger,
    graph_maintenance_worker,
    resume_execution,
    resume_parent_run,
    cortex_resume_scheduled,
    critic_calibration_job,
    skill_promotion_scan,
    meta_agent_prompt_evolution,
    kpi_rollup_refresh,
    cost_estimator_refresh,
)
from src.ai.campaign_worker import (
    execute_campaign_task,
    pause_campaign_task,
    stop_campaign_task,
)
from src.ai.signals.dispatcher import dispatch_signal
from src.ai.signals.email_poll import email_inbound_poll
from src.ai.signals.sweeper import signal_sweeper
from src.ai.tenant_schema.maintenance import (
    tenant_db_hibernation,
    tenant_db_nightly_backup,
)
from src.ai.loop.heartbeat import loop_heartbeat
from src.ai.loop.watchdog import loop_watchdog
from src.ai.memory.rechunk_cron import chunk_upgrade_sweep
from src.ai.trust.crons import dunning_sweep
from src.ai.evolution.crons import entity_canary_sweep
from src.ai.governance.crons import demotion_sweep
from src.ai.learning.crons import (
    drift_sweep,
    kpi_snapshot_sweep,
    learning_harvest_sweep,
    platform_pooling_sweep,
)
from src.ai.strategy.crons import review_due_sweep
from src.ai.library.crons import (
    credential_expiry_sweep,
    influence_rollup_sweep,
    staleness_sweep,
)
from src.ai.voice_loop.crons import voice_deferred_reap, voice_deferred_sweep
from src.ai.lead_queue_worker import poll_lead_queue_task

# Register Solo Pack agent tools (Inc 2) on worker boot — the agent loop runs here.
from src.ai.solo_pack.tools import register_solo_pack_tools
register_solo_pack_tools()
# Install the TRUST consent registry into the KAR outbound seam (Inc 2 / D6).
from src.ai.trust.consent_registry import install_consent_registry
install_consent_registry()
# Inc-6 STRAT: fills the record service's write-policy seam so Planning state
# transitions are enforced on every write path, agent and human alike.
from src.ai.strategy.governance import install_strategy_write_policy
install_strategy_write_policy()
# Install the CONN+SOR connector-backed write-back provider into the SOR seam (Inc 4).
from src.ai.connectors.writeback import install_connector_writeback
install_connector_writeback()

# Model imports needed by arq at module scope
from src.common.database import AsyncSessionLocal  # noqa: F401


# ---------------------------------------------------------------------------
# Arq WorkerSettings
# ---------------------------------------------------------------------------

# Intended dedicated queue for async child runs, so a fan-out PROCESS can't
# starve top-level runs (and vice-versa). NOT routed yet: enqueuing children
# here requires deploying a worker bound to this queue, otherwise children
# would never be consumed. Until that worker exists, child dispatch stays on
# the default queue and load is bounded by governance.max_concurrent_children
# (see ChildEntityExecutor). Wire this in the C4 chain alongside the deletion.
CHILD_RUN_QUEUE = "children"


class WorkerSettings:
    functions = [
        run_execution_recursive,
        process_gateway_event,
        process_document,
        execute_campaign_task,
        pause_campaign_task,
        stop_campaign_task,
        resume_execution,
        resume_parent_run,
        # Outcome-triggered Dreaming.
        dreaming_outcome_trigger,
        # Signal bus (Increment 1 / SIG).
        dispatch_signal,
    ]
    # Register CORTEX scheduled wake-up cron
    cron_jobs = [
        # Run every 5 minutes to check for scheduled tree resumptions
        # arq expects: cron(coroutine, minute=set, hour=set, ...)
    ]

    job_timeout = 7200  # 2-hour absolute ceiling; per-entity timeout via logic_gate config

    # Parse Redis URL from environment config
    @staticmethod
    def _parse_redis_url():
        from src.common.config import settings
        from urllib.parse import urlparse
        parsed = urlparse(settings.REDIS_URL or "redis://localhost:6379")
        return parsed.hostname or "localhost", parsed.port or 6379

    _host, _port = _parse_redis_url.__func__()
    redis_settings = RedisSettings(host=_host, port=_port)


try:
    from arq.cron import cron
    WorkerSettings.cron_jobs = [
        cron(cortex_resume_scheduled, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        # C: Auto-schedule dreaming every 6 hours
        cron(dreaming_cron_trigger, hour={0, 6, 12, 18}, minute={15}),
        # Weekly critic calibration (Sunday 03:15 UTC)
        cron(critic_calibration_job, weekday=6, hour=3, minute=15),
        # Weekly skill candidate scan (Sunday 04:30 UTC)
        cron(skill_promotion_scan, weekday=6, hour=4, minute=30),
        # Weekly Meta-Agent prompt-evolution candidates
        # (Monday 05:00 UTC; never auto-applies — HITL gate required).
        cron(meta_agent_prompt_evolution, weekday=0, hour=5, minute=0),
        # Hourly KPI rollup refresh (xx:07 to spread
        # load away from other top-of-hour crons).
        cron(kpi_rollup_refresh, minute={7}),
        # /9: Nightly cost-estimator baseline refresh from
        # telemetry (02:30 UTC — quiet hour, follows the daily aggregate).
        cron(cost_estimator_refresh, hour=2, minute=30),
        # Signal-bus sweeper: every minute — re-dispatch stale PENDING,
        # review PARKED, drive retry backoff (Inc 1 / SIG §18.2–.3).
        cron(signal_sweeper, minute=set(range(60))),
        # Inbound email poll → email.inbound signals (subscription-gated).
        cron(email_inbound_poll, minute={m for m in range(0, 60, 2)}),
        # Tenant-DB hibernation (container backend only; no-op on schema).
        cron(tenant_db_hibernation, minute={m for m in range(0, 60, 5)}),
        # Nightly per-tenant backup (03:40 UTC — quiet hour).
        cron(tenant_db_nightly_backup, hour=3, minute=40),
        # Loop heartbeat scan (every minute; per-Loop pacing is heartbeat_interval_s).
        cron(loop_heartbeat, minute=set(range(60))),
        # Loop watchdog: flag stalled heartbeats (every 2 minutes).
        cron(loop_watchdog, minute={m for m in range(0, 60, 2)}),
        # Dunning ladder sweep (TRUST C5) — daily at 01:10 UTC, after the
        # midnight daily-credit job so a tenant's ladder position reflects the
        # day it just entered.
        cron(dunning_sweep, hour=1, minute=10),
        # Lazy chunk upgrade (RETR T2) — a small batch hourly at :35. No
        # deadline; it shares the embedding rate limit with live ingestion,
        # which must win, and parks at B13's platform cap.
        cron(chunk_upgrade_sweep, minute={35}),
        # C4 autonomy demotion (Inc 3) — daily. The observation window is 7
        # days, so a trend cannot change between two minutes; running it on
        # the 60s sweeper would repeat per-agent aggregates 1,440× for the
        # same answer. Sits after the dunning sweep.
        # LEARN (Inc 6) — the KPI history this increment exists to measure
        # against. 01:25 sits after C5's dunning sweep (a reading should reflect
        # the billing state just entered) and before C4's demotion sweep (a
        # demotion decided at 01:40 belongs to tomorrow's series). Unmeasurable
        # KPIs are recorded as absences, never skipped.
        cron(kpi_snapshot_sweep, hour=1, minute=25),
        # LEARN T7 — weekly behaviour series + drift. Monday 01:05, deliberately
        # *before* the demotion sweep below, which reads the drift signals as one
        # of its triggers. LEARN measures; C4 alone decides what it costs.
        cron(drift_sweep, weekday=0, hour=1, minute=5),
        cron(demotion_sweep, hour=1, minute=40),
        # SEGA T5 — judge every open entity canary. Deliberately *after* the
        # demotion sweep: demotion is about authority and this is about
        # version, and running demotion first means a rolled-back entity is not
        # simultaneously demoted for the failures its rollback just removed.
        cron(entity_canary_sweep, hour=1, minute=50),
        # B10 — pool yesterday's routing decisions, k-anonymity floor applied in
        # the job. Yesterday because a day cannot be aggregated until it is over.
        cron(platform_pooling_sweep, hour=2, minute=10),
        # LEARN T6 — grade recent runs, distil, propose. Daily rather than at
        # run completion because CSAT arrives *after* a run ends, so a
        # completion hook would miss the best evidence the platform has.
        cron(learning_harvest_sweep, hour=2, minute=30),
        # Inc-4 T6 — drain the post-call queue Inc-3 left filling. Small batch,
        # no deadline: a call reflected on an hour late is worth what one
        # reflected on immediately is worth, and the provider rate limit
        # belongs to live conversation.
        cron(voice_deferred_sweep, minute={m for m in range(0, 60, 10)}),
        # ...and reap finished rows, or draining just converts an unbounded
        # queue into an unbounded archive.
        cron(voice_deferred_reap, hour=2, minute=50),
        # LIB T3 — roll the retrieval-usage log up, then reap what the rollup
        # covered. One job, and the order inside it is the guarantee: the
        # reaper's cutoff is clamped to the last rolled-up day, so a worker
        # that missed a fortnight keeps the raw rows rather than deleting a
        # fortnight of influence history nothing ever aggregated.
        # STRAT T6 — mandates whose review date has arrived. At 02:20, inside
        # the quiet hour and before LIB's sweeps; it emits and never writes.
        cron(review_due_sweep, hour=2, minute=20),
        cron(influence_rollup_sweep, hour=2, minute=40),
        # LIB T4 — re-derive every document's staleness *and its reason*. Runs
        # after the rollup because a document flagged stale today should have
        # today's influence already counted against it: "high influence, old
        # content" is the pair worth surfacing first.
        cron(staleness_sweep, hour=2, minute=50),
        # LIB T8 (VG-16) — warn before a connector's credentials expire, not
        # after. `status` already records that a binding broke; nothing
        # recorded that one was about to.
        cron(credential_expiry_sweep, hour=3, minute=10),
        # Lead queue poller: every minute — pick pending leads and place
        # outbound calls via Tata Tele (CRM lead.created pipeline).
        cron(poll_lead_queue_task, minute=set(range(60))),
    ]
except ImportError:
    pass  # arq.cron may not be available in all versions

